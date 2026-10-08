"""Tanulóplatform – FastAPI alkalmazás."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field

from . import __version__, backup, packs, transfer
from .config import Settings, load_settings
from .db import Tx, connect, init_db, now_iso
from .validator import ID_RE, validate_text

log = logging.getLogger("tanulo")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
PALETTE = ["#e4572e", "#2e86ab", "#3bb273", "#7768ae", "#f2a541", "#d1495b", "#00a6a6", "#8c6a5d"]
IMPORT_EXTRA_BYTES = 200 * 1024 * 1024


# ------------------------------------------------------------------ alkalmazás
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings.db_path)
        log.info("tanulóplatform %s indul, adatbázis: %s", __version__, settings.db_path)
        thread = None
        if settings.backup_enabled:
            thread = backup.BackupThread(settings.db_path, settings.backup_dir, settings.backup_keep_days)
            thread.start()
        yield
        if thread:
            thread.stop()

    app = FastAPI(title="Tanulóplatform", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings = settings
    # Tesztekhez és lifespan nélküli futtatáshoz is legyen séma.
    try:
        init_db(settings.db_path)
    except (PermissionError, sqlite3.OperationalError) as e:
        raise RuntimeError(
            f"Az adatkönyvtár ({settings.data_dir}) nem írható ({e}). Dockerben a konténer a 10001-es "
            "felhasználóként fut; a gépen: sudo chown -R 10001:10001 ./data"
        ) from e

    @app.middleware("http")
    async def limits_and_cache(request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit():
            limit = IMPORT_EXTRA_BYTES if request.url.path == "/api/import" else settings.max_upload_bytes * 2 + 65536
            if int(cl) > limit:
                return JSONResponse({"detail": "A kérés túl nagy."}, status_code=413)
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errs = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query", "path"))
            errs.append({"path": loc, "message": e.get("msg", ""), "text": f"{loc}: {e.get('msg', '')}"})
        return JSONResponse({"detail": "Hibás kérés.", "errors": errs}, status_code=422)

    register_routes(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app


# ------------------------------------------------------------------ függőségek
def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_profile(conn: sqlite3.Connection = Depends(get_conn),
                x_profile_id: str | None = Header(default=None)) -> sqlite3.Row | None:
    if x_profile_id is None or x_profile_id.strip() == "":
        return None
    if not x_profile_id.isdigit():
        raise HTTPException(401, detail={"message": "Ismeretlen profil, válassz újra.", "code": "unknown_profile"})
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (int(x_profile_id),)).fetchone()
    if row is None:
        raise HTTPException(401, detail={"message": "Ismeretlen profil, válassz újra.", "code": "unknown_profile"})
    return row


def require_profile(profile: sqlite3.Row | None = Depends(get_profile)) -> sqlite3.Row:
    if profile is None:
        raise HTTPException(401, detail={"message": "Előbb válassz profilt.", "code": "no_profile"})
    return profile


def require_parent(profile: sqlite3.Row = Depends(require_profile)) -> sqlite3.Row:
    if profile["role"] != "parent":
        raise HTTPException(403, detail={"message": "Ehhez szülői profil kell.", "code": "parent_only"})
    return profile


def err(status: int, message: str, code: str = "error", **extra: Any) -> HTTPException:
    return HTTPException(status, detail={"message": message, "code": code, **extra})


def check_pack_id(pack_id: str) -> None:
    if not ID_RE.match(pack_id):
        raise err(404, "Nincs ilyen anyag.", "not_found")


def profile_dict(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "name": r["name"], "color": r["color"], "role": r["role"], "created_at": r["created_at"]}


# ------------------------------------------------------------------ modellek
class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = None
    role: Literal["parent", "child"] = "child"


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = None
    role: Literal["parent", "child"] | None = None


class UploadIn(BaseModel):
    content: str
    meta: dict[str, Any] | None = None


class PackPatch(BaseModel):
    title: str | None = None
    topic: str | None = None
    subject: str | None = None
    tags: list[str] | None = None
    level: str | None = None
    archived: bool | None = None


class CardMark(BaseModel):
    item_id: str
    status: Literal["new", "learning", "known"]


class TaskAnswer(BaseModel):
    task_id: str
    question_id: str
    answer: str = Field(max_length=10000)


class ProgressIn(BaseModel):
    cards: list[CardMark] = Field(default_factory=list, max_length=2000)
    answers: list[TaskAnswer] = Field(default_factory=list, max_length=500)


class QuizIn(BaseModel):
    chapter: str | None = None
    score: int = Field(ge=0)
    max: int = Field(ge=1, le=1000)
    wrong_ids: list[str] = Field(default_factory=list, max_length=1000)


# ------------------------------------------------------------------ útvonalak
def register_routes(app: FastAPI) -> None:
    settings: Settings = app.state.settings

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: HTTPException):
        d = exc.detail
        body = d if isinstance(d, dict) else {"message": str(d), "code": "error"}
        body = {"detail": body.get("message"), **{k: v for k, v in body.items() if k != "message"}}
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    # ---------------- állapot
    @app.get("/api/health")
    def health(conn: sqlite3.Connection = Depends(get_conn)):
        conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "version": __version__,
                "schema_version": conn.execute("PRAGMA user_version").fetchone()[0]}

    @app.get("/api/config")
    def config():
        return {"version": __version__, "max_upload_bytes": settings.max_upload_bytes}

    # ---------------- profilok
    @app.get("/api/profiles")
    def list_profiles(conn: sqlite3.Connection = Depends(get_conn)):
        return [profile_dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY id")]

    @app.post("/api/profiles", status_code=201)
    def create_profile(body: ProfileIn, conn: sqlite3.Connection = Depends(get_conn),
                       profile: sqlite3.Row | None = Depends(get_profile)):
        count = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        if count == 0:
            if body.role != "parent":
                raise err(422, "Az első profil szülői kell legyen, hogy kezelni tudja a többit.", "first_parent")
        elif profile is None or profile["role"] != "parent":
            raise err(403, "Új profilt csak szülői profillal lehet létrehozni.", "parent_only")
        name = body.name.strip()
        if not name:
            raise err(422, "A név nem lehet üres.", "invalid")
        color = body.color or PALETTE[count % len(PALETTE)]
        if not COLOR_RE.match(color):
            raise err(422, "A szín formátuma #rrggbb.", "invalid")
        with Tx(conn):
            cur = conn.execute("INSERT INTO profiles (name, color, role, created_at) VALUES (?, ?, ?, ?)",
                               (name, color.lower(), body.role, now_iso()))
        return profile_dict(conn.execute("SELECT * FROM profiles WHERE id = ?", (cur.lastrowid,)).fetchone())

    def parents_count(conn: sqlite3.Connection) -> int:
        return conn.execute("SELECT COUNT(*) FROM profiles WHERE role = 'parent'").fetchone()[0]

    @app.patch("/api/profiles/{profile_id}")
    def patch_profile(profile_id: int, body: ProfilePatch, conn: sqlite3.Connection = Depends(get_conn),
                      _: sqlite3.Row = Depends(require_parent)):
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise err(404, "Nincs ilyen profil.", "not_found")
        name = body.name.strip() if body.name is not None else row["name"]
        color = body.color if body.color is not None else row["color"]
        role = body.role or row["role"]
        if not name:
            raise err(422, "A név nem lehet üres.", "invalid")
        if not COLOR_RE.match(color):
            raise err(422, "A szín formátuma #rrggbb.", "invalid")
        if row["role"] == "parent" and role == "child" and parents_count(conn) <= 1:
            raise err(409, "Legalább egy szülői profilnak maradnia kell.", "last_parent")
        with Tx(conn):
            conn.execute("UPDATE profiles SET name=?, color=?, role=? WHERE id=?", (name, color.lower(), role, profile_id))
        return profile_dict(conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone())

    @app.delete("/api/profiles/{profile_id}")
    def delete_profile(profile_id: int, confirm: str = Query(default=""),
                       conn: sqlite3.Connection = Depends(get_conn), _: sqlite3.Row = Depends(require_parent)):
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise err(404, "Nincs ilyen profil.", "not_found")
        if confirm != str(profile_id):
            raise err(400, "A törléshez megerősítés kell.", "confirm_required")
        if row["role"] == "parent" and parents_count(conn) <= 1:
            raise err(409, "Az utolsó szülői profil nem törölhető.", "last_parent")
        with Tx(conn):
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        return {"deleted": profile_id}

    # ---------------- csomagok
    @app.get("/api/packs")
    def get_packs(q: str = "", subject: str = "", tag: str = "",
                  sort: Literal["recent", "uploaded", "title"] = "recent", archived: bool = False,
                  conn: sqlite3.Connection = Depends(get_conn),
                  profile: sqlite3.Row | None = Depends(get_profile)):
        return packs.list_packs(conn, profile["id"] if profile else None, q=q[:200], subject=subject,
                                tag=tag, sort=sort, archived=archived)

    @app.get("/api/packs/{pack_id}")
    def get_pack(pack_id: str, conn: sqlite3.Connection = Depends(get_conn),
                 profile: sqlite3.Row | None = Depends(get_profile)):
        check_pack_id(pack_id)
        result = packs.get_pack(conn, pack_id)
        if result is None:
            raise err(404, "Nincs ilyen anyag.", "not_found")
        if profile is not None:
            with Tx(conn):
                conn.execute(
                    """INSERT INTO last_opened (profile_id, pack_id, opened_at) VALUES (?, ?, ?)
                       ON CONFLICT (profile_id, pack_id) DO UPDATE SET opened_at = excluded.opened_at""",
                    (profile["id"], pack_id, now_iso()),
                )
        return result

    async def read_raw(request: Request) -> bytes:
        return await request.body()

    def validation_payload(conn: sqlite3.Connection, raw: bytes) -> tuple[Any, dict[str, Any]]:
        result = validate_text(raw, settings.max_upload_bytes)
        payload = result.as_dict()
        payload["existing"] = None
        if result.ok:
            row = conn.execute("SELECT * FROM packs WHERE id = ?", (result.meta()["id"],)).fetchone()
            if row is not None:
                payload["existing"] = {**packs.pack_row(row), "next_version": row["current_version"] + 1}
        return result, payload

    @app.post("/api/packs/validate")
    async def validate_pack(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
        """Törzs: a csomag nyers JSON-szövege (vagy {"content": "..."})."""
        raw = await read_raw(request)
        raw = _unwrap_content(raw)
        _, payload = validation_payload(conn, raw)
        return payload

    @app.post("/api/packs", status_code=201)
    def upload_pack(body: UploadIn, conn: sqlite3.Connection = Depends(get_conn),
                    profile: sqlite3.Row = Depends(require_parent)):
        raw = body.content.encode("utf-8")
        result, payload = validation_payload(conn, raw)
        if not result.ok:
            raise err(422, "A csomag hibás, nem menthető.", "invalid_pack",
                      errors=payload["errors"], warnings=payload["warnings"])
        try:
            saved = packs.save_pack(conn, result, body.content.lstrip("﻿"), body.meta, profile["id"])
        except packs.MetaError as e:
            raise err(422, "A metaadatok hibásak.", "invalid_meta", errors=e.errors)
        log.info("csomag mentve: %s v%s (%s)", saved["id"], saved["version"], profile["name"])
        return {**saved, "counts": result.counts(), "warnings": payload["warnings"]}

    @app.patch("/api/packs/{pack_id}")
    def patch_pack(pack_id: str, body: PackPatch, conn: sqlite3.Connection = Depends(get_conn),
                   _: sqlite3.Row = Depends(require_parent)):
        check_pack_id(pack_id)
        changes = body.model_dump(exclude_unset=True)
        try:
            packs.update_meta(conn, pack_id, changes)
        except KeyError:
            raise err(404, "Nincs ilyen anyag.", "not_found")
        except packs.MetaError as e:
            raise err(422, "A metaadatok hibásak.", "invalid_meta", errors=e.errors)
        return packs.pack_row(conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone())

    @app.delete("/api/packs/{pack_id}")
    def delete_pack(pack_id: str, confirm: str = Query(default=""),
                    conn: sqlite3.Connection = Depends(get_conn), profile: sqlite3.Row = Depends(require_parent)):
        check_pack_id(pack_id)
        if conn.execute("SELECT 1 FROM packs WHERE id = ?", (pack_id,)).fetchone() is None:
            raise err(404, "Nincs ilyen anyag.", "not_found")
        if confirm != pack_id:
            raise err(400, "A végleges törléshez írd be az anyag azonosítóját.", "confirm_required")
        with Tx(conn):
            conn.execute("DELETE FROM packs WHERE id = ?", (pack_id,))  # minden haladás kaszkáddal törlődik
        log.info("csomag véglegesen törölve: %s (%s)", pack_id, profile["name"])
        return {"deleted": pack_id}

    # ---------------- haladás
    def pack_exists(conn: sqlite3.Connection, pack_id: str) -> None:
        check_pack_id(pack_id)
        if conn.execute("SELECT 1 FROM packs WHERE id = ?", (pack_id,)).fetchone() is None:
            raise err(404, "Nincs ilyen anyag.", "not_found")

    @app.get("/api/progress/{pack_id}")
    def get_progress(pack_id: str, conn: sqlite3.Connection = Depends(get_conn),
                     profile: sqlite3.Row = Depends(require_profile)):
        pack_exists(conn, pack_id)
        pid = profile["id"]
        cards = {
            r["item_id"]: {"status": r["status"], "seen_count": r["seen_count"], "last_seen_at": r["last_seen_at"]}
            for r in conn.execute("SELECT * FROM card_progress WHERE profile_id = ? AND pack_id = ?", (pid, pack_id))
        }
        answers: dict[str, dict[str, str]] = {}
        for r in conn.execute("SELECT * FROM task_answers WHERE profile_id = ? AND pack_id = ?", (pid, pack_id)):
            answers.setdefault(r["task_id"], {})[r["question_id"]] = r["answer"]
        quiz = [
            {"id": r["id"], "chapter": r["chapter"], "score": r["score"], "max": r["max"],
             "wrong_ids": json.loads(r["wrong_ids"]), "taken_at": r["taken_at"]}
            for r in conn.execute(
                "SELECT * FROM quiz_attempts WHERE profile_id = ? AND pack_id = ? ORDER BY taken_at DESC, id DESC LIMIT 10",
                (pid, pack_id))
        ]
        return {"cards": cards, "answers": answers, "quiz_attempts": quiz}

    @app.put("/api/progress/{pack_id}")
    def put_progress(pack_id: str, body: ProgressIn, conn: sqlite3.Connection = Depends(get_conn),
                     profile: sqlite3.Row = Depends(require_profile)):
        pack_exists(conn, pack_id)
        pid = profile["id"]
        valid = {(r["kind"], r["item_id"]) for r in conn.execute(
            "SELECT kind, item_id FROM pack_items WHERE pack_id = ?", (pack_id,))}
        ts = now_iso()
        ignored = 0
        with Tx(conn):
            for m in body.cards:
                if ("cards", m.item_id) not in valid:
                    ignored += 1
                    continue
                conn.execute(
                    """INSERT INTO card_progress (profile_id, pack_id, item_id, status, seen_count, last_seen_at)
                       VALUES (?, ?, ?, ?, 1, ?)
                       ON CONFLICT (profile_id, pack_id, item_id) DO UPDATE SET
                         status = excluded.status, seen_count = card_progress.seen_count + 1,
                         last_seen_at = excluded.last_seen_at""",
                    (pid, pack_id, m.item_id, m.status, ts),
                )
                conn.execute(
                    "INSERT INTO review_log (profile_id, pack_id, item_id, rating, reviewed_at) VALUES (?, ?, ?, ?, ?)",
                    (pid, pack_id, m.item_id, m.status, ts),
                )
            for a in body.answers:
                if ("tasks", a.task_id) not in valid or not ID_RE.match(a.question_id):
                    ignored += 1
                    continue
                if a.answer.strip() == "":
                    conn.execute(
                        "DELETE FROM task_answers WHERE profile_id=? AND pack_id=? AND task_id=? AND question_id=?",
                        (pid, pack_id, a.task_id, a.question_id))
                else:
                    conn.execute(
                        """INSERT INTO task_answers (profile_id, pack_id, task_id, question_id, answer, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT (profile_id, pack_id, task_id, question_id) DO UPDATE SET
                             answer = excluded.answer, updated_at = excluded.updated_at""",
                        (pid, pack_id, a.task_id, a.question_id, a.answer, ts),
                    )
        return {"saved": len(body.cards) + len(body.answers) - ignored, "ignored": ignored}

    @app.post("/api/progress/{pack_id}/quiz", status_code=201)
    def post_quiz(pack_id: str, body: QuizIn, conn: sqlite3.Connection = Depends(get_conn),
                  profile: sqlite3.Row = Depends(require_profile)):
        pack_exists(conn, pack_id)
        if body.score > body.max:
            raise err(422, "A pontszám nem lehet nagyobb a maximumnál.", "invalid")
        with Tx(conn):
            cur = conn.execute(
                """INSERT INTO quiz_attempts (profile_id, pack_id, chapter, score, max, wrong_ids, taken_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (profile["id"], pack_id, body.chapter, body.score, body.max, json.dumps(body.wrong_ids), now_iso()),
            )
        return {"id": cur.lastrowid}

    # ---------------- export / import
    @app.get("/api/export")
    def export(conn: sqlite3.Connection = Depends(get_conn), _: sqlite3.Row = Depends(require_parent)):
        data = transfer.export_all(conn)
        fname = f"tanulo-export-{now_iso()[:10]}.json"
        return Response(json.dumps(data, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    @app.post("/api/import")
    async def do_import(request: Request, confirm: str = Query(default=""),
                        conn: sqlite3.Connection = Depends(get_conn),
                        profile: sqlite3.Row | None = Depends(get_profile)):
        has_profiles = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] > 0
        if has_profiles and (profile is None or profile["role"] != "parent"):
            raise err(403, "Visszatölteni csak szülői profillal lehet.", "parent_only")
        if confirm != "replace":
            raise err(400, "A visszatöltés minden jelenlegi adatot lecserél; megerősítés kell.", "confirm_required")
        raw = await request.body()
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise err(422, f"Az exportfájl nem érvényes JSON: {e}", "invalid_import")
        try:
            counts = transfer.import_all(conn, data)
        except transfer.ImportError_ as e:
            raise err(422, f"A visszatöltés nem sikerült, semmi nem változott: {e}", "invalid_import")
        log.info("visszatöltés kész: %s", counts)
        return {"imported": counts}


def _unwrap_content(raw: bytes) -> bytes:
    """A validate végpont nyers szöveget vár, de elfogad {"content": "..."} burkolatot is."""
    head = raw.lstrip()[:200]
    if head.startswith(b"{") and b'"content"' in head and b'"schema"' not in head:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("content"), str) and set(obj) <= {"content", "meta"}:
                return obj["content"].encode("utf-8")
        except (ValueError, UnicodeDecodeError):
            pass
    return raw

