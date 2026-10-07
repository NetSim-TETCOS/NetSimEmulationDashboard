from backend.app.database import Database


def test_session_participant_probe_and_export(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    session = database.start_session("Test", "Teacher")
    participant = database.register_participant({
        "id": "P001", "session_id": session["id"], "display_name": "A", "institution": "Lab",
        "ip_address": "127.0.0.1", "user_agent": "pytest", "browser": "Other", "os": "Other",
    })
    assert participant["status"] == "online"
    for sequence in range(1, 12):
        database.record_probe(session["id"], "P001", sequence, 1000, 1010, sequence * 10, "success")
    detail = database.participant("P001")
    assert detail is not None
    assert detail["baseline_rtt"] == 55.0
    marker = database.add_marker(session["id"], "EXPERIMENT", "Delay enabled", "")
    assert marker["label"] == "Delay enabled"
    exported = database.export_session(session["id"])
    assert exported is not None
    assert exported["participants"][0]["id"] == "P001"
    assert exported["event_markers"][0]["label"] == "Delay enabled"


def test_reconnection_reuses_participant(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    session = database.start_session("Test", "Teacher")
    base = {"id":"P001", "session_id":session["id"], "display_name":"", "institution":"",
            "ip_address":"1.2.3.4", "user_agent":"one", "browser":"Other", "os":"Other"}
    database.register_participant(base)
    database.mark_disconnected("P001")
    base["display_name"] = "Reconnected"
    result = database.register_participant(base)
    assert result["status"] == "online"
    assert result["display_name"] == "Reconnected"
    assert len(database.participants(session["id"])) == 1
