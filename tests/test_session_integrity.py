"""Data tests: a processed session on disk is complete and well-formed.

Run against the validation session (5 phones, 3 sensors, 3 annotators). They
assert the shape the paper and the tools expect, so a broken postprocessing or
export shows up as a failing structural check rather than a silent bad file.
No services are needed.
"""

import json

import pandas as pd
import pytest

pytestmark = pytest.mark.data

EXPECTED_SENSORS = {"Accelerometer", "LinearAccelerometer", "Gyroscope"}
MIN_DEVICES = 5
MIN_ANNOTATORS = 3


@pytest.fixture(scope="module")
def manifest(session_dir):
    path = session_dir / "session_manifest.json"
    assert path.exists(), "session_manifest.json is missing"
    with open(path) as f:
        return json.load(f)


def _sensor_files(session_dir):
    return sorted((session_dir / "sensors").glob("*.csv"))


def _split_name(path):
    """<Sensor>_<Device>.csv -> ('Sensor', 'Device'); device may contain spaces."""
    stem = path.stem
    sensor, _, device = stem.partition("_")
    return sensor, device


def test_pipeline_status_complete(manifest):
    status = manifest.get("pipeline_status", {})
    for stage in ("server_processed", "face_masked", "annotated"):
        assert status.get(stage) is True, f"pipeline stage not done: {stage}"


def test_sensor_grid_is_complete(session_dir):
    files = _sensor_files(session_dir)
    assert files, "no sensor CSVs found"
    sensors, devices = set(), set()
    for f in files:
        s, d = _split_name(f)
        sensors.add(s)
        devices.add(d)

    assert EXPECTED_SENSORS <= sensors, f"missing sensors: {EXPECTED_SENSORS - sensors}"
    assert (
        len(devices) >= MIN_DEVICES
    ), f"expected >= {MIN_DEVICES} devices, got {sorted(devices)}"

    # Every sensor present for every device (no gaps in the grid).
    present = {(_split_name(f)) for f in files}
    for s in EXPECTED_SENSORS:
        for d in devices:
            assert (s, d) in present, f"missing {s} for device {d}"


# VideoTimelapse is in milliseconds on the shared video timebase. With video
# sync, each device starts at its own small offset from the video start (a few
# ms), not exactly 0, so the invariant is: non-negative, a small start offset,
# and time-ordered.
MAX_START_OFFSET_MS = 1000


@pytest.mark.parametrize("sensor", sorted(EXPECTED_SENSORS))
def test_sensor_csv_timebase(session_dir, sensor):
    """Each sensor CSV sits on the video timebase and is time-ordered."""
    files = [f for f in _sensor_files(session_dir) if _split_name(f)[0] == sensor]
    assert files, f"no files for sensor {sensor}"
    for f in files:
        df = pd.read_csv(f)
        assert "VideoTimelapse" in df.columns, f"{f.name}: no VideoTimelapse"
        assert "Sensor Frequency (Hz)" in df.columns, f"{f.name}: no frequency column"
        assert len(df) > 0, f"{f.name}: empty"
        first = df["VideoTimelapse"].iloc[0]
        assert (
            0 <= first < MAX_START_OFFSET_MS
        ), f"{f.name}: start offset {first} ms outside [0, {MAX_START_OFFSET_MS})"
        assert df[
            "VideoTimelapse"
        ].is_monotonic_increasing, f"{f.name}: not time-ordered"


def test_configured_frequency_is_recorded(session_dir):
    """At least one sensor file reports a positive configured frequency."""
    f = _sensor_files(session_dir)[0]
    df = pd.read_csv(f)
    freq = df["Sensor Frequency (Hz)"].iloc[0]
    assert float(freq) > 0, f"{f.name}: non-positive configured frequency {freq}"


def test_masked_video_present(session_dir):
    videos = session_dir / "videos"
    assert videos.exists(), "videos folder missing"
    masked = list(videos.glob("*_masked_*.mp4"))
    assert masked, "no masked video rendered for the session"


def test_annotations_present(session_dir):
    ann = session_dir / "annotations"
    assert ann.exists(), "annotations folder missing"
    files = list(ann.glob("*_Ann_*.csv"))
    assert (
        len(files) >= MIN_ANNOTATORS
    ), f"expected >= {MIN_ANNOTATORS} annotation files, got {[f.name for f in files]}"
    for f in files:
        df = pd.read_csv(f)
        assert len(df) > 0, f"{f.name}: empty annotation file"
