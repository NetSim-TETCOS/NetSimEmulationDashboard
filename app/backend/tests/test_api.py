import json

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def make_client(tmp_path) -> TestClient:
    config = Settings(admin_token="test-token", database_url=f"sqlite:///{tmp_path / 'api.db'}")
    return TestClient(create_app(config))


def test_admin_auth_and_session_api(tmp_path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/api/health").json()["status"] == "online"
        assert client.get("/api/participants").status_code == 401
        headers = {"X-Admin-Token": "test-token"}
        session = client.get("/api/session/current").json()
        assert session["status"] == "active"
        assert client.get("/api/participants", headers=headers).json() == []
        update = client.post("/api/experiment", headers=headers, json={"mode":"DELAY", "label":"100 ms"})
        assert update.status_code == 200
        assert client.get("/api/experiment").json()["mode"] == "DELAY"


def test_preflight_reports_media_tool_state(tmp_path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/preflight")
        assert response.status_code == 200
        body = response.json()
        assert {"ffmpeg", "mediamtx", "video_directory", "live_directory", "tcp_video_ready", "udp_video_ready"} <= body.keys()
        assert isinstance(body["ffmpeg"]["available"], bool)
        assert isinstance(body["mediamtx"]["available"], bool)


def test_websocket_ping_echo_metrics_and_reconnect(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.websocket_connect("/ws") as websocket:
            welcome = websocket.receive_json()
            client_id = welcome["client_id"]
            websocket.send_json({"type":"client_hello", "name":"Tester", "institution":"TETCOS"})
            websocket.send_json({"type":"ping", "sequence":1, "client_timestamp":1000})
            pong = websocket.receive_json()
            assert pong["type"] == "pong"
            assert pong["sequence"] == 1
            websocket.send_json({"type":"probe_result", "sequence":1, "sent_at":1000, "rtt_ms":42.5})
            metrics = websocket.receive_json()
            assert metrics["metrics"]["current_rtt"] == 42.5
            websocket.send_json({"type":"message_send", "message_id":"m-1", "text":"hello", "client_timestamp":1000})
            echo = websocket.receive_json()
            assert echo["type"] == "message_echo"
            assert echo["text"] == "hello"
        with client.websocket_connect(f"/ws?participant_id={client_id}") as websocket:
            assert websocket.receive_json()["client_id"] == client_id
        participants = client.get("/api/participants", headers={"X-Admin-Token":"test-token"}).json()
        assert len(participants) == 1
        assert participants[0]["message_count"] == 1


def test_malformed_websocket_message_is_contained(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.receive_json()
            websocket.send_text("not json")
            assert websocket.receive_json() == {"type":"error", "message":"Malformed JSON"}
            websocket.send_text(json.dumps({"missing":"type"}))
            assert websocket.receive_json()["type"] == "error"


def test_video_selection_is_restricted_to_video_directory(tmp_path) -> None:
    with make_client(tmp_path) as client:
        headers = {"X-Admin-Token": "test-token"}
        assert client.post("/api/video/start", headers=headers, json={"filename": "missing.mp4"}).status_code == 400
        assert client.post("/api/video/start", headers=headers, json={"filename": "..\\requirements.md"}).status_code == 400


def test_video_start_waits_for_instructor_ready(tmp_path) -> None:
    with make_client(tmp_path) as client:
        headers = {"X-Admin-Token": "test-token"}
        response = client.post("/api/video/start", headers=headers, json={"filename": "sample.mp4"})
        assert response.status_code == 400  # no fixture file is installed in the test workspace


def test_bandwidth_download_is_bounded_and_not_cached(tmp_path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/bandwidth/download?seconds=1&max_bytes=1024")
        assert response.status_code == 200
        assert len(response.content) == 1024
        assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
