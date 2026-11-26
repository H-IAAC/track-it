"""YOLO head tracking: detect every N frames, IoU association, backward fill."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import cv2

from interpolator import _lerp
from metadata_fixer import normalize_rotation
from detectors import get_detector
from onnx_detector import Detection


def _iou(a: dict, b: dict) -> float:
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]
    ix1, iy1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union else 0.0


def _apply_pad(det: Detection, pad_pct: float, w_max: int, h_max: int) -> dict:
    """Grow a detection box by pad_pct (%) on every side, clamped to frame."""
    pad_w = det.w * pad_pct / 100.0
    pad_h = det.h * pad_pct / 100.0
    x = max(0.0, det.x - pad_w)
    y = max(0.0, det.y - pad_h)
    x2 = min(float(w_max), det.x + det.w + pad_w)
    y2 = min(float(h_max), det.y + det.h + pad_h)
    return {"x": x, "y": y, "w": x2 - x, "h": y2 - y}


def _grow_box(box: dict, dist: int, span: int, grow_pct: float) -> dict:
    """Hold a box `dist` frames from its anchor, grown to reflect rising
    position uncertainty (grow_pct% at the far end, 0 at the anchor). Centred."""
    factor = (grow_pct / 100.0) * (dist / max(1, span))
    gw = box["w"] * factor
    gh = box["h"] * factor
    return {
        "x": box["x"] - gw / 2,
        "y": box["y"] - gh / 2,
        "w": box["w"] + gw,
        "h": box["h"] + gh,
    }


def _fill_redundancy(
    anchors: dict[int, list[dict]],
    start_frame: int,
    end_frame: int,
    window: int,
    lead_in: int,
    coast: int,
    grow: float,
) -> None:
    """detect_every==1 redundancy: keep ids alive across short detector dropouts.

    Three injections, all tagged source != 'tracked' so the audit/manual layer
    can tell them apart from real detections:
      * gap bridge — id present before AND after a hole <= `window` frames wide
                     gets the hole linearly interpolated (no unmasked frame
                     mid-track);
      * lead-in    — the first box of a track is held over the `lead_in` frames
                     before it appears (head covered just before lock-on);
      * tail coast — the last box is held over the `coast` frames after it
                     vanishes, before the track is allowed to die.
    Mutates `anchors` in place. Only ever writes into frames that already exist
    as anchors (every frame is an anchor when detect_every==1), so it never
    perturbs the anchor set _write_jsonl reasons about.
    """
    presence: dict[str, list[int]] = {}
    box_at: dict[tuple, dict] = {}
    for f in sorted(anchors):
        for m in anchors[f]:
            presence.setdefault(m["id"], []).append(f)
            box_at[(m["id"], f)] = m

    def present(f: int, mid: str) -> bool:
        return any(mm["id"] == mid for mm in anchors.get(f, []))

    for mid, frames in presence.items():
        frames.sort()
        # 1) interpolate interior holes up to `window` frames wide
        for a, b in zip(frames, frames[1:]):
            if 1 <= b - a - 1 <= window:
                pa, pb = box_at[(mid, a)], box_at[(mid, b)]
                for f in range(a + 1, b):
                    if present(f, mid):
                        continue
                    t = (f - a) / (b - a)
                    anchors.setdefault(f, []).append({
                        "id": mid,
                        "x": _lerp(pa["x"], pb["x"], t),
                        "y": _lerp(pa["y"], pb["y"], t),
                        "w": _lerp(pa["w"], pb["w"], t),
                        "h": _lerp(pa["h"], pb["h"], t),
                        "state": "active",
                        "source": "interpolated",
                    })
        # 2) lead-in before first appearance
        fp = frames[0]
        first = box_at[(mid, fp)]
        for f in range(max(start_frame, fp - lead_in), fp):
            if present(f, mid):
                continue
            anchors.setdefault(f, []).append({
                "id": mid, **_grow_box(first, fp - f, lead_in, grow),
                "state": "active", "source": "backward",
            })
        # 3) tail coast after last appearance
        lp = frames[-1]
        last = box_at[(mid, lp)]
        for f in range(lp + 1, min(end_frame, lp + coast + 1)):
            if present(f, mid):
                continue
            anchors.setdefault(f, []).append({
                "id": mid, **_grow_box(last, f - lp, coast, grow),
                "state": "active", "source": "backward",
            })


def run_tracking(
    video_path: str | Path,
    jsonl_path: str | Path,
    start_frame: int,
    end_frame: int,
    detect_every: int,
    model_path: str | Path,
    head_pad: float,
    backward: bool = True,
    backfill_grow: float = 0.0,
    iou_threshold: float = 0.3,
    conf_threshold: float = 0.4,
    assoc_window: int = 3,
    lead_frames: int = 3,
    ws_callback: Callable[[dict], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    """Run detection + simple IoU tracking, write JSONL one line per frame.

    Anchors are produced every `detect_every` frames. When `backward` is set,
    frames between two anchors carrying the same mask id are linearly
    interpolated. Returns the jsonl path.
    """
    detector = get_detector(str(model_path))
    # Bake any display rotation into the pixels (replacing the original without keeping
    # a backup) so detection, the player and the renderer all share one
    # upright orientation. No-op once the file is already rotation 0.
    normalize_rotation(video_path, keep_backup=False)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if end_frame <= 0 or end_frame > total:
        end_frame = total

    print(f"[FaceMasking] Tracking started: {Path(video_path).name} (frames {start_frame}..{end_frame}/{total}, step={detect_every})", flush=True)

    next_id = 1
    # anchors: frame -> list of mask dicts {id, x, y, w, h}
    anchors: dict[int, list[dict]] = {}
    # track registry for windowed association: id -> {box, last_frame}. Lets a
    # detection re-associate with a track seen a few frames back (not only the
    # immediately previous detection), so a single-frame detector dropout no
    # longer spawns a new id. Window is detect_every frames normally (identical
    # to prior behaviour) but widens to `assoc_window` frames when detect_every
    # == 1, where the previous-frame-only match was fragile.
    tracks: dict[str, dict] = {}
    window_frames = assoc_window if detect_every == 1 else detect_every

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_idx = start_frame
    cancelled = False
    step_pct = max(1, (end_frame - start_frame) // 20)
    while frame_idx < end_frame:
        if should_cancel is not None and should_cancel():
            cancelled = True
            break
        ok, frame = cap.read()
        if not ok:
            break

        if (frame_idx - start_frame) % detect_every == 0:
            dets = detector.detect(frame, conf_threshold=conf_threshold)
            det_boxes = [_apply_pad(d, head_pad, src_w, src_h) for d in dets]
            # candidate tracks still inside the association window
            cand = [
                (tid, t) for tid, t in tracks.items()
                if frame_idx - t["last_frame"] <= window_frames
            ]
            # greedy global match: rank every (detection, track) pair by IoU
            # (ties broken toward the more recent track) and assign best-first,
            # so one strong dropout doesn't steal a better match's track.
            pairs = []
            for di, box in enumerate(det_boxes):
                for tid, t in cand:
                    score = _iou(box, t["box"])
                    if score >= iou_threshold:
                        pairs.append((score, t["last_frame"], di, tid))
            pairs.sort(reverse=True)
            det_to_id: dict[int, str] = {}
            used_tracks: set[str] = set()
            for _score, _lf, di, tid in pairs:
                if di in det_to_id or tid in used_tracks:
                    continue
                det_to_id[di] = tid
                used_tracks.add(tid)
            masks: list[dict] = []
            for di, box in enumerate(det_boxes):
                tid = det_to_id.get(di)
                if tid is None:
                    tid = f"t_{next_id:03d}"
                    next_id += 1
                tracks[tid] = {"box": box, "last_frame": frame_idx}
                masks.append({"id": tid, **box})
            anchors[frame_idx] = masks

            # Terminal progress logging (every ~5% of frames or final frame)
            if (frame_idx - start_frame) % step_pct == 0 or frame_idx >= end_frame - 1:
                pct = int(100.0 * (frame_idx - start_frame + 1) / max(1, end_frame - start_frame))
                print(f"[FaceMasking] Tracking frame {frame_idx}/{end_frame} ({pct}%) | Active tracks: {len(tracks)} | Detections: {len(masks)}", flush=True)

            if ws_callback:
                ws_callback(
                    {
                        "type": "tracking_progress",
                        "frame": frame_idx,
                        "total": end_frame,
                        "detections": len(masks),
                    }
                )
        frame_idx += 1

    cap.release()

    if cancelled:
        print(f"[FaceMasking] Tracking CANCELLED for {Path(video_path).name} at frame {frame_idx}", flush=True)
        if ws_callback:
            ws_callback({"type": "tracking_cancelled"})
        return str(jsonl_path)

    # detect_every==1: the sparse-anchor backward fill in _write_jsonl is a no-op
    # (no inter-anchor gaps), so add the per-id redundancy here instead — bridge
    # short detector dropouts, plus a lead-in / tail coast around each track.
    if detect_every == 1:
        _fill_redundancy(
            anchors, start_frame, end_frame,
            window=assoc_window, lead_in=lead_frames, coast=lead_frames,
            grow=backfill_grow,
        )

    _write_jsonl(
        jsonl_path, anchors, start_frame, end_frame, detect_every, fps, backward,
        backfill_grow,
    )

    print(f"[FaceMasking] Tracking completed: {Path(video_path).name} -> {jsonl_path} ({len(anchors)} keyframes)", flush=True)

    if ws_callback:
        ws_callback(
            {
                "type": "tracking_done",
                "pass": 0,
                "jsonl_path": str(jsonl_path),
            }
        )
    return str(jsonl_path)


def _write_jsonl(
    jsonl_path: str | Path,
    anchors: dict[int, list[dict]],
    start_frame: int,
    end_frame: int,
    detect_every: int,
    fps: float,
    backward: bool,
    backfill_grow: float = 0.0,
) -> None:
    """Materialize anchors into a per-frame JSONL with backward interpolation."""
    anchor_frames = sorted(anchors.keys())
    Path(jsonl_path).parent.mkdir(parents=True, exist_ok=True)

    # Precompute dead keyframes: a tracked id present at anchor A but absent at
    # the next anchor B dies on frame A+1 (spec: anterior + 1 frame).
    dead_kf: dict[int, list[dict]] = {}
    for i, af in enumerate(anchor_frames[:-1]):
        nxt = anchor_frames[i + 1]
        cur = {m["id"]: m for m in anchors[af]}
        nxt_ids = {m["id"] for m in anchors[nxt]}
        for mid, m in cur.items():
            if mid not in nxt_ids:
                dead_kf.setdefault(min(af + 1, end_frame - 1), []).append(
                    {
                        "id": mid,
                        "x": m["x"],
                        "y": m["y"],
                        "w": m["w"],
                        "h": m["h"],
                        "state": "dead",
                        "source": "tracked",
                    }
                )

    def masks_for(frame: int) -> list[dict]:
        if frame in anchors:
            return [
                {**m, "state": "active", "source": "tracked"}
                for m in anchors[frame]
            ]
        if not backward:
            return []
        # find bounding anchors
        prev_a = max((f for f in anchor_frames if f < frame), default=None)
        next_a = min((f for f in anchor_frames if f > frame), default=None)
        if next_a is None:
            return []
        next_list = {m["id"]: m for m in anchors[next_a]}
        prev_list = {m["id"]: m for m in anchors[prev_a]} if prev_a is not None else {}
        span = next_a - prev_a if prev_a is not None else None
        # static backward fill cannot reach further than detect_every-1 frames
        # before the detection that produced it.
        backfill_floor = next_a - (detect_every - 1)
        out: list[dict] = []
        for mid, nm in next_list.items():
            if mid in prev_list:
                # id present in both anchors -> linear interpolation
                pm = prev_list[mid]
                t = (frame - prev_a) / span
                out.append(
                    {
                        "id": mid,
                        "x": _lerp(pm["x"], nm["x"], t),
                        "y": _lerp(pm["y"], nm["y"], t),
                        "w": _lerp(pm["w"], nm["w"], t),
                        "h": _lerp(pm["h"], nm["h"], t),
                        "state": "active",
                        "source": "interpolated",
                    }
                )
            elif frame >= backfill_floor:
                # id only at next anchor (fast motion broke IoU association):
                # hold the detected box over the preceding frames so the gap is
                # not left unmasked. Grow the box the further it sits from the
                # detection (position uncertainty rises), shrinking back to the
                # anchor size as it approaches it. Box stays centred.
                dist = next_a - frame  # 1 (next to anchor) .. detect_every-1
                denom = max(1, detect_every - 1)
                factor = (backfill_grow / 100.0) * (dist / denom)
                gw = nm["w"] * factor
                gh = nm["h"] * factor
                out.append(
                    {
                        "id": mid,
                        "x": nm["x"] - gw / 2,
                        "y": nm["y"] - gh / 2,
                        "w": nm["w"] + gw,
                        "h": nm["h"] + gh,
                        "state": "active",
                        "source": "backward",
                    }
                )
        return out

    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for frame in range(start_frame, end_frame):
            masks = masks_for(frame)
            if frame in dead_kf:
                masks = masks + dead_kf[frame]
            line = {
                "frame": frame,
                "ts": round(frame / fps, 3) if fps else 0.0,
                "masks": [
                    {
                        "id": m["id"],
                        "x": round(m["x"], 2),
                        "y": round(m["y"], 2),
                        "w": round(m["w"], 2),
                        "h": round(m["h"], 2),
                        "state": m["state"],
                        "source": m["source"],
                    }
                    for m in masks
                ],
            }
            fh.write(json.dumps(line) + "\n")
