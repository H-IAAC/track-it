/* history.js — UI panel for logging and tracking mask edits with visual Undo/Redo */
const EditHistory = (() => {
  const logs = [];
  let currentIndex = -1;
  let colEl, listEl, toggleBtn, closeBtn;
  let isOpen = false;

  function init() {
    colEl = document.getElementById("history-col");
    listEl = document.getElementById("history-list");
    toggleBtn = document.getElementById("btn-toggle-history");
    closeBtn = document.getElementById("btn-close-history");

    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => setOpen(!isOpen));
    }
    if (closeBtn) {
      closeBtn.addEventListener("click", () => setOpen(false));
    }
  }

  function setOpen(on) {
    if (!colEl) return;
    isOpen = on;
    if (on) {
      colEl.classList.remove("collapsed");
    } else {
      colEl.classList.add("collapsed");
    }
    
    if (toggleBtn) {
      toggleBtn.classList.toggle("active", on);
      toggleBtn.textContent = on ? "Hide History" : "Show History";
    }
    if (on) {
      render(); // ensure latest items are visible
      scrollToBottom();
    }
  }

  // Clear history on video load or pass load
  function reset() {
    logs.length = 0;
    currentIndex = -1;
    render();
  }

  // Push an initial state if history is empty
  function initPassState(snapshot) {
    if (logs.length === 0) {
      logs.push({
        action: "Start",
        maskId: "-",
        frame: "-",
        desc: "Original pass state",
        timestamp: Date.now(),
        seekFrame: 0,
        snapshot: snapshot
      });
      currentIndex = 0;
      render();
    }
  }

  function fmtFrame(frame) {
    if (Array.isArray(frame)) return `f: ${frame.join(" - ")}`;
    return `f: ${frame}`;
  }

  // Pre-defined color tags for actions
  const actionColors = {
    "Created": "var(--sage)",
    "Deleted": "var(--red)",
    "Ended": "var(--orange)",
    "Moved": "var(--blue)",
    "Delete Segment": "var(--red)",
    "Extended": "var(--indigo)",
    "Revived": "var(--sage)",
    "Keyframe Deleted": "var(--amber)"
  };

  function log(action, maskId, frame, desc, snapshot) {
    // Only log if the video is actually loaded
    if (!Player.video || !Player.video.videoWidth) return;

    // If we are back in time, discard the future
    if (currentIndex < logs.length - 1) {
      logs.splice(currentIndex + 1);
    }

    logs.push({
      action,
      maskId,
      frame,
      desc,
      timestamp: Date.now(),
      seekFrame: Array.isArray(frame) ? frame[0] : parseInt(frame, 10) || Player.currentFrame(),
      snapshot
    });

    // Enforce MAX_UNDO
    const MAX_UNDO = 50;
    if (logs.length > MAX_UNDO) {
      logs.shift();
    }

    currentIndex = logs.length - 1;

    if (isOpen) {
      render();
      scrollToActive();
    }
  }



  function scrollToActive() {
    if (listEl) {
      setTimeout(() => {
        const active = listEl.querySelector(".hist-current");
        if (active) active.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 50);
    }
  }

  function render() {
    if (!listEl) return;
    if (logs.length === 0) {
      listEl.innerHTML = `<div class="hist-empty">No edits made in this pass.</div>`;
      return;
    }

    const html = [...logs].reverse().map((lg, reversedIdx) => {
      const i = logs.length - 1 - reversedIdx;
      const color = lg.action === "Start" ? "var(--ink-2)" : (actionColors[lg.action] || "var(--ink-2)");
      const isFuture = i > currentIndex;
      const isCurrent = i === currentIndex;
      
      return `
        <div class="hist-item ${isFuture ? 'hist-future' : ''} ${isCurrent ? 'hist-current' : ''}" 
             data-idx="${i}" onclick="EditHistory.seekTo(${i})">
          <div class="hist-hdr">
            <span class="hist-action" style="color: ${color}">${lg.action}</span>
            <span class="hist-frame">${fmtFrame(lg.frame)}</span>
          </div>
          <div class="hist-body">
            <span class="hist-id">${lg.maskId}</span>
          </div>
        </div>
      `;
    }).join("");

    listEl.innerHTML = html;
  }

  function seekTo(idx) {
    const lg = logs[idx];
    if (!lg) return;
    
    // Jump in video
    if (typeof lg.seekFrame === "number") {
      Player.seekFrame(lg.seekFrame);
    }

    // Restore state if it differs
    if (idx !== currentIndex && lg.snapshot) {
      currentIndex = idx;
      MaskState.restoreSnap(lg.snapshot);
      MaskState.emitDirect(); // force re-render without pushing to history
      render();
    }
  }

  // Called by Ctrl+Z hotkey
  function undo() {
    if (currentIndex > 0) {
      seekTo(currentIndex - 1);
      scrollToActive();
      return true;
    }
    return false;
  }

  function redo() {
    if (currentIndex < logs.length - 1) {
      seekTo(currentIndex + 1);
      scrollToActive();
      return true;
    }
    return false;
  }

  function canUndo() {
    return currentIndex > 0;
  }

  return { init, log, setOpen, reset, seekTo, initPassState, undo, redo, canUndo };
})();
window.EditHistory = EditHistory;
