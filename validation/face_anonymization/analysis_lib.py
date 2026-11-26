"""
analysis_lib.py
───────────────
Compare the masking output of several models against a manually-annotated
ground-truth ("label") video, plus speed / volume stats.

Each model run is a pair of files produced by the studio backend or by
shoulder_anonymize.py:
    <name>.mp4            the masked video
    <name>_frames.csv     per-frame detections
The CSV must have at least: frame, process_time_ms, bboxes (JSON list of
[x1,y1,x2,y2] in that video's own pixel space).

Coordinate spaces differ between runs (e.g. 480x720 portrait letterbox vs
960x540 landscape), so every bbox is converted to RELATIVE [0,1] coordinates
using its own video's width/height, then rasterised onto a common canvas
before any pixel-level comparison. That keeps the metrics meaningful across
resolutions — but note that if two runs use a different *framing* (letterboxed
portrait vs raw landscape) the relative positions won't line up until both are
re-exported with the same normalisation. Count/speed metrics are unaffected.

The label video is the reference: its pixel-coverage is 100% by definition.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

import cv2
import numpy as np
import pandas as pd

# Location of the per-model output folders (env HIAAC_MASKING_DATA or override in the notebook).
DATA_ROOT = os.environ.get("HIAAC_MASKING_DATA", "data/mascaramento")


# ═════════════════════════════════════════════════════════════════════════════
# Discovery
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Run:
    name: str          # display name
    csv: str           # path to *_frames.csv (per-frame detections)
    video: str         # path to the matching .mp4 ('' if missing)
    is_label: bool     # True for the ground-truth manual annotation
    w: int = 0
    h: int = 0
    fps: float = 0.0
    nframes: int = 0
    # ── metadata from the *_passes.json manifest (empty if absent) ──────────
    model: str = ""    # model file/name that produced this run
    stage: str = ""    # pipeline stage / pass kind: track | manual | refine | ...
    wall_s: float = 0.0  # total processing wall-time for the last pass
    passes: list = None  # full list of pass dicts (for multi-pass histories)


def _pretty_name(folder: str, stem: str) -> str:
    """Human-friendly model name from folder + file stem."""
    s = stem
    s = s.replace("855565-hd_1920_1080_24fps", "").strip("_")
    s = s.replace("_tracked_", "").replace("tracked_", "")
    s = s.replace("_post_480x640", "").replace("_manual_blur", "")
    s = s.strip("_") or os.path.basename(folder)
    return f"{os.path.basename(folder)}/{s}" if s else os.path.basename(folder)


def load_passes(json_path: str) -> list:
    """Read a *_passes.json manifest → list of pass dicts (may be empty)."""
    try:
        with open(json_path) as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(d, dict):                 # tolerate {"passes": [...]} wrapping
        d = d.get("passes", [d])
    return d if isinstance(d, list) else []


def _resolve_run(folder: str, stem: str) -> Run | None:
    """Build a Run for `stem` in `folder`, pulling per-frame data from the CSV
    and metadata (model / stage / wall-time) from the passes JSON if present.

    Works whether the on-disk artefact is a *_frames.csv, a *_passes.json, or
    both — the two export formats the pipeline produces.
    """
    csv_path  = os.path.join(folder, stem + "_frames.csv")
    json_path = os.path.join(folder, stem + "_passes.json")
    video     = os.path.join(folder, stem + ".mp4")

    model = stage = ""
    wall_s = 0.0
    passes = []
    if os.path.exists(json_path):
        passes = load_passes(json_path)
        if passes:
            last = passes[-1]
            model  = last.get("model", "") or ""
            stage  = last.get("kind", "") or ""
            wall_s = float(last.get("wall_s", 0.0) or 0.0)
            # Prefer the LOCAL sibling artefacts (folders are often copies, so
            # the manifest's absolute paths may point elsewhere); fall back to
            # the manifest path only when the local file is missing.
            if not os.path.exists(csv_path) and last.get("output_csv"):
                csv_path = last["output_csv"]
            if not os.path.exists(video) and last.get("output_video"):
                video = last["output_video"]

    if not os.path.exists(csv_path):
        return None  # no per-frame detections → can't analyse this run

    # The reference is the manual *label* folder, or the final *validated* pass —
    # NOT an intermediate 'manual'/'refine' stage of the pipeline.
    is_label = ("label" in folder.lower()) or ("manual_blur" in stem.lower()) \
        or (stage.lower() in ("validated", "label"))
    run = Run(name=_pretty_name(folder, stem), csv=csv_path,
              video=video if os.path.exists(video) else "",
              is_label=is_label, model=model, stage=stage,
              wall_s=wall_s, passes=passes)
    if run.video:
        run.w, run.h, run.fps, run.nframes = read_video_size(run.video)
    return run


def discover_runs(data_root: str = DATA_ROOT, folders=None) -> dict[str, Run]:
    """Find every run under data_root's model folders. A run is identified by a
    *_frames.csv and/or a *_passes.json sharing the same stem; metadata (model,
    pipeline stage, wall-time) is taken from the JSON when available. A run is
    flagged as the label if its folder/name mentions 'label'/'manual' or its
    pass kind is manual/validated.

    Returns {name: Run}, with video size/fps filled in when the .mp4 exists.
    """
    if folders is None:
        folders = sorted(
            d for d in glob.glob(os.path.join(data_root, "*"))
            if os.path.isdir(d) and ("video" in os.path.basename(d).lower())
        )
    runs: dict[str, Run] = {}
    for folder in folders:
        # Union of stems from both export formats.
        stems = set()
        for p in glob.glob(os.path.join(folder, "*_frames.csv")):
            stems.add(os.path.basename(p)[: -len("_frames.csv")])
        for p in glob.glob(os.path.join(folder, "*_passes.json")):
            stems.add(os.path.basename(p)[: -len("_passes.json")])
        for stem in sorted(stems):
            run = _resolve_run(folder, stem)
            if run is not None:
                runs[run.name] = run
    return runs


def read_video_size(video: str) -> tuple[int, int, float, int]:
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        return 0, 0, 0.0, 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return w, h, fps, n


# ═════════════════════════════════════════════════════════════════════════════
# CSV loading
# ═════════════════════════════════════════════════════════════════════════════

def _parse_bboxes(cell) -> list:
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    if isinstance(cell, str):
        cell = cell.strip()
        if not cell:
            return []
        try:
            return json.loads(cell)
        except json.JSONDecodeError:
            return []
    return cell if isinstance(cell, list) else []


def load_run(run: Run) -> pd.DataFrame:
    """Load a run's CSV, parsing bboxes and coercing numeric columns."""
    return _load_frames_csv(run.csv)


def _load_frames_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["bboxes"] = df["bboxes"].apply(_parse_bboxes)
    df["n_boxes"] = df["bboxes"].apply(len)
    for col in ("process_time_ms", "persons_detected", "faces_masked"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_detections(path: str) -> pd.DataFrame:
    """Load per-frame detections from EITHER a *_frames.csv or a *_passes.json
    (the latter is followed to its referenced output_csv). Accepts both export
    formats the pipeline produces."""
    if path.endswith(".json"):
        passes = load_passes(path)
        csv_path = passes[-1].get("output_csv") if passes else None
        if not csv_path or not os.path.exists(csv_path):
            # fall back to the sibling <stem>_frames.csv
            csv_path = path[: -len("_passes.json")] + "_frames.csv"
        return _load_frames_csv(csv_path)
    return _load_frames_csv(path)


# ═════════════════════════════════════════════════════════════════════════════
# Mask rasterisation + pixel metrics
# ═════════════════════════════════════════════════════════════════════════════

def rasterize(bboxes: list, src_wh: tuple[int, int],
              canvas_wh: tuple[int, int]) -> np.ndarray:
    """Render bboxes (in src pixel space) as a filled boolean mask on a canvas,
    scaling via relative [0,1] coordinates so different resolutions line up."""
    cw, ch = canvas_wh
    mask = np.zeros((ch, cw), dtype=np.uint8)
    sw, sh = src_wh
    if sw <= 0 or sh <= 0:
        return mask.astype(bool)
    for b in bboxes:
        if len(b) < 4:
            continue
        x1, y1, x2, y2 = b[:4]
        rx1, ry1 = x1 / sw, y1 / sh
        rx2, ry2 = x2 / sw, y2 / sh
        X1, Y1 = int(round(rx1 * cw)), int(round(ry1 * ch))
        X2, Y2 = int(round(rx2 * cw)), int(round(ry2 * ch))
        X1, X2 = sorted((max(0, min(cw, X1)), max(0, min(cw, X2))))
        Y1, Y2 = sorted((max(0, min(ch, Y1)), max(0, min(ch, Y2))))
        if X2 > X1 and Y2 > Y1:
            mask[Y1:Y2, X1:X2] = 1
    return mask.astype(bool)


def mask_scores(pred: np.ndarray, gt: np.ndarray) -> dict:
    """IoU / precision / recall(coverage) between two boolean masks."""
    pred_a = int(pred.sum())
    gt_a   = int(gt.sum())
    inter  = int(np.logical_and(pred, gt).sum())
    union  = pred_a + gt_a - inter

    if gt_a == 0 and pred_a == 0:
        return dict(iou=1.0, precision=1.0, recall=1.0,
                    pred_area=0, gt_area=0, inter=0)
    iou       = inter / union if union else 0.0
    precision = inter / pred_a if pred_a else (1.0 if gt_a == 0 else 0.0)
    recall    = inter / gt_a if gt_a else (1.0 if pred_a == 0 else 0.0)
    return dict(iou=iou, precision=precision, recall=recall,
                pred_area=pred_a, gt_area=gt_a, inter=inter)


def per_frame_metrics(model_df: pd.DataFrame, model_wh: tuple[int, int],
                      label_df: pd.DataFrame, label_wh: tuple[int, int],
                      canvas_wh: tuple[int, int]) -> pd.DataFrame:
    """Frame-by-frame pixel comparison of a model against the label."""
    lab = label_df.set_index("frame")
    rows = []
    for _, mrow in model_df.iterrows():
        f = int(mrow["frame"])
        gt_boxes = lab.loc[f, "bboxes"] if f in lab.index else []
        pred = rasterize(mrow["bboxes"], model_wh, canvas_wh)
        gt   = rasterize(gt_boxes,       label_wh, canvas_wh)
        sc = mask_scores(pred, gt)
        sc["frame"]      = f
        sc["count_pred"] = len(mrow["bboxes"])
        sc["count_gt"]   = len(gt_boxes)
        sc["ms"]         = float(mrow.get("process_time_ms", np.nan))
        rows.append(sc)
    return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════════════════════
# Aggregation / summary table
# ═════════════════════════════════════════════════════════════════════════════

def aggregate(name: str, run: Run, per_frame: pd.DataFrame | None,
              model_df: pd.DataFrame) -> dict:
    """One summary row: accuracy vs label (where available) + absolute stats."""
    ms = pd.to_numeric(model_df.get("process_time_ms"), errors="coerce")
    n  = len(model_df)
    if ms.notna().any() and ms.mean():
        avg_ms, med_ms = round(ms.mean(), 2), round(ms.median(), 2)
        fps = round(1000.0 / ms.mean(), 2)
    elif run.wall_s and n:                       # fallback: total wall-time
        avg_ms, med_ms = round(1000.0 * run.wall_s / n, 2), np.nan
        fps = round(n / run.wall_s, 2)
    else:
        avg_ms = med_ms = fps = np.nan
    row = {
        "model":            name,
        "weights":          run.model or "?",
        "stage":            run.stage or "?",
        "is_label":         run.is_label,
        "resolution":       f"{run.w}x{run.h}" if run.w else "?",
        "frames":           n,
        "avg_masks/frame":  round(model_df["n_boxes"].mean(), 3),
        "total_masks":      int(model_df["n_boxes"].sum()),
        "avg_ms/frame":     avg_ms,
        "median_ms":        med_ms,
        "fps":              fps,
    }
    if per_frame is not None and len(per_frame):
        row.update({
            "IoU":            round(per_frame["iou"].mean(), 4),
            "coverage_%":     round(100 * per_frame["recall"].mean(), 2),   # privacy: GT pixels masked
            "precision_%":    round(100 * per_frame["precision"].mean(), 2),
            "count_MAE":      round((per_frame["count_pred"] - per_frame["count_gt"]).abs().mean(), 3),
            "mean_pred_px":   int(per_frame["pred_area"].mean()),
            "mean_gt_px":     int(per_frame["gt_area"].mean()),
            "total_pred_px":  int(per_frame["pred_area"].sum()),
        })
    else:
        row.update({"IoU": np.nan, "coverage_%": np.nan, "precision_%": np.nan,
                    "count_MAE": np.nan, "mean_pred_px": np.nan,
                    "mean_gt_px": np.nan, "total_pred_px": np.nan})
    return row


def build_summary(data_root: str = DATA_ROOT, canvas_wh: tuple[int, int] | None = None,
                  folders=None):
    """End-to-end: discover runs, compare each to the label, return
    (summary_df, per_frame_dict, runs, label_name).

    `folders` optionally restricts which model folders are scanned (e.g. to
    pick the portrait re-run instead of the old landscape one)."""
    runs = discover_runs(data_root, folders=folders)
    if not runs:
        raise RuntimeError(f"No *_frames.csv runs found under {data_root}")

    labels = [n for n, r in runs.items() if r.is_label]
    if not labels:
        raise RuntimeError("No label/manual run found (expected 'video_label' or 'manual').")
    label_name = labels[0]
    label_run  = runs[label_name]
    label_df   = load_run(label_run)
    label_wh   = (label_run.w, label_run.h)

    if canvas_wh is None:
        canvas_wh = label_wh if label_wh[0] else (480, 720)

    summary_rows, per_frame_dict = [], {}
    for name, run in runs.items():
        mdf = load_run(run)
        if run.is_label:
            pf = None   # label vs itself is trivially 100%; keep absolute stats only
        else:
            pf = per_frame_metrics(mdf, (run.w, run.h), label_df, label_wh, canvas_wh)
            per_frame_dict[name] = pf
        summary_rows.append(aggregate(name, run, pf, mdf))

    summary = pd.DataFrame(summary_rows)

    # Primary metric (per request): number of masks relative to the label total.
    # This rewards detecting the same *count* of faces regardless of mask size,
    # so small-box detectors (e.g. yolov7-tiny head) are not penalised the way
    # pixel-IoU penalises them.
    label_total = int(summary.loc[summary["is_label"], "total_masks"].iloc[0])
    summary["masks_vs_label_%"] = (100 * summary["total_masks"] / max(label_total, 1)).round(1)

    # label first, then closest mask count to the label on top
    summary["_dist"] = (summary["masks_vs_label_%"] - 100).abs()
    summary = summary.sort_values(
        ["is_label", "_dist"], ascending=[False, True]
    ).drop(columns="_dist").reset_index(drop=True)
    return summary, per_frame_dict, runs, label_name


def stage_table(summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a summary by pipeline stage — the structure for the per-stage
    validation table once the 40-video collection is processed.

    Each video produces several passes (track → manual → refine → validated),
    each tagged with its `stage` (read from *_passes.json). This groups every
    run by stage and reports total faces masked, average mask count per frame,
    coverage vs the validated reference (when computed), and throughput.

    Expected outcome: `masks_vs_label_%` rises from the automatic stage toward
    100% at the validated stage, quantifying each manual step.
    """
    g = summary.groupby("stage", dropna=False)
    out = g.agg(
        runs=("model", "count"),
        faces_masked=("total_masks", "sum"),
        avg_masks_per_frame=("avg_masks/frame", "mean"),
        masks_vs_label_pct=("masks_vs_label_%", "mean"),
        fps=("fps", "mean"),
    ).reset_index()
    return out.round(2)


if __name__ == "__main__":
    summ, _, _, label = build_summary()
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(f"Label (100% reference): {label}\n")
    cols = ["model", "weights", "stage", "resolution", "masks_vs_label_%",
            "total_masks", "avg_masks/frame", "avg_ms/frame", "fps"]
    print(summ[[c for c in cols if c in summ.columns]].to_string(index=False))
    if summ["stage"].nunique() > 1:
        print("\nBy pipeline stage:\n")
        print(stage_table(summ).to_string(index=False))
