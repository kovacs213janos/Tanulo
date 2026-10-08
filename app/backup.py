"""Napi, tranzakcióbiztos adatbázismentés VACUUM INTO-val, megőrzési idővel.

A futó WAL-os adatbázis fájlszintű másolata inkonzisztens lehet; a VACUUM INTO
egy konzisztens pillanatképet ír egy új fájlba.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from .db import connect

log = logging.getLogger("tanulo.backup")
NAME_RE = re.compile(r"^app-(\d{8})\.db$")
CHECK_INTERVAL_S = 30 * 60


def backup_path(backup_dir: Path, day: date) -> Path:
    return backup_dir / f"app-{day:%Y%m%d}.db"


def make_backup(db_path: Path, backup_dir: Path, day: date | None = None) -> Path:
    """Elkészíti az adott napi mentést (ha már van, felülírja)."""
    day = day or datetime.now().date()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_path(backup_dir, day)
    tmp = target.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = connect(db_path)
    try:
        conn.execute("VACUUM INTO ?", (str(tmp),))
    finally:
        conn.close()
    tmp.replace(target)
    return target


def prune(backup_dir: Path, keep_days: int, today: date | None = None) -> list[Path]:
    today = today or datetime.now().date()
    cutoff = today - timedelta(days=max(keep_days, 1) - 1)
    removed = []
    if not backup_dir.exists():
        return removed
    for p in backup_dir.iterdir():
        m = NAME_RE.match(p.name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y%m%d").date()
        if d < cutoff:
            p.unlink()
            removed.append(p)
    return removed


def run_once(db_path: Path, backup_dir: Path, keep_days: int) -> Path | None:
    """Ha mára még nincs mentés, elkészíti; utána takarít. Visszaadja az új fájlt."""
    today = datetime.now().date()
    made = None
    if not backup_path(backup_dir, today).exists():
        made = make_backup(db_path, backup_dir, today)
        log.info("adatbázismentés kész: %s", made)
    for p in prune(backup_dir, keep_days, today):
        log.info("régi mentés törölve: %s", p.name)
    return made


class BackupThread(threading.Thread):
    def __init__(self, db_path: Path, backup_dir: Path, keep_days: int):
        super().__init__(name="backup", daemon=True)
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.keep_days = keep_days
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                run_once(self.db_path, self.backup_dir, self.keep_days)
            except Exception:  # a mentés hibája ne állítsa le az alkalmazást
                log.exception("adatbázismentés sikertelen")
            self.stop_event.wait(CHECK_INTERVAL_S)

    def stop(self) -> None:
        self.stop_event.set()
