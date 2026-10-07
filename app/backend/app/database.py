from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metrics import calculate_rtt_metrics, percentile


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                    instructor TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
                    experiment_mode TEXT NOT NULL DEFAULT 'BASELINE', experiment_label TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS participants (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
                    institution TEXT NOT NULL DEFAULT '', ip_address TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '', browser TEXT NOT NULL DEFAULT '', os TEXT NOT NULL DEFAULT '',
                    connected_at TEXT NOT NULL, disconnected_at TEXT, last_seen TEXT NOT NULL, status TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE TABLE IF NOT EXISTS probe_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL, direction TEXT NOT NULL, sent_at INTEGER,
                    received_at INTEGER NOT NULL, rtt_ms REAL, status TEXT NOT NULL,
                    UNIQUE(client_id, direction, sequence)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    message_id TEXT NOT NULL, original_text TEXT NOT NULL, received_text TEXT NOT NULL,
                    sent_at INTEGER, server_received_at INTEGER NOT NULL, client_received_at INTEGER, rtt_ms REAL,
                    UNIQUE(client_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS event_markers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL, label TEXT NOT NULL, notes TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_probes_client ON probe_samples(client_id, id);
                CREATE INDEX IF NOT EXISTS idx_participants_session ON participants(session_id);
                CREATE INDEX IF NOT EXISTS idx_markers_session ON event_markers(session_id, id);
                """
            )

    def current_session(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE status='active' ORDER BY started_at DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def start_session(self, name: str, instructor: str) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc)
        base_id = timestamp.strftime("session-%Y-%m-%d-%H%M%S")
        with self._lock, self.connect() as db:
            db.execute("UPDATE sessions SET status='stopped', ended_at=? WHERE status='active'", (timestamp.isoformat(),))
            session_id = base_id
            suffix = 1
            while db.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
                suffix += 1
                session_id = f"{base_id}-{suffix}"
            db.execute(
                "INSERT INTO sessions(id,name,status,instructor,started_at) VALUES(?,?,?,?,?)",
                (session_id, name, "active", instructor, timestamp.isoformat()),
            )
        return self.get_session(session_id)

    def stop_session(self) -> dict[str, Any] | None:
        current = self.current_session()
        if not current:
            return None
        with self.connect() as db:
            db.execute("UPDATE sessions SET status='stopped', ended_at=? WHERE id=?", (now_iso(), current["id"]))
        return self.get_session(current["id"])

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["connected_participant_count"] = db.execute(
                "SELECT COUNT(*) FROM participants WHERE session_id=? AND status='online'", (session_id,)
            ).fetchone()[0]
            return result

    def allocate_participant_id(self, session_id: str) -> str:
        """Reserve the next ID in the same transaction that calculates it."""
        with self._lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            number = db.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTR(id,2) AS INTEGER)),0)+1 FROM participants WHERE id GLOB 'P[0-9]*'"
            ).fetchone()[0]
            client_id = f"P{number:03d}"
            timestamp = now_iso()
            db.execute(
                """INSERT INTO participants(id,session_id,connected_at,last_seen,status)
                   VALUES(?,?,?,?,?)""",
                (client_id, session_id, timestamp, timestamp, "connecting"),
            )
            return client_id

    def register_participant(self, data: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self._lock, self.connect() as db:
            existing = db.execute("SELECT * FROM participants WHERE id=?", (data["id"],)).fetchone()
            if existing:
                db.execute(
                    """UPDATE participants SET session_id=?, display_name=?, institution=?, ip_address=?,
                       user_agent=?, browser=?, os=?, disconnected_at=NULL, last_seen=?, status='online' WHERE id=?""",
                    (data["session_id"], data["display_name"], data["institution"], data["ip_address"],
                     data["user_agent"], data["browser"], data["os"], timestamp, data["id"]),
                )
            else:
                db.execute(
                    """INSERT INTO participants(id,session_id,display_name,institution,ip_address,user_agent,
                       browser,os,connected_at,last_seen,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (data["id"], data["session_id"], data["display_name"], data["institution"], data["ip_address"],
                     data["user_agent"], data["browser"], data["os"], timestamp, timestamp, "online"),
                )
        return self.participant(data["id"]) or data

    def mark_disconnected(self, client_id: str) -> None:
        with self.connect() as db:
            timestamp = now_iso()
            db.execute(
                "UPDATE participants SET status='offline', disconnected_at=?, last_seen=? WHERE id=?",
                (timestamp, timestamp, client_id),
            )

    def touch(self, client_id: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE participants SET last_seen=? WHERE id=?", (now_iso(), client_id))

    def record_probe(self, session_id: str, client_id: str, sequence: int, sent_at: int | None,
                     received_at: int, rtt_ms: float | None, status: str) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO probe_samples(session_id,client_id,sequence,direction,sent_at,received_at,rtt_ms,status)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(client_id,direction,sequence) DO UPDATE SET
                   received_at=excluded.received_at,rtt_ms=excluded.rtt_ms,status=excluded.status""",
                (session_id, client_id, sequence, "client_to_server", sent_at, received_at, rtt_ms, status),
            )
            db.execute("UPDATE participants SET last_seen=? WHERE id=?", (now_iso(), client_id))

    def record_message(self, session_id: str, client_id: str, message_id: str, text: str,
                       sent_at: int | None, server_received_at: int) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO messages(session_id,client_id,message_id,original_text,received_text,
                   sent_at,server_received_at) VALUES(?,?,?,?,?,?,?)""",
                (session_id, client_id, message_id, text, text, sent_at, server_received_at),
            )
            db.execute("UPDATE participants SET last_seen=? WHERE id=?", (now_iso(), client_id))

    def participant(self, client_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM participants WHERE id=?", (client_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            probes = db.execute(
                "SELECT rtt_ms,status,received_at FROM probe_samples WHERE client_id=? ORDER BY id", (client_id,)
            ).fetchall()
            values = [row["rtt_ms"] for row in probes if row["status"] in ("success", "late") and row["rtt_ms"] is not None]
            timeouts = sum(row["status"] == "timeout" for row in probes)
            result.update(calculate_rtt_metrics(values, timeouts))
            result["message_count"] = db.execute("SELECT COUNT(*) FROM messages WHERE client_id=?", (client_id,)).fetchone()[0]
            result["probe_count"] = len(probes)
            result["rtt_history"] = [
                {"timestamp": row["received_at"], "rtt_ms": row["rtt_ms"], "status": row["status"]}
                for row in probes[-600:]
            ]
            return result

    def participants(self, session_id: str | None = None, active_only: bool = False,
                    stale_timeout_sec: int = 45) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc).timestamp() - stale_timeout_sec
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
        with self.connect() as db:
            if session_id:
                db.execute(
                    """UPDATE participants SET status='offline', disconnected_at=COALESCE(disconnected_at, ?)
                       WHERE session_id=? AND status IN ('online','connecting') AND last_seen < ?""",
                    (now_iso(), session_id, cutoff_iso),
                )
            if session_id:
                ids = [row[0] for row in db.execute("SELECT id FROM participants WHERE session_id=? ORDER BY id", (session_id,))]
            else:
                ids = [row[0] for row in db.execute("SELECT id FROM participants ORDER BY id")]
        results = [participant for client_id in ids if (participant := self.participant(client_id))]
        return [participant for participant in results if participant["status"] == "online"] if active_only else results

    def delete_participant(self, client_id: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("UPDATE participants SET status='disconnected', disconnected_at=? WHERE id=?", (now_iso(), client_id))
            return cursor.rowcount > 0

    def set_experiment(self, session_id: str, mode: str, label: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("UPDATE sessions SET experiment_mode=?, experiment_label=? WHERE id=?", (mode, label, session_id))
        return self.get_session(session_id) or {}

    def add_marker(self, session_id: str, event_type: str, label: str, notes: str) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO event_markers(session_id,timestamp,event_type,label,notes) VALUES(?,?,?,?,?)",
                (session_id, timestamp, event_type, label, notes),
            )
            row = db.execute("SELECT * FROM event_markers WHERE id=?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def markers(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM event_markers WHERE session_id=? ORDER BY id", (session_id,))]

    def summary(self, session_id: str) -> dict[str, Any]:
        participants = self.participants(session_id)
        online = [p for p in participants if p["status"] == "online"]
        current = [p["current_rtt"] for p in online if p["current_rtt"] is not None]
        all_success = sum(p["success_count"] for p in participants)
        all_timeouts = sum(p["timeout_count"] for p in participants)
        total = all_success + all_timeouts
        return {
            "connected_clients": len(online),
            "active_probes": sum(p["current_rtt"] is not None for p in online),
            "median_client_rtt": round(float(__import__("statistics").median(current)), 2) if current else None,
            "mean_client_rtt": round(sum(current) / len(current), 2) if current else None,
            "p95_client_rtt": percentile(current, 95),
            "average_jitter": round(sum(p["jitter"] for p in online) / len(online), 2) if online else 0.0,
            "total_messages": sum(p["message_count"] for p in participants),
            "total_timeouts": all_timeouts,
            "timeout_percentage": round(all_timeouts / total * 100, 2) if total else 0.0,
        }

    def export_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        if not session:
            return None
        return {
            "session": session,
            "participants": self.participants(session_id),
            "event_markers": self.markers(session_id),
            "summary": self.summary(session_id),
            "exported_at": now_iso(),
        }
