/* editor.js — mask editing on the overlay canvas (Edição pane). */
const Editor = (() => {
  let canvas;
  let active = false;
  let selectedId = null;

  // drag state
  let dragging = false, mode = null; // 'create' | 'move' | 'resize'
  let ghostDrag = false; // dragging the ghost of an out-of-span selected mask
  let startPt = null, draftBox = null, grabOff = null;
  let hoverPt = null;
  let resizeHandle = null, resizeOrig = null; // active resize handle + box at grab

  const HANDLE = 6; // px tolerance (canvas space) around edges/corners
  const CURSOR = {
    n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize",
    ne: "nesw-resize", sw: "nesw-resize", nw: "nwse-resize", se: "nwse-resize",
  };

  function init() {
    canvas = Player.canvas;
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    // click outside the video (the letterbox margins of the player column)
    // deselects the current mask
    const col = document.getElementById("player-col");
    if (col) col.addEventListener("mousedown", (e) => {
      if (!active || e.target === canvas) return; // canvas clicks handled by onDown
      if (selectedId !== null) { selectedId = null; App.refreshMaskList(); }
    });
    Player.setEditorDraw(drawOverlay);
  }

  function setActive(on) {
    active = on;
    canvas.style.pointerEvents = on ? "auto" : "none";
    canvas.style.cursor = on ? "crosshair" : "default";
    if (!on) selectedId = null;
  }
  function getSelected() { return selectedId; }
  function select(id) { selectedId = id; }

  // Delete actions driven by the toolbar buttons (no persistent delete mode):
  // they operate on the currently selected mask. 'mask' removes it entirely,
  // 'frame' drops the keyframe at the current frame, 'range' needs a trecho
  // marked on the timeline (the button arms that selection on the first press).
  function deleteSelected(kind) {
    if (!selectedId) return App.toast("Select a mask first", true);
    const frame = Player.currentFrame();
    if (kind === "mask") {
      MaskState.deleteMask(selectedId);
      selectedId = null;
    } else if (kind === "range") {
      const rg = Timeline.getRange();
      if (!rg) {
        Timeline.setRangeSelect(true);
        App.showDelHint(true);
        App.toast("Mark the segment on the timeline (orange), then click Segment");
        return;
      }
      MaskState.deleteRange(selectedId, rg.start, rg.end);
      Timeline.setRangeSelect(false);
      Timeline.clearRange();
      App.showDelHint(false);
    } else {
      MaskState.deleteFrameAt(selectedId, frame);
    }
    App.refreshMaskList();
  }

  // ---- cursor --------------------------------------------------------------
  // edge/corner resize cursors over a handle, pointer over the body (move),
  // grabbing while moving, crosshair over empty area (ready to create).
  function updateCursor(pt) {
    if (!active) { canvas.style.cursor = "default"; return; }
    const frame = Player.currentFrame();
    let c;
    const g = currentGhost(frame);
    if (g && pointInBox(pt, g)) {
      const hd = handleAt(pt, g);
      c = hd ? CURSOR[hd] : "grab";
    } else {
      const hit = maskAtPoint(pt, frame);
      if (hit) {
        const hd = handleAt(pt, hit);
        c = hd ? CURSOR[hd] : "pointer";
      } else {
        c = "crosshair";
      }
    }
    canvas.style.cursor = c;
  }

  // ---- hit-testing ---------------------------------------------------------
  // padded so edge/corner handles just outside the box are still grabbable.
  function pointInBox(pt, b) {
    const minX = Math.min(b.x, b.x + b.w) - HANDLE;
    const maxX = Math.max(b.x, b.x + b.w) + HANDLE;
    const minY = Math.min(b.y, b.y + b.h) - HANDLE;
    const maxY = Math.max(b.y, b.y + b.h) + HANDLE;
    return pt.x >= minX && pt.x <= maxX && pt.y >= minY && pt.y <= maxY;
  }
  function maskAtPoint(pt, frame) {
    const ms = MaskState.getMasksAtFrame(frame);
    if (selectedId) {
      const sel = ms.find((m) => m.id === selectedId);
      if (sel && pointInBox(pt, sel)) return sel;
    }
    for (let i = ms.length - 1; i >= 0; i--) {
      if (ms[i].id === selectedId) continue;
      if (pointInBox(pt, ms[i])) return ms[i];
    }
    return null;
  }
  // Ghost box of the selected mask when it is NOT present at `frame`, else null.
  function currentGhost(frame) {
    if (!selectedId) return null;
    if (MaskState.getMasksAtFrame(frame).some((m) => m.id === selectedId)) return null;
    return MaskState.ghostBox(selectedId, frame);
  }
  // returns which resize handle the point is on (n/s/e/w/ne/nw/se/sw) or null.
  function handleAt(pt, b) {
    const minX = Math.min(b.x, b.x + b.w);
    const maxX = Math.max(b.x, b.x + b.w);
    const minY = Math.min(b.y, b.y + b.h);
    const maxY = Math.max(b.y, b.y + b.h);
    const nearL = Math.abs(pt.x - minX) <= HANDLE;
    const nearR = Math.abs(pt.x - maxX) <= HANDLE;
    const nearT = Math.abs(pt.y - minY) <= HANDLE;
    const nearB = Math.abs(pt.y - maxY) <= HANDLE;
    const spanX = pt.x >= minX - HANDLE && pt.x <= maxX + HANDLE;
    const spanY = pt.y >= minY - HANDLE && pt.y <= maxY + HANDLE;
    if (nearT && nearL) return "nw";
    if (nearT && nearR) return "ne";
    if (nearB && nearL) return "sw";
    if (nearB && nearR) return "se";
    if (nearT && spanX) return "n";
    if (nearB && spanX) return "s";
    if (nearL && spanY) return "w";
    if (nearR && spanY) return "e";
    return null;
  }
  // build a new box by dragging `hd` to `pt`, anchoring the opposite edges.
  function applyResize(orig, hd, pt) {
    let left = orig.x, top = orig.y, right = orig.x + orig.w, bottom = orig.y + orig.h;
    if (hd.includes("e")) right = pt.x;
    if (hd.includes("w")) left = pt.x;
    if (hd.includes("s")) bottom = pt.y;
    if (hd.includes("n")) top = pt.y;
    return {
      x: Math.min(left, right), y: Math.min(top, bottom),
      w: Math.max(4, Math.abs(right - left)), h: Math.max(4, Math.abs(bottom - top)),
    };
  }

  // ---- mouse ---------------------------------------------------------------
  function onDown(e) {
    if (!active) return;
    // editing a mask by hand must freeze the picture so the box lands on the frame
    // the user is looking at.
    if (Player.video && !Player.video.paused) Player.video.pause();
    const pt = Player.eventToCanvas(e);
    const frame = Player.currentFrame();
    const ghost = currentGhost(frame);

    // over the selected mask's ghost → drag it to revive the mask at this frame;
    // over a real mask → select & move/resize; empty area → create.
    if (ghost && pointInBox(pt, ghost)) {
      dragging = true; ghostDrag = true;
      const hd = handleAt(pt, ghost);
      if (hd) {
        mode = "resize"; resizeHandle = hd; resizeOrig = { ...ghost }; draftBox = { ...ghost };
        canvas.style.cursor = CURSOR[hd];
      } else {
        mode = "move"; draftBox = { ...ghost }; grabOff = { x: pt.x - ghost.x, y: pt.y - ghost.y };
        canvas.style.cursor = "grabbing";
      }
    } else {
      const hit = maskAtPoint(pt, frame);
      if (hit) {
        selectedId = hit.id;
        dragging = true;
        const hd = handleAt(pt, hit);
        if (hd) {
          mode = "resize"; resizeHandle = hd; resizeOrig = { ...hit }; draftBox = { ...hit };
          canvas.style.cursor = CURSOR[hd];
        } else {
          mode = "move"; draftBox = { ...hit }; grabOff = { x: pt.x - hit.x, y: pt.y - hit.y };
          canvas.style.cursor = "grabbing";
        }
      } else {
        selectedId = null;
        dragging = true; mode = "create"; startPt = pt;
        draftBox = { x: pt.x, y: pt.y, w: 0, h: 0 };
        canvas.style.cursor = "crosshair";
      }
    }
    App.refreshMaskList();
  }

  function onMove(e) {
    if (!active) return;
    const pt = Player.eventToCanvas(e);
    hoverPt = pt;
    if (!dragging) { updateCursor(pt); return; }
    if (mode === "create") {
      draftBox = norm(startPt, pt);
    } else if (mode === "resize") {
      draftBox = applyResize(resizeOrig, resizeHandle, pt);
    } else if (mode === "move") {
      draftBox.x = pt.x - grabOff.x;
      draftBox.y = pt.y - grabOff.y;
    }
  }

  function onUp() {
    if (!dragging) return;
    dragging = false;
    const frame = Player.currentFrame();
    if (ghostDrag && selectedId && draftBox) {
      // committing a ghost drag revives the mask at the current frame.
      MaskState.reviveAt(selectedId, frame, draftBox);
    } else if (mode === "create" && draftBox && draftBox.w > 5 && draftBox.h > 5) {
      selectedId = MaskState.createMask(frame, draftBox);
    } else if ((mode === "resize" || mode === "move") && selectedId && draftBox) {
      MaskState.updateBox(selectedId, frame, draftBox);
    }
    mode = null; ghostDrag = false; draftBox = null; grabOff = null; resizeHandle = null; resizeOrig = null;
    if (hoverPt) updateCursor(hoverPt);
    App.refreshMaskList();
  }

  function norm(a, b) {
    return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
             w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) };
  }

  // ---- lifecycle -----------------------------------------------------------
  // Encerrar (matar): terminate the mask at the current frame (dead keyframe);
  // it no longer exists from here on. Extending a mask is done directly in the
  // video now — drag its ghost box to a frame and it revives/extends there.
  function endMask() {
    if (!selectedId) return App.toast("Select a mask first", true);
    MaskState.killAt(selectedId, Player.currentFrame());
    App.refreshMaskList();
  }

  // Fechar trecho: close the manual edit segment at the current frame so manual
  // interpolation stops and the underlying tracking resumes after it. Lets a
  // tracked mask carry several disjoint manual segments with tracked spans in
  // between.
  function closeSegment() {
    if (!selectedId) return App.toast("Select a mask first", true);
    MaskState.closeSegmentAt(selectedId, Player.currentFrame());
    App.refreshMaskList();
  }

  function clearSelection() { selectedId = null; }

  // ---- overlay draw (called from player loop) ------------------------------
  function drawOverlay(ctx, frame) {
    if (draftBox) {
      ctx.save();
      ctx.strokeStyle = "#5d7f4c"; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
      ctx.strokeRect(draftBox.x, draftBox.y, draftBox.w, draftBox.h);
      ctx.restore();
    }
    if (selectedId) {
      const b = MaskState.getMasksAtFrame(frame).find((m) => m.id === selectedId);
      if (b) {
        ctx.save();
        ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
        ctx.strokeRect(b.x - 2, b.y - 2, b.w + 4, b.h + 4);
        ctx.setLineDash([]);
        // 8 resize handles: 4 corners + 4 edge midpoints
        const cx = b.x + b.w / 2, cy = b.y + b.h / 2, r = b.x + b.w, bot = b.y + b.h;
        const pts = [
          [b.x, b.y], [cx, b.y], [r, b.y],
          [b.x, cy],             [r, cy],
          [b.x, bot], [cx, bot], [r, bot],
        ];
        ctx.fillStyle = "#ff9d1c"; ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1;
        for (const [hx, hy] of pts) {
          ctx.fillRect(hx - 5, hy - 5, 10, 10);
          ctx.strokeRect(hx - 5, hy - 5, 10, 10);
        }
        ctx.restore();
      } else {
        // selected but outside its appearance span: draw a ghost at its nearest
        // known position so the user still sees where it lives. Hidden mid-drag
        // so the dashed draft box leads instead.
        const g = MaskState.ghostBox(selectedId, frame);
        if (g && !dragging) drawGhost(ctx, g);
      }
    }
  }

  // Ghost = dashed orange outline + diagonal X + a small ✕ badge at the top-left
  // corner. Visually distinct from the solid white/orange active selection, and
  // text-free so it stays legible at any video resolution.
  function drawGhost(ctx, b) {
    ctx.save();
    ctx.lineCap = "round";
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = "#ff9d1c"; ctx.lineWidth = 2; ctx.setLineDash([6, 5]);
    ctx.strokeRect(b.x, b.y, b.w, b.h);
    ctx.beginPath();
    ctx.moveTo(b.x, b.y); ctx.lineTo(b.x + b.w, b.y + b.h);
    ctx.moveTo(b.x + b.w, b.y); ctx.lineTo(b.x, b.y + b.h);
    ctx.stroke();
    ctx.setLineDash([]);
    // corner badge
    const r = Math.max(7, Math.min(11, b.w * 0.06));
    ctx.globalAlpha = 0.95;
    ctx.fillStyle = "#ff9d1c";
    ctx.beginPath(); ctx.arc(b.x, b.y, r, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = Math.max(1.4, r * 0.22);
    const k = r * 0.42;
    ctx.beginPath();
    ctx.moveTo(b.x - k, b.y - k); ctx.lineTo(b.x + k, b.y + k);
    ctx.moveTo(b.x + k, b.y - k); ctx.lineTo(b.x - k, b.y + k);
    ctx.stroke();
    ctx.restore();
  }

  return { init, setActive, deleteSelected, endMask, closeSegment, clearSelection, getSelected, select };
})();
