"""Csomagok tárolása, listázása, haladás számolása."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import Tx, now_iso
from .text import escape_like, normalize, search_terms
from .validator import ITEM_KINDS, ValidationResult, validate_data

META_LIMITS = {"title": 120, "topic": 200, "subject": 60, "level": 40}
SORTS = ("recent", "uploaded", "title")


class MetaError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(e["text"] for e in errors))
        self.errors = errors


def _issue(path: str, msg: str) -> dict[str, str]:
    return {"path": path, "message": msg, "text": f"{path}: {msg}"}


def clean_meta(meta: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    """Metaadat-űrlap ellenőrzése. partial=True: csak a megadott mezők (PATCH)."""
    out: dict[str, Any] = {}
    errors = []
    for key, limit in META_LIMITS.items():
        if key not in meta:
            if not partial and key != "level":
                errors.append(_issue(key, "kötelező mező hiányzik"))
            continue
        v = meta[key]
        if v is None and key == "level":
            out[key] = None
            continue
        if not isinstance(v, str):
            errors.append(_issue(key, "szöveg kell legyen"))
            continue
        v = v.strip()
        if not v and key != "level":
            errors.append(_issue(key, "nem lehet üres"))
            continue
        if len(v) > limit:
            errors.append(_issue(key, f"túl hosszú: {len(v)} karakter (legfeljebb {limit})"))
            continue
        out[key] = v or None
    if "tags" in meta:
        tags = meta["tags"]
        if tags is None:
            tags = []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            errors.append(_issue("tags", "szövegek listája kell legyen"))
        else:
            cleaned, seen = [], set()
            for t in tags:
                t = t.strip()
                if not t or normalize(t) in seen:
                    continue
                if len(t) > 40:
                    errors.append(_issue("tags", f'"{t[:20]}…" túl hosszú (legfeljebb 40 karakter)'))
                seen.add(normalize(t))
                cleaned.append(t)
            if len(cleaned) > 10:
                errors.append(_issue("tags", f"túl sok címke: {len(cleaned)} (legfeljebb 10)"))
            out["tags"] = cleaned
    elif not partial:
        out["tags"] = []
    if errors:
        raise MetaError(errors)
    return out


def make_search_text(title: str, topic: str, subject: str, tags: list[str], level: str | None) -> str:
    return normalize(" ".join([title, topic, subject, " ".join(tags), level or ""]))


def rebuild_items(conn: sqlite3.Connection, pack_id: str, item_ids: dict[str, list[str]]) -> None:
    conn.execute("DELETE FROM pack_items WHERE pack_id = ?", (pack_id,))
    rows = [(pack_id, kind, iid) for kind in ITEM_KINDS for iid in dict.fromkeys(item_ids.get(kind, []))]
    conn.executemany("INSERT INTO pack_items (pack_id, kind, item_id) VALUES (?, ?, ?)", rows)


def save_pack(conn: sqlite3.Connection, result: ValidationResult, raw_json: str,
              meta_override: dict[str, Any] | None, profile_id: int | None) -> dict[str, Any]:
    """Új csomag vagy új verzió mentése. A haladás az azonosítókhoz kötődik, nem nyúlunk hozzá."""
    assert result.ok and result.data is not None
    json_meta = result.meta()
    pack_id = json_meta["id"]
    merged = {k: json_meta.get(k) for k in ("title", "topic", "subject", "tags", "level")}
    for k, v in (meta_override or {}).items():
        if k in merged:
            merged[k] = v
    meta = clean_meta(merged)
    ts = now_iso()
    search = make_search_text(meta["title"], meta["topic"], meta["subject"], meta["tags"], meta.get("level"))
    with Tx(conn):
        row = conn.execute("SELECT current_version FROM packs WHERE id = ?", (pack_id,)).fetchone()
        if row:
            version = row["current_version"] + 1
            conn.execute(
                """UPDATE packs SET title=?, topic=?, subject=?, tags=?, level=?, current_version=?,
                   archived=0, search_text=?, updated_at=? WHERE id=?""",
                (meta["title"], meta["topic"], meta["subject"], json.dumps(meta["tags"], ensure_ascii=False),
                 meta.get("level"), version, search, ts, pack_id),
            )
        else:
            version = 1
            conn.execute(
                """INSERT INTO packs (id, title, topic, subject, tags, level, current_version, archived,
                   search_text, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)""",
                (pack_id, meta["title"], meta["topic"], meta["subject"],
                 json.dumps(meta["tags"], ensure_ascii=False), meta.get("level"), search, ts, ts),
            )
        conn.execute(
            "INSERT INTO pack_versions (pack_id, version, json, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (pack_id, version, raw_json, profile_id, ts),
        )
        rebuild_items(conn, pack_id, result.item_ids())
    return {"id": pack_id, "version": version, "created": version == 1}


def update_meta(conn: sqlite3.Connection, pack_id: str, changes: dict[str, Any]) -> None:
    row = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
    if row is None:
        raise KeyError(pack_id)
    meta_changes = clean_meta({k: v for k, v in changes.items() if k in (*META_LIMITS, "tags")}, partial=True)
    cur = pack_row(row)
    cur.update(meta_changes)
    archived = row["archived"]
    if "archived" in changes:
        archived = 1 if changes["archived"] else 0
    search = make_search_text(cur["title"], cur["topic"], cur["subject"], cur["tags"], cur.get("level"))
    with Tx(conn):
        conn.execute(
            """UPDATE packs SET title=?, topic=?, subject=?, tags=?, level=?, archived=?, search_text=?,
               updated_at=? WHERE id=?""",
            (cur["title"], cur["topic"], cur["subject"], json.dumps(cur["tags"], ensure_ascii=False),
             cur.get("level"), archived, search,
             now_iso() if meta_changes else row["updated_at"], pack_id),
        )


def pack_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "topic": row["topic"],
        "subject": row["subject"],
        "tags": json.loads(row["tags"] or "[]"),
        "level": row["level"],
        "current_version": row["current_version"],
        "archived": bool(row["archived"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_packs(conn: sqlite3.Connection, profile_id: int | None, q: str = "", subject: str = "",
               tag: str = "", sort: str = "recent", archived: bool = False) -> dict[str, Any]:
    sql = "SELECT * FROM packs WHERE archived = ?"
    params: list[Any] = [1 if archived else 0]
    for term in search_terms(q):
        sql += " AND search_text LIKE ? ESCAPE '\\'"
        params.append(f"%{escape_like(term)}%")
    rows = [pack_row(r) for r in conn.execute(sql, params)]

    # Szűrők és facetták (a facetták a nem archivált, szűretlen listából)
    if subject:
        rows = [r for r in rows if normalize(r["subject"]) == normalize(subject)]
    if tag:
        rows = [r for r in rows if normalize(tag) in {normalize(t) for t in r["tags"]}]

    counts: dict[str, dict[str, int]] = {}
    for r in conn.execute("SELECT pack_id, kind, COUNT(*) AS n FROM pack_items GROUP BY pack_id, kind"):
        counts.setdefault(r["pack_id"], {})[r["kind"]] = r["n"]

    progress: dict[str, dict[str, int]] = {}
    opened: dict[str, str] = {}
    if profile_id is not None:
        for r in conn.execute(
            """SELECT cp.pack_id, cp.status, COUNT(*) AS n FROM card_progress cp
               JOIN pack_items pi ON pi.pack_id = cp.pack_id AND pi.kind = 'cards' AND pi.item_id = cp.item_id
               WHERE cp.profile_id = ? GROUP BY cp.pack_id, cp.status""",
            (profile_id,),
        ):
            progress.setdefault(r["pack_id"], {})[r["status"]] = r["n"]
        for r in conn.execute("SELECT pack_id, opened_at FROM last_opened WHERE profile_id = ?", (profile_id,)):
            opened[r["pack_id"]] = r["opened_at"]

    for r in rows:
        c = counts.get(r["id"], {})
        r["counts"] = {k: c.get(k, 0) for k in ITEM_KINDS}
        p = progress.get(r["id"], {})
        r["progress"] = None if profile_id is None else {
            "known": p.get("known", 0),
            "learning": p.get("learning", 0),
            "total": r["counts"]["cards"],
        }
        r["last_opened_at"] = opened.get(r["id"])

    if sort == "title":
        rows.sort(key=lambda r: (normalize(r["title"]), r["title"]))
    elif sort == "uploaded":
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
    else:  # recent: legutóbb megnyitott elöl, a soha meg nem nyitottak feltöltés szerint utána
        rows.sort(key=lambda r: (r["last_opened_at"] or "", r["updated_at"]), reverse=True)

    subjects: dict[str, str] = {}
    tags: dict[str, str] = {}
    for r in conn.execute("SELECT subject, tags FROM packs WHERE archived = 0"):
        subjects.setdefault(normalize(r["subject"]), r["subject"])
        for t in json.loads(r["tags"] or "[]"):
            tags.setdefault(normalize(t), t)
    archived_count = conn.execute("SELECT COUNT(*) FROM packs WHERE archived = 1").fetchone()[0]
    return {
        "items": rows,
        "subjects": sorted(subjects.values(), key=normalize),
        "tags": sorted(tags.values(), key=normalize),
        "archived_count": archived_count,
    }


def get_pack(conn: sqlite3.Connection, pack_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
    if row is None:
        return None
    v = conn.execute(
        "SELECT json FROM pack_versions WHERE pack_id = ? AND version = ?", (pack_id, row["current_version"])
    ).fetchone()
    versions = [
        {"version": r["version"], "uploaded_at": r["uploaded_at"], "uploaded_by": r["name"]}
        for r in conn.execute(
            """SELECT pv.version, pv.uploaded_at, p.name FROM pack_versions pv
               LEFT JOIN profiles p ON p.id = pv.uploaded_by WHERE pv.pack_id = ? ORDER BY pv.version DESC""",
            (pack_id,),
        )
    ]
    return {"pack": pack_row(row), "content": json.loads(v["json"]), "versions": versions}


def items_from_json(raw_json: str) -> dict[str, list[str]]:
    """Elemazonosítók kinyerése egy már tárolt verzióból (importnál)."""
    return validate_data(json.loads(raw_json)).item_ids()
