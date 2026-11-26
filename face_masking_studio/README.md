# Track-It Masking Studio (Face Masking Studio)

Local web tool to anonymize faces and heads in the recorded videos. It runs an automatic detection and tracking pass, then lets you audit and fix the masks by hand and render the final video. Backend in FastAPI, frontend in plain HTML/CSS/JS with the shared H.IAAC theme.

## Setup and run

You need Python 3.12 or newer, plus `ffmpeg` and `ffprobe` on the `PATH`.

```bash
./run.sh            # uses ../.venv if it exists, else creates .venv and installs backend/requirements.txt
```

To run it by hand instead:

```bash
cd backend
pip install -r requirements.txt     # with a GPU, use onnxruntime-gpu instead of onnxruntime
uvicorn main:app --host 127.0.0.1 --port 8000 --ws websockets
```

Then open http://127.0.0.1:8000.

## Modes

- **Standalone:** put videos in `videos/raw/` or upload them in the UI. Mask passes go to `videos/masks_data/` and renders to `videos/output/`.
- **Dataset Flow:** pick a session from `../data/`. The video comes from `data/<session>/videos/`. Masks and renders are saved back into that folder as `<session>_masked_<pass>.mp4`, and the manifest gets `anonymized_video` and `pipeline_status.face_masked = true`.

The server postprocessor starts the automatic pass by itself through `POST /api/video/dataset:<session>/auto-anonymize`. Because of that, the studio has to be running before the server receives sessions with video.

## Workflow

`RAW → Track → TRACKED → Manual 1/2/3 → Render`

- **Tracking:** runs detection every N frames, matches detections by IoU, propagates masks backward, and applies `head_pad`.
- **Progress Visibility (Terminal Logs vs. Web UI):**
  - **Manual UI Tracking:** Displays real-time WebSocket progress in the tracking panel.
  - **Automatic Pipeline Anonymization (`auto-anonymize`):** When triggered by the server postprocessor in the background, there is **no global progress bar in the web UI**. Progress is streamed directly to the terminal console (e.g. `[Face Masking] Tracking: 45% (frame 450/1000)` and `[Face Masking] Rendering: 60%`). Operators can monitor this via `./run_all.sh logs face-mask` or by watching service logs.
- **Canceling a Tracking Job:**
  - **In the Web UI:** Click the red **"Cancel tracking"** button in the sidebar to halt the active tracking run immediately.
  - **Via API:** Send an HTTP request to `POST /api/video/{id}/track/cancel`.
- **Edit:** create, select, move, resize, or delete masks; end a mask (`dead`) or reactivate and extend it. The work autosaves every 30 s.
- **Render:** blur, pixelate, or fill, with optional orientation normalization. The **Output** area lists every rendered pass and plays the newest one.

Mask data is stored as JSONL, one file per pass (`<video>_pass<N>.jsonl`) with one line per frame.

## Detection model

All methods go through `backend/detectors.py` and write the same `pass0.jsonl`, so the editor, tracking and render work the same for each one. Pick the method in the header model selector (editor) or with `--model` in `batch_tracking.py`.

| Model id | Backend | Target | Mask | Install |
|---|---|---|---|---|
| `yolov7_tiny_head_0.752_post_480x640.onnx` (**default**) | onnxruntime | Head | Head box | `requirements.txt` |
| `mediapipe-face` | MediaPipe | Face (frontal only) | Face box | `requirements-extra.txt` |
| `yolo11x-pose.pt` | Ultralytics | Pose | Person top to the shoulders | `requirements-extra.txt` |
| `yolo26m-pose.pt` | Ultralytics | Pose | Person top to the shoulders | `requirements-extra.txt` |
| `yolo11m.pt` | Ultralytics | Person | Upper half of the box | `requirements-extra.txt` |

The default model is set by `DEFAULT_MODEL` in `config.py` and is also used by the server `auto-anonymize` route. Methods whose package is missing show as "(not installed)" in the selector. Ultralytics weights download into `backend/models/` on first use.

```bash
pip install -r backend/requirements-extra.txt   # MediaPipe + Ultralytics (AGPL-3.0) + PyTorch CPU
```

The YOLOv7 ONNX is decoded in `onnx_detector.py`; its post-NMS layout (NMS built into the model) is:

| Tensor | Shape | Contents |
|---|---|---|
| `score` | `[N,1]` f32 | Confidence per detection |
| `batchno_classid_x1y1x2y2` | `[N,6]` i64 | `[batch, class, x1, y1, x2, y2]` in 640×480 space |

- Input: `[1,3,480,640]` NCHW, RGB, divided by 255, with letterbox.
- The device comes from the onnxruntime providers: `CUDAExecutionProvider` means GPU, otherwise CPU.

## Main API

| Method | Route | Use |
|---|---|---|
| GET | `/api/videos`, `/api/sessions` | List Standalone videos and Dataset Flow sessions |
| POST | `/api/video/{id}/track` | Automatic pass |
| POST | `/api/video/{id}/auto-anonymize` | Automatic pass and render in one call (used by the server) |
| GET/POST | `/api/video/{id}/masks/{pass}` | Read or save a mask pass |
| POST | `/api/video/{id}/render` | Render a pass |
| GET | `/api/video/{id}/outputs`, `/api/video/{id}/output/{pass}` | List rendered passes and download one |
| WS | `/ws/progress/{id}` | Tracking and render progress |

For Dataset Flow sessions, `{id}` is `dataset:<session>`.

## More docs

- `docs/FRONTEND.md`: frontend structure.
- `docs/generate.md`: design notes.
- `offline/README.md`: setup on a machine without internet.

## Credits and license

The Face Masking Studio code is MIT (see `../LICENSE`). **The detection models are not MIT**: the weights in `backend/models/` keep the licenses of their authors (see [`backend/models/README.md`](backend/models/README.md)). Using the studio with a model means following that model's license:
- **YOLOv7-tiny head (default):** Katsuya Hyodo ([PINTO0309/crowdhuman_hollywoodhead_yolo_convert](https://github.com/PINTO0309/crowdhuman_hollywoodhead_yolo_convert)), based on [WongKinYiu/yolov7](https://github.com/WongKinYiu/yolov7), GPL-3.0.
- **MediaPipe face** (optional): Google, Apache-2.0.
- **YOLO11x-pose, YOLO26m-pose, YOLO11m** (optional): [Ultralytics](https://github.com/ultralytics/ultralytics), AGPL-3.0. Installing `requirements-extra.txt` means accepting that license.
