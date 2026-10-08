"""SQLite-kapcsolat és séma.

Egy fájl (DATA_DIR/app.db), WAL mód, idegen kulcsok bekapcsolva.
Sémaverzió a PRAGMA user_version-ben; új migráció = új elem a MIGRATIONS listában.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1: alapséma
    """
    CREATE TABLE profiles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        color       TEXT NOT NULL,
        role        TEXT NOT NULL CHECK (role IN ('parent', 'child')),
        created_at  TEXT NOT NULL
    );

    CREATE TABLE packs (
        id              TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        topic           TEXT NOT NULL,
        subject         TEXT NOT NULL,
        tags            TEXT NOT NULL DEFAULT '[]',
        level           TEXT,
        current_version INTEGER NOT NULL,
        archived        INTEGER NOT NULL DEFAULT 0,
        search_text     TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );

    CREATE TABLE pack_versions (
        pack_id     TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        version     INTEGER NOT NULL,
        json        TEXT NOT NULL,
        uploaded_by INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
        uploaded_at TEXT NOT NULL,
        PRIMARY KEY (pack_id, version)
    );

    -- Az aktuális verzió elemazonosítói; ebből számol a lista ("Tudom: 34/160").
    CREATE TABLE pack_items (
        pack_id TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        kind    TEXT NOT NULL,
        item_id TEXT NOT NULL,
        PRIMARY KEY (pack_id, kind, item_id)
    );

    CREATE TABLE card_progress (
        profile_id   INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        pack_id      TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        item_id      TEXT NOT NULL,
        status       TEXT NOT NULL CHECK (status IN ('new', 'learning', 'known')),
        seen_count   INTEGER NOT NULL DEFAULT 0,
        last_seen_at TEXT,
        PRIMARY KEY (profile_id, pack_id, item_id)
    );

    -- Minden jelölés naplója: a v2 (FSRS) ebből indulhat.
    CREATE TABLE review_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        pack_id     TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        item_id     TEXT NOT NULL,
        rating      TEXT NOT NULL,
        reviewed_at TEXT NOT NULL
    );
    CREATE INDEX review_log_lookup ON review_log (profile_id, pack_id, item_id);

    CREATE TABLE quiz_attempts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        pack_id    TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        chapter    TEXT,
        score      INTEGER NOT NULL,
        max        INTEGER NOT NULL,
        wrong_ids  TEXT NOT NULL DEFAULT '[]',
        taken_at   TEXT NOT NULL
    );
    CREATE INDEX quiz_attempts_lookup ON quiz_attempts (profile_id, pack_id, taken_at);

    CREATE TABLE task_answers (
        profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        pack_id     TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        task_id     TEXT NOT NULL,
        question_id TEXT NOT NULL,
        answer      TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        PRIMARY KEY (profile_id, pack_id, task_id, question_id)
    );

    CREATE TABLE last_opened (
        profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        pack_id    TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
        opened_at  TEXT NOT NULL,
        PRIMARY KEY (profile_id, pack_id)
    );
    """,
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    # check_same_thread=False: egy kérésen belül a kapcsolat szálak között vándorolhat (async végpont),
    # de egyszerre mindig csak egy szál használja.
    conn = sqlite3.connect(db_path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, sql in enumerate(MIGRATIONS, start=1):
            if i <= current:
                continue
            conn.execute("BEGIN IMMEDIATE")
            try:
                # executescript() saját COMMIT-ot adna ki, ezért utasításonként futtatjuk
                for stmt in _split_sql(sql):
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {i}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


def _split_sql(script: str) -> list[str]:
    """Egyszerű szétbontás ';' mentén (a séma nem tartalmaz ';'-t szövegben)."""
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


class Tx:
    """Kontextuskezelő: BEGIN IMMEDIATE ... COMMIT / ROLLBACK."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
