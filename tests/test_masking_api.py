"""Integration tests against a running Face Masking Studio.

Start the studio first (./face_masking_studio/run.sh) and point FMS_URL at it
(default http://127.0.0.1:8000). The config contract test runs whenever the
server is up. The "every available model masks" test is the one from the plan:
it runs each usable model over a short clip and checks it produces mask boxes.
It needs a sample video and is marked slow.

    FMS_URL            base URL of the studio
    FMS_SAMPLE_VIDEO   path to a short .mp4 to upload and mask (optional)
"""

import os
import time
import urllib.parse
from pathlib import Path

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.needs_server]


def _q(video_id: str) -> str:
    return urllib.parse.quote(video_id, safe="/:")


def test_config_contract(fms_up):
    """/api/config exposes the model list, a default, and the default is usable."""
    cfg = requests.get(f"{fms_up}/api/config", timeout=5).json()
    assert "models" in cfg and cfg["models"], "config has no models"
    assert "default_model" in cfg, "config has no default_model"

    ids = {m["id"] for m in cfg["models"]}
    assert cfg["default_model"] in ids, "default_model is not in the model list"

    default = next(m for m in cfg["models"] if m["id"] == cfg["default_model"])
    assert default["available"] is True, "default model is reported unavailable"


def _pick_sample_video(base_url: str) -> str:
    """Return a raw video id to mask: an uploaded sample, or an existing one."""
    sample = os.environ.get("FMS_SAMPLE_VIDEO")
    if not sample:
        # Fall back to the bundled public sample clip (has a face, safe to
        # commit), so the masking test runs with no setup.
        fixture = Path(__file__).resolve().parent / "fixtures" / "sample_face.mp4"
        if fixture.exists():
            sample = str(fixture)
    if sample:
        p = Path(sample)
        if not p.exists():
            pytest.skip(f"FMS_SAMPLE_VIDEO not found: {p}")
        with open(p, "rb") as f:
            r = requests.post(
                f"{base_url}/api/upload",
                files={"file": (p.name, f, "video/mp4")},
                timeout=30,
            )
        r.raise_for_status()
        filename = r.json()["filename"]
        # The track/mask routes use the video id, which is the path under
        # RAW_DIR WITHOUT the extension, not the filename. Resolve it via the
        # listing so we never guess the id scheme.
        return _id_for_filename(base_url, filename)

    videos = requests.get(f"{base_url}/api/videos", timeout=5).json()
    for v in videos:
        vid = v.get("id") if isinstance(v, dict) else v
        if vid and not str(vid).startswith("dataset:"):
            return vid
    pytest.skip("no sample video available (set FMS_SAMPLE_VIDEO to a short .mp4)")


def _id_for_filename(base_url: str, filename: str) -> str:
    videos = requests.get(f"{base_url}/api/videos", timeout=5).json()
    for v in videos:
        if isinstance(v, dict) and v.get("filename") == filename:
            return v["id"]
    pytest.skip(f"uploaded {filename} but it did not appear in /api/videos")


def _cancel(base_url: str, video_id: str) -> None:
    try:
        requests.post(f"{base_url}/api/video/{_q(video_id)}/track/cancel", timeout=10)
    except Exception:
        pass


def _start_track(base_url: str, video_id: str, model: str, timeout: int = 60):
    """POST /track, retrying while a previous job is still registered (409)."""
    body = {"start_frame": 0, "end_frame": 20, "detect_every": 1, "model": model}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.post(
            f"{base_url}/api/video/{_q(video_id)}/track", json=body, timeout=30
        )
        if r.status_code == 409:
            time.sleep(3)
            continue
        return r
    pytest.fail(f"{model}: /track stayed 409 (busy) for {timeout}s")


def _wait_pass0(pass0: Path, timeout: int = 120) -> bool:
    """Wait until THIS model rewrites a non-empty pass-0 mask file."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pass0.exists() and pass0.stat().st_size > 0:
            return True
        time.sleep(2)
    return False


@pytest.mark.slow
def test_every_available_model_masks(fms_up, repo_root):
    """Each model the studio reports as available produces masks on a clip.

    The pass-0 mask file is deleted before each model and we wait for that model
    to rewrite it, so the check is per-model and never passes on stale output.
    """
    masks_dir = repo_root / "face_masking_studio" / "videos" / "masks_data"
    cfg = requests.get(f"{fms_up}/api/config", timeout=5).json()
    available = [m["id"] for m in cfg["models"] if m["available"]]
    assert available, "no models reported available"

    video_id = _pick_sample_video(fms_up)
    pass0 = masks_dir / f"{video_id.replace('/', '__')}_pass0.jsonl"

    results = {}
    for model in available:
        _cancel(fms_up, video_id)
        time.sleep(1)
        if pass0.exists():
            pass0.unlink()
        r = _start_track(fms_up, video_id, model)
        if r.status_code not in (200, 202):
            results[model] = f"track {r.status_code}"
            continue
        results[model] = "masked" if _wait_pass0(pass0) else "no masks"
        _cancel(fms_up, video_id)
        time.sleep(1)

    print("\nPer-model masking result:")
    for m, outcome in results.items():
        print(f"  {outcome:>10}  {m}")

    failed = {m: o for m, o in results.items() if o != "masked"}
    assert not failed, f"models that did not mask: {failed}"
