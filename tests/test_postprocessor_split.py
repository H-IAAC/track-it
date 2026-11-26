"""Unit test for the postprocessor sensor split (CsvUtils.split).

The server receives one raw CSV per device holding several sensors mixed
together. split() must break it into one clean CSV per sensor, named
<Sensor>_<Position>.csv, with a VideoTimelapse column that starts at zero and
is sorted ascending. This is the step that produces the data/<session>/sensors
files the other tools read.
"""

import pandas as pd
import pytest

pytestmark = pytest.mark.unit

RAW_COLUMNS = [
    "Experiment Name",
    "Sensor Name",
    "Power Consumption (mAh)",
    "Sensor Frequency (Hz)",
    "Timestamp Server",
    "Timestamp Local",
    "Value 1",
    "Value 2",
    "Value 3",
    "Data Status",
]


def _write_raw(path):
    """A raw device CSV (semicolon separated) with two sensors, out of order."""
    rows = [
        # name, ts_server, ts_local, v1, v2, v3
        ("Accelerometer", 1000, 500, 0.1, 0.2, 9.8),
        ("Gyroscope", 1005, 505, 0.0, 0.0, 0.0),
        ("Accelerometer", 1010, 510, 0.3, 0.1, 9.7),  # later in time
        ("Accelerometer", 1000, 500, 0.1, 0.2, 9.8),  # exact duplicate -> dropped
        ("Gyroscope", 1015, 515, 0.1, 0.0, 0.0),
    ]
    with open(path, "w") as f:
        f.write(";".join(RAW_COLUMNS) + "\n")
        for name, tss, tsl, v1, v2, v3 in rows:
            f.write(f"exp;{name};0.2;100;{tss};{tsl};{v1};{v2};{v3};VALID\n")


def test_split_produces_one_clean_file_per_sensor(postprocessor, tmp_path):
    # Filename must carry the on-body position as the 3rd-from-last _ token.
    # The app names files [subject]_[exp]_[activity]_[device]__[timestamp].csv,
    # and the empty token from the double underscore puts the device at [-3].
    raw = tmp_path / "subject_exp_walking_Backpack__1700000000.csv"
    _write_raw(raw)
    dest = str(tmp_path) + "/"

    created = postprocessor.split(str(raw), dest, video_start_time=None)

    assert created, "split returned no files"
    names = sorted(p.rsplit("/", 1)[-1] for p in created)
    assert names == ["Accelerometer_Backpack.csv", "Gyroscope_Backpack.csv"]

    acc = pd.read_csv(created[0] if "Acceler" in created[0] else created[1])
    # VideoTimelapse exists, starts at zero, is sorted ascending
    assert "VideoTimelapse" in acc.columns
    assert acc["VideoTimelapse"].iloc[0] == 0
    assert acc["VideoTimelapse"].is_monotonic_increasing
    # The 'Sensor Name' column is dropped from the per-sensor file
    assert "Sensor Name" not in acc.columns
    # The exact duplicate accelerometer row was removed (2 unique accel rows)
    assert len(acc) == 2


def test_split_rejects_filename_without_position(postprocessor, tmp_path):
    raw = tmp_path / "noposition.csv"
    _write_raw(raw)
    # stem "noposition" has no '_' tokens -> split('_')[-3] raises IndexError,
    # which split() catches and turns into a False return.
    result = postprocessor.split(str(raw), str(tmp_path) + "/", video_start_time=None)
    assert result is False
