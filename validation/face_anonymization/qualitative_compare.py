"""
qualitative_compare.py
──────────────────────
Build side-by-side qualitative comparison images of every model's masked video
at one or more timestamps. For each requested time it grabs the matching frame
from each run's .mp4, labels it with the model name, and stacks them in a row.
Optionally combines all timestamps into a single grid (rows = times).

Usage
-----
    python qualitative_compare.py --times 1,3,5,7
    python qualitative_compare.py --times 2.5 --out frames_cmp/ --grid
    python qualitative_compare.py --data-root /path/to/mascaramento --times 0,1,2,3

Output (default ./qualitative/):
    compare_t<seconds>.png   one row per timestamp (all models)
    grid_all_times.png       single grid (only with --grid)
"""

import argparse
import glob
import os

import cv2
import numpy as np

import analysis_lib as al

TITLE_H   = 34
PAD       = 6
ROW_H     = 480   # each frame resized to this height (aspect preserved)
FONT      = cv2.FONT_HERSHEY_SIMPLEX
BG        = (28, 28, 28)


def grab_frame(video: str, t_s: float, fps: float):
    """Return the BGR frame nearest to t_s seconds, or None."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        return None
    f = int(round(t_s * (fps or cap.get(cv2.CAP_PROP_FPS) or 24)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, f))
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def crop_letterbox(frame: np.ndarray, thr: int = 12, pad: int = 4) -> np.ndarray:
    """Remove the pure-black letterbox/pillarbox padding around the real image,
    keeping a few px of padding. Rows/cols whose brightest pixel stays under
    `thr` (i.e. solid black bars) are trimmed; interior black masks are kept
    because the image content on their sides keeps those rows/cols bright."""
    if frame is None or frame.size == 0:
        return frame
    g = frame.max(axis=2)
    rows = np.where(g.max(axis=1) > thr)[0]
    cols = np.where(g.max(axis=0) > thr)[0]
    if rows.size == 0 or cols.size == 0:
        return frame
    h, w = frame.shape[:2]
    y1, y2 = max(0, rows[0] - pad), min(h, rows[-1] + 1 + pad)
    x1, x2 = max(0, cols[0] - pad), min(w, cols[-1] + 1 + pad)
    return frame[y1:y2, x1:x2]


def labelled_tile(frame: np.ndarray, title: str, height: int = ROW_H,
                  crop: bool = True) -> np.ndarray:
    """Resize frame to `height` (keep aspect) and add a title bar on top.
    With `crop`, trims the black letterbox so only the real image shows."""
    if crop:
        frame = crop_letterbox(frame)
    h, w = frame.shape[:2]
    new_w = max(1, int(round(w * height / h)))
    tile  = cv2.resize(frame, (new_w, height))
    bar   = np.full((TITLE_H, new_w, 3), BG, np.uint8)
    cv2.putText(bar, title[:42], (8, TITLE_H - 11), FONT, 0.6,
                (245, 245, 245), 1, cv2.LINE_AA)
    return np.vstack([bar, tile])


def _pad_to_height(tile: np.ndarray, h: int) -> np.ndarray:
    if tile.shape[0] == h:
        return tile
    pad = np.full((h - tile.shape[0], tile.shape[1], 3), BG, np.uint8)
    return np.vstack([tile, pad])


def hstack_pad(tiles: list[np.ndarray]) -> np.ndarray:
    """Horizontally stack tiles of possibly different heights/widths."""
    h = max(t.shape[0] for t in tiles)
    tiles = [_pad_to_height(t, h) for t in tiles]
    sep   = np.full((h, PAD, 3), (90, 90, 90), np.uint8)
    out   = tiles[0]
    for t in tiles[1:]:
        out = np.hstack([out, sep, t])
    return out


def vstack_pad(rows: list[np.ndarray]) -> np.ndarray:
    w = max(r.shape[1] for r in rows)
    padded = []
    for r in rows:
        if r.shape[1] < w:
            r = np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), BG, np.uint8)])
        padded.append(r)
    sep = np.full((PAD, w, 3), (90, 90, 90), np.uint8)
    out = padded[0]
    for r in padded[1:]:
        out = np.vstack([out, sep, r])
    return out


def ordered_runs(runs: dict) -> list:
    """Label first, then the rest alphabetically."""
    items = list(runs.values())
    items.sort(key=lambda r: (not r.is_label, r.name))
    return [r for r in items if r.video]


def accuracy_by_run(runs: dict) -> dict:
    """Lightweight accuracy = masks drawn vs the label's total mask count (%).
    No rasterisation, just per-frame box counts."""
    totals = {}
    for name, r in runs.items():
        try:
            totals[name] = int(al.load_run(r)["n_boxes"].sum())
        except Exception:
            totals[name] = 0
    label_total = next((t for n, t in totals.items() if runs[n].is_label), 0) or 1
    return {n: 100.0 * t / label_total for n, t in totals.items()}


def ranked_runs(runs: dict, best_first: bool = True) -> list:
    """[(run, accuracy%)] ordered by accuracy, label always first."""
    acc = accuracy_by_run(runs)
    items = [(r, acc.get(r.name, float("nan"))) for r in runs.values() if r.video]
    sign = -1 if best_first else 1
    items.sort(key=lambda ra: (not ra[0].is_label,
                               sign * (ra[1] if ra[1] == ra[1] else -1e9)))
    return items


def tile_title(run, acc: float) -> str:
    """Top-of-tile caption: model name + accuracy."""
    short = run.name.split("/")[-1]
    pct = f"{acc:.0f}%" if acc == acc else "?"
    return ("LABEL " if run.is_label else "") + f"{short}  ({pct})"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=al.DATA_ROOT)
    ap.add_argument("--times", required=True,
                    help="Comma-separated timestamps in seconds, e.g. 1,3,5.5")
    ap.add_argument("--out", default="qualitative")
    ap.add_argument("--height", type=int, default=ROW_H)
    ap.add_argument("--exclude", default="video_yolonotrack_mediapipe",
                    help="Comma-separated folder names to skip "
                         "(default: the old landscape detect/mediapipe folder).")
    ap.add_argument("--no-crop", action="store_true",
                    help="Keep the black letterbox padding (default: crop it).")
    ap.add_argument("--worst-first", action="store_true",
                    help="Order tiles worst→best (default: best→worst).")
    ap.add_argument("--grid", action="store_true",
                    help="Also write a single grid image (rows = timestamps).")
    args = ap.parse_args()

    times = [float(t) for t in args.times.split(",") if t.strip()]
    os.makedirs(args.out, exist_ok=True)

    excl = {x.strip() for x in args.exclude.split(",") if x.strip()}
    folders = sorted(
        d for d in glob.glob(os.path.join(args.data_root, "*"))
        if os.path.isdir(d) and "video" in os.path.basename(d).lower()
        and os.path.basename(d) not in excl
    )
    runs = ranked_runs(al.discover_runs(args.data_root, folders=folders),
                       best_first=not args.worst_first)
    if not runs:
        raise SystemExit(f"No runs with videos found under {args.data_root}")
    print("Models (best→worst): "
          + ", ".join(f"{r.name.split('/')[-1]} {a:.0f}%" for r, a in runs))

    grid_rows = []
    for t in times:
        tiles = []
        for r, acc in runs:
            frame = grab_frame(r.video, t, r.fps)
            if frame is None:
                frame = np.full((args.height, args.height, 3), (40, 40, 40), np.uint8)
            tiles.append(labelled_tile(frame, tile_title(r, acc), args.height,
                                       crop=not args.no_crop))
        row = hstack_pad(tiles)
        out_path = os.path.join(args.out, f"compare_t{t:g}.png")
        cv2.imwrite(out_path, row)
        print(f"  wrote {out_path}  ({row.shape[1]}x{row.shape[0]})")
        grid_rows.append(row)

    if args.grid and grid_rows:
        grid = vstack_pad(grid_rows)
        gpath = os.path.join(args.out, "grid_all_times.png")
        cv2.imwrite(gpath, grid)
        print(f"  wrote {gpath}  ({grid.shape[1]}x{grid.shape[0]})")


if __name__ == "__main__":
    main()
