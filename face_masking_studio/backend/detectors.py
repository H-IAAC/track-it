"""Detector registry: every method returns mask boxes for one BGR frame.

All detectors expose ``detect(frame_bgr, conf_threshold) -> list[Detection]``
with boxes in original-frame pixels, so the tracker writes the same
``pass0.jsonl`` whatever the method.

| Model id                         | Backend     | Target    | Mask                         |
|----------------------------------|-------------|-----------|------------------------------|
| yolov7_tiny_head_*.onnx          | onnxruntime | head      | head box (default)           |
| mediapipe-face                   | MediaPipe   | face      | face box (frontal only)      |
| yolo11x-pose.pt / yolo26m-pose.pt| Ultralytics | pose      | person top -> shoulders      |
| yolo11m.pt                       | Ultralytics | person    | upper half of the person box |

MediaPipe and Ultralytics are optional (``requirements-extra.txt``); a method
whose package is missing is listed as unavailable.
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache

import numpy as np

import config
from onnx_detector import Detection, HeadDetector

MEDIAPIPE_FACE = "mediapipe-face"
ULTRALYTICS_MODELS = {
    "yolo11x-pose.pt": "pose",
    "yolo26m-pose.pt": "pose",
    "yolo11m.pt": "person",
}
BUILTIN_LABELS = {
    "yolov7_tiny_head_0.752_post_480x640.onnx": "YOLOv7-tiny head",
    MEDIAPIPE_FACE: "MediaPipe face",
    "yolo11x-pose.pt": "YOLO11x-pose (shoulders)",
    "yolo26m-pose.pt": "YOLO26m-pose (shoulders)",
    "yolo11m.pt": "YOLO11m person (upper half)",
}
SHOULDER_MARGIN_PX = 10
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def list_models() -> list[dict]:
    """All selectable methods, with availability (missing optional package)."""
    models = [
        {"id": name, "label": BUILTIN_LABELS.get(name, name.removesuffix(".onnx")),
         "backend": "onnx",
         "available": True}
        for name in config.list_onnx_models()
    ]
    models.append({"id": MEDIAPIPE_FACE, "label": BUILTIN_LABELS[MEDIAPIPE_FACE],
                   "backend": "mediapipe", "available": _has("mediapipe")})
    for name in ULTRALYTICS_MODELS:
        models.append({"id": name, "label": BUILTIN_LABELS[name],
                       "backend": "ultralytics", "available": _has("ultralytics")})
    return models


def validate_model(model: str | None) -> str:
    """Resolve a model id (None -> default); raise ValueError if unusable."""
    name = model or config.DEFAULT_MODEL
    info = next((m for m in list_models() if m["id"] == name), None)
    if info is None:
        raise ValueError(f"Model not found: {name}")
    if not info["available"]:
        raise ValueError(
            f"{name} needs the optional '{info['backend']}' package "
            "(pip install -r requirements-extra.txt)"
        )
    return name


def _to_det(x1: float, y1: float, x2: float, y2: float, score: float,
            w_max: int, h_max: int) -> Detection | None:
    x1, x2 = max(0.0, x1), min(float(w_max), x2)
    y1, y2 = max(0.0, y1), min(float(h_max), y2)
    if x2 - x1 <= 1 or y2 - y1 <= 1:
        return None
    return Detection(int(x1), int(y1), int(x2 - x1), int(y2 - y1), float(score))


class MediaPipeFaceDetector:
    """MediaPipe face detection (full-range model). Frontal faces only."""

    def __init__(self) -> None:
        import mediapipe as mp

        self._mp = mp
        self._detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.1
        )
        print("[mediapipe] face_detection (full range) on CPU")

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.4) -> list[Detection]:
        import cv2

        h, w = frame_bgr.shape[:2]
        res = self._detector.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        dets: list[Detection] = []
        for d in res.detections or []:
            score = d.score[0] if d.score else 0.0
            if score < conf_threshold:
                continue
            bb = d.location_data.relative_bounding_box
            det = _to_det(bb.xmin * w, bb.ymin * h, (bb.xmin + bb.width) * w,
                          (bb.ymin + bb.height) * h, score, w, h)
            if det:
                dets.append(det)
        return dets


class UltralyticsDetector:
    """Ultralytics pose/person models. Weights download on first use."""

    def __init__(self, name: str) -> None:
        from ultralytics import YOLO

        self.kind = ULTRALYTICS_MODELS[name]
        config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(config.MODELS_DIR / name))
        import torch

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[ultralytics] {name} ({self.kind}) on {self.device}")

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.4) -> list[Detection]:
        h, w = frame_bgr.shape[:2]
        kwargs = {"conf": conf_threshold, "device": self.device, "verbose": False}
        if self.kind == "person":
            kwargs["classes"] = [0]
        result = self.model(frame_bgr, **kwargs)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        kpts = None
        if self.kind == "pose" and result.keypoints is not None:
            kpts = result.keypoints.xy.cpu().numpy()

        dets: list[Detection] = []
        for i, (x1, y1, x2, y2) in enumerate(xyxy):
            bottom = y1 + (y2 - y1) / 2.0
            if kpts is not None:
                shoulders = [
                    kpts[i][k][1] for k in (LEFT_SHOULDER, RIGHT_SHOULDER)
                    if k < len(kpts[i]) and (kpts[i][k] > 0).all()
                ]
                if shoulders:
                    bottom = min(shoulders) + SHOULDER_MARGIN_PX
            det = _to_det(x1, y1, x2, bottom, confs[i], w, h)
            if det:
                dets.append(det)
        return dets


@lru_cache(maxsize=8)
def get_detector(model: str):
    """Cache one loaded detector per model id."""
    if model == MEDIAPIPE_FACE:
        return MediaPipeFaceDetector()
    if model in ULTRALYTICS_MODELS:
        return UltralyticsDetector(model)
    return HeadDetector(config.MODELS_DIR / model)
