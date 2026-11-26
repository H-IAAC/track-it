"""Shared fixtures for the Track-It test suite.

The suite lives in tests/ at the repo root. It imports the toolkit components
by adding their folders to sys.path (the components are apps, not installed
packages) and reads a processed session and a running service through
environment variables.

    HIAAC_REPO     toolkit root (defaults to this repo, tests/..)
    HIAAC_SESSION  a processed session folder (data/<session>) for the data tests
    FMS_URL        base URL of a running Face Masking Studio (integration only)
    FMS_SAMPLE_VIDEO  a short .mp4 to mask in the per-model integration test

Markers: unit, data, integration, needs_server, slow (see pytest.ini).
"""

import os
import sys
import urllib.request
from pathlib import Path

import pytest

REPO_FROM_HERE = Path(__file__).resolve().parents[1]
DEFAULT_FMS_URL = "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    root = Path(os.environ.get("HIAAC_REPO", REPO_FROM_HERE))
    if not (root / "face_masking_studio").exists():
        pytest.skip(f"toolkit not found at {root} (set HIAAC_REPO)")
    return root


@pytest.fixture(scope="session")
def session_dir() -> Path:
    # HIAAC_SESSION points at a real processed session; without it, fall back to
    # the tiny synthetic fixture so the data tests still run (e.g. in CI).
    env = os.environ.get("HIAAC_SESSION")
    sess = (
        Path(env) if env else (REPO_FROM_HERE / "tests" / "fixtures" / "mini_session")
    )
    if not sess.exists():
        pytest.skip(f"session not found: {sess} (set HIAAC_SESSION)")
    return sess


@pytest.fixture(scope="session")
def fms_url() -> str:
    return os.environ.get("FMS_URL", DEFAULT_FMS_URL).rstrip("/")


@pytest.fixture(scope="session")
def fms_up(fms_url: str) -> str:
    """Skip unless the Masking Studio answers /api/config."""
    try:
        with urllib.request.urlopen(f"{fms_url}/api/config", timeout=3) as r:
            if r.status != 200:
                pytest.skip(f"Masking Studio at {fms_url} returned {r.status}")
    except Exception as e:
        pytest.skip(f"Masking Studio not reachable at {fms_url} ({e})")
    return fms_url


@pytest.fixture(scope="session")
def masking_backend(repo_root: Path):
    """Import the Masking Studio backend modules, or skip if deps are missing."""
    backend = repo_root / "face_masking_studio" / "backend"
    if not backend.exists():
        pytest.skip(f"backend not found: {backend}")
    sys.path.insert(0, str(backend))
    try:
        import config
        import detectors
    except Exception as e:  # onnxruntime or another dep missing
        pytest.skip(f"cannot import masking backend ({e})")
    return config, detectors


@pytest.fixture(scope="session")
def postprocessor(repo_root: Path):
    """Import the postprocessor CsvUtils, or skip if it cannot load."""
    pp = repo_root / "server-processing" / "postprocessor"
    if not pp.exists():
        pytest.skip(f"postprocessor not found: {pp}")
    sys.path.insert(0, str(pp))
    try:
        import CsvUtils
    except Exception as e:
        pytest.skip(f"cannot import CsvUtils ({e})")
    return CsvUtils.CsvUtils
