"""Video orientation: read rotation for informational display only."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _ffprobe_json(video_path: str | Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(video_path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def get_rotation(video_path: str | Path) -> int:
    """Return display rotation in degrees: 0, 90, 180 or 270."""
    try:
        data = _ffprobe_json(video_path)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return 0

    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        # Legacy 'rotate' tag.
        tag = stream.get("tags", {}).get("rotate")
        if tag is not None:
            return int(tag) % 360
        # Modern display matrix side data.
        for sd in stream.get("side_data_list", []):
            if "rotation" in sd:
                # ffprobe rotation is counter-clockwise display rotation.
                return (-int(sd["rotation"])) % 360
    return 0


def normalize_rotation(video_path: str | Path, keep_backup: bool = True) -> bool:
    """Bake display rotation into the pixels so the file is upright (rotation=0).

    Phones record landscape pixels plus a 90/270 display-rotation flag. YOLO and
    the renderer decode raw pixels (sideways), so we re-encode with ffmpeg, whose
    autorotate (on by default) applies the flag and writes upright pixels with no
    rotation metadata. The original is replaced in place.

    With ``keep_backup`` the untouched original is renamed to ``<name>.orig.<ext>``
    (only the first time; later runs are no-ops since rotation is already 0).
    Returns True if the file was rewritten, False if nothing to do.
    """
    path = Path(video_path)
    if get_rotation(path) == 0:
        return False

    tmp = path.with_name(f"{path.stem}.__upright__{path.suffix}")
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(tmp),
    ]
    subprocess.run(cmd, check=True)

    if keep_backup:
        backup = path.with_name(f"{path.stem}.orig{path.suffix}")
        if not backup.exists():
            path.rename(backup)
        else:
            path.unlink()
    else:
        path.unlink()
    tmp.rename(path)
    return True


def get_video_info(video_path: str | Path) -> dict:
    """Return resolution, fps, duration, frame count, rotation."""
    data = _ffprobe_json(video_path)
    info = {
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "duration": 0.0,
        "frame_count": 0,
        "rotation": 0,
    }
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        info["width"] = int(stream.get("width", 0))
        info["height"] = int(stream.get("height", 0))
        num, _, den = stream.get("avg_frame_rate", "0/1").partition("/")
        den_val = float(den) if den else 1.0
        info["fps"] = (float(num) / den_val) if den_val else 0.0
        dur = stream.get("duration") or data.get("format", {}).get("duration", 0)
        info["duration"] = float(dur)
        nb = stream.get("nb_frames")
        if nb:
            info["frame_count"] = int(nb)
        elif info["fps"] and info["duration"]:
            info["frame_count"] = int(round(info["fps"] * info["duration"]))
        break
    info["rotation"] = get_rotation(video_path)
    return info
