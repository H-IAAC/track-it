/* app.js — bootstrap: wires header, tabs, tracking, editing, render, WS. */
const App = (() => {
  function getStatePass(s) {
    if (s === "RAW") return null;
    if (s === "TRACKED") return 0;
    if (s.startsWith("MANUAL_")) return parseInt(s.split("_")[1], 10);
    return null;
  }
  function getStateBadge(s) {
    if (s === "RAW") return "raw";
    if (s === "TRACKED") return "tracked";
    if (s.startsWith("MANUAL_")) return "manual";
    return "";
  }
  function getStageLabel(s) {
    if (s === "RAW") return "Raw";
    if (s === "TRACKED") return "Tracking";
    if (s.startsWith("MANUAL_")) return `Manual ${s.split("_")[1]}`;
    return s;
  }

  const ctx = { id: null, meta: null, state: "RAW", pass: null };
  let cfg = null;
  let tracking = false;
  let activeTab = "files";
  let savedManual = {};
  let laneCache = [];
  let promoting = false; // guards the one-shot TRACKED -> MANUAL_1 auto-migration

  const $ = (id) => document.getElementById(id);

  // ---- init ----------------------------------------------------------------
  async function init() {
    Player.init();
    Timeline.init();
    Editor.init();
    if (window.EditHistory) EditHistory.init();
    MaskState.bindAutosave(() => (ctx.id && ctx.pass != null ? { id: ctx.id, pass: ctx.pass } : null));
    // on every model change: auto-migrate to MANUAL_1 on the first manual edit
    // of a freshly tracked video, then keep the current pass lane live.
    MaskState.onChange(() => { maybeAutoMigrateToM1(); recomputeLiveLane(); });
    Player.onFrame(onFrame);

    bindHeader();
    bindTabs();
    bindTrack();
    bindRefine();
    bindManual();
    bindTimeline();
    bindWS();

    await loadConfig();
    setTheme(localStorage.getItem("fms-theme") || "light");
    if ($("app-mode-toggle") && $("app-mode-toggle").checked) {
      syncSessions();
    } else {
      syncVideos();
    }
  }

  // ---- config --------------------------------------------------------------
  async function loadConfig() {
    try {
      cfg = await API.getConfig();
      const sel = $("model-select");
      sel.innerHTML = "";
      (cfg.models || []).forEach((m) => {
        const o = document.createElement("option");
        o.value = m.id;
        o.textContent = m.available ? m.label : `${m.label} (not installed)`;
        o.disabled = !m.available;
        if (m.id === cfg.default_model) o.selected = true;
        sel.appendChild(o);
      });
      const dev = $("device-indicator");
      const gpu = cfg.device === "GPU";
      dev.classList.toggle("gpu", gpu);
      dev.querySelector(".dtxt").textContent = cfg.device;
      $("base-dir").textContent = cfg.base_dir || "";
    } catch (e) { toast("Failed to load /api/config", true); }
  }

  // ---- header --------------------------------------------------------------
  function bindHeader() {
    $("btn-theme").addEventListener("click", () =>
      setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    // Ctrl/Cmd+Z → undo last mask edit
    window.addEventListener("keydown", (e) => {
      const tag = (document.activeElement && document.activeElement.tagName) || "";
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (MaskState.undo()) { Editor.clearSelection(); refreshMaskList(); toast("Undone"); }
        else toast("Nothing to undo", true);
      } else if ((e.ctrlKey || e.metaKey) && ((e.shiftKey && (e.key === "z" || e.key === "Z")) || e.key === "y" || e.key === "Y")) {
        e.preventDefault();
        if (window.EditHistory && EditHistory.redo()) { Editor.clearSelection(); refreshMaskList(); toast("Redone"); }
        else toast("Nothing to redo", true);
      }
    });
  }

  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    localStorage.setItem("fms-theme", t);
  }

  function setVideoTitle(meta) {
    const el = $("current-video");
    if (!meta) {
      el.classList.remove("loaded"); el.classList.add("is-empty"); el.title = "";
      el.querySelector(".vt-text").textContent = "No video loaded";
      el.querySelector(".vt-hint").textContent = "select in the Files tab";
      return;
    }
    el.classList.add("loaded"); el.classList.remove("is-empty");
    el.title = meta.filename || meta.id;
    el.querySelector(".vt-text").textContent = meta.filename || meta.id;
    el.querySelector(".vt-hint").textContent = meta.state || "RAW";
  }

  // ---- tabs ----------------------------------------------------------------
  function bindTabs() {
    document.querySelectorAll(".tab").forEach((tab) =>
      tab.addEventListener("click", () => switchTab(tab.dataset.tab)));
  }
  function switchTab(name) {
    activeTab = name;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.toggle("active", p.id === `pane-${name}`));
    Editor.setActive(name === "edit");
    if (name !== "edit" && window.EditHistory) {
      EditHistory.setOpen(false);
    }
    if (name === "files") {
      if ($("app-mode-toggle") && $("app-mode-toggle").checked) syncSessions();
      else syncVideos();
    }
    if (name === "edit") refreshMaskList();
    if (name === "render") loadOutputs();
    savePassQuiet();
  }

  // ---- video loading -------------------------------------------------------
  async function loadVideo(id) {
    try {
      const meta = await API.metadata(id);
      ctx.id = id; ctx.meta = meta; ctx.state = meta.state || "RAW";
      ctx.pass = getStatePass(ctx.state);

      Player.load(API.fileUrl(id), meta.fps || 30);
      MaskState.reset(meta.frame_count || 0, meta.fps || 30);

      setVideoTitle(meta);
      renderMeta(meta);

      WSClient.connect(id);
      await loadMasksForPass(ctx.pass);
      toast(`Loaded: ${meta.filename || id}`);
    } catch (e) {
      toast(`Error loading video: ${e.message}`, true);
    }
  }

  async function loadMasksForPass(pass) {
    // Stamp new manual edits with the pass being edited so a newer pass's anchors
    // take priority over older ones it brackets. Editing TRACKED (pass 0) becomes
    // MANUAL_1, so the floor is 1.
    MaskState.setCurrentPass(Math.max(1, pass || 0));
    if (pass == null) { MaskState.reset(ctx.meta.frame_count || 0, ctx.meta.fps || 30); refreshMaskList(); return; }
    try {
      const r = await API.getMasks(ctx.id, pass);
      MaskState.loadJSONL(r.jsonl);
    } catch (e) {
      // no jsonl for this pass yet — leave empty
      MaskState.reset(ctx.meta.frame_count || 0, ctx.meta.fps || 30);
    }
    refreshMaskList();
    rebuildPassLanes();
    renderPassSelector();
  }

  function renderPassSelector() {
    const container = $("pass-selector");
    if (!container || !ctx.meta) return;
    container.innerHTML = "";
    
    const passes = ctx.meta.passes || [];
    const maxPass = passes.length > 0 ? Math.max(...passes) : 0;
    const targetPass = Math.max(maxPass, ctx.pass || 0);
    
    for (let p = 0; p <= targetPass; p++) {
      const btn = document.createElement("button");
      btn.className = "btn btn--mini";
      if (p === ctx.pass) {
        btn.style.backgroundColor = "#d97706"; // amber-600
        btn.style.color = "#fff";
        btn.style.borderColor = "#b45309";
      }
      btn.textContent = p === 0 ? "Tracking" : `Pass ${p}`;
      btn.onclick = async () => {
        if (p === ctx.pass) return;
        savePassQuiet(); // silently saves current edits if any
        ctx.pass = p;
        ctx.state = p === 0 ? "TRACKED" : `MANUAL_${p}`;
        updateStageTag();
        await loadMasksForPass(p);
      };
      container.appendChild(btn);
    }
  }

  // ---- per-pass edit lanes (timeline lower section) ------------------------
  // Parse one pass JSONL into manual keyframes: { id: [{frame, key}] }.
  function parseManual(text) {
    const out = {};
    (text || "").split("\n").forEach((line) => {
      line = line.trim(); if (!line) return;
      let rec; try { rec = JSON.parse(line); } catch (_) { return; }
      const f = rec.frame | 0;
      (rec.masks || []).forEach((mk) => {
        if (mk.source !== "manual") return;
        (out[mk.id] = out[mk.id] || []).push({
          frame: f,
          key: `${Math.round(mk.x)}|${Math.round(mk.y)}|${Math.round(mk.w)}|${Math.round(mk.h)}`,
          seg: mk.state === "seg_end",
        });
      });
    });
    return out;
  }

  // Edits introduced in `cur` relative to `base`. Returns lane items:
  //   dots     — changed/new manual anchors {f, seg}; seg => seg_end (filled dot)
  //   segments — only the manual INTERPOLATION spans [a,b]: between consecutive
  //              anchors whose LEFT one is NOT a seg_end (after a seg_end the
  //              tracking resumes, so that span is not an interpolated trecho).
  function diffLane(cur, base) {
    const items = [];
    for (const id in cur) {
      const baseMap = {};
      (base[id] || []).forEach((e) => { baseMap[e.frame] = e.key; });
      const anchors = [...cur[id]].sort((a, b) => a.frame - b.frame);
      const dots = anchors
        .filter((e) => baseMap[e.frame] !== e.key)
        .map((e) => ({ f: e.frame, seg: !!e.seg }));
      const segments = [];
      for (let i = 0; i + 1 < anchors.length; i++) {
        if (!anchors[i].seg) segments.push([anchors[i].frame, anchors[i + 1].frame]);
      }
      if (dots.length || segments.length) {
        items.push({
          id, dots, segments,
          min: anchors[0].frame, max: anchors[anchors.length - 1].frame,
        });
      }
    }
    return items;
  }

  // Build the current pass lane from live edits diffed against the prior saved pass.
  function liveLaneFor(pass) {
    const cur = MaskState.manualKeyframes();
    return { label: `M${pass}`, items: diffLane(cur, savedManual[pass - 1] || {}) };
  }

  function recomputeLiveLane() {
    if (ctx.pass == null || ctx.pass < 1 || !laneCache.length) return;
    laneCache[ctx.pass - 1] = liveLaneFor(ctx.pass);
    Timeline.setPassEdits(laneCache);
  }

  // First manual edit of a freshly tracked video (state TRACKED, pass 0):
  // write the current masks straight into pass 1 and advance the backend state
  // TRACKED -> MANUAL_1. The pass-1 file already exists after the save, so the
  // backend advance won't overwrite it with a plain copy of pass 0. From here
  // ctx.pass is 1, so the live M1 lane (and keyframe dots) work normally.
  async function maybeAutoMigrateToM1() {
    if (promoting || ctx.state !== "TRACKED" || ctx.pass !== 0) return;
    // only on a real user edit (dirty), never on a load (loadJSONL keeps dirty
    // false) that merely happens to carry manual keyframes.
    if (!MaskState.dirty) return;
    if (!Object.keys(MaskState.manualKeyframes()).length) return;
    promoting = true;
    try {
      // The frontend may show the Tracking (pass 0) view while the backend has
      // already advanced to a MANUAL_n pass (e.g. the user clicked back to the
      // Tracking lane and edited again). A blind relative advance would then
      // jump M1->M2->M3 on each new edit. Check backend truth first: if a manual
      // pass already exists, adopt it and write the edit there instead of
      // advancing. Only when no manual pass exists do we create Manual 1.
      const meta = await API.metadata(ctx.id);
      const backendPass = getStatePass(meta.state);
      if (backendPass != null && backendPass >= 1) {
        ctx.state = meta.state; ctx.pass = backendPass; ctx.meta = meta;
        MaskState.setCurrentPass(ctx.pass);
        await API.saveMasks(ctx.id, ctx.pass, MaskState.serialize());
      } else {
        await API.saveMasks(ctx.id, 1, MaskState.serialize());
        const r = await API.advance(ctx.id);
        ctx.state = r.state; ctx.pass = getStatePass(r.state);
        MaskState.setCurrentPass(ctx.pass || 1);
        ctx.meta = await API.metadata(ctx.id);
      }
      updateStageTag();
      await rebuildPassLanes();
      toast(`Editing started — ${getStageLabel(ctx.state)}`);
    } catch (e) {
      toast("Failed to migrate to Manual 1: " + e.message, true);
    } finally {
      promoting = false;
    }
  }

  async function rebuildPassLanes() {
    if (!ctx.id) return;
    const passes = ctx.meta.passes || [];
    const maxPass = passes.length > 0 ? Math.max(...passes) : 0;
    const targetPass = Math.max(maxPass, ctx.pass || 0);

    for (let n = 1; n <= targetPass; n++) {
      try { savedManual[n] = parseManual((await API.getMasks(ctx.id, n)).jsonl); }
      catch (_) { savedManual[n] = {}; }
    }

    laneCache = [];
    for (let n = 1; n <= targetPass; n++) {
      if (n === ctx.pass) {
        laneCache.push(liveLaneFor(n));
      } else {
        laneCache.push({ label: `M${n}`, items: diffLane(savedManual[n] || {}, savedManual[n - 1] || {}) });
      }
    }
    Timeline.setPassEdits(laneCache);
  }

  function renderMeta(m) {
    const dl = $("track-meta");
    const rows = [
      ["File", m.filename || m.id],
      ["Resolution", `${m.width}×${m.height}`],
      ["FPS", (m.fps || 0).toFixed(2)],
      ["Duration", `${(m.duration || 0).toFixed(1)}s`],
      ["Frames", m.frame_count || 0],
      ["Rotation", `${m.rotation || 0}°`],
      ["State", m.state || "RAW"],
      ["Passes", (m.passes || []).join(", ") || "—"],
    ];
    dl.innerHTML = rows.map(([k, v]) =>
      `<dt>${k}</dt><dd>${v}</dd>`).join("");
    updateStageTag();
  }

  function updateStageTag() {
    const el = $("tl-stage");
    if (!el) return;
    el.dataset.stage = getStateBadge(ctx.state);
    el.textContent = getStageLabel(ctx.state);
    
    const passLabel = $("current-pass-label");
    if (passLabel) passLabel.textContent = getStageLabel(ctx.state).toUpperCase();
    
    renderPassSelector();
  }

  // ---- tracking ------------------------------------------------------------
  function bindTrack() {
    $("btn-track-full").addEventListener("click", () => startTrack(false)); // "Track region"
    $("btn-track-region").addEventListener("click", () => startTrack(true)); // "Full"
    $("btn-track-cancel").addEventListener("click", cancelTrack);
  }

  async function startTrack(full) {
    if (!ctx.id) return toast("Load a video first", true);
    const fps = ctx.meta.fps || 30;
    const payload = {
      start_frame: full ? 0 : Math.round((parseFloat($("start-sec").value) || 0) * fps),
      end_frame: full ? 0 : Math.round((parseFloat($("end-sec").value) || 0) * fps),
      detect_every: parseInt($("detect-every").value, 10) || 1,
      model: $("model-select").value,
      head_pad: parseFloat($("head-pad").value) || 20,
      backward: true,
      backfill_grow: parseFloat($("backfill-grow").value) || 0,
    };
    try {
      await API.track(ctx.id, payload);
      tracking = true;
      $("btn-track-full").disabled = $("btn-track-region").disabled = true;
      $("btn-track-cancel").disabled = false;
      $("track-status").textContent = "Starting tracking…";
    } catch (e) {
      toast(e.status === 409 ? "Tracking already running" : `Error: ${e.message}`, true);
    }
  }

  async function cancelTrack() {
    try { await API.cancelTrack(ctx.id); $("track-status").textContent = "Canceling…"; }
    catch (e) { toast(e.message, true); }
  }

  function resetTrackUI() {
    tracking = false;
    $("btn-track-full").disabled = $("btn-track-region").disabled = false;
    $("btn-track-cancel").disabled = true;
  }

  // ---- refine / editing ----------------------------------------------------
  function bindRefine() {
    // Delete buttons act directly on the selected mask; they stay disabled
    // until a mask is selected (state synced in refreshMaskList).
    document.querySelectorAll(".del-action").forEach((b) =>
      b.addEventListener("click", () => {
        if (b.disabled) return;
        Editor.deleteSelected(b.dataset.del);
      }));
    $("overlay-type").addEventListener("change", (e) => {
      Player.setOverlayType(e.target.value);
      e.target.blur();
    });
    $("fill-color").addEventListener("input", (e) => Player.setFillColor(e.target.value));
    $("btn-kill").addEventListener("click", () => Editor.closeSegment());
    $("btn-outlines").addEventListener("click", (e) => {
      const btn = e.currentTarget;
      const show = btn.getAttribute("aria-pressed") === "false"; // toggling -> show
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.title = show ? "Hide IDs and outlines to see masks"
        : "Show IDs and outlines";
      Player.setOutlinesVisible(show);
    });
    $("btn-kf-prev").addEventListener("click", () => jumpKeyframe(-1));
    $("btn-kf-next").addEventListener("click", () => jumpKeyframe(1));
    $("btn-save-pass").addEventListener("click", () => savePass());
    $("btn-advance").addEventListener("click", advance);
  }

  // Jump to the previous/next keyframe of the selected mask.
  function jumpKeyframe(dir) {
    const id = Editor.getSelected();
    if (!id) return toast("Select a mask first", true);
    const kfs = MaskState.keyframeFrames(id);
    if (!kfs.length) return toast("No manual keyframes (edit the mask first)", true);
    const f = Player.currentFrame();
    const target = dir < 0
      ? [...kfs].reverse().find((k) => k < f)
      : kfs.find((k) => k > f);
    if (target == null) return toast(dir < 0 ? "First keyframe" : "Last keyframe", true);
    Player.seekFrame(target);
  }

  // Save current masks into a pass JSONL. `pass` defaults to the active pass;
  // callers (advance) may force a different one. Returns true on success.
  async function savePass(pass = ctx.pass) {
    if (!ctx.id || pass == null) { toast("Nothing to save (track first)", true); return false; }
    try {
      await API.saveMasks(ctx.id, pass, MaskState.serialize());
      $("pass-status").textContent = `Pass ${pass} saved.`;
      toast(`Pass ${pass} saved`);
      rebuildPassLanes(); // refresh saved-pass edit lanes
      return true;
    } catch (e) { toast(e.message, true); return false; }
  }

  async function advance() {
    if (!ctx.id) return;
    // Persist edits BEFORE moving on, and abort if the save fails so the user
    // never loses work. In RAW there is no pass file yet, so any manually drawn
    // masks belong to pass 0 (TRACKED) — the state we are about to enter.
    const savePassN = ctx.pass != null ? ctx.pass : 0;
    if (ctx.pass != null || MaskState.raw.size > 0) {
      const ok = await savePass(savePassN);
      if (!ok) return toast("Advance canceled: failed to save pass", true);
    }
    try {
      const r = await API.advance(ctx.id);
      ctx.state = r.state; ctx.pass = getStatePass(r.state);
      $("pass-status").textContent = `Advanced to ${r.state} (pass ${ctx.pass}).`;
      const meta = await API.metadata(ctx.id); ctx.meta = meta; renderMeta(meta);
      await loadMasksForPass(ctx.pass);
      toast(`State: ${r.state}`);
    } catch (e) { toast(e.message, true); }
  }

  // Toggle the del-hint line (Trecho instructions) on the editing pane.
  function showDelHint(on) { const h = $("del-hint"); if (h) h.hidden = !on; }

  // Enable the delete buttons only while a mask is selected. When nothing is
  // selected, also drop any armed trecho range-selection so the timeline scrubs
  // normally again.
  function syncDeleteButtons() {
    const sel = Editor.getSelected();
    // keyframe-delete only makes sense ON an actual manual keyframe: not on
    // tracked masks (no manual anchors) and not on interpolated frames (no
    // keyframe sits there to remove).
    const onKeyframe = sel && MaskState.keyframeFrames(sel).includes(Player.currentFrame());
    document.querySelectorAll(".del-action").forEach((b) => {
      b.disabled = !sel || (b.dataset.del === "frame" && !onKeyframe);
    });
    Timeline.setSelectedMask(sel || null);
    if (!sel) { Timeline.setRangeSelect(false); showDelHint(false); }
  }

  function refreshMaskList() {
    syncDeleteButtons();
    const list = $("mask-list");
    if (!list) return;
    const frame = Player.currentFrame();
    const ms = MaskState.getMasksAtFrame(frame);
    const sel = Editor.getSelected();
    // selected mask outside its appearance span -> still list it as a ghost row.
    const ghost = sel && !ms.some((b) => b.id === sel);
    $("mask-count").textContent = ms.length;
    if (!ms.length && !ghost) { list.innerHTML = `<div class="pane-empty">No masks on this frame.</div>`; updateKfPos(); return; }
    const rows = ms.map((b) =>
      `<div class="mrow ${b.id === sel ? "sel" : ""}" data-id="${b.id}">
         <span class="swatch-dot ${b.source}"></span>
         <span class="mid">${b.id}</span>
         <span class="msrc">${b.source}</span>
       </div>`);
    if (ghost) rows.push(
      `<div class="mrow sel ghost" data-id="${sel}">
         <span class="swatch-dot ghost"></span>
         <span class="mid">${sel}</span>
         <span class="msrc">✕ outside segment</span>
       </div>`);
    list.innerHTML = rows.join("");
    list.querySelectorAll(".mrow").forEach((row) =>
      row.addEventListener("click", () => {
        // click the already-selected row again to deselect (toggle)
        if (Editor.getSelected() === row.dataset.id) Editor.clearSelection();
        else Editor.select(row.dataset.id);
        refreshMaskList();
      }));
    updateKfPos();
  }

  // Show "kf N/total" for the selected mask in the keyframe-nav strip.
  function updateKfPos() {
    const el = $("kf-pos"); if (!el) return;
    const id = Editor.getSelected();
    const kfs = id ? MaskState.keyframeFrames(id) : [];
    if (!kfs.length) { el.textContent = "—"; return; }
    const f = Player.currentFrame();
    const idx = kfs.indexOf(f);
    el.textContent = idx >= 0 ? `kf ${idx + 1}/${kfs.length}` : `${kfs.length} kf`;
  }

  // ---- manual / render -----------------------------------------------------
  function bindManual() {
    $("btn-render").addEventListener("click", startRender);
  }
  async function startRender() {
    if (!ctx.id) return toast("Load a video first", true);
    const [r, g, b] = hexToRgb($("render-color").value);
    try {
      const res = await API.render(ctx.id, { mask_type: $("render-type").value, fill_color: [r, g, b] });
      $("render-status").textContent = "Rendering…";
      $("render-output").textContent = "Started...";
    } catch (e) { toast(e.message, true); }
  }

  async function loadOutputs() {
    if (!ctx.id) return;
    try {
      const outputs = await API.getOutputs(ctx.id);
      const container = $("render-output");
      const btnDownload = $("btn-download");
      
      if (!outputs || outputs.length === 0) {
        container.innerHTML = "No render yet.";
        btnDownload.style.display = "none";
        return;
      }
      
      let html = `<div style="display: flex; flex-direction: column; gap: 8px;">`;
      
      // Make the download button point to the latest pass
      const latestPass = Math.max(...outputs);
      btnDownload.style.display = "block";
      btnDownload.onclick = () => {
        const a = document.createElement("a");
        a.href = API.outputUrl(ctx.id, latestPass);
        a.download = `${ctx.id.replace(/\//g, '_')}_masked_${latestPass}.mp4`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      };
      [...outputs].reverse().forEach(pass_n => {
        const url = API.outputUrl(ctx.id, pass_n);
        
        let changesText = "";
        if (pass_n === 0) {
          changesText = "Base pass (Tracking)";
        } else {
          const items = diffLane(savedManual[pass_n] || {}, savedManual[pass_n - 1] || {});
          const totalFrames = items.reduce((acc, it) => acc + it.dots.length, 0);
          changesText = totalFrames === 1 ? "1 new change" : `${totalFrames} new changes`;
        }

        html += `<div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #27272a;">
                   <div>
                     <div style="font-weight: 600; color: #d4d4d8;">Render Pass ${pass_n}</div>
                     <div style="font-size: 11px; color: #a1a1aa; margin-top: 2px;">${changesText}</div>
                   </div>
                   <button type="button" class="btn btn--mini btn-load-out" data-url="${url}" style="padding: 2px 8px; flex: 0 0 auto;">Play</button>
                 </div>`;
      });
      html += `</div>`;
      html += `<p class="section-note" style="margin-top: 12px; font-size: 11px;">To return to the original video (RAW) with boxes, reload it in the <b>1. Files</b> tab.</p>`;
      container.innerHTML = html;

      container.querySelectorAll(".btn-load-out").forEach(btn => {
        btn.addEventListener("click", (e) => {
          Player.load(e.target.dataset.url, ctx.meta.fps || 30);
          toast("Rendered video loaded in main player!");
        });
      });
    } catch (e) {
      $("render-output").innerHTML = "Error loading outputs.";
    }
  }
  function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }

  // ---- timeline / transport ------------------------------------------------
  function bindTimeline() {
    $("tl-start").addEventListener("click", () => Player.seekFrame(0));
    $("tl-back").addEventListener("click", () => Player.step(-1));
    $("btn-play").addEventListener("click", () => Player.togglePlay());
    $("tl-fwd").addEventListener("click", () => Player.step(1));
    $("tl-end").addEventListener("click", () => Player.seekFrame((MaskState.frameCount || 1) - 1));
    $("speed-select").addEventListener("change", (e) => { Player.setSpeed(parseFloat(e.target.value)); e.target.blur(); });
    $("btn-tl-expand").addEventListener("click", () => Timeline.toggleExpand());
  }

  function onFrame(frame) {
    const fps = Player.fps;
    const total = MaskState.frameCount || 0;
    $("tl-clock").querySelector(".cur").textContent = fmtClock(frame / fps);
    $("tl-clock").querySelector(".dur").textContent = fmtClock(total / fps);
    $("tl-frames").textContent = `f.${frame} / f.${Math.max(0, total - 1)}`;
    if (activeTab === "edit") refreshMaskList();
  }
  function fmtClock(s) {
    const m = Math.floor(s / 60);
    const sec = (s % 60);
    return `${m}:${sec.toFixed(1).padStart(4, "0")}`;
  }

  // ---- files ---------------------------------------------------------------
  function bindFiles() { 
    $("btn-sync").addEventListener("click", syncVideos); 
    $("btn-sync-sessions").addEventListener("click", syncSessions);
    
    $("app-mode-toggle").addEventListener("change", (e) => {
      const isFlow = e.target.checked;
      $("standalone-panel").style.display = isFlow ? "none" : "block";
      $("dataset-flow-panel").style.display = isFlow ? "block" : "none";
      if (isFlow) {
        $("mode-label-standalone").style.color = "var(--muted)";
        $("mode-label-flow").style.color = "var(--accent)";
        syncSessions();
      } else {
        $("mode-label-standalone").style.color = "var(--accent)";
        $("mode-label-flow").style.color = "var(--muted)";
        syncVideos();
      }
    });
    
    $("btn-upload-video").addEventListener("click", () => {
      $("video-upload-input").click();
    });

    $("video-upload-input").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      
      $("btn-upload-video").disabled = true;
      $("upload-progress-container").style.display = "block";
      $("upload-bar").style.width = "50%"; // Fake progress for now
      $("upload-status").textContent = "Uploading...";
      
      try {
        await API.uploadVideo(file);
        $("upload-bar").style.width = "100%";
        $("upload-status").textContent = "Upload complete!";
        toast("Video uploaded successfully.");
        await syncVideos();
      } catch (err) {
        $("upload-status").textContent = "Upload failed: " + err.message;
        toast("Upload failed", true);
      } finally {
        $("btn-upload-video").disabled = false;
        setTimeout(() => {
          $("upload-progress-container").style.display = "none";
          $("upload-bar").style.width = "0%";
          if ($("upload-status").textContent.includes("complete")) {
            $("upload-status").textContent = "";
          }
        }, 2000);
        e.target.value = "";
      }
    });
  }
  async function syncVideos() {
    const list = $("video-list");
    try {
      const vids = await API.listVideos();
      if (!vids.length) { list.innerHTML = `<div class="pane-empty">No videos in videos/raw/.</div>`; return; }

      // group by folder; "" (root) first, then subfolders alphabetically
      const groups = {};
      vids.forEach((v) => { const f = v.folder || ""; (groups[f] = groups[f] || []).push(v); });
      const folders = Object.keys(groups).sort((a, b) =>
        a === "" ? -1 : b === "" ? 1 : a.localeCompare(b));

      const vitem = (v) =>
        `<div class="vitem ${v.id === ctx.id ? "active" : ""}" data-id="${v.id}">
           <div style="flex:1;min-width:0">
             <div class="vitem-name">${v.filename}</div>
             <div class="vitem-sub">${(v.passes || []).length} pass(es)</div>
           </div>
           <span class="badge ${getStateBadge(v.state)}">${v.state}</span>
         </div>`;

      list.innerHTML = folders.map((f) => {
        const label = f === "" ? "root" : f;
        return `<div class="vgroup" data-folder="${f}">
                  <button class="vgroup-head" type="button">
                    <span class="vgroup-caret">▾</span>
                    <span class="vgroup-path">${label}</span>
                    <span class="vgroup-count">${groups[f].length}</span>
                  </button>
                  <div class="vgroup-items">${groups[f].map(vitem).join("")}</div>
                </div>`;
      }).join("");

      list.querySelectorAll(".vgroup-head").forEach((head) =>
        head.addEventListener("click", () => head.parentElement.classList.toggle("collapsed")));
      list.querySelectorAll(".vitem").forEach((it) =>
        it.addEventListener("click", () => loadVideo(it.dataset.id)));
    } catch (e) { toast(e.message, true); }
  }

  async function syncSessions() {
    const list = $("session-list");
    try {
      const vids = await API.listSessions();
      if (!vids.length) { list.innerHTML = `<div class="pane-empty">No HIAAC Sessions found.</div>`; return; }

      const vitem = (v) =>
        `<div class="vitem ${v.id === ctx.id ? "active" : ""}" data-id="${v.id}">
           <div style="flex:1;min-width:0">
             <div class="vitem-name" style="font-weight: 600;">${v.filename}</div>
             <div class="vitem-sub" style="color: var(--accent);">${(v.passes || []).length} pass(es)</div>
           </div>
           <span class="badge ${getStateBadge(v.state)}">${v.state}</span>
         </div>`;

      list.innerHTML = vids.map(vitem).join("");

      list.querySelectorAll(".vitem").forEach((it) =>
        it.addEventListener("click", () => loadVideo(it.dataset.id)));
    } catch (e) { toast(e.message, true); }
  }

  // ---- WS ------------------------------------------------------------------
  function bindWS() {
    WSClient.on("tracking_progress", (m) => {
      const pct = m.total ? Math.min(100, (m.frame / m.total) * 100) : 0;
      $("track-bar").style.width = pct + "%";
      $("track-status").textContent = `Frame ${m.frame}/${m.total || "?"} · ${m.detections} detections`;
    });
    WSClient.on("tracking_done", async (m) => {
      resetTrackUI();
      $("track-bar").style.width = "100%";
      $("track-status").textContent = "Tracking finished.";
      ctx.state = "TRACKED"; ctx.pass = 0;
      const meta = await API.metadata(ctx.id); ctx.meta = meta; renderMeta(meta);
      await loadMasksForPass(0); // masks appear automatically
      toast("Tracking finished — masks loaded");
    });
    WSClient.on("tracking_cancelled", () => {
      resetTrackUI();
      $("track-bar").style.width = "0%";
      $("track-status").textContent = "Tracking canceled.";
    });
    WSClient.on("render_progress", (m) => {
      const pct = m.total ? Math.min(100, (m.frame / m.total) * 100) : 0;
      $("render-bar").style.width = pct + "%";
      $("render-status").textContent = `Frame ${m.frame}/${m.total}`;
    });
    WSClient.on("render_done", async (m) => {
      $("render-bar").style.width = "100%";
      $("render-status").textContent = "Render finished.";
      updateStageTag();
      if (activeTab === "render") loadOutputs();
      toast("Render finished");
    });
    WSClient.on("error", (m) => { resetTrackUI(); toast(`Error: ${m.message}`, true); });
  }

  // ---- helpers -------------------------------------------------------------
  let toastTimer = null;
  function toast(msg, isErr) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.toggle("err", !!isErr);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
  }
  // Silent save into the current pass JSONL (e.g. when leaving the edit tab).
  async function savePassQuiet() {
    if (!MaskState.dirty || !ctx.id || ctx.pass == null) return;
    try { await API.saveMasks(ctx.id, ctx.pass, MaskState.serialize()); } catch (_) { }
  }

  // expose
  document.addEventListener("DOMContentLoaded", () => { init(); bindFiles(); });
  return { toast, refreshMaskList, showDelHint, loadVideo };
})();
