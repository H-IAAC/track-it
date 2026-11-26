# Third-party notices

The source code of the HIAAC Toolkit is released under the [MIT License](LICENSE) (Copyright (c) 2026 H.IAAC). The files below are bundled from other projects and keep their own licenses. In particular, the Face Masking Studio code is MIT but its detection models are not.

## Bundled files

| Component | Location | Author / source | License |
|---|---|---|---|
| YOLOv7-tiny head detector, default model (`yolov7_tiny_head_0.752_post_480x640.onnx`) | `face_masking_studio/backend/models/` | Katsuya Hyodo (PINTO0309), [crowdhuman_hollywoodhead_yolo_convert](https://github.com/PINTO0309/crowdhuman_hollywoodhead_yolo_convert); architecture by [WongKinYiu/yolov7](https://github.com/WongKinYiu/yolov7) | GPL-3.0 |
| JetBrains Mono font | `shared/hiaac-theme/web/fonts/` and each tool's `hiaac/fonts/` | [JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono) | SIL OFL 1.1 (`OFL.txt` next to the fonts) |
| d3.js v4.13.0 | `server-processing/preprocessor/public/graph/d3.v4.js` | Mike Bostock, [d3/d3](https://github.com/d3/d3) | ISC (notice kept in the file header) |

## Training datasets of the bundled models

The head detectors were trained by their authors on public datasets that have their own terms of use:

- [CrowdHuman](https://www.crowdhuman.org/) (YOLOv7-tiny head)
- [HollywoodHeads](https://www.di.ens.fr/willow/research/headdetection/) (YOLOv7-tiny head)

## Optional detection methods (not bundled)

Installed only with `face_masking_studio/backend/requirements-extra.txt`:

- [MediaPipe](https://github.com/google-ai-edge/mediapipe) face detection, Google, Apache-2.0.
- [Ultralytics](https://github.com/ultralytics/ultralytics) YOLO11x-pose, YOLO26m-pose and YOLO11m, AGPL-3.0 (code and weights). The weights (`*.pt`) are downloaded from Ultralytics on first use and are not in this repository. PyTorch (BSD-3-Clause) comes with it.

## Loaded at runtime (not bundled)

- [Material Icons](https://github.com/google/material-design-icons) (Google Fonts CDN, Face Masking Studio), Apache-2.0.
- Python, Node.js and Android dependencies listed in the `requirements*.txt`, `package.json` and `build.gradle` files are installed by their package managers and keep their own licenses (mostly MIT, BSD and Apache-2.0).

## Components based on H.IAAC / Instituto Eldorado repositories

These components were started from repositories developed by H.IAAC and Instituto Eldorado. The upstream repositories have no license file; the code is released here under the MIT License with their authorization.

### Android app (`android_app/`)

Based on [H-IAAC/sensor-toolkit](https://github.com/H-IAAC/sensor-toolkit), tag `v3.0.1`, commit `db5ce43` (2025-02-18). Upstream authors: [Felipe Augusto](https://github.com/felipeaps89), [Saulo A. Moraes](https://github.com/saulo-moraes) and [Daniel Adam Miranda](https://github.com/DanielMirandaEldorado), with contributions from [Fabio Grassiotto](https://github.com/fabiogras). Upstream kept evolving after `v3.0.1` (ExtraSensory and inference-service work in `HiaacLib` and `SensorSDK`, last commit 2026-04-16 on `dev`); those changes are not included. Changes in this toolkit: the shared H.IAAC theme (colors, light/dark mode, logo, monospace typography), the "no server connected" warning, the open source licenses screen and build fixes.

### Server processing (`server-processing/`)

Based on [H-IAAC/data_collection_server](https://github.com/H-IAAC/data_collection_server), commit `89ce88f` (2024-12-04, tip of branches `v4.0`, `v4.1` and `4.1.yolo_pose_n`, the latest upstream commit). Upstream authors: [Saulo A. Moraes](https://github.com/saulo-moraes) and [Amparo Díaz Muñoz](https://github.com/amparomunoz). Changes in this toolkit: session manifests and the `data/<session>` output, automatic masking through the Face Masking Studio API instead of the Ultralytics `VideoConverter`, `process_files.py`, the shared H.IAAC theme in the preprocessor pages, and updated requirements.

### Annotation Interface (`annotation_interface/`)

Based on branch `Time-Series-Labeling-Tool` of [H-IAAC/viewer_tool_jupyter](https://github.com/H-IAAC/viewer_tool_jupyter), commit `ed91011` (2024-09-06, latest commit of that branch). Upstream author: [Amparo Díaz Muñoz](https://github.com/amparomunoz), building on earlier versions of the tool by [Daniel Adam Miranda](https://github.com/DanielMirandaEldorado) and [Saulo A. Moraes](https://github.com/saulo-moraes). Changes in this toolkit: Dataset Flow (sessions from `data/`), standalone Create/Upload/Download of annotation CSVs, the ends-at annotation convention, server-side file loading and the shared H.IAAC theme.

The Viewer Interface (`viewer_interface/`) and the Face Masking Studio were written for this toolkit.
