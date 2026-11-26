"""Apply masks to the raw video and export final MP4 via FFmpeg pipe."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


def _apply_blur(roi: np.ndarray) -> np.ndarray:
    k = max(11, (min(roi.shape[:2]) // 2) | 1)
    return cv2.GaussianBlur(roi, (k, k), 0)


def _apply_pixelate(roi: np.ndarray, blocks: int = 12) -> np.ndarray:
    h, w = roi.shape[:2]
    bw = max(1, w // blocks)
    bh = max(1, h // blocks)
    small = cv2.resize(roi, (bw, bh), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def _read_masks(jsonl_path: str | Path):
    """Yield (frame_index, masks) streaming from a JSONL file."""
    with open(jsonl_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            yield rec["frame"], rec.get("masks", [])


def render_video(
    video_path: str | Path,
    jsonl_path: str | Path,
    output_path: str | Path,
    mask_type: str = "blur",
    fill_color: tuple[int, int, int] = (0, 0, 0),
    ws_callback: Callable[[dict], None] | None = None,
) -> str:
    """Burn masks into the video. mask_type: 'blur' | 'pixel' | 'fill'."""
    src_path = Path(video_path)

    cap = cv2.VideoCapture(str(src_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {src_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Index masks by frame (one pass over the JSONL).
    masks_by_frame: dict[int, list[dict]] = {
        f: m for f, m in _read_masks(jsonl_path)
    }

    print(f"[FaceMasking] Rendering started: {src_path.name} -> {output_path} (mask: {mask_type}, total frames: {total})", flush=True)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-i",
            str(src_path),
            "-map",
            "0:v",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-shortest",
            str(output_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    frame_idx = 0
    step_pct = max(1, total // 20)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            for m in masks_by_frame.get(frame_idx, []):
                if m.get("state") == "dead":
                    continue
                x, y = int(m["x"]), int(m["y"])
                w, h = int(m["w"]), int(m["h"])
                x2, y2 = min(x + w, width), min(y + h, height)
                x, y = max(0, x), max(0, y)
                if x2 <= x or y2 <= y:
                    continue
                if mask_type == "fill":
                    cv2.rectangle(frame, (x, y), (x2, y2), fill_color, -1)
                else:
                    roi = frame[y:y2, x:x2]
                    if mask_type == "pixel":
                        frame[y:y2, x:x2] = _apply_pixelate(roi)
                    else:  # blur
                        frame[y:y2, x:x2] = _apply_blur(roi)
            ffmpeg.stdin.write(frame.tobytes())
            frame_idx += 1

            # Terminal progress logging (every ~5% or final frame)
            if frame_idx % step_pct == 0 or frame_idx >= total:
                pct = int(100.0 * frame_idx / max(1, total))
                print(f"[FaceMasking] Rendering frame {frame_idx}/{total} ({pct}%)", flush=True)

            if ws_callback and frame_idx % 15 == 0:
                ws_callback(
                    {
                        "type": "render_progress",
                        "frame": frame_idx,
                        "total": total,
                    }
                )
    finally:
        cap.release()
        if ffmpeg.stdin:
            ffmpeg.stdin.close()
        ffmpeg.wait()

    print(f"[FaceMasking] Rendering completed: {output_path}", flush=True)

    if ws_callback:
        ws_callback({"type": "render_done", "output_path": str(output_path)})
    return str(output_path)
