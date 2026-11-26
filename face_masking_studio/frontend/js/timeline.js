/* timeline.js — scrubber canvas: density bars, edit dots, playhead. */
const Timeline = (() => {
  let canvas, ctx, wrap;
  let pxPerFrame = 6;
  let offset = 0;          // first visible frame
  const FRAME0_MARGIN = 48; // px gap before frame 0 at the very start (start only,
                            // not a global gutter) — lets you see the timeline head
  // pan-by-default: drag anywhere to pan; a click (no drag) seeks
  let mouseDown = false, downX = 0, panStartOff = 0, moved = false;
  // range selection (for "delete trecho")
  let rangeSelecting = false, draggingRange = false;
  let rangeStart = null, rangeEnd = null;
  // per-pass edit lanes: [{label, items:[{min,max,frames:[]}]}] for M1/M2/M3.
  // null until App feeds data — falls back to a single live dot lane.
  let passLanes = null;
  function setPassEdits(lanes) { passLanes = lanes; }
  // when a mask is selected, the edit lanes show only that mask's keyframes.
  let selectedMaskId = null;
  function setSelectedMask(id) { selectedMaskId = id; }
  // space key: tap = play/pause toggle, hold = fast-forward (2x; ctrl = 0.5x).
  let spaceTimer = null, ffActive = false;
  const SPACE_HOLD_MS = 250;

  // ---- height / collapse ---------------------------------------------------
  // Timeline height is JS-driven (inline). Drag the top handle to resize within
  // [COLLAPSE_AT, MAX]; drag below COLLAPSE_AT and it collapses to COLLAPSED
  // (which is a touch taller than before and shows ONLY the density section).
  const TL = { COLLAPSED: 92, DEFAULT: 240, MAX: 460, COLLAPSE_AT: 132 };
  let expandedH = TL.DEFAULT;   // remembered height while expanded
  let resizing = false, startY = 0, startH = 0;

  function isCollapsed() { return wrap.classList.contains("collapsed"); }
  function setCollapsed(on) {
    wrap.classList.toggle("collapsed", on);
    wrap.style.height = (on ? TL.COLLAPSED : expandedH) + "px";
  }

  function init() {
    canvas = document.getElementById("tl-canvas");
    wrap = document.getElementById("tl-canvas-wrap");
    ctx = canvas.getContext("2d");

    canvas.addEventListener("click", onClick);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", () => { mouseDown = false; draggingRange = false; canvas.style.cursor = rangeSelecting ? "col-resize" : "grab"; });
    window.addEventListener("mousemove", onMove);

    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKeyUp);

    const handle = document.getElementById("tl-resize");
    if (handle) handle.addEventListener("mousedown", onResizeDown);

    wrap.style.height = expandedH + "px"; // expanded by default
    canvas.style.cursor = "grab";
    new ResizeObserver(resize).observe(wrap);
    resize();
    loop();
  }

  // ---- drag-to-resize ------------------------------------------------------
  function onResizeDown(e) {
    e.preventDefault();
    resizing = true;
    startY = e.clientY;
    startH = wrap.getBoundingClientRect().height;
    wrap.classList.add("dragging");
    document.getElementById("tl-resize").classList.add("dragging");
    document.body.style.cursor = "row-resize";
    window.addEventListener("mousemove", onResizeMove);
    window.addEventListener("mouseup", onResizeUp);
  }
  function onResizeMove(e) {
    let h = startH - (e.clientY - startY); // drag up → taller
    if (h < TL.COLLAPSE_AT) {
      if (!isCollapsed()) setCollapsed(true); // crossed the lower limit → collapse
    } else {
      if (isCollapsed()) wrap.classList.remove("collapsed");
      expandedH = Math.min(TL.MAX, h);
      wrap.style.height = expandedH + "px";
    }
  }
  function onResizeUp() {
    resizing = false;
    wrap.classList.remove("dragging");
    document.getElementById("tl-resize").classList.remove("dragging");
    document.body.style.cursor = "";
    window.removeEventListener("mousemove", onResizeMove);
    window.removeEventListener("mouseup", onResizeUp);
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = wrap.getBoundingClientRect();
    canvas.width = r.width * dpr;
    canvas.height = r.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function cssSize() {
    const r = wrap.getBoundingClientRect();
    return { w: r.width, h: r.height };
  }

  function xToFrame(x) { return Math.round(offset + x / pxPerFrame); }
  function frameToX(f) { return (f - offset) * pxPerFrame; }

  // ---- interaction ---------------------------------------------------------
  function onClick(e) {
    if (moved) { moved = false; return; } // was a pan-drag, not a click
    if (rangeSelecting) return;            // don't seek while marking a range
    const r = canvas.getBoundingClientRect();
    Player.seekFrame(xToFrame(e.clientX - r.left));
  }
  function clampFrame(f) {
    const fc = MaskState.frameCount || 1;
    return Math.max(0, Math.min(fc - 1, f));
  }
  function onWheel(e) {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const fAtCursor = offset + mx / pxPerFrame;
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    pxPerFrame = Math.max(0.05, Math.min(50, pxPerFrame * factor));
    offset = fAtCursor - mx / pxPerFrame;
    clampOffset();
  }
  function onDown(e) {
    if (rangeSelecting) {
      draggingRange = true;
      const r = canvas.getBoundingClientRect();
      rangeStart = rangeEnd = clampFrame(xToFrame(e.clientX - r.left));
      return;
    }
    mouseDown = true;
    downX = e.clientX;
    panStartOff = offset;
    moved = false;
  }
  function onMove(e) {
    if (draggingRange) {
      const r = canvas.getBoundingClientRect();
      rangeEnd = clampFrame(xToFrame(e.clientX - r.left));
      return;
    }
    if (!mouseDown) return;
    const dx = e.clientX - downX;
    if (Math.abs(dx) > 3) { moved = true; canvas.style.cursor = "grabbing"; }
    offset = panStartOff - dx / pxPerFrame;
    clampOffset();
  }

  // ---- range API (delete trecho) -------------------------------------------
  function setRangeSelect(on) {
    rangeSelecting = !!on;
    canvas.style.cursor = on ? "col-resize" : "grab";
    if (!on) { rangeStart = rangeEnd = null; draggingRange = false; }
  }
  function getRange() {
    if (rangeStart == null || rangeEnd == null) return null;
    return { start: Math.min(rangeStart, rangeEnd), end: Math.max(rangeStart, rangeEnd) };
  }
  function clearRange() { rangeStart = rangeEnd = null; }
  function clampOffset() {
    const fc = MaskState.frameCount || 1;
    // min offset is slightly negative so frame 0 sits FRAME0_MARGIN px from the
    // left edge when scrolled fully left — a head margin, not a global padding.
    const minOff = -FRAME0_MARGIN / pxPerFrame;
    offset = Math.max(minOff, Math.min(offset, fc - 1));
  }

  function onKey(e) {
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
    // Space: a quick tap toggles play/pause; holding fast-forwards at 2x
    // (Ctrl+hold = 0.5x slow-mo). Tap/hold is decided by SPACE_HOLD_MS.
    if (e.code === "Space") {
      e.preventDefault();
      if (e.repeat || spaceTimer || ffActive) return;
      const slow = e.ctrlKey || e.metaKey;
      spaceTimer = setTimeout(() => {
        spaceTimer = null;
        ffActive = true;
        Player.setSpeed(slow ? 0.5 : 2.0);
        if (Player.video && Player.video.paused) Player.video.play();
      }, SPACE_HOLD_MS);
      return;
    }
    const f = Player.currentFrame();
    // step: shift = 5s, plain = 1 frame (ctrl+arrow seek removed)
    const step = e.shiftKey ? Math.round(5 * Player.fps) : 1;
    if (e.key === "ArrowLeft")  { e.preventDefault(); Player.seekFrame(f - step); }
    if (e.key === "ArrowRight") { e.preventDefault(); Player.seekFrame(f + step); }
    if (e.key === "c" || e.key === "C") center();
  }

  function onKeyUp(e) {
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
    if (e.code === "Space") {
      e.preventDefault();
      if (spaceTimer) {
        // released before the hold threshold → treat as a tap: play/pause.
        clearTimeout(spaceTimer); spaceTimer = null;
        Player.togglePlay();
      } else if (ffActive) {
        // releasing a hold stops fast-forward and restores selected speed.
        ffActive = false;
        if (Player.video) Player.video.pause();
        const speedSelect = document.getElementById("speed-select");
        Player.setSpeed(speedSelect ? parseFloat(speedSelect.value) || 1.0 : 1.0);
      }
    }
  }

  function center() {
    const { w } = cssSize();
    offset = Player.currentFrame() - (w / pxPerFrame) / 2;
    clampOffset();
  }

  function toggleExpand() {
    setCollapsed(!isCollapsed());
    setTimeout(resize, 210);
  }

  // ---- draw ----------------------------------------------------------------
  function loop() {
    requestAnimationFrame(loop);
    const { w, h } = cssSize();
    const css = getComputedStyle(document.documentElement);
    const line = css.getPropertyValue("--line").trim();
    const ink3 = css.getPropertyValue("--ink-3").trim();

    ctx.clearRect(0, 0, w, h);

    const fc = MaskState.frameCount || 0;
    if (fc <= 1) {
      ctx.fillStyle = ink3;
      ctx.font = "12px 'Helvetica Neue', Helvetica, Arial, sans-serif";
      ctx.fillText("sem dados de timeline", 12, h / 2 + 4);
      return;
    }

    const collapsed = isCollapsed();
    const mid = h * 0.5;
    const counts = MaskState.getPersonCountPerFrame();
    let maxCount = 1;
    for (let i = 0; i < counts.length; i++) if (counts[i] > maxCount) maxCount = counts[i];

    const fStart = Math.max(0, Math.floor(offset));
    const fEnd = Math.min(fc - 1, Math.ceil(offset + w / pxPerFrame));

    // density bars — mask count per frame. Collapsed shows ONLY this section, so
    // bars use (almost) the full height; expanded keeps them in the upper half.
    const densBottom = collapsed ? (h - 12) : (mid - 4);
    const densAvail = densBottom - 8;
    const bw = Math.max(1, pxPerFrame);
    for (let f = fStart; f <= fEnd; f++) {
      const c = counts[f];
      if (!c) continue;
      const intensity = 0.25 + 0.75 * (c / maxCount);
      ctx.fillStyle = `rgba(58,109,176,${intensity})`;
      const x = frameToX(f);
      const bh = densAvail * (c / maxCount);
      ctx.fillRect(x, densBottom - bh, Math.max(1, bw - 0.5), bh);
    }

    // selected range highlight (delete trecho) — orange band
    const rg = getRange();
    if (rg) {
      const x1 = frameToX(rg.start);
      const x2 = frameToX(rg.end + 1);
      const rw = Math.max(2, x2 - x1);
      ctx.fillStyle = "rgba(207,95,41,0.22)";
      ctx.fillRect(x1, 0, rw, h);
      ctx.strokeStyle = "#ff9d1c"; ctx.lineWidth = 1;
      ctx.strokeRect(x1 + 0.5, 0.5, rw - 1, h - 1);
    }

    // The center rule + per-pass edit lanes only exist in the expanded view.
    if (!collapsed) {
      // center rule
      ctx.strokeStyle = line; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();

      // ---- edit lanes (lower half): one lane per manual pass (M1/M2/M3) -----
      // Each mask's edits in a pass draw as a translucent orange span from its
      // first to its last keyframe; overlapping spans composite to a more opaque
      // band (more edited masks → more opaque). Dots mark the keyframes. Falls
      // back to a single live dot lane until the per-pass data has loaded.
      const ORANGE = "207,95,41";
      const laneTop = mid + 8, laneBot = h - 13;
      if (passLanes && passLanes.length) {
        const laneH = (laneBot - laneTop) / passLanes.length;
        const barH = Math.min(7, laneH * 0.55);
        passLanes.forEach((lane, i) => {
          const yMid = laneTop + laneH * (i + 0.5);
          // when a mask is selected, restrict the lane to that mask's items.
          const items = (lane.items || []).filter(
            (it) => !selectedMaskId || it.id === selectedMaskId);
          // lane baseline + label
          ctx.globalAlpha = 0.45; ctx.strokeStyle = line; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(0, yMid + 0.5); ctx.lineTo(w, yMid + 0.5); ctx.stroke();
          ctx.globalAlpha = 1;
          ctx.fillStyle = items.length ? `rgba(${ORANGE},0.8)` : ink3;
          ctx.font = "700 9.5px 'Helvetica Neue', Helvetica, Arial, sans-serif";
          ctx.fillText(lane.label, 3, yMid - barH / 2 - 2);
          // translucent spans — only the manual interpolation trechos (not the
          // whole mask span). Overlap accumulates opacity via source-over.
          ctx.fillStyle = `rgba(${ORANGE},0.16)`;
          items.forEach((it) =>
            (it.segments || []).forEach(([a, b]) => {
              if (b < fStart || a > fEnd) return;
              const x1 = frameToX(a) + bw / 2;
              const x2 = frameToX(b) + bw / 2;
              ctx.fillRect(x1, yMid - barH / 2, Math.max(2, x2 - x1), barH);
            }));
          // keyframe dots (opaque, filled)
          ctx.fillStyle = `rgba(${ORANGE},0.95)`;
          items.forEach((it) =>
            (it.dots || []).forEach((d) => {
              if (d.f < fStart || d.f > fEnd) return;
              ctx.beginPath();
              ctx.arc(frameToX(d.f) + bw / 2, yMid, 2.8, 0, Math.PI * 2);
              ctx.fill();
            }));
        });
      } else {
        // no per-pass data yet: live dots. Restrict to the selected mask's
        // keyframes when one is selected, else show every manual edit.
        const edits = selectedMaskId
          ? MaskState.keyframeFrames(selectedMaskId)
          : MaskState.getEditedFrames();
        ctx.fillStyle = "#5d7f4c";
        edits.forEach((f) => {
          if (f < fStart || f > fEnd) return;
          ctx.beginPath();
          ctx.arc(frameToX(f) + bw / 2, mid + 14, 3.5, 0, Math.PI * 2);
          ctx.fill();
        });
      }
    }

    // time ticks
    ctx.fillStyle = ink3;
    ctx.font = "10.5px 'Helvetica Neue', Helvetica, Arial, sans-serif";
    const tickEveryFrames = niceTick(pxPerFrame);
    for (let f = Math.ceil(fStart / tickEveryFrames) * tickEveryFrames; f <= fEnd; f += tickEveryFrames) {
      const x = frameToX(f);
      ctx.fillRect(x, h - 10, 1, 5);
      ctx.fillText(fmtTime(f / Player.fps), x + 3, h - 3);
    }

    // playhead
    const px = frameToX(Player.currentFrame());
    if (px >= 0 && px <= w) {
      ctx.strokeStyle = "#1d1a16";
      if (document.documentElement.dataset.theme === "dark") ctx.strokeStyle = "#efe9dc";
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, h); ctx.stroke();
      ctx.fillStyle = "#ff9d1c";
      ctx.beginPath(); ctx.moveTo(px - 4, 0); ctx.lineTo(px + 4, 0); ctx.lineTo(px, 6); ctx.closePath(); ctx.fill();
    }
  }

  function niceTick(ppf) {
    const targetPx = 70;
    const framesPerTarget = targetPx / ppf;
    const steps = [1, 5, 10, 30, 60, 150, 300, 600, 1800, 3600];
    for (const s of steps) if (s >= framesPerTarget) return s;
    return 3600;
  }
  function fmtTime(s) {
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  }

  return { init, toggleExpand, center, setRangeSelect, getRange, clearRange, setPassEdits, setSelectedMask };
})();
