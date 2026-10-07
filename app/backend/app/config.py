from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file() -> None:
    """Load simple KEY=VALUE entries without adding a runtime dependency."""
    path = Path.cwd() / ".env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


_load_env_file()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = _int_env("PORT", 8080)
    public_host: str = os.getenv("PUBLIC_HOST", "netsimemulation.ddns.net")
    probe_interval_ms: int = _int_env("PROBE_INTERVAL_MS", 1000)
    probe_timeout_ms: int = _int_env("PROBE_TIMEOUT_MS", 5000)
    session_name: str = os.getenv("SESSION_NAME", "NetSim Online Emulation Demo")
    admin_token: str = os.getenv("ADMIN_TOKEN", "change-me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./netsim_demo.db")
    allowed_origins: tuple[str, ...] = tuple(
        value.strip().rstrip("/")
        for value in os.getenv("ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    )
    max_message_bytes: int = _int_env("MAX_MESSAGE_BYTES", 16384)
    participant_stale_timeout_sec: int = _int_env("PARTICIPANT_STALE_TIMEOUT_SEC", 45)
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    mediamtx_path: str = os.getenv("MEDIAMTX_PATH", "mediamtx")
    bandwidth_test_max_seconds: int = _int_env("BANDWIDTH_TEST_MAX_SECONDS", 10)
    bandwidth_test_max_bytes: int = _int_env("BANDWIDTH_TEST_MAX_BYTES", 50 * 1024 * 1024)
    bandwidth_test_max_concurrent: int = _int_env("BANDWIDTH_TEST_MAX_CONCURRENT", 4)

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported in the MVP")
        path = Path(self.database_url[len(prefix) :])
        return path if path.is_absolute() else Path.cwd() / path


settings = Settings()
