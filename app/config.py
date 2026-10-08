"""Konfiguráció környezeti változókból."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "igen")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    port: int
    max_upload_bytes: int
    backup_enabled: bool
    backup_keep_days: int
    log_level: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        port=_int("PORT", 8000),
        max_upload_bytes=_int("MAX_UPLOAD_MB", 2) * 1024 * 1024,
        backup_enabled=_bool("BACKUP_ENABLED", True),
        backup_keep_days=_int("BACKUP_KEEP_DAYS", 14),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
