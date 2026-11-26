"""Unit tests for the Masking Studio model registry (no server needed).

These check the contract the UI and the server rely on: the five documented
models are registered, the default is the bundled ONNX head, and model
resolution behaves (default when None, error when unknown).
"""

import pytest

pytestmark = pytest.mark.unit

EXPECTED_MODELS = {
    "yolov7_tiny_head_0.752_post_480x640.onnx",
    "mediapipe-face",
    "yolo11x-pose.pt",
    "yolo26m-pose.pt",
    "yolo11m.pt",
}
VALID_BACKENDS = {"onnx", "mediapipe", "ultralytics"}


def test_list_models_has_the_five_documented(masking_backend):
    _, detectors = masking_backend
    ids = {m["id"] for m in detectors.list_models()}
    missing = EXPECTED_MODELS - ids
    assert not missing, f"models missing from the registry: {missing}"


def test_each_model_entry_is_well_formed(masking_backend):
    _, detectors = masking_backend
    for m in detectors.list_models():
        assert m["id"], "model id must be non-empty"
        assert m["label"], f"{m['id']} must have a label"
        assert m["backend"] in VALID_BACKENDS, f"{m['id']}: bad backend {m['backend']}"
        assert isinstance(m["available"], bool), f"{m['id']}: available must be bool"


def test_default_model_is_the_bundled_onnx(masking_backend):
    config, detectors = masking_backend
    assert config.DEFAULT_MODEL == "yolov7_tiny_head_0.752_post_480x640.onnx"
    assert config.DEFAULT_MODEL in config.list_onnx_models()
    assert (
        config.MODELS_DIR / config.DEFAULT_MODEL
    ).exists(), "default weights file is missing"


def test_default_model_is_available(masking_backend):
    _, detectors = masking_backend
    default = next(
        m
        for m in detectors.list_models()
        if m["id"] == "yolov7_tiny_head_0.752_post_480x640.onnx"
    )
    assert default["available"] is True, "the default ONNX head must always be usable"


def test_validate_model_resolves_none_to_default(masking_backend):
    config, detectors = masking_backend
    assert detectors.validate_model(None) == config.DEFAULT_MODEL


def test_validate_model_rejects_unknown(masking_backend):
    _, detectors = masking_backend
    with pytest.raises(ValueError):
        detectors.validate_model("not-a-real-model.onnx")


def test_available_models_validate_cleanly(masking_backend):
    """Any model reported as available must resolve without raising."""
    _, detectors = masking_backend
    for m in detectors.list_models():
        if m["available"]:
            assert detectors.validate_model(m["id"]) == m["id"]
