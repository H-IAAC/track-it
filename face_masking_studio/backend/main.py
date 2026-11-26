"""FastAPI app: REST routes, WebSocket progress, static frontend."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import detectors
import metadata_fixer
import renderer
import session_manager
import tracker

config.ensure_dirs()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Face Masking Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket progress broadcaster ----------------------------------------
class ProgressHub:
    """Routes worker-thread progress messages to subscribed WebSockets."""

    def __init__(self) -> None:
        self._subs: dict[str, set[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self, video_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._subs.setdefault(video_id, set()).add(ws)

    def unsubscribe(self, video_id: str, ws: WebSocket) -> None:
        self._subs.get(video_id, set()).discard(ws)

    async def _send(self, video_id: str, message: dict) -> None:
        dead = []
        for ws in list(self._subs.get(video_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unsubscribe(video_id, ws)

    def emit(self, video_id: str, message: dict) -> None:
        """Thread-safe emit callable from worker threads."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._send(video_id, message), self._loop
        )


hub = ProgressHub()


@app.on_event("startup")
async def _startup() -> None:
    hub.set_loop(asyncio.get_running_loop())


# --- helpers ----------------------------------------------------------------
def _resolve_raw(video_id: str) -> Path:
    import json
    if video_id.startswith("dataset:"):
        session_id = video_id.split(":", 1)[1]
        session_dir = config.DATASET_DIR / session_id
        manifest_path = session_dir / "session_manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            video_file = manifest.get("artifacts", {}).get("raw_video")
            if video_file:
                return (session_dir / video_file).resolve()
        raise HTTPException(404, f"Dataset session video not found: {video_id}")
        
    # video_id is the POSIX relative path under RAW_DIR without extension
    # (e.g. "subA/clip"). Reject path traversal before touching the filesystem.
    root = config.RAW_DIR.resolve()
    for ext in config.VIDEO_EXTENSIONS:
        p = (config.RAW_DIR / f"{video_id}{ext}").resolve()
        if root in p.parents and p.exists():
            return p
    raise HTTPException(404, f"Video not found: {video_id}")

@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    import json
    sessions = []
    if not config.DATASET_DIR.exists():
        return sessions
        
    for p in sorted(config.DATASET_DIR.iterdir()):
        if p.is_dir():
            manifest_path = p / "session_manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    # Only include sessions that have a raw_video
                    if manifest.get("artifacts", {}).get("raw_video"):
                        video_id = f"dataset:{p.name}"
                        sessions.append({
                            "id": video_id,
                            "filename": f"[{p.name}] " + manifest["artifacts"]["raw_video"],
                            "folder": "Dataset Sessions",
                            "state": session_manager.get_state(video_id),
                            "passes": session_manager.existing_passes(video_id),
                        })
                except Exception:
                    pass
    return sessions


# --- REST: config -----------------------------------------------------------
@app.get("/api/config")
def get_config() -> dict:
    return {
        "base_dir": str(config.VIDEOS_DIR),
        "models": detectors.list_models(),
        "default_model": config.DEFAULT_MODEL,
        "device": config.detect_device(),
    }


class ConfigUpdate(BaseModel):
    base_dir: str | None = None


@app.post("/api/config")
def update_config(payload: ConfigUpdate) -> dict:
    if payload.base_dir:
        base = Path(payload.base_dir)
        config.VIDEOS_DIR = base
        config.RAW_DIR = base / "raw"
        config.MASKS_DIR = base / "masks_data"
        config.TMP_DIR = base / "tmp"
        config.OUTPUT_DIR = base / "output"
        config.ensure_dirs()
    return get_config()


# --- REST: videos -----------------------------------------------------------
@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    out_path = config.RAW_DIR / file.filename
    # Handle filename collisions if necessary, or just overwrite
    with open(out_path, "wb") as f:
        f.write(await file.read())
    return {"status": "success", "filename": file.filename}

@app.get("/api/videos")
def list_videos() -> list[dict]:
    videos = []
    # recurse into subfolders of raw/ — id is the relative path (no extension),
    # folder is its parent ("" for files sitting directly in raw/).
    for p in sorted(config.RAW_DIR.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in config.VIDEO_EXTENSIONS:
            continue
        # Skip pre-rotation backups left by normalize_rotation (<name>.orig.<ext>).
        if p.stem.endswith(".orig"):
            continue
        rel = p.relative_to(config.RAW_DIR)
        vid = rel.with_suffix("").as_posix()
        folder = rel.parent.as_posix()
        if folder == ".":
            folder = ""
        videos.append(
            {
                "id": vid,
                "filename": p.name,
                "folder": folder,
                "state": session_manager.get_state(vid),
                "passes": session_manager.existing_passes(vid),
            }
        )
    return videos


@app.get("/api/video/{video_id:path}/metadata")
def video_metadata(video_id: str) -> dict:
    path = _resolve_raw(video_id)
    info = metadata_fixer.get_video_info(path)
    info["id"] = video_id
    info["filename"] = path.name
    state = session_manager.get_state(video_id)
    if video_id in _track_jobs:
        state = "TRACKING"
    info["state"] = state
    info["passes"] = session_manager.existing_passes(video_id)
    return info


@app.get("/api/video/{video_id:path}/file")
def video_file(video_id: str) -> FileResponse:
    path = _resolve_raw(video_id)
    return FileResponse(path)

@app.get("/api/video/{video_id:path}/outputs")
def get_video_outputs(video_id: str) -> list[int]:
    import glob
    is_dataset = video_id.startswith("dataset:")
    outputs = []
    
    if is_dataset:
        session_id = video_id.split(":", 1)[1]
        session_dir = config.DATASET_DIR / session_id
        for d in (session_dir / "videos", session_dir):
            for p in d.glob(f"{glob.escape(session_id)}_masked_*.mp4"):
                try:
                    pass_n = int(p.stem.split("_")[-1])
                    if pass_n not in outputs:
                        outputs.append(pass_n)
                except ValueError:
                    pass
    else:
        stem = session_manager.safe_stem(video_id)
        for p in config.OUTPUT_DIR.glob(f"{glob.escape(stem)}_masked_*.mp4"):
            try:
                pass_n = int(p.stem.split("_")[-1])
                outputs.append(pass_n)
            except ValueError:
                pass
                
    return sorted(outputs)

@app.get("/api/video/{video_id:path}/output/{pass_n}")
def get_video_output_file(video_id: str, pass_n: int) -> FileResponse:
    is_dataset = video_id.startswith("dataset:")
    if is_dataset:
        session_id = video_id.split(":", 1)[1]
        session_dir = config.DATASET_DIR / session_id
        name = f"{session_id}_masked_{pass_n}.mp4"
        path = session_dir / "videos" / name
        if not path.exists():
            path = session_dir / name
    else:
        stem = session_manager.safe_stem(video_id)
        path = config.OUTPUT_DIR / f"{stem}_masked_{pass_n}.mp4"
        
    if not path.exists():
        raise HTTPException(404, "Output video not found")
    return FileResponse(path, media_type="video/mp4")


# --- REST: tracking ---------------------------------------------------------
# Active tracking jobs: video_id -> cancel Event. Guards against parallel runs.
_track_jobs: dict[str, threading.Event] = {}
_track_lock = threading.Lock()


class TrackRequest(BaseModel):
    start_frame: int = 0
    end_frame: int = 0
    detect_every: int = 1
    model: str | None = None
    head_pad: float = 20.0
    backward: bool = True
    backfill_grow: float = 30.0


@app.post("/api/video/{video_id:path}/track")
def start_track(video_id: str, req: TrackRequest) -> dict:
    path = _resolve_raw(video_id)
    out_jsonl = session_manager.jsonl_path(video_id, 0)
    try:
        model = detectors.validate_model(req.model)
    except ValueError as e:
        raise HTTPException(400, str(e))

    with _track_lock:
        if video_id in _track_jobs:
            raise HTTPException(409, "Tracking already running for this video")
        cancel_ev = threading.Event()
        _track_jobs[video_id] = cancel_ev

    def worker() -> None:
        try:
            tracker.run_tracking(
                video_path=path,
                jsonl_path=out_jsonl,
                start_frame=req.start_frame,
                end_frame=req.end_frame,
                detect_every=max(1, req.detect_every),
                model_path=model,
                head_pad=req.head_pad,
                backward=req.backward,
                backfill_grow=max(0.0, req.backfill_grow),
                ws_callback=lambda msg: hub.emit(video_id, msg),
                should_cancel=cancel_ev.is_set,
            )
            if not cancel_ev.is_set():
                session_manager.set_state(video_id, "TRACKED")
                if video_id.startswith("dataset:"):
                    import json
                    session_id = video_id.split(":", 1)[1]
                    session_dir = config.DATASET_DIR / session_id
                    manifest_path = session_dir / "session_manifest.json"
                    if manifest_path.exists():
                        with open(manifest_path, "r") as f:
                            manifest = json.load(f)
                        manifest.setdefault("artifacts", {})["masks_data"] = "videos/masks_data"
                        with open(manifest_path, "w") as f:
                            json.dump(manifest, f, indent=4)
        except Exception as exc:  # surface to client
            hub.emit(video_id, {"type": "error", "message": str(exc)})
        finally:
            with _track_lock:
                _track_jobs.pop(video_id, None)

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started", "jsonl": str(out_jsonl)}


@app.post("/api/video/{video_id:path}/track/cancel")
def cancel_track(video_id: str) -> dict:
    with _track_lock:
        cancel_ev = _track_jobs.get(video_id)
    if cancel_ev is None:
        raise HTTPException(404, "No tracking running for this video")
    cancel_ev.set()
    return {"status": "cancelling"}


@app.post("/api/video/{video_id:path}/auto-anonymize")
def start_auto_anonymize(video_id: str) -> dict:
    path = _resolve_raw(video_id)
    out_jsonl = session_manager.jsonl_path(video_id, 0)
    try:
        model = detectors.validate_model(None)
    except ValueError as e:
        raise HTTPException(400, str(e))

    with _track_lock:
        if video_id in _track_jobs:
            raise HTTPException(409, "Tracking already running for this video")
        cancel_ev = threading.Event()
        _track_jobs[video_id] = cancel_ev

    def worker() -> None:
        try:
            print(f"[FaceMasking] [Auto-Anonymize] Starting pipeline for {video_id}...", flush=True)
            # 1. Tracking
            tracker.run_tracking(
                video_path=path,
                jsonl_path=out_jsonl,
                start_frame=0,
                end_frame=0,
                detect_every=1,
                model_path=model,
                head_pad=20.0,
                backward=True,
                backfill_grow=30.0,
                ws_callback=lambda msg: hub.emit(video_id, msg),
                should_cancel=cancel_ev.is_set,
            )
            if cancel_ev.is_set():
                print(f"[FaceMasking] [Auto-Anonymize] Cancelled for {video_id}", flush=True)
                return
                
            session_manager.set_state(video_id, "TRACKED")
            is_dataset = video_id.startswith("dataset:")
            if is_dataset:
                import json
                session_id = video_id.split(":", 1)[1]
                session_dir = config.DATASET_DIR / session_id
                manifest_path = session_dir / "session_manifest.json"
                if manifest_path.exists():
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    manifest.setdefault("artifacts", {})["masks_data"] = "videos/masks_data"
                    with open(manifest_path, "w") as f:
                        json.dump(manifest, f, indent=4)
            
            # 2. Rendering
            if is_dataset:
                videos_dir = session_dir / "videos"
                videos_dir.mkdir(exist_ok=True)
                out = videos_dir / f"{session_id}_masked_0.mp4"
            else:
                out = config.OUTPUT_DIR / f"{session_manager.safe_stem(video_id)}_masked_0.mp4"
                
            renderer.render_video(
                video_path=path,
                jsonl_path=out_jsonl,
                output_path=out,
                mask_type="fill",
                fill_color=(0, 0, 0),
                ws_callback=lambda msg: hub.emit(video_id, msg),
            )
            
            if is_dataset:
                if manifest_path.exists():
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    manifest.setdefault("artifacts", {})["anonymized_video"] = f"videos/{out.name}"
                    if "pipeline_status" in manifest:
                        manifest["pipeline_status"]["face_masked"] = True
                    with open(manifest_path, "w") as f:
                        json.dump(manifest, f, indent=4)
                        
            print(f"[FaceMasking] [Auto-Anonymize] Successfully completed pipeline for {video_id} -> {out}", flush=True)
            hub.emit(video_id, {"type": "finished", "message": "Auto-anonymize completed"})
            
        except Exception as exc:
            print(f"[FaceMasking] [Auto-Anonymize] ERROR for {video_id}: {exc}", flush=True)
            hub.emit(video_id, {"type": "error", "message": str(exc)})
        finally:
            with _track_lock:
                _track_jobs.pop(video_id, None)

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started"}


# --- REST: masks ------------------------------------------------------------
class MasksPayload(BaseModel):
    jsonl: str


@app.get("/api/video/{video_id:path}/masks/{pass_n}")
def get_masks(video_id: str, pass_n: int) -> JSONResponse:
    path = session_manager.jsonl_path(video_id, pass_n)
    if not path.exists():
        raise HTTPException(404, f"No JSONL for pass {pass_n}")
    return JSONResponse(
        {"pass": pass_n, "jsonl": path.read_text(encoding="utf-8")}
    )


@app.post("/api/video/{video_id:path}/masks/{pass_n}")
def save_masks(video_id: str, pass_n: int, payload: MasksPayload) -> dict:
    path = session_manager.jsonl_path(video_id, pass_n)
    path.write_text(payload.jsonl, encoding="utf-8")
    return {"status": "saved", "path": str(path)}


@app.post("/api/video/{video_id:path}/advance")
def advance_state(video_id: str) -> dict:
    new_state = session_manager.advance(video_id, video_id)
    return {"state": new_state}


# --- REST: render -----------------------------------------------------------
class RenderRequest(BaseModel):
    mask_type: str = "blur"
    pass_n: int | None = None
    fill_color: list[int] = [0, 0, 0]


@app.post("/api/video/{video_id:path}/render")
def start_render(video_id: str, req: RenderRequest) -> dict:
    import json
    path = _resolve_raw(video_id)
    passes = session_manager.existing_passes(video_id)
    if not passes:
        raise HTTPException(400, "No mask data to render")
    pass_n = req.pass_n if req.pass_n is not None else max(passes)
    jsonl = session_manager.jsonl_path(video_id, pass_n)
    
    is_dataset = video_id.startswith("dataset:")
    if is_dataset:
        session_id = video_id.split(":", 1)[1]
        session_dir = config.DATASET_DIR / session_id
        videos_dir = session_dir / "videos"
        videos_dir.mkdir(exist_ok=True)
        out = videos_dir / f"{session_id}_masked_{pass_n}.mp4"
    else:
        out = config.OUTPUT_DIR / f"{session_manager.safe_stem(video_id)}_masked_{pass_n}.mp4"

    def worker() -> None:
        try:
            renderer.render_video(
                video_path=path,
                jsonl_path=jsonl,
                output_path=out,
                mask_type=req.mask_type,
                fill_color=tuple(req.fill_color[::-1]),  # RGB->BGR
                ws_callback=lambda msg: hub.emit(video_id, msg),
            )
            
            if is_dataset:
                # Update manifest
                manifest_path = session_dir / "session_manifest.json"
                if manifest_path.exists():
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    manifest.setdefault("artifacts", {})["anonymized_video"] = f"videos/{out.name}"
                    if "pipeline_status" in manifest:
                        manifest["pipeline_status"]["face_masked"] = True
                    with open(manifest_path, "w") as f:
                        json.dump(manifest, f, indent=4)
                        
        except Exception as exc:
            hub.emit(video_id, {"type": "error", "message": str(exc)})

    threading.Thread(target=worker, daemon=True).start()
    return {"status": "started", "output": str(out)}


# --- WebSocket --------------------------------------------------------------
@app.websocket("/ws/progress/{video_id:path}")
async def ws_progress(ws: WebSocket, video_id: str) -> None:
    await hub.subscribe(video_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.unsubscribe(video_id, ws)


# --- Static frontend (mounted last so /api wins) ----------------------------
app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="static")
