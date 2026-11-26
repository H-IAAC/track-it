"""ONNX head detector for the YOLOv7-tiny head layout with NMS baked in.

yolov7-tiny-head with NMS baked in (yolov7_tiny_head_*.onnx):
     input  : 'input'  float32 [1, 3, 480, 640]  NCHW, RGB, /255
     outputs: 'score'                    float32 [N, 1]
              'batchno_classid_x1y1x2y2' int64   [N, 6]  [b, cls, x1, y1, x2, y2]

Boxes are returned in the original frame's pixel coordinates (letterbox undone).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from config import onnx_providers


class Detection:
    """A single head detection in original-frame pixel coordinates."""

    __slots__ = ("x", "y", "w", "h", "score")

    def __init__(self, x: int, y: int, w: int, h: int, score: float) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.score = score


class HeadDetector:
    """Runs a head-detection ONNX model on BGR frames."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = str(model_path)
        providers = onnx_providers()
        try:
            self.session = ort.InferenceSession(
                self.model_path, providers=providers
            )
        except Exception:
            # CUDA EP listed but failed to initialize (missing libs / no GPU):
            # fall back to CPU instead of crashing tracking.
            self.session = ort.InferenceSession(
                self.model_path, providers=["CPUExecutionProvider"]
            )
        self.providers = self.session.get_providers()
        print(f"[onnx] {Path(self.model_path).name} running on {self.providers}")
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        # Static shape [1, 3, H, W]
        _, _, self.in_h, self.in_w = (
            d if isinstance(d, int) else -1 for d in inp.shape
        )
        if self.in_h <= 0 or self.in_w <= 0:
            self.in_h, self.in_w = 640, 640
        self.output_names = [o.name for o in self.session.get_outputs()]

    def _letterbox(self, frame: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        """Resize keeping aspect ratio, pad to (in_h, in_w). Returns scale+pads."""
        src_h, src_w = frame.shape[:2]
        scale = min(self.in_w / src_w, self.in_h / src_h)
        new_w, new_h = int(round(src_w * scale)), int(round(src_h * scale))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        pad_x = (self.in_w - new_w) // 2
        pad_y = (self.in_h - new_h) // 2
        canvas = np.full((self.in_h, self.in_w, 3), 114, dtype=np.uint8)
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
        return canvas, scale, pad_x, pad_y

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.4) -> list[Detection]:
        """Detect heads in a BGR frame. Returns boxes in original coordinates."""
        canvas, scale, pad_x, pad_y = self._letterbox(frame_bgr)
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[None]  # NCHW

        outputs = self.session.run(self.output_names, {self.input_name: blob})
        src_hw = frame_bgr.shape[:2]
        return self._decode_yolov7(outputs, scale, pad_x, pad_y, src_hw, conf_threshold)

    def _undo_letterbox(
        self, x1: float, y1: float, x2: float, y2: float,
        scale: float, pad_x: int, pad_y: int, src_hw: tuple[int, int],
    ) -> tuple[float, float, float, float] | None:
        src_h, src_w = src_hw
        ox1 = max(0.0, min((x1 - pad_x) / scale, src_w))
        oy1 = max(0.0, min((y1 - pad_y) / scale, src_h))
        ox2 = max(0.0, min((x2 - pad_x) / scale, src_w))
        oy2 = max(0.0, min((y2 - pad_y) / scale, src_h))
        if ox2 - ox1 <= 1 or oy2 - oy1 <= 1:
            return None
        return ox1, oy1, ox2, oy2

    def _decode_yolov7(
        self, outputs, scale, pad_x, pad_y, src_hw, conf_threshold,
    ) -> list[Detection]:
        scores, boxes = outputs
        if scores.shape[0] == 0:
            return []
        detections: list[Detection] = []
        for (_, _, y1, x1, y2, x2), (conf,) in zip(boxes, scores):
            if conf < conf_threshold:
                continue
            box = self._undo_letterbox(x1, y1, x2, y2, scale, pad_x, pad_y, src_hw)
            if box is None:
                continue
            ox1, oy1, ox2, oy2 = box
            detections.append(
                Detection(int(ox1), int(oy1), int(ox2 - ox1), int(oy2 - oy1), float(conf))
            )
        return detections
