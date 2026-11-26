# Track-It Labeler (Annotation Interface)

Dash web tool to label activities on sensor signals synchronized with the video. It exports the annotations as CSV.

## Setup and run

You need Python 3.12 or newer.

```bash
pip install -r requirements.txt     # or use the root .venv (requirements_cpu.txt)
python main.py                      # http://127.0.0.1:8050
```

## Modes

- **Standalone:** load a sensor CSV and a video from your computer, then manage the annotation file at the bottom of the page:
  - **Create** starts a new annotation (or reopens one with the same name) in `annotation_interface/annotations/`;
  - **Upload** opens an annotation CSV from your computer (it must have `timestamp`, `left_label` and `change_point_name`); a copy is saved in `annotations/` and edits go to that copy;
  - **Download** saves the current annotation CSV to your computer.
- **Dataset Flow:** pick a session from `../data/`, select the desired sensor stream and body placement from the dropdown, and pick or create an annotator.
  - Automatically loads the session and clean sensor streams upon selection.
  - To create a new annotator, type its name in the search box and select `Create "<name>"`.
  - The tool loads the clean sensors (`sensors/`) and the masked video listed in `session_manifest.json`.
  - Saves to `data/<session>/annotations/<session>_Ann_<annotator>.csv`.
  - Updates `artifacts.annotation_files` and sets `pipeline_status.annotated = true`.
  - The session list refreshes every 5 s, so sessions that arrive while the tool is open show up without a restart.

## Dynamic Label Management (⚙ Gear Button)

Activity labels are fully dynamic and do not require code or configuration file edits:
- Click the **⚙** gear button in the top navigation header next to the theme toggle.
- Add new activity labels (e.g. `JUMPING`, `CYCLING`) or remove unwanted labels using the `✕` buttons.
- In **Dataset Flow** mode, changes are saved per-session into `data/<session>/session_manifest.json` and synchronized to `config.yaml`, surviving page reloads (F5) and service restarts.

## Annotation convention (ends-at)

Each change point marks the **end** of the activity with that name.

- To mark an activity, first add a `-1` point where it starts, then a point with the activity name (for example `WALKING`) where it ends, so that `t_WALKING > t_-1`.
- The interval between the two points gets the label `WALKING`.

The output has the columns `timestamp, left_label, change_point_name, change_point_time, sensor_ref`. The `validation/` analyses read this format.

## Configuration (`config.yaml`)

- `server.port` and `server.debug` (`debug: false` for daemon background execution).
- `data_schema.time_column` (default `VideoTimelapse`) and `time_conversion_factor` (ms to s = `1000`).
- `activities`: list of default predefined activity labels.
- Layout colors use the variables of the shared theme (`var(--paper)`, `var(--ink)`); see `../shared/hiaac-theme`.

## Credits and license

MIT (see `../LICENSE`). Based on the `Time-Series-Labeling-Tool` branch of [H-IAAC/viewer_tool_jupyter](https://github.com/H-IAAC/viewer_tool_jupyter) (commit `ed91011`), developed by H.IAAC and Instituto Eldorado ([Amparo Díaz Muñoz](https://github.com/amparomunoz), building on earlier versions by [Daniel Adam Miranda](https://github.com/DanielMirandaEldorado) and [Saulo A. Moraes](https://github.com/saulo-moraes)) and released here under MIT with their authorization. See `../THIRD_PARTY_NOTICES.md` for what changed.
