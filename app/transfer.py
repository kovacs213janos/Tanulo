"""Teljes export és visszatöltés (tanulo-export/1)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import __version__
from .db import Tx, now_iso
from .packs import items_from_json

FORMAT = "tanulo-export/1"

# tábla -> oszlopok, a visszatöltés sorrendjében (idegen kulcsok miatt)
TABLES: dict[str, list[str]] = {
    "profiles": ["id", "name", "color", "role", "created_at"],
    "packs": ["id", "title", "topic", "subject", "tags", "level", "current_version", "archived",
              "search_text", "created_at", "updated_at"],
    "pack_versions": ["pack_id", "version", "json", "uploaded_by", "uploaded_at"],
    "card_progress": ["profile_id", "pack_id", "item_id", "status", "seen_count", "last_seen_at"],
    "review_log": ["id", "profile_id", "pack_id", "item_id", "rating", "reviewed_at"],
    "quiz_attempts": ["id", "profile_id", "pack_id", "chapter", "score", "max", "wrong_ids", "taken_at"],
    "task_answers": ["profile_id", "pack_id", "task_id", "question_id", "answer", "updated_at"],
    "last_opened": ["profile_id", "pack_id", "opened_at"],
}
DELETE_ORDER = ["last_opened", "task_answers", "quiz_attempts", "review_log", "card_progress",
                "pack_items", "pack_versions", "packs", "profiles"]


def export_all(conn: sqlite3.Connection) -> dict[str, Any]:
    out: dict[str, Any] = {"format": FORMAT, "app_version": __version__, "exported_at": now_iso()}
    for table, cols in TABLES.items():
        rows = []
        for r in conn.execute(f"SELECT {', '.join(cols)} FROM {table}"):
            d = dict(r)
            if table == "pack_versions":
                d["json"] = json.loads(d["json"])  # olvasható, nem escape-elt JSON
            if table == "packs":
                d["tags"] = json.loads(d["tags"] or "[]")
                d.pop("search_text", None)
            if table == "quiz_attempts":
                d["wrong_ids"] = json.loads(d["wrong_ids"] or "[]")
            rows.append(d)
        out[table] = rows
    return out


class ImportError_(ValueError):
    pass


def import_all(conn: sqlite3.Connection, data: Any) -> dict[str, int]:
    """Minden meglévő adatot lecserél az exportban lévőre, egyetlen tranzakcióban."""
    from .packs import make_search_text, rebuild_items

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ImportError_(f'nem tanulóplatform-export (a "format" mező értéke "{FORMAT}" kell legyen)')
    for table in TABLES:
        if not isinstance(data.get(table, []), list):
            raise ImportError_(f'a(z) "{table}" rész tömb kell legyen')

    counts: dict[str, int] = {}
    with Tx(conn):
        for table in DELETE_ORDER:
            conn.execute(f"DELETE FROM {table}")
        for table, cols in TABLES.items():
            rows = data.get(table, [])
            for i, r in enumerate(rows):
                if not isinstance(r, dict):
                    raise ImportError_(f"{table}[{i}]: objektum kell legyen")
                d = dict(r)
                if table == "pack_versions" and not isinstance(d.get("json"), str):
                    d["json"] = json.dumps(d.get("json"), ensure_ascii=False)
                if table == "packs":
                    tags = d.get("tags") or []
                    d["tags"] = json.dumps(tags, ensure_ascii=False) if not isinstance(tags, str) else tags
                    tag_list = json.loads(d["tags"])
                    d["search_text"] = make_search_text(d.get("title", ""), d.get("topic", ""),
                                                        d.get("subject", ""), tag_list, d.get("level"))
                if table == "quiz_attempts" and not isinstance(d.get("wrong_ids"), str):
                    d["wrong_ids"] = json.dumps(d.get("wrong_ids") or [])
                try:
                    conn.execute(
                        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        [d.get(c) for c in cols],
                    )
                except sqlite3.Error as e:
                    raise ImportError_(f"{table}[{i}]: nem tölthető be ({e})") from e
            counts[table] = len(rows)
        for p in conn.execute("SELECT id, current_version FROM packs").fetchall():
            v = conn.execute("SELECT json FROM pack_versions WHERE pack_id = ? AND version = ?",
                             (p["id"], p["current_version"])).fetchone()
            if v is None:
                raise ImportError_(f'packs: a(z) "{p["id"]}" csomag aktuális verziója ({p["current_version"]}) hiányzik')
            rebuild_items(conn, p["id"], items_from_json(v["json"]))
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            t = problems[0][0]
            raise ImportError_(f"hivatkozási hiba a(z) {t} táblában ({len(problems)} sor)")
    return counts
