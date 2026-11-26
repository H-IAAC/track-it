# validation / face_anonymization

Reproduces the masking accuracy results reported in the paper. Includes the four stage pipeline analysis (automatic tracking, two auditing rounds, and final validation) over the annotated videos, and the qualitative and quantitative comparison of detection models.

## Contents

| File | What |
|------|------|
| `analysis_lib.py` | Discovery, CSV loading, mask rasterization, IoU/precision/coverage, summary table |
| `model_comparison.ipynb` | Model comparison: summary table, accuracy, speed vs coverage, per-frame timelines |
| `04_stage_analysis_v3.ipynb` | Four-stage analysis: automatic, annotator 1, annotator 2, and final validation |
| `qualitative_compare.py` | Side-by-side frame grids at chosen timestamps |

```bash
pip install -r requirements.txt     # Python 3.12 or newer
```

The videos are not versioned. Set `DATA_ROOT` in `analysis_lib.py` to the local folder with the runs.

## Model masking comparison

Quantitative + qualitative comparison of every masked-video run against the
**manually annotated label** (privacy ground truth = 100%).

Each run is a `<name>.mp4` + `<name>_frames.csv` pair under `DATA_ROOT`
(env `HIAAC_MASKING_DATA`, default `data/mascaramento`), one folder per source:
`video_label/` (the label), `videos_yolopose/`, `video_yolonotrack_mediapipe/`,
`video_yolov7tiny/`, `video_mediapipe/`, … Runs are auto-discovered.

### Run

```bash
jupyter nbconvert --to notebook --execute --inplace model_comparison.ipynb
python analysis_lib.py              # summary table only
```

## Metrics

- **`masks_vs_label_%` (primary)** — total masks drawn / label's total masks.
  Measures how many faces are caught regardless of mask size, so small-box
  detectors (yolov7-tiny head) score well. Label = 100%.
- **count_MAE** — mean absolute difference in number of masks per frame vs label.
- **Absolute** — `avg_masks/frame`, `total_masks`, `avg_ms/frame`, `fps`.
- **Secondary (pixel)** — `coverage_%` (recall of label-masked pixels), `IoU`,
  `precision_%`. Kept in the detailed table only.

Bboxes are normalised to relative `[0,1]` per video before rasterising, so
different resolutions compare fairly.

### Folders / framing

All runs are letterboxed **portrait 480×720**. The `detect`/`mediapipe` runs
were re-exported with the studio `normalize` step into
`video_yolonotrack_mediapipe_portrait/` (use `shoulder_anonymize.py --normalize`).
The old landscape folder `video_yolonotrack_mediapipe/` is excluded by default
(notebook `FOLDERS`, CLI `--exclude`).

## Qualitative images

```bash
python qualitative_compare.py --times 1,3,5,7 --out qualitative/ --grid
```

Writes `compare_t<s>.png` per timestamp (label first, then each model) and,
with `--grid`, a combined `grid_all_times.png`. The black letterbox padding
around each frame is cropped automatically (`--no-crop` to keep it); the old
landscape folder is skipped via `--exclude` (default
`video_yolonotrack_mediapipe`).