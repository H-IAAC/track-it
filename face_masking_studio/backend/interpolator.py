"""Linear interpolation of mask positions between keyframes."""
from __future__ import annotations


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def interpolate_masks(keyframes: list[dict]) -> dict[int, dict]:
    """Expand a mask's keyframes into a per-frame position dict.

    keyframes: list of {frame, x, y, w, h, state} ordered by frame.
    For each consecutive pair of "active" keyframes, intermediate frames are
    linearly interpolated. A "dead" keyframe ends the mask: nothing after it
    (up to the next "active" reactivation) is generated.

    Returns {frame_number: {x, y, w, h, state, source}}.
    """
    if not keyframes:
        return {}

    kfs = sorted(keyframes, key=lambda k: k["frame"])
    result: dict[int, dict] = {}

    for i, kf in enumerate(kfs):
        frame = kf["frame"]
        result[frame] = {
            "x": kf["x"],
            "y": kf["y"],
            "w": kf["w"],
            "h": kf["h"],
            "state": kf["state"],
            "source": kf.get("source", "interpolated"),
        }
        if kf["state"] == "dead":
            # No fill after a dead keyframe.
            continue
        if i + 1 >= len(kfs):
            continue
        nxt = kfs[i + 1]
        if nxt["state"] == "dead":
            # Hold up to (but not including) the dead frame; dead frame itself
            # is written on its own iteration.
            continue
        span = nxt["frame"] - frame
        if span <= 1:
            continue
        for f in range(frame + 1, nxt["frame"]):
            t = (f - frame) / span
            result[f] = {
                "x": _lerp(kf["x"], nxt["x"], t),
                "y": _lerp(kf["y"], nxt["y"], t),
                "w": _lerp(kf["w"], nxt["w"], t),
                "h": _lerp(kf["h"], nxt["h"], t),
                "state": "active",
                "source": "interpolated",
            }
    return result
