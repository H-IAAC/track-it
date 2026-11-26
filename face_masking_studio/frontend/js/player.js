/* player.js — <video> + <canvas> overlay. Per-frame mask drawing. */
const Player = (() => {
  let video, canvas, ctx, wrap;
  let fps = 30;
  let overlayType = "box";
  let fillColor = "#000000";
  let outlinesVisible = true;
  let onFrameCb = null;
  let editorDraw = null; // editor hooks its in-progress overlay here
  let rafId = null;
  let tmpCanvas = null, tmpCtx = null; // offscreen buffer for pixelate

  function init() {
    video = document.getElementById("video");
    canvas = document.getElementById("overlay");
    wrap = document.getElementById("video-wrap");
    ctx = canvas.getContext("2d");
    tmpCanvas = document.createElement("canvas");
    tmpCtx = tmpCanvas.getContext("2d");
    video.addEventListener("loadedmetadata", syncCanvasSize);
    video.addEventListener("play", () => updatePlayIcon(true));
    video.addEventListener("pause", () => updatePlayIcon(false));
    loop();
  }

  function syncCanvasSize() {
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
  }

  function load(url, framerate) {
    fps = framerate || 30;
    video.src = url;
    wrap.hidden = false;
    document.getElementById("player-placeholder").style.display = "none";
    video.load();
  }

  // ---- transport -----------------------------------------------------------
  function currentFrame() { return Math.round(video.currentTime * fps); }
  function seekFrame(f) {
    const max = (MaskState.frameCount || 1) - 1;
    f = Math.max(0, Math.min(max, f));
    video.currentTime = f / fps;
  }
  function step(d) { video.pause(); seekFrame(currentFrame() + d); }
  function togglePlay() { video.paused ? video.play() : video.pause(); }
  function setSpeed(r) { video.playbackRate = r; }
  function updatePlayIcon(playing) {
    const b = document.getElementById("btn-play");
    if (b) b.textContent = playing ? "⏸" : "▶";
  }

  // ---- coordinate mapping (CSS px -> native video px) ----------------------
  function eventToCanvas(ev) {
    const r = canvas.getBoundingClientRect();
    const sx = canvas.width / r.width;
    const sy = canvas.height / r.height;
    return { x: (ev.clientX - r.left) * sx, y: (ev.clientY - r.top) * sy };
  }

  // ---- drawing -------------------------------------------------------------
  function hexToRgb(h) {
    const n = parseInt(h.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function drawMask(b) {
    const stroke = b.source === "manual" ? "#ff9d1c" : "#3a6db0";
    const x = b.x, y = b.y, w = b.w, h = b.h;

    if (w <= 0 || h <= 0) return;

    if (overlayType === "fill") {
      const [r, g, bl] = hexToRgb(fillColor);
      ctx.fillStyle = `rgb(${r},${g},${bl})`;
      ctx.fillRect(x, y, w, h);
    } else if (overlayType === "blur") {
      // CSS `blur()` IS a gaussian blur. The earlier "radial" look was an edge
      // artifact: clipping to the box made the kernel sample transparent pixels
      // outside the drawn region, so the borders faded → looked like a vignette.
      // Fix: feed the kernel a PADDED source region (real neighbour pixels), then
      // clip the *display* to the box. Result is uniform gaussian across the box.
      const r = Math.max(4, Math.min(40, w / 6)) | 0;
      const pad = r * 3;
      const vw = video.videoWidth, vh = video.videoHeight;
      const sx = Math.max(0, x - pad), sy = Math.max(0, y - pad);
      const ex = Math.min(vw, x + w + pad), ey = Math.min(vh, y + h + pad);
      ctx.save();
      ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
      ctx.filter = `blur(${r}px)`;
      try { ctx.drawImage(video, sx, sy, ex - sx, ey - sy, sx, sy, ex - sx, ey - sy); } catch (_) {}
      ctx.restore(); // also resets ctx.filter to "none"
    } else if (overlayType === "pixel") {
      // downscale the region then upscale with smoothing off → blocky pixels
      const block = Math.max(6, w / 14);
      const pw = Math.max(1, Math.round(w / block));
      const ph = Math.max(1, Math.round(h / block));
      tmpCanvas.width = pw; tmpCanvas.height = ph;
      try {
        tmpCtx.drawImage(video, x, y, w, h, 0, 0, pw, ph);
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(tmpCanvas, 0, 0, pw, ph, x, y, w, h);
        ctx.restore();
      } catch (_) {}
    }

    // outline + id (hidden when outlinesVisible is off, for a clean preview)
    if (!outlinesVisible) return;
    ctx.lineWidth = 2;
    ctx.strokeStyle = stroke;
    ctx.strokeRect(x, y, w, h);
    ctx.font = "600 13px 'Helvetica Neue', Helvetica, Arial, sans-serif";
    ctx.fillStyle = stroke;
    ctx.fillText(b.id, x + 1, y - 5);
  }

  let lastFrame = -1;
  function loop() {
    rafId = requestAnimationFrame(loop);
    if (!video || !video.videoWidth) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const frame = currentFrame();
    const ms = MaskState.getMasksAtFrame(frame);
    if (window.Editor) {
      const sel = Editor.getSelected();
      if (sel) ms.sort((a, b) => a.id === sel ? 1 : b.id === sel ? -1 : 0);
    }
    ms.forEach(drawMask);
    if (editorDraw) editorDraw(ctx, frame);
    // onFrameCb rebuilds DOM (mask list, clock) — fire only when the frame
    // actually changes, not every RAF tick. Rebuilding 60×/s destroyed the
    // mask-list rows between mousedown and mouseup, killing row clicks.
    if (frame !== lastFrame) { lastFrame = frame; if (onFrameCb) onFrameCb(frame, ms); }
  }

  // ---- config setters ------------------------------------------------------
  function setOverlayType(t) { overlayType = t; }
  function setFillColor(c) { fillColor = c; }
  function setOutlinesVisible(v) { outlinesVisible = !!v; }
  function onFrame(fn) { onFrameCb = fn; }
  function setEditorDraw(fn) { editorDraw = fn; }

  return {
    init, load, syncCanvasSize,
    currentFrame, seekFrame, step, togglePlay, setSpeed,
    eventToCanvas, setOverlayType, setFillColor, setOutlinesVisible, onFrame, setEditorDraw,
    get video() { return video; },
    get canvas() { return canvas; },
    get fps() { return fps; },
  };
})();
