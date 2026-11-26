# Tests

Unit and integration tests for the toolkit. Tests are grouped by pytest marker,
not by folder, so one `pytest` run covers every component.

| File | Marker | Component | What it checks |
|---|---|---|---|
| `test_masking_models.py` | `unit` | Face Masking Studio | Model registry: the five documented models are registered, each entry is well formed, the default is the bundled ONNX head and is always available, `validate_model` resolves `None` to the default and rejects unknown names. |
| `test_postprocessor_split.py` | `unit` | server-processing | `CsvUtils.split` turns one raw multi-sensor CSV into one clean `<Sensor>_<Position>.csv` each, with a sorted `VideoTimelapse` starting at 0, the `Sensor Name` column dropped and duplicates removed, and rejects filenames without an on-body position. |
| `test_session_integrity.py` | `data` | pipeline output | A processed session is complete: all pipeline stages done, the full sensor grid (3 sensors x >=5 devices), each CSV on the video timebase and time-ordered, a positive configured frequency, a rendered masked video, and >=3 annotator files. |
| `test_masking_api.py` | `integration` | Face Masking Studio | `/api/config` exposes the models and a usable default; every available model produces mask boxes on a clip (`slow`, needs a sample video). |
| `test_pipeline_flow.py` | `integration` | server flow | Opt-in end-to-end: a raw session dropped into the preprocessor input is processed into `data/<session>` with split sensors and `server_processed` set. |

## Run

```bash
pip install -r requirements-test.txt
# to run (not skip) the Masking Studio unit tests, also:
pip install -r face_masking_studio/backend/requirements.txt
pip install -r server-processing/postprocessor/requirements.txt

# offline (unit + data), against a processed session:
HIAAC_SESSION=/path/to/data/<session> pytest -m "not integration"

# everything, with the studio up and a short sample clip:
./face_masking_studio/run.sh
FMS_URL=http://127.0.0.1:8000 FMS_SAMPLE_VIDEO=/path/to/short.mp4 pytest
```

## Configuration (environment variables)

| Variable | Default | Used by |
|---|---|---|
| `HIAAC_REPO` | this repo (`tests/..`) | all |
| `HIAAC_SESSION` | bundled `tests/fixtures/mini_session` | `data` tests |
| `FMS_URL` | `http://127.0.0.1:8000` | integration |
| `FMS_SAMPLE_VIDEO` | bundled `tests/fixtures/sample_face.mp4` | `test_masking_api` slow test |
| `HIAAC_FLOW_TEST`, `HIAAC_RAW_SESSION`, `HIAAC_PRE_DIR`, `HIAAC_DATA_DIR` | unset | `test_pipeline_flow` |

Tests that cannot run (missing service, data or deps) skip with a reason rather
than fail, so a partial environment still gives a clean run. CI runs the offline
tests and the fast integration checks (`.github/workflows/tests.yml`); the slow
per-model masking test and the live flow test run locally.
