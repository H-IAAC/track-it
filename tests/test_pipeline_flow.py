"""End-to-end flow test: a raw session dropped into the preprocessor input is
picked up by the postprocessor and written to data/<session> with the sensors
split and the manifest marked server_processed.

This mutates a live watched folder, so it is opt-in. Set all of:

    HIAAC_FLOW_TEST=1          enable the test
    HIAAC_RAW_SESSION=<path>   a raw, unprocessed session folder to inject
    HIAAC_PRE_DIR=<path>       preprocessor input (…/preprocessor/_preprocessor)
    HIAAC_DATA_DIR=<path>      postprocessor output (…/data)

The postprocessor only reacts to new folders, so the test copies under a fresh
name each run and cleans it up afterwards.
"""

import json
import os
import shutil
import time
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]


@pytest.fixture
def flow_env(repo_root):
    if os.environ.get("HIAAC_FLOW_TEST") != "1":
        pytest.skip("set HIAAC_FLOW_TEST=1 to run the live flow test")
    # Default to the bundled simulated raw session (no real data, no video).
    raw = os.environ.get("HIAAC_RAW_SESSION") or str(
        repo_root / "tests" / "fixtures" / "raw_session"
    )
    if not Path(raw).exists():
        pytest.skip(f"raw session not found: {raw}")
    pre = Path(
        os.environ.get(
            "HIAAC_PRE_DIR",
            repo_root / "server-processing" / "preprocessor" / "_preprocessor",
        )
    )
    data = Path(os.environ.get("HIAAC_DATA_DIR", repo_root / "data"))
    if not pre.exists():
        pytest.skip(f"preprocessor input not found: {pre}")
    return Path(raw), pre, data


def test_raw_session_flows_to_data(flow_env):
    raw_session, pre_dir, data_dir = flow_env
    name = f"flowtest_{uuid.uuid4().hex[:8]}"
    injected = pre_dir / name
    # Drop the sensor CSVs and manifest first; the postprocessor parks a
    # video-less CSV in a waiting area and only splits it once a .no_video flag
    # arrives. Create that flag last so the CSVs are already on disk.
    shutil.copytree(raw_session, injected)
    time.sleep(2)
    (injected / f"{name}.no_video").write_text("")
    try:
        out = data_dir / name
        deadline = time.time() + 300
        manifest = None
        while time.time() < deadline:
            mpath = out / "session_manifest.json"
            if mpath.exists():
                try:
                    manifest = json.loads(mpath.read_text())
                    if manifest.get("pipeline_status", {}).get("server_processed"):
                        break
                except json.JSONDecodeError:
                    pass  # still being written
            time.sleep(5)

        assert manifest is not None, f"postprocessor did not produce {out} in time"
        assert manifest["pipeline_status"]["server_processed"] is True
        sensors = list((out / "sensors").glob("*.csv"))
        assert sensors, "no split sensor files were written"
    finally:
        shutil.rmtree(injected, ignore_errors=True)
