/* mask_state.js — in-memory mask model.
 *
 * masks: Map<id, { id, source, deleted, keyframes: [{frame,x,y,w,h,state,source,pass?}] }>
 * Boxes between keyframes are linearly interpolated. A `dead` keyframe is the
 * mask's last visible/renderable frame; the mask is hidden strictly after it.
 * Manual keyframes carry `pass` (MANUAL_n provenance): a newer pass's anchors
 * suppress older anchors they bracket — see effManual().
 * Serializes to/from dense JSONL (one line per frame).
 */
const MaskState = (() => {
  const masks = new Map();
  let frameCount = 0;
  let fps = 30;
  let dirty = false;
  let idCounter = 0;
  const listeners = [];
  let ctxGetter = null; // () => {id, pass} | null  (for autosave)
  // Cached per-frame mask counts (timeline density). Recomputed lazily and only
  // after a mutation — never on the 60fps draw loops that read it. null = stale.
  let countsCache = null;
  function invalidate() { countsCache = null; }

  // undo history is now managed externally by EditHistory for visual Undo/Redo

  function onChange(fn) { listeners.push(fn); }
  function emit() { dirty = true; invalidate(); listeners.forEach((f) => f()); }

  function reset(fc, framerate) {
    masks.clear();
    frameCount = fc || 0;
    fps = framerate || 30;
    idCounter = 0;
    dirty = false;
    if (window.EditHistory) EditHistory.reset();
    invalidate();
  }

  // ---- undo ----------------------------------------------------------------
  // Snapshot the whole model (keyframes + holes). Bounded to MAX_UNDO entries,
  // so memory is at most MAX_UNDO × (current model size). pushUndo() is called
  // at the start of every mutating op, capturing the state *before* the change.
  function snapshot() {
    const arr = [];
    for (const m of masks.values()) {
      arr.push({
        id: m.id, source: m.source, deleted: m.deleted,
        keyframes: m.keyframes.map((k) => ({ ...k })),
        holes: Array.from(m.holes),
      });
    }
    return { frameCount, fps, masks: arr };
  }
  function restoreSnap(s) {
    masks.clear();
    frameCount = s.frameCount; fps = s.fps;
    for (const sm of s.masks) {
      masks.set(sm.id, {
        id: sm.id, source: sm.source, deleted: sm.deleted,
        keyframes: sm.keyframes.map((k) => ({ ...k })),
        holes: new Set(sm.holes),
      });
    }
  }

  function emitDirect() {
    dirty = true;
    invalidate();
    listeners.forEach((f) => f());
  }

  // Backwards compatibility for Ctrl+Z
  function undo() {
    if (window.EditHistory) return EditHistory.undo();
    return false;
  }
  function canUndo() {
    if (window.EditHistory) return EditHistory.canUndo();
    return false;
  }

  // ---- keyframe helpers ----------------------------------------------------
  function sortKf(m) { m.keyframes.sort((a, b) => a.frame - b.frame); }

  // pass provenance: each MANUAL keyframe carries the pass (MANUAL_n) it was
  // created in. A later pass's anchors suppress older anchors strictly bracketed
  // by them (see effManual). `currentPass` is the pass currently being edited —
  // set by the app on pass switch; while editing TRACKED (pass 0) it is 1, since
  // the first manual edit promotes the video to MANUAL_1.
  let currentPass = 1;
  function setCurrentPass(p) { currentPass = Math.max(1, p | 0); }

  function setKeyframe(id, frame, box, state, source, passNum) {
    let m = masks.get(id);
    if (!m) {
      m = { id, source: source || "manual", deleted: false, keyframes: [], holes: new Set() };
      masks.set(id, m);
    }
    const isManualKf = (source || "manual") === "manual";
    // explicit passNum (from load) wins; else stamp the pass being edited.
    const pass = passNum != null ? (passNum | 0) : (isManualKf ? currentPass : undefined);
    const existing = m.keyframes.find((k) => k.frame === frame);
    const w = Math.abs(box.w);
    const h = Math.abs(box.h);
    const x = box.w < 0 ? box.x + box.w : box.x;
    const y = box.h < 0 ? box.y + box.h : box.y;
    const kf = { frame, x, y, w, h,
                 state: state || "active", source: source || "manual" };
    if (pass != null) kf.pass = pass;
    if (existing) Object.assign(existing, kf);
    else { m.keyframes.push(kf); sortKf(m); }
    if (source === "manual") m.source = "manual";
    m._manual = null; m._eff = null; // invalidate cached manual-keyframe views
    return m;
  }

  function newId() {
    // continue past any existing m_/t_ numeric suffixes
    for (const id of masks.keys()) {
      const n = parseInt(String(id).replace(/\D/g, ""), 10);
      if (!isNaN(n) && n > idCounter) idCounter = n;
    }
    return `m_${String(++idCounter).padStart(3, "0")}`;
  }

  // ---- queries -------------------------------------------------------------
  function lerp(a, b, t) { return a + (b - a) * t; }

  // Index of the last keyframe with .frame <= frame (-1 if none). Keyframes are
  // always kept sorted, so this is a binary search — O(log n) instead of an
  // O(n) scan per query, which matters for dense tracked masks on long videos.
  function bisectPrev(arr, frame) {
    let lo = 0, hi = arr.length - 1, res = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid].frame <= frame) { res = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    return res;
  }

  // Cached subset of manual keyframes for a mask (invalidated on mutation).
  function manualOf(m) {
    if (!m._manual) m._manual = m.keyframes.filter((k) => k.source === "manual");
    return m._manual;
  }

  // EFFECTIVE manual anchors: manual keyframes after pass-priority suppression.
  // A newer pass (higher MANUAL_n) overrides older anchors it brackets — an
  // anchor is dropped iff some anchor to its LEFT and some to its RIGHT both
  // belong to a strictly greater pass. Example: anchors 0(p1),3(p2),5(p1),
  // 7(p2),9(p1) -> 5 is bracketed by 3 & 7 (both p2) -> dropped -> 0-3-7-9.
  // No pass field (legacy/tracked-derived) counts as pass 0. Cached (._eff).
  function effManual(m) {
    if (m._eff) return m._eff;
    const man = manualOf(m);
    const n = man.length;
    if (n < 3) { m._eff = man.slice(); return m._eff; }
    const passOf = (k) => k.pass || 0;
    const leftMax = new Array(n);
    const rightMax = new Array(n);
    let pref = -Infinity;
    for (let i = 0; i < n; i++) { leftMax[i] = pref; const p = passOf(man[i]); if (p > pref) pref = p; }
    let suf = -Infinity;
    for (let i = n - 1; i >= 0; i--) { rightMax[i] = suf; const p = passOf(man[i]); if (p > suf) suf = p; }
    const eff = [];
    for (let i = 0; i < n; i++) {
      const p = passOf(man[i]);
      if (!(leftMax[i] > p && rightMax[i] > p)) eff.push(man[i]);
    }
    m._eff = eff;
    return eff;
  }

  // Frames of manual anchors suppressed by pass priority (for query filtering).
  function suppressedFrames(m) {
    const eff = new Set(effManual(m).map((k) => k.frame));
    const out = new Set();
    for (const k of manualOf(m)) if (!eff.has(k.frame)) out.add(k.frame);
    return out;
  }

  function boxAtFrame(m, frame) {
    const kfs = m.keyframes;
    if (m.deleted || kfs.length === 0 || frame < kfs[0].frame) return null;
    if (m.holes && m.holes.has(frame)) return null; // frame/range delete

    // Manual keyframes act as anchors: between two consecutive MANUAL keyframes
    // we interpolate using only those two, discarding the dense tracked boxes
    // that sit in the span. Outside the manual span we fall back to the raw
    // keyframes (tracked data stays as-is).
    const manual = effManual(m);
    if (manual.length) {
      const i = bisectPrev(manual, frame);
      const mp = i >= 0 ? manual[i] : null;
      const mn = i + 1 < manual.length ? manual[i + 1] : null;
      if (mp) {
        // a dead anchor ends the mask: the dead frame itself stays visible (it
        // is the last frame), everything strictly after it is hidden.
        if (mp.state === "dead") {
          return mp.frame === frame
            ? { id: m.id, x: mp.x, y: mp.y, w: mp.w, h: mp.h, state: "active", source: mp.source, pass: mp.pass }
            : null;
        }
        // a seg_end anchor CLOSES the manual segment: the marker frame shows the
        // manual box (persisted with state "seg_end"); frames AFTER it fall back
        // to the raw/tracked keyframes so tracking resumes — instead of manual-
        // interpolating across the gap to the next manual segment.
        if (mp.state === "seg_end") {
          if (mp.frame === frame) {
            return { id: m.id, x: mp.x, y: mp.y, w: mp.w, h: mp.h, state: "seg_end", source: mp.source, pass: mp.pass };
          }
          // else: fall through to raw keyframes below (tracked resumes)
        } else if (mn) {
          // inside a manual segment: interpolate between the two manual anchors
          if (mp.frame === frame) {
            return { id: m.id, x: mp.x, y: mp.y, w: mp.w, h: mp.h, state: "active", source: mp.source, pass: mp.pass };
          }
          const t = (frame - mp.frame) / (mn.frame - mp.frame);
          return {
            id: m.id,
            x: lerp(mp.x, mn.x, t), y: lerp(mp.y, mn.y, t),
            w: lerp(mp.w, mn.w, t), h: lerp(mp.h, mn.h, t),
            state: "active", source: "interpolated",
          };
        } else if (mp.frame === frame) {
          // last manual anchor, active: show it (frames after fall to raw)
          return { id: m.id, x: mp.x, y: mp.y, w: mp.w, h: mp.h, state: "active", source: mp.source, pass: mp.pass };
        }
        // mp active without a following anchor, or seg_end past its frame:
        // fall through to raw kfs
      }
      // frame before first manual anchor → fall through to raw kfs
    }

    const j = bisectPrev(kfs, frame);
    const prev = j >= 0 ? kfs[j] : null;
    const next = j + 1 < kfs.length ? kfs[j + 1] : null;
    if (!prev) return null;
    // dead keyframe ends the mask, but the dead frame itself is the last visible
    // (and renderable) frame; only frames strictly after it are hidden.
    if (prev.state === "dead") {
      return prev.frame === frame
        ? { id: m.id, x: prev.x, y: prev.y, w: prev.w, h: prev.h, state: "active", source: prev.source, pass: prev.pass }
        : null;
    }
    // seg_end in the raw chain: visible on its own frame only. A dense tracked
    // mask never reaches here past the marker (the next integer frame carries
    // its own tracked keyframe); a sparse manual mask has nothing after it.
    if (prev.state === "seg_end") {
      return prev.frame === frame
        ? { id: m.id, x: prev.x, y: prev.y, w: prev.w, h: prev.h, state: "seg_end", source: prev.source, pass: prev.pass }
        : null;
    }

    if (!next || prev.frame === frame) {
      return { id: m.id, x: prev.x, y: prev.y, w: prev.w, h: prev.h,
        state: "active", source: prev.frame === frame ? prev.source : "interpolated",
               pass: prev.frame === frame ? prev.pass : undefined };
    }
    const t = (frame - prev.frame) / (next.frame - prev.frame);
    return {
      id: m.id,
      x: lerp(prev.x, next.x, t), y: lerp(prev.y, next.y, t),
      w: lerp(prev.w, next.w, t), h: lerp(prev.h, next.h, t),
      state: "active", source: "interpolated",
    };
  }

  function getMasksAtFrame(frame) {
    const out = [];
    for (const m of masks.values()) {
      const b = boxAtFrame(m, frame);
      if (b) out.push(b);
    }
    return out;
  }

  // Per-frame mask counts for the timeline density bars. Read on every timeline
  // RAF tick, so it is memoised: the O(frames × masks) sweep only runs after a
  // mutation invalidates the cache, not 60×/s.
  function getPersonCountPerFrame() {
    const n = Math.max(1, frameCount);
    if (countsCache && countsCache.length === n) return countsCache;
    const counts = new Int16Array(n);
    for (let f = 0; f < frameCount; f++) counts[f] = getMasksAtFrame(f).length;
    countsCache = counts;
    return counts;
  }

  // frames carrying at least one manual keyframe (for timeline edit dots).
  // Anchors suppressed by a newer pass are not edit points anymore -> skipped.
  function getEditedFrames() {
    const s = new Set();
    for (const m of masks.values()) {
      const sup = suppressedFrames(m);
      for (const k of m.keyframes)
        if (k.source === "manual" && !sup.has(k.frame)) s.add(k.frame);
    }
    return s;
  }

  // sorted unique frames of the mask's MANUAL keyframes (for keyframe nav).
  // Only manual anchors are meaningful edit points; tracked masks are dense (a
  // keyframe per frame) so navigating those is useless. A mask with no manual
  // edits has no nav targets (returns []).
  function keyframeFrames(id) {
    const m = masks.get(id);
    if (!m) return [];
    const manual = effManual(m);
    return [...new Set(manual.map((k) => k.frame))].sort((a, b) => a - b);
  }

  // live manual keyframes per mask: { id: [{frame, key}] } where key encodes the
  // rounded box — used to diff against a saved pass for the edit-lane display.
  function manualKeyframes() {
    const out = {};
    for (const m of masks.values()) {
      const ks = effManual(m);
      if (!ks.length) continue;
      out[m.id] = ks.map((k) => ({
        frame: k.frame,
        key: `${Math.round(k.x)}|${Math.round(k.y)}|${Math.round(k.w)}|${Math.round(k.h)}`,
        seg: k.state === "seg_end",
      }));
    }
    return out;
  }

  // Frames carrying a seg_end (segment-close) manual keyframe — for the timeline
  // to render those dots filled vs hollow. `id` optional (one mask, else all).
  function segEndFrames(id) {
    const out = new Set();
    const src = id != null ? [masks.get(id)].filter(Boolean) : [...masks.values()];
    for (const m of src)
      for (const k of effManual(m))
        if (k.state === "seg_end") out.add(k.frame);
    return [...out];
  }

  // ---- editing ops ---------------------------------------------------------
  function createMask(frame, box) {
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    const id = newId();
    setKeyframe(id, frame, box, "active", "manual");
    if (window.EditHistory) EditHistory.log("Created", id, frame, `Mask started manually`, snapshot());
    emit();
    return id;
  }
  function updateBox(id, frame, box) {
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    setKeyframe(id, frame, box, "active", "manual");
    if (window.EditHistory) EditHistory.log("Moved", id, frame, `Position/size changed`, snapshot());
    emit();
  }
  // Bring a mask back at `frame` (dragging its ghost), clearing any hole there.
  // If `frame` lands AFTER a mask that ended on a dead keyframe, reactivate that
  // terminator and move the dead marker to `frame` (the dragged box becomes the
  // new end) so the mask extends old-end -> frame. Otherwise just place an
  // active manual keyframe (reviving before the start or in a middle gap).
  function reviveAt(id, frame, box) {
    const m = masks.get(id); if (!m || !m.keyframes.length) return;
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    m.holes.delete(frame);
    const last = m.keyframes[m.keyframes.length - 1];
    if (frame > last.frame && last.state === "dead") {
      last.state = "active";                       // old end -> normal keyframe
      for (let f = last.frame; f <= frame; f++) m.holes.delete(f);
      setKeyframe(id, frame, box, "dead", "manual"); // new terminator at the drag
    } else {
      setKeyframe(id, frame, box, "active", "manual");
    }
    if (window.EditHistory) EditHistory.log("Revived", id, frame, `Pause finished, mask became active again`, snapshot());
    emit();
  }
  function deleteMask(id) {
    const m = masks.get(id);
    if (m) {
      if (window.EditHistory) EditHistory.initPassState(snapshot());
      masks.delete(id);
      if (window.EditHistory) EditHistory.log("Deleted", id, "-", `Mask completely removed`, snapshot());
      emit();
    }
  }
  // Remove the keyframe at `frame` (default delete). For tracked masks (dense
  // keyframes) this drops that frame's box so it interpolates from neighbours;
  // for manual masks it removes the anchor. If no keyframe sits exactly on the
  // frame, fall back to hiding it (hole) so the action still does something.
  function deleteFrameAt(id, frame) {
    const m = masks.get(id); if (!m) return;
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    const before = m.keyframes.length;
    m.keyframes = m.keyframes.filter((k) => k.frame !== frame);
    if (m.keyframes.length === before) m.holes.add(frame);
    m._manual = null; m._eff = null;
    if (window.EditHistory) EditHistory.log("Keyframe Deleted", id, frame, `Anchor point removed`, snapshot());
    emit();
  }
  // Delete an inclusive frame range [a,b] from a mask, restructuring keyframes
  // so dots/navigation/render all stay consistent. Four cases by how the range
  // overlaps the mask's span [first,last]:
  //   1. covers the whole mask        -> remove the mask entirely
  //   2. cuts the tail (b >= last)    -> end the mask just before the cut
  //   3. cuts the head (a <= first)   -> mask now starts just after the cut
  //   4. cuts the middle              -> split: keyframes after the cut move to
  //      a NEW id, the leading part gets a dead terminator at a-1.
  function deleteRange(id, start, end) {
    const m = masks.get(id); if (!m) return;
    const kfs = m.keyframes;
    if (!kfs.length) return;
    const a = Math.max(0, Math.min(start, end));
    const b = Math.min((frameCount || 1) - 1, Math.max(start, end));
    const first = kfs[0].frame, last = kfs[kfs.length - 1].frame;
    if (window.EditHistory) EditHistory.initPassState(snapshot());

    // 1) range spans the whole mask -> drop it
    if (a <= first && b >= last) {
      masks.delete(id);
      if (window.EditHistory) EditHistory.log("Delete Segment", id, [a, b], `Mask removed (segment covered everything)`, snapshot());
      emit();
      return;
    }

    // box that should terminate the leading part (last visible frame before the
    // cut), captured before any mutation; fall back to the last leading kf box.
    function leadingEndBox() {
      let box = a > 0 ? boxAtFrame(m, a - 1) : null;
      if (!box) {
        const lead = kfs.filter((k) => k.frame < a);
        const lk = lead[lead.length - 1];
        if (lk) box = { x: lk.x, y: lk.y, w: lk.w, h: lk.h };
      }
      return box;
    }

    // 3) head cut -> trim the start; mask begins after the cut
    if (a <= first) {
      m.keyframes = kfs.filter((k) => k.frame > b);
      m.holes = new Set([...m.holes].filter((h) => h > b));
      m._manual = null; m._eff = null;
      if (window.EditHistory) EditHistory.log("Delete Segment", id, [a, b], `Start of the mask was cut`, snapshot());
      emit();
      return;
    }

    // 4) middle cut -> split keyframes after the cut into a new mask id. The
    // trailing part also gets a starting keyframe at b+1 (the interpolated box
    // where it resumes) so it is visible right after the cut, not only from its
    // first pre-existing keyframe.
    const isInfinite = (kfs[kfs.length - 1].state !== "dead");
    const extendsPastCut = b < last || (isInfinite && b < (frameCount || 1) - 1);

    if (extendsPastCut) {
      const moved = kfs.filter((k) => k.frame > b);
      const nid = newId();
      const newSrc = moved.some((k) => k.source === "manual") ? "manual"
        : (moved[0] && moved[0].source) || "tracked";
      const startBox = boxAtFrame(m, b + 1);
      const newKfs = moved.map((k) => ({ ...k }));
      if (startBox && !newKfs.some((k) => k.frame === b + 1)) {
        newKfs.push({ frame: b + 1, x: startBox.x, y: startBox.y,
                      w: startBox.w, h: startBox.h, state: "active", source: newSrc });
        newKfs.sort((p, q) => p.frame - q.frame);
      }
      // terminate the trailing mask at its own last keyframe (mirrors the dead
      // terminator placed on the leading part), so it does not hold past its end.
      if (newKfs.length) newKfs[newKfs.length - 1].state = "dead";
      masks.set(nid, {
        id: nid, source: newSrc, deleted: false,
        keyframes: newKfs,
        holes: new Set([...m.holes].filter((h) => h > b)),
      });
    }

    // 2 & 4) leading part: keep keyframes before the cut + a dead terminator
    const endBox = leadingEndBox();
    m.keyframes = kfs.filter((k) => k.frame < a);
    m.holes = new Set([...m.holes].filter((h) => h < a));
    if (endBox) setKeyframe(id, a - 1, endBox, "dead", "manual");
    m._manual = null; m._eff = null;
    if (window.EditHistory) EditHistory.log("Delete Segment", id, [a, b], extendsPastCut ? `Split in two` : `End cut`, snapshot());
    emit();
  }
  function killAt(id, frame) {
    const m = masks.get(id); if (!m) return;
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    const b = boxAtFrame(m, frame) || m.keyframes[m.keyframes.length - 1];
    // drop any later keyframes so the dead marker actually terminates the mask
    m.keyframes = m.keyframes.filter((k) => k.frame < frame);
    setKeyframe(id, frame, b, "dead", "manual");
    if (window.EditHistory) EditHistory.log("Ended", id, frame, `The mask does not exist from this frame onwards`, snapshot());
    emit();
  }
  // Close the manual segment at `frame`: place a seg_end anchor so manual
  // interpolation stops here and the underlying tracked keyframes resume for the
  // frames after it (until the next manual anchor / segment). Keeps later
  // keyframes intact (unlike killAt). Adjacent-close rule: if the previous
  // manual anchor is itself a seg_end with no manual anchor between, demote it
  // to a normal interior keyframe so the segment end just moves forward.
  function closeSegmentAt(id, frame) {
    const m = masks.get(id); if (!m) return;
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    const b = boxAtFrame(m, frame) || nearestBox(m, frame) || m.keyframes[m.keyframes.length - 1];
    if (!b) return;
    const prevManual = [...manualOf(m)].reverse().find((k) => k.frame < frame);
    if (prevManual && prevManual.state === "seg_end") prevManual.state = "active";
    // dense tracked keyframes stay, so tracking interpolation takes over the freed span.
    setKeyframe(id, frame, { x: b.x, y: b.y, w: b.w, h: b.h }, "seg_end", "manual");
    m._manual = null; m._eff = null;
    if (window.EditHistory) EditHistory.log("Segment closed", id, frame, `Manual segment ended; tracking resumes after this frame`, snapshot());
    emit();
  }
  // nearest active keyframe box to `frame` (for extending the mask there)
  function nearestBox(m, frame) {
    let best = null, bestD = Infinity;
    for (const k of m.keyframes) {
      if (k.state === "dead") continue;
      const d = Math.abs(k.frame - frame);
      if (d < bestD) { bestD = d; best = k; }
    }
    return best ? { x: best.x, y: best.y, w: best.w, h: best.h } : null;
  }
  // Extend the mask to `frame` where it currently isn't present.
  //  - If the mask was ENDED earlier (dead keyframe before `frame`): move that
  //    end forward — the old end becomes a normal keyframe and a new dead
  //    keyframe is placed at `frame` (the mask now spans oldEnd→frame and ends
  //    there, NOT at the end of the video).
  //  - Otherwise (a mid gap / hole): just re-show the mask at `frame`.
  function extendTo(id, frame, fallback) {
    const m = masks.get(id); if (!m) return;
    if (window.EditHistory) EditHistory.initPassState(snapshot());
    m.holes.delete(frame);

    // the dead keyframe that currently terminates the mask at/before `frame`
    let deadKf = null;
    for (const k of m.keyframes) {
      if (k.state === "dead" && k.frame <= frame && (!deadKf || k.frame > deadKf.frame)) deadKf = k;
    }

    if (deadKf) {
      const ref = { x: deadKf.x, y: deadKf.y, w: deadKf.w, h: deadKf.h };
      deadKf.state = "active";                 // old end → normal keyframe
      for (let f = deadKf.frame; f <= frame; f++) m.holes.delete(f);
      m.keyframes = m.keyframes.filter((k) => k.frame <= frame); // nothing past the new end
      setKeyframe(id, frame, ref, "dead", "manual"); // new terminating keyframe
    } else {
      const ref = nearestBox(m, frame) || fallback;
      if (!ref) return;
      setKeyframe(id, frame, ref, "active", "manual"); // fill the gap
    }
    if (window.EditHistory) EditHistory.log("Extended", id, frame, `Mask extended up to this frame`, snapshot());
    emit();
  }
  function isActiveAt(id, frame) {
    const m = masks.get(id); if (!m) return false;
    return boxAtFrame(m, frame) !== null;
  }
  // A mask is "manual" once it carries any manual edit (created by hand or a
  // tracked mask the user touched). Tracked, untouched masks are not manual.
  function isManual(id) { const m = masks.get(id); return !!m && m.source === "manual"; }

  // Nearest known box for a mask that is NOT present at `frame` — used to draw
  // a "ghost" of a selected mask outside its appearance span. null if the mask
  // has no usable keyframes.
  function ghostBox(id, frame) {
    const m = masks.get(id);
    if (!m || !m.keyframes.length) return null;
    // nearest keyframe (including the dead terminator, which carries the mask's
    // last visible box) so the ghost sits at the closest boundary of its span.
    let best = null, bestD = Infinity;
    for (const k of m.keyframes) {
      const d = Math.abs(k.frame - frame);
      if (d < bestD) { bestD = d; best = k; }
    }
    return best ? { id, x: best.x, y: best.y, w: best.w, h: best.h } : null;
  }

  // ---- (de)serialization ---------------------------------------------------
  function loadJSONL(text) {
    masks.clear();
    let maxFrame = 0;
    text.split("\n").forEach((line) => {
      line = line.trim();
      if (!line) return;
      let rec; try { rec = JSON.parse(line); } catch (_) { return; }
      const f = rec.frame | 0;
      if (f > maxFrame) maxFrame = f;
      (rec.masks || []).forEach((mk) => {
        setKeyframe(mk.id, f, mk, mk.state || "active", mk.source || "tracked", mk.pass);
      });
    });
    if (maxFrame + 1 > frameCount) frameCount = maxFrame + 1;

    // serialize() is dense (one entry per present frame) and never writes a
    // `dead` marker, so on reload a terminated mask would otherwise interpolate
    // across interior gaps and extrapolate its last box past the end. Rebuild
    // both from the present-frame pattern: interior gaps -> holes; a mask whose
    // last present frame is before the video end -> dead terminator there.
    for (const m of masks.values()) {
      if (!m.keyframes.length) continue;
      const present = new Set(m.keyframes.map((k) => k.frame));
      const lo = m.keyframes[0].frame;
      const hi = m.keyframes[m.keyframes.length - 1].frame;
      for (let f = lo + 1; f < hi; f++) if (!present.has(f)) m.holes.add(f);
      if (hi < frameCount - 1) m.keyframes[m.keyframes.length - 1].state = "dead";
      m._manual = null; m._eff = null;
    }

    dirty = false;
    if (window.EditHistory) {
      EditHistory.reset();
      EditHistory.initPassState(snapshot());
    }
    invalidate();
    listeners.forEach((f) => f());
  }

  function serialize() {
    const lines = [];
    for (let f = 0; f < frameCount; f++) {
      const ms = getMasksAtFrame(f).map((b) => {
        const o = {
          id: b.id,
          x: +b.x.toFixed(2), y: +b.y.toFixed(2),
          w: +b.w.toFixed(2), h: +b.h.toFixed(2),
          state: b.state, source: b.source,
        };
        if (b.source === "manual" && b.pass != null) o.pass = b.pass;
        return o;
      });
      lines.push(JSON.stringify({ frame: f, ts: +(f / fps).toFixed(3), masks: ms }));
    }
    return lines.join("\n") + "\n";
  }

  // ---- autosave (every 30s when dirty) ------------------------------------
  // Saves straight into the current pass JSONL — there is no separate temp file.
  function bindAutosave(getCtx) { ctxGetter = getCtx; }
  setInterval(async () => {
    if (!dirty || !ctxGetter) return;
    const ctx = ctxGetter();
    if (!ctx || ctx.pass == null) return;
    try { await API.saveMasks(ctx.id, ctx.pass, serialize()); dirty = false; }
    catch (_) {}
  }, 30000);

  return {
    reset, onChange, loadJSONL, serialize,
    getMasksAtFrame, getPersonCountPerFrame, getEditedFrames, keyframeFrames, manualKeyframes, segEndFrames,
    createMask, updateBox, reviveAt, deleteMask, deleteFrameAt, deleteRange, killAt, closeSegmentAt, extendTo, isActiveAt, isManual, ghostBox,
    undo, canUndo,
    snapshot, restoreSnap, emitDirect,
    bindAutosave, setCurrentPass,
    get frameCount() { return frameCount; },
    set frameCount(v) { frameCount = v; invalidate(); },
    get fps() { return fps; },
    get dirty() { return dirty; },
    get raw() { return masks; },
  };
})();
window.MaskState = MaskState;
