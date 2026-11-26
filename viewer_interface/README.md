# Track-It Viewer (Viewer Interface)

Dash web tool to inspect a collection: the sensor signals, the video synchronized with the plot, and the annotations of one or more annotators.

## Setup and run

You need Python 3.12 or newer.

```bash
pip install -r requirements.txt     # or use the root .venv (requirements_cpu.txt)
python visualize_dataset.py         # http://127.0.0.1:8052
```

## Modes

- **Standalone:** load a sensor CSV and a video by hand. The CSV needs a `timestamp` column (and `label` to show annotations).
- **Dataset Flow:** pick a session from `../data/`. The viewer reads `session_manifest.json` and loads:
  - the clean sensors (`sensors/`);
  - the masked video (or the original if there is none);
  - the annotation files of each annotator (`annotations/*_Ann_*.csv`).
  - *Dynamic Ingestion:* The session dropdown automatically polls `data/` every 5 seconds (with a manual ↻ refresh button) so newly processed sessions appear without restarting the viewer.

## Usage

- Pick the sensor and device to plot. The marker on the plot follows the video, and dragging the marker or clicking the plot seeks the video.
- Pick one or more annotators to compare their intervals, shown as colored bands over the signal.
- **Consolidation:** with two or more annotators selected, pick Union (instants labeled by at least one annotator, without conflicting labels), Intersection (same label from every annotator) or Majority (label from more than half). Click or hover over the **`?`** helper icon next to the dropdown to inspect the mathematical consensus criteria. The result is drawn as an extra row, and **Export CSV** saves it as `annotations/<session>_Ann_<mode>.csv` in the Labeler format (`timestamp, left_label, change_point_name, change_point_time, sensor_ref`; uncovered intervals end with `-1`), so it can be opened in the Annotation Interface.
- The light/dark toggle in the header uses the shared H.IAAC theme.
