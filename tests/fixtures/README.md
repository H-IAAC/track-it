# Test fixtures

Small, committable assets so the suite runs without a real collection.

## `mini_session/`
A tiny synthetic processed session (3 sensors x 5 devices, 3 annotators, a
0.3 s gray masked video, a complete manifest). It is generated data, not a real
collection, and feeds `test_session_integrity.py` so the data tests run in CI.
The `data` tests use it automatically when `HIAAC_SESSION` is not set.

## `sample_face.mp4`
A 3 s, 320x480 clip trimmed from the public Pexels video id 855565 (the same
video used for the masking results in the paper). It contains a face, so the
masking models actually detect something, and the Pexels license allows free
use and redistribution, so it is safe to version here. `test_masking_api.py`
uses it by default when `FMS_SAMPLE_VIDEO` is not set.

Source: https://www.pexels.com/video/855565/ (Pexels License).

## `raw_session/`
A simulated raw collection in the app upload format (one `;`-separated CSV per
device, all sensors mixed, named `[subject]_[exp]_[activity]_[device]__[ts].csv`),
plus a minimal `session_manifest.json`. Fully synthetic: no real sensor values,
no video, no annotator names. It feeds the opt-in `test_pipeline_flow.py` so the
end-to-end flow can be exercised without a real collection. The real collection
on disk was deliberately not used: its raw video can show a face, and the
postprocessor splits by format, not content, so synthetic data verifies the
flow just as well.
