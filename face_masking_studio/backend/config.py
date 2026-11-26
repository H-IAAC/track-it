"""Central configuration: paths, default model, device detection."""
from __future__ import annotations

from pathlib import Path

import onnxruntime as ort

# Load the CUDA/cuDNN shared libs that ship as nvidia-*-cu12 pip wheels
# (see backend/requirements.txt). On onnxruntime >=1.21 this makes the
# CUDAExecutionProvider available without any system-wide CUDA install.
# No-op / harmless on CPU-only setups or older onnxruntime.
if hasattr(ort, "preload_dlls"):
    try:
        ort.preload_dlls()
    except Exception:  # pragma: no cover - best effort, falls back to CPU
        pass

# --- Paths -----------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
MODELS_DIR = BACKEND_DIR / "models"
DATASET_DIR = PROJECT_ROOT.parent / "data"

# Video base folder (configurable at runtime via /api/config)
VIDEOS_DIR = PROJECT_ROOT / "videos"
RAW_DIR = VIDEOS_DIR / "raw"
MASKS_DIR = VIDEOS_DIR / "masks_data"
TMP_DIR = VIDEOS_DIR / "tmp"
OUTPUT_DIR = VIDEOS_DIR / "output"

DEFAULT_MODEL = "yolov7_tiny_head_0.752_post_480x640.onnx"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def ensure_dirs() -> None:
    """Create the working directories if they do not exist."""
    for directory in (RAW_DIR, MASKS_DIR, TMP_DIR, OUTPUT_DIR, MODELS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def list_onnx_models() -> list[str]:
    """Return ONNX model filenames in the models directory."""
    if not MODELS_DIR.exists():
        return []
    return sorted(p.name for p in MODELS_DIR.glob("*.onnx"))


def detect_device() -> str:
    """Return 'GPU' if a CUDA execution provider is available, else 'CPU'."""
    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" in providers:
        return "GPU"
    return "CPU"


def onnx_providers() -> list[str]:
    """Preferred onnxruntime providers (CUDA first when present)."""
    available = ort.get_available_providers()
    preferred = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return [p for p in preferred if p in available] or ["CPUExecutionProvider"]
