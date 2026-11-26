# Detection models

The Face Masking Studio code is MIT, but these weights are third-party files and are **not** covered by the MIT license. `yolov7_tiny_head_0.752_post_480x640.onnx` is the default model.

| File | Origin | License |
|---|---|---|
| `yolov7_tiny_head_0.752_post_480x640.onnx` | [PINTO0309/crowdhuman_hollywoodhead_yolo_convert](https://github.com/PINTO0309/crowdhuman_hollywoodhead_yolo_convert): YOLOv7-tiny trained on CrowdHuman + HollywoodHeads (heads only), exported to ONNX with NMS. Based on [WongKinYiu/yolov7](https://github.com/WongKinYiu/yolov7). | GPL-3.0 |

If you redistribute or use these files, follow their licenses and the terms of the training datasets ([CrowdHuman](https://www.crowdhuman.org/), [HollywoodHeads](https://www.di.ens.fr/willow/research/headdetection/)).

The optional Ultralytics weights (`yolo11x-pose.pt`, `yolo26m-pose.pt`, `yolo11m.pt`) are downloaded here on first use (git-ignored). They are AGPL-3.0, like the Ultralytics package.
