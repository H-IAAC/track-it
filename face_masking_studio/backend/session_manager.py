"""Per-video state machine and pass bookkeeping (persisted to JSON)."""
from __future__ import annotations

import json
from pathlib import Path

from config import MASKS_DIR

_STATE_FILE = MASKS_DIR / "_session_state.json"


def _load() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save(data: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_state(video_id: str) -> str:
    """Return the current pipeline state for a video (default RAW)."""
    state = _load().get(video_id, {}).get("state")
    if state:
        return state
        
    # Auto-recover state if missing but JSONL passes exist
    passes = existing_passes(safe_stem(video_id))
    if passes:
        max_pass = max(passes)
        return "TRACKED" if max_pass == 0 else f"MANUAL_{max_pass}"
        
    return "RAW"


def set_state(video_id: str, state: str) -> None:
    data = _load()
    data.setdefault(video_id, {})["state"] = state
    _save(data)


def safe_stem(video_id: str) -> str:
    """Flatten a (possibly nested) video id into a filesystem-safe stem.

    Videos can live in subfolders of raw/, so an id like "subA/clip" must not
    create nested mask files — encode the separator instead.
    """
    return video_id.replace("/", "__")


def jsonl_name(video_stem: str, pass_n: int) -> str:
    return f"{safe_stem(video_stem)}_pass{pass_n}.jsonl"


def jsonl_path(video_stem: str, pass_n: int) -> Path:
    from config import DATASET_DIR
    if video_stem.startswith("dataset:"):
        session_id = video_stem.split(":", 1)[1]
        session_dir = DATASET_DIR / session_id
        session_masks_dir = session_dir / "videos" / "masks_data"
        session_masks_dir.mkdir(parents=True, exist_ok=True)
        return session_masks_dir / jsonl_name(video_stem, pass_n)
    return MASKS_DIR / jsonl_name(video_stem, pass_n)


def existing_passes(video_stem: str) -> list[int]:
    """Return pass numbers that have a saved JSONL on disk."""
    found = []
    n = 0
    while jsonl_path(video_stem, n).exists():
        found.append(n)
        n += 1
    return found


def advance(video_id: str, video_stem: str) -> str:
    """Move to the next state, copying the prior pass JSONL as edit base."""
    current = get_state(video_id)
    if current == "RAW":
        return current
    elif current == "TRACKED":
        target = "MANUAL_1"
        target_pass = 1
    elif current.startswith("MANUAL_"):
        n = int(current.split("_")[1])
        target = f"MANUAL_{n+1}"
        target_pass = n + 1
    else:
        return current

    if target_pass >= 1:
        prev_pass = target_pass - 1
        src = jsonl_path(video_stem, prev_pass)
        dst = jsonl_path(video_stem, target_pass)
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    set_state(video_id, target)
    return target
