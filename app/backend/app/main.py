from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
import httpx
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import Settings, settings
from .database import Database
from .models import ExperimentUpdate, MarkerCreate, SessionStart
from .websocket_manager import ConnectionManager

LOGGER = logging.getLogger("netsim_demo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
CLIENT_ID_RE = re.compile(r"^P\d{3,9}$")
STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public"
VIDEO_DIR = Path(__file__).resolve().parents[2] / "media" / "videos"
LIVE_DIR = Path(__file__).resolve().parents[2] / "media" / "live"
MEDIAMTX_CONFIG = Path(__file__).resolve().parents[2] / "mediamtx.yml"
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov", ".m4v"}


def detect_client(user_agent: str) -> tuple[str, str]:
    browser = "Other"
    for token, name in (("Edg/", "Edge"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"), ("Safari/", "Safari")):
        if token in user_agent:
            browser = name
            break
    os_name = "Other"
    for token, name in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iOS"), ("Mac OS", "macOS"), ("Linux", "Linux")):
        if token in user_agent:
            os_name = name
            break
    return browser, os_name


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    cfg = custom_settings or settings
    database = Database(cfg.database_path)
    manager = ConnectionManager()
    app_state: dict[str, Any] = {"video": None, "video_pending": None}
    ffmpeg_process: subprocess.Popen[bytes] | None = None
    mediamtx_process: subprocess.Popen[bytes] | None = None
    bandwidth_slots = asyncio.Semaphore(max(1, cfg.bandwidth_test_max_concurrent))

    def video_snapshot(video: dict[str, Any] | None) -> dict[str, Any] | None:
        if not video:
            return None
        snapshot = dict(video)
        if snapshot.get("playing"):
            elapsed = max(0.0, (time.time() * 1000 - snapshot["position_updated_at"]) / 1000)
            snapshot["position"] = snapshot["position"] + elapsed
        snapshot["position"] = round(max(0.0, snapshot.get("position", 0.0)), 3)
        snapshot["position_updated_at"] = int(time.time() * 1000)
        snapshot.pop("source_path", None)
        snapshot.pop("webrtc_base_url", None)
        return snapshot

    def stop_ffmpeg() -> None:
        nonlocal ffmpeg_process
        if ffmpeg_process is None:
            return
        if ffmpeg_process.poll() is None:
            ffmpeg_process.terminate()
            try:
                ffmpeg_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ffmpeg_process.kill()
                ffmpeg_process.wait(timeout=3)
        ffmpeg_process = None

    def ensure_mediamtx() -> None:
        nonlocal mediamtx_process
        if mediamtx_process is not None and mediamtx_process.poll() is None:
            return
        executable = cfg.mediamtx_path
        if not Path(executable).is_file() and not shutil.which(executable):
            raise RuntimeError(f"MediaMTX was not found. Install it or set MEDIAMTX_PATH (current: {executable})")
        try:
            mediamtx_process = subprocess.Popen([executable, str(MEDIAMTX_CONFIG)], stdin=subprocess.DEVNULL,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
        except OSError as error:
            mediamtx_process = None
            raise RuntimeError(f"MediaMTX could not be started from {executable}: {error}") from error

    def stop_mediamtx() -> None:
        nonlocal mediamtx_process
        if mediamtx_process is None:
            return
        if mediamtx_process.poll() is None:
            mediamtx_process.terminate()
            try:
                mediamtx_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                mediamtx_process.kill()
                mediamtx_process.wait(timeout=3)
        mediamtx_process = None

    def start_ffmpeg(video: dict[str, Any], position: float = 0.0) -> None:
        nonlocal ffmpeg_process
        executable = cfg.ffmpeg_path
        if not Path(executable).is_file() and not shutil.which(executable):
            raise RuntimeError(f"FFmpeg was not found. Install it or set FFMPEG_PATH (current: {executable})")
        command = [executable, "-hide_banner", "-loglevel", "error", "-re"]
        if position > 0:
            command.extend(["-ss", f"{position:.3f}"])
        if video["transport"] == "udp":
            ensure_mediamtx()
            command.extend([
                "-i", str(video["source_path"]), "-an", "-c:v", "libx264", "-preset", "veryfast",
                "-tune", "zerolatency", "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
                "-f", "rtsp", "-rtsp_transport", "udp", f"rtsp://127.0.0.1:8554/{video['stream_id']}",
            ])
        else:
            stream_dir = LIVE_DIR / video["stream_id"]
            stream_dir.mkdir(parents=True, exist_ok=True)
            playlist = stream_dir / "index.m3u8"
            command.extend([
                "-i", str(video["source_path"]), "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-g", "30", "-keyint_min", "30", "-sc_threshold", "0", "-c:a", "aac", "-ar", "48000",
                "-f", "hls", "-hls_time", "1", "-hls_list_size", "5",
                "-hls_flags", "delete_segments+append_list+independent_segments",
                "-hls_segment_filename", str(stream_dir / "segment_%06d.ts"), str(playlist),
            ])
        stop_ffmpeg()
        try:
            ffmpeg_process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            ffmpeg_process = None
            raise RuntimeError(f"FFmpeg could not be started from {executable}: {error}") from error
        if video["transport"] == "tcp":
            video["stream_url"] = f"/media/live/{video['stream_id']}/index.m3u8"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(database.initialize)
        if not await asyncio.to_thread(database.current_session):
            await asyncio.to_thread(database.start_session, cfg.session_name, "Instructor")
        yield
        stop_ffmpeg()
        stop_mediamtx()

    app = FastAPI(title="NetSim Web Emulation Lab", version="1.0.0", lifespan=lifespan)
    app.state.database = database
    app.state.manager = manager
    @app.middleware("http")
    async def no_cache_frontend(request: Request, call_next):
        response = await call_next(request)
        if request.url.path in ("/", "/instructor") or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response
    if cfg.allowed_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=list(cfg.allowed_origins), allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-Admin-Token"]
        )

    def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
        if not x_admin_token or x_admin_token != cfg.admin_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid X-Admin-Token required")

    async def active_session() -> dict[str, Any]:
        session = await asyncio.to_thread(database.current_session)
        if not session:
            raise HTTPException(status_code=409, detail="No active session")
        return session

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "online", "build": "2026-09-30-tcp-udp-video"}

    def executable_status(configured: str) -> dict[str, Any]:
        configured_path = Path(configured)
        found = configured_path if configured_path.is_file() else shutil.which(configured)
        return {
            "configured": configured,
            "available": bool(found),
            "path": str(Path(found).resolve()) if found else None,
        }

    @app.get("/api/preflight")
    async def preflight() -> dict[str, Any]:
        ffmpeg = executable_status(cfg.ffmpeg_path)
        mediamtx = executable_status(cfg.mediamtx_path)
        video_dir_exists = VIDEO_DIR.is_dir()
        live_dir_exists = LIVE_DIR.is_dir()
        video_count = sum(1 for path in VIDEO_DIR.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS) if video_dir_exists else 0
        return {
            "ffmpeg": ffmpeg,
            "mediamtx": mediamtx,
            "video_directory": {"available": video_dir_exists, "path": str(VIDEO_DIR), "video_count": video_count},
            "live_directory": {"available": live_dir_exists, "path": str(LIVE_DIR)},
            "tcp_video_ready": ffmpeg["available"] and video_count > 0,
            "udp_video_ready": ffmpeg["available"] and mediamtx["available"] and video_count > 0,
        }

    @app.get("/api/bandwidth/download")
    async def bandwidth_download(seconds: float = 10, max_bytes: int | None = None) -> StreamingResponse:
        duration = min(max(1.0, seconds), max(1, cfg.bandwidth_test_max_seconds))
        byte_limit = min(cfg.bandwidth_test_max_bytes, max_bytes or cfg.bandwidth_test_max_bytes)
        byte_limit = max(1, byte_limit)
        chunk = b"NetsimBandwidthTest" * 4096
        try:
            await asyncio.wait_for(bandwidth_slots.acquire(), timeout=0.1)
        except asyncio.TimeoutError as error:
            raise HTTPException(429, "Bandwidth test capacity is currently in use") from error

        async def body():
            sent = 0
            started = time.monotonic()
            try:
                while sent < byte_limit and time.monotonic() - started < duration:
                    piece = chunk[:min(len(chunk), byte_limit - sent)]
                    sent += len(piece)
                    yield piece
                    await asyncio.sleep(0)
            finally:
                bandwidth_slots.release()

        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Content-Encoding": "identity",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(body(), media_type="application/octet-stream", headers=headers)

    @app.get("/api/videos", dependencies=[Depends(require_admin)])
    async def list_videos() -> dict[str, Any]:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        videos = [
            {"name": path.name, "size_bytes": path.stat().st_size}
            for path in sorted(VIDEO_DIR.iterdir())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        return {"videos": videos, "active": video_snapshot(app_state["video"])}

    @app.post("/api/video/start", dependencies=[Depends(require_admin)])
    async def start_video(payload: dict[str, str]) -> dict[str, Any]:
        filename = str(payload.get("filename", "")).strip()
        transport = str(payload.get("transport", "tcp")).lower()
        if transport not in {"tcp", "udp"}:
            raise HTTPException(400, "Transport must be tcp or udp")
        candidate = (VIDEO_DIR / filename).resolve()
        if not filename or candidate.parent != VIDEO_DIR.resolve() or candidate.suffix.lower() not in VIDEO_EXTENSIONS or not candidate.is_file():
            raise HTTPException(400, "Choose a video file from media/videos")
        now = int(time.time() * 1000)
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        video = {"name": candidate.name, "url": f"/media/videos/{candidate.name}", "source_path": candidate,
                 "stream_id": f"stream_{now}", "transport": transport, "started_at": now, "position": 0.0,
                 "playing": True, "position_updated_at": now}
        if transport == "udp":
            video["stream_url"] = f"/api/video/webrtc/{video['stream_id']}/whep"
        try:
            start_ffmpeg(video)
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from error
        app_state["video_pending"] = video
        return video_snapshot(video)

    @app.post("/api/video/ready", dependencies=[Depends(require_admin)])
    async def ready_video() -> dict[str, Any]:
        video = app_state.get("video_pending")
        if not video:
            raise HTTPException(409, "No video is waiting for instructor readiness")
        app_state["video_pending"] = None
        app_state["video"] = video
        if video["transport"] == "tcp":
            playlist = LIVE_DIR / video["stream_id"] / "index.m3u8"
            for _ in range(40):
                if playlist.is_file():
                    break
                await asyncio.sleep(0.25)
            if not playlist.is_file():
                stop_ffmpeg()
                app_state["video"] = None
                raise HTTPException(503, "FFmpeg did not produce an HLS playlist")
        else:
            await asyncio.sleep(1)
            if ffmpeg_process is None or ffmpeg_process.poll() is not None:
                stop_ffmpeg()
                app_state["video"] = None
                raise HTTPException(503, "FFmpeg did not publish the UDP stream")
        snapshot = video_snapshot(video)
        await manager.broadcast({"type": "video_stream", "status": "started", **snapshot})
        return snapshot

    @app.post("/api/video/control", dependencies=[Depends(require_admin)])
    async def control_video(payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", ""))
        if action not in {"play", "pause", "seek"}:
            raise HTTPException(400, "Video action must be play, pause, or seek")
        if not app_state.get("video"):
            raise HTTPException(409, "No active video stream")
        position = max(0.0, float(payload.get("position", 0)))
        video = app_state["video"]
        video["position"] = position
        video["position_updated_at"] = int(time.time() * 1000)
        requested_playing = bool(payload.get("playing", action != "pause"))
        video["playing"] = requested_playing
        if action == "pause" or (action == "seek" and not requested_playing):
            stop_ffmpeg()
            await manager.broadcast({"type": "video_control", "action": action, "position": position, "playing": requested_playing})
        elif action in {"play", "seek"}:
            video["stream_id"] = f"stream_{int(time.time() * 1000)}"
            if video["transport"] == "udp":
                video["stream_url"] = f"/api/video/webrtc/{video['stream_id']}/whep"
            try:
                start_ffmpeg(video, position)
            except RuntimeError as error:
                video["playing"] = False
                raise HTTPException(503, str(error)) from error
            if video["transport"] == "tcp":
                for _ in range(40):
                    if (LIVE_DIR / video["stream_id"] / "index.m3u8").is_file():
                        break
                    await asyncio.sleep(0.25)
            else:
                await asyncio.sleep(1)
            await manager.broadcast({"type": "video_stream", "status": "started", **video_snapshot(video)})
        return {"action": action, "position": position}

    @app.post("/api/video/webrtc/{stream_id}/whep")
    async def video_webrtc_whep(stream_id: str, request: Request) -> Response:
        video = app_state.get("video")
        if not video or video.get("transport") != "udp" or video.get("stream_id") != stream_id:
            raise HTTPException(404, "UDP video stream not found")
        offer = await request.body()
        if not offer:
            raise HTTPException(400, "A WebRTC SDP offer is required")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                upstream = await client.post(f"http://127.0.0.1:8889/{stream_id}/whep",
                                             content=offer, headers={"Content-Type": "application/sdp"})
        except httpx.HTTPError as error:
            raise HTTPException(503, "Media gateway is not reachable") from error
        return Response(content=upstream.content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type", "application/sdp"))

    @app.post("/api/video/stop", dependencies=[Depends(require_admin)])
    async def stop_video() -> dict[str, str]:
        app_state["video"] = None
        app_state["video_pending"] = None
        stop_ffmpeg()
        await manager.broadcast({"type": "video_stream", "status": "stopped"})
        return {"status": "stopped"}

    @app.get("/api/session/current")
    async def get_current_session() -> dict[str, Any]:
        return await active_session()

    @app.get("/api/session/{session_id}", dependencies=[Depends(require_admin)])
    async def get_session(session_id: str) -> dict[str, Any]:
        result = await asyncio.to_thread(database.get_session, session_id)
        if not result:
            raise HTTPException(404, "Session not found")
        return result

    @app.post("/api/session/start", dependencies=[Depends(require_admin)])
    async def start_session(payload: SessionStart) -> dict[str, Any]:
        session = await asyncio.to_thread(database.start_session, payload.name, payload.instructor)
        await manager.broadcast({"type": "session_state", "session": session})
        return session

    @app.post("/api/session/stop", dependencies=[Depends(require_admin)])
    async def stop_session() -> dict[str, Any]:
        session = await asyncio.to_thread(database.stop_session)
        if not session:
            raise HTTPException(409, "No active session")
        await manager.broadcast({"type": "session_state", "session": session})
        return session

    @app.get("/api/participants", dependencies=[Depends(require_admin)])
    async def get_participants(active_only: bool = False) -> list[dict[str, Any]]:
        session = await active_session()
        return await asyncio.to_thread(database.participants, session["id"], active_only, cfg.participant_stale_timeout_sec)

    @app.get("/api/participants/{client_id}", dependencies=[Depends(require_admin)])
    async def get_participant(client_id: str) -> dict[str, Any]:
        result = await asyncio.to_thread(database.participant, client_id)
        if not result:
            raise HTTPException(404, "Participant not found")
        return result

    @app.delete("/api/participants/{client_id}", dependencies=[Depends(require_admin)])
    async def remove_participant(client_id: str) -> dict[str, bool]:
        disconnected = await manager.close(client_id, code=4001)
        changed = await asyncio.to_thread(database.delete_participant, client_id)
        return {"disconnected": disconnected or changed}

    @app.get("/api/experiment")
    async def get_experiment() -> dict[str, Any]:
        session = await active_session()
        return {"mode": session["experiment_mode"], "label": session["experiment_label"]}

    @app.post("/api/experiment", dependencies=[Depends(require_admin)])
    async def set_experiment(payload: ExperimentUpdate) -> dict[str, Any]:
        session = await active_session()
        updated = await asyncio.to_thread(database.set_experiment, session["id"], payload.mode, payload.label)
        message = {"type": "experiment_state", "mode": payload.mode, "label": payload.label,
                   "timestamp": int(time.time() * 1000)}
        await manager.broadcast(message)
        await asyncio.to_thread(database.add_marker, session["id"], "EXPERIMENT", payload.label or payload.mode, "")
        return updated

    @app.post("/api/experiment/marker", dependencies=[Depends(require_admin)])
    async def add_marker(payload: MarkerCreate) -> dict[str, Any]:
        session = await active_session()
        marker = await asyncio.to_thread(database.add_marker, session["id"], payload.event_type, payload.label, payload.notes)
        await manager.broadcast({"type": "event_marker", **marker})
        return marker

    @app.get("/api/metrics/summary", dependencies=[Depends(require_admin)])
    async def metrics_summary() -> dict[str, Any]:
        session = await active_session()
        await asyncio.to_thread(database.participants, session["id"], False, cfg.participant_stale_timeout_sec)
        return await asyncio.to_thread(database.summary, session["id"])

    @app.get("/api/metrics/client/{client_id}", dependencies=[Depends(require_admin)])
    async def client_metrics(client_id: str) -> dict[str, Any]:
        participant = await asyncio.to_thread(database.participant, client_id)
        if not participant:
            raise HTTPException(404, "Participant not found")
        return participant

    @app.get("/api/metrics/session/{session_id}", dependencies=[Depends(require_admin)])
    async def session_metrics(session_id: str) -> dict[str, Any]:
        if not await asyncio.to_thread(database.get_session, session_id):
            raise HTTPException(404, "Session not found")
        return await asyncio.to_thread(database.summary, session_id)

    @app.get("/api/export/session/{session_id}.json", dependencies=[Depends(require_admin)])
    async def export_session(session_id: str) -> JSONResponse:
        payload = await asyncio.to_thread(database.export_session, session_id)
        if not payload:
            raise HTTPException(404, "Session not found")
        return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{session_id}.json"'})

    def origin_allowed(websocket: WebSocket) -> bool:
        origin = websocket.headers.get("origin")
        if not origin:
            return True
        normalized = origin.rstrip("/")
        request_host = websocket.headers.get("host", "")
        return normalized in cfg.allowed_origins or normalized in (f"http://{request_host}", f"https://{request_host}")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if not origin_allowed(websocket):
            await websocket.close(code=1008)
            return
        session = await asyncio.to_thread(database.current_session)
        if not session:
            await websocket.close(code=1013)
            return
        requested_id = websocket.query_params.get("participant_id", "")
        client_id = (
            requested_id
            if CLIENT_ID_RE.fullmatch(requested_id)
            else await asyncio.to_thread(database.allocate_participant_id, session["id"])
        )
        previous = await manager.connect(client_id, websocket)
        if previous:
            try:
                await previous.close(code=4000, reason="Reconnected in another browser connection")
            except Exception:
                pass
        user_agent = websocket.headers.get("user-agent", "")
        browser, os_name = detect_client(user_agent)
        participant_data = {
            "id": client_id, "session_id": session["id"], "display_name": "", "institution": "",
            "ip_address": websocket.client.host if websocket.client else "", "user_agent": user_agent,
            "browser": browser, "os": os_name,
        }
        await asyncio.to_thread(database.register_participant, participant_data)
        await websocket.send_json({
            "type": "welcome", "client_id": client_id, "session_id": session["id"],
            "probe_interval_ms": cfg.probe_interval_ms, "probe_timeout_ms": cfg.probe_timeout_ms,
            "experiment": {"mode": session["experiment_mode"], "label": session["experiment_label"]},
            "markers": await asyncio.to_thread(database.markers, session["id"]),
            "video": video_snapshot(app_state["video"]),
        })
        LOGGER.info("client_connected client_id=%s remote_ip=%s session_id=%s", client_id, participant_data["ip_address"], session["id"])
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw.encode("utf-8")) > cfg.max_message_bytes:
                    await websocket.close(code=1009)
                    break
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Malformed JSON"})
                    continue
                if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                    await websocket.send_json({"type": "error", "message": "A message type is required"})
                    continue
                kind = message["type"]
                if kind == "client_hello":
                    participant_data["display_name"] = str(message.get("name", ""))[:80].strip()
                    participant_data["institution"] = str(message.get("institution", ""))[:120].strip()
                    await asyncio.to_thread(database.register_participant, participant_data)
                elif kind == "ping":
                    if not manager.allowed(client_id, "probe", 10):
                        await websocket.send_json({"type": "error", "message": "Probe rate limit exceeded"})
                        continue
                    sequence = int(message.get("sequence", 0))
                    client_timestamp = int(message.get("client_timestamp", 0))
                    await websocket.send_json({"type": "pong", "sequence": sequence,
                                               "client_timestamp": client_timestamp,
                                               "server_timestamp": int(time.time() * 1000)})
                elif kind in ("probe_result", "probe_timeout"):
                    sequence = int(message.get("sequence", 0))
                    received_at = int(time.time() * 1000)
                    rtt = float(message["rtt_ms"]) if kind == "probe_result" else None
                    if rtt is not None and not (0 <= rtt <= 300000):
                        await websocket.send_json({"type": "error", "message": "Invalid RTT"})
                        continue
                    sample_status = "late" if bool(message.get("late")) else ("success" if rtt is not None else "timeout")
                    await asyncio.to_thread(database.record_probe, session["id"], client_id, sequence,
                                            message.get("sent_at"), received_at, rtt, sample_status)
                    metrics = await asyncio.to_thread(database.participant, client_id)
                    await websocket.send_json({"type": "metrics", "metrics": metrics})
                elif kind == "message_send":
                    if not manager.allowed(client_id, "message", 5):
                        await websocket.send_json({"type": "error", "message": "Message rate limit exceeded"})
                        continue
                    text = str(message.get("text", ""))[:1000]
                    message_id = str(message.get("message_id", ""))[:80]
                    if not text or not message_id:
                        await websocket.send_json({"type": "error", "message": "Message ID and text are required"})
                        continue
                    received_at = int(time.time() * 1000)
                    await asyncio.to_thread(database.record_message, session["id"], client_id, message_id, text,
                                            message.get("client_timestamp"), received_at)
                    await websocket.send_json({"type": "message_echo", "message_id": message_id, "text": text,
                                               "server_received_at": received_at,
                                               "server_echo_timestamp": int(time.time() * 1000)})
                elif kind == "heartbeat":
                    await asyncio.to_thread(database.touch, client_id)
                    await websocket.send_json({"type": "heartbeat_ack", "timestamp": int(time.time() * 1000)})
                else:
                    await websocket.send_json({"type": "error", "message": f"Unsupported message type: {kind}"})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if await manager.disconnect(client_id, websocket):
                await asyncio.to_thread(database.mark_disconnected, client_id)
                LOGGER.info("client_disconnected client_id=%s session_id=%s", client_id, session["id"])

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media/videos", StaticFiles(directory=VIDEO_DIR), name="videos")
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media/live", StaticFiles(directory=LIVE_DIR), name="live")

    @app.get("/instructor", include_in_schema=False)
    async def instructor_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "instructor.html")

    @app.get("/", include_in_schema=False)
    async def participant_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
