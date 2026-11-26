#!/usr/bin/env python3
"""Import 'normalized' videos into raw/ and run sequential head tracking.

Walks a directory, copies every video whose filename contains "normalized"
into ``videos/raw`` renamed as ``{parent_folder}_{clean_name}.mp4``, then lets
you pick which of them to track. Selected videos are tracked one after another
(each finishes before the next starts), producing a pass-0 JSONL and marking
the session state TRACKED — same output the web UI would produce.

Usage (from backend/, with the project venv so onnxruntime is available):
    python batch_tracking.py <dir> [options]

Examples:
    python batch_tracking.py ~/legacy_sessions            # import + ask
    python batch_tracking.py ~/legacy_sessions --all      # import + track all
    python batch_tracking.py ~/legacy_sessions --import-only

Options:
    --all              track every imported video, no prompt
    --import-only      only copy to raw/, skip tracking
    --model NAME       model id: an ONNX file in backend/models, mediapipe-face,
                       yolo11x-pose.pt, yolo26m-pose.pt or yolo11m.pt (default: config default)
    --detect-every N   detection cadence (default 1)
    --head-pad P       box padding %% (default 20)
    --backfill-grow P  backward-fill growth %% (default 30)
    --force            overwrite an existing raw/ file instead of skipping
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import config
import session_manager
import detectors
import tracker

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def clean_name(stem: str) -> str:
    """Drop the 'normalized' marker from a filename stem and tidy separators."""
    s = re.sub(r"[_-]?normalized", "", stem, flags=re.IGNORECASE)
    s = re.sub(r"_{2,}", "_", s).strip("_- ")
    return s or stem


def import_videos(src_dir: Path, force: bool) -> list[str]:
    """Copy every *normalized* video under src_dir into raw/ as {parent}_{name}.

    Returns the list of imported video ids (raw stems)."""
    config.ensure_dirs()
    found = sorted(
        p for p in src_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and "normalized" in p.name.lower()
    )
    if not found:
        print(f"No video with 'normalized' in the name found in {src_dir}")
        return []

    imported: list[str] = []
    for vid in found:
        new_id = f"{vid.parent.name}_{clean_name(vid.stem)}"
        target = config.RAW_DIR / f"{new_id}.mp4"
        if target.exists() and not force:
            print(f"[skip ] already exists: raw/{target.name}")
        else:
            print(f"[copy ] {vid}  ->  raw/{target.name}")
            shutil.copy2(vid, target)
        if new_id not in imported:
            imported.append(new_id)
    return imported


def _parse_selection(s: str, n: int) -> list[int]:
    """Parse '1,3,5' / '2-4' / mixed into a sorted list of 1-based indices."""
    out: set[int] = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                for k in range(int(a), int(b) + 1):
                    if 1 <= k <= n:
                        out.add(k)
        elif part.isdigit():
            k = int(part)
            if 1 <= k <= n:
                out.add(k)
    return sorted(out)


def choose(videos: list[str], take_all: bool) -> list[str]:
    """Interactive selection of which imported videos to track."""
    if not videos:
        return []
    if take_all:
        return videos
    print("\nImported videos:")
    for i, v in enumerate(videos, 1):
        print(f"  {i:2d}. {v}   [{session_manager.get_state(v)}]")
    raw = input("\nSelect to track (e.g. 1,3,5 | 2-4 | all | q): ").strip().lower()
    if raw in ("", "q", "quit"):
        return []
    if raw == "all":
        return videos
    return [videos[i - 1] for i in _parse_selection(raw, len(videos))]


def track_one(
    video_id: str,
    model: str,
    detect_every: int,
    head_pad: float,
    backfill_grow: float,
) -> bool:
    """Run tracking for one raw video; write pass-0 JSONL and set TRACKED."""
    raw = config.RAW_DIR / f"{video_id}.mp4"
    if not raw.exists():
        print(f"[error] raw video not found: {raw}")
        return False

    out_jsonl = session_manager.jsonl_path(video_id, 0)
    progress = {"pct": -5}

    def cb(msg: dict) -> None:
        if msg.get("type") == "tracking_progress":
            f = msg.get("frame", 0)
            t = msg.get("total", 0) or 1
            pct = int(f * 100 / t)
            if pct >= progress["pct"] + 5:
                progress["pct"] = pct
                print(f"\r    {pct:3d}%  (f{f}/{t})", end="", flush=True)

    print(f"\n=== tracking: {video_id} ===")
    tracker.run_tracking(
        video_path=str(raw),
        jsonl_path=str(out_jsonl),
        start_frame=0,
        end_frame=0,
        detect_every=detect_every,
        model_path=model,
        head_pad=head_pad,
        backward=True,
        backfill_grow=backfill_grow,
        ws_callback=cb,
    )
    print()  # close the progress line
    session_manager.set_state(video_id, "TRACKED")
    print(f"    -> TRACKED · {out_jsonl.name}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Import normalized videos + sequential tracking")
    ap.add_argument("directory", help="directory containing 'normalized' videos (recursive search)")
    ap.add_argument("--model", default=None, help="model ID (see detectors.py)")
    ap.add_argument("--detect-every", type=int, default=1)
    ap.add_argument("--head-pad", type=float, default=20.0)
    ap.add_argument("--backfill-grow", type=float, default=30.0)
    ap.add_argument("--all", action="store_true", help="track all without prompting")
    ap.add_argument("--import-only", action="store_true", help="copy to raw/ only, skip tracking")
    ap.add_argument("--force", action="store_true", help="overwrite existing file in raw/")
    args = ap.parse_args()

    src = Path(args.directory).expanduser()
    if not src.is_dir():
        print(f"Error: not a directory: {src}")
        sys.exit(1)

    try:
        model = detectors.validate_model(args.model)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    imported = import_videos(src, force=args.force)
    print(f"\n{len(imported)} video(s) imported to raw/.")
    if args.import_only or not imported:
        return

    chosen = choose(imported, take_all=args.all)
    if not chosen:
        print("Nothing selected. Exiting.")
        return

    print(f"\nTracking {len(chosen)} video(s) sequentially...")
    ok = 0
    for v in chosen:
        try:
            if track_one(v, model, args.detect_every, args.head_pad, args.backfill_grow):
                ok += 1
        except KeyboardInterrupt:
            print("\n[interrupted] stopping batch.")
            break
        except Exception as exc:  # one bad video must not kill the batch
            print(f"\n[error] {v}: {exc}")
    print(f"\nDone: {ok}/{len(chosen)} tracked.")


if __name__ == "__main__":
    main()
