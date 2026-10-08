"""A tanulo-csomag/1 formátum validátora, magyar, mezőszintű hibaüzenetekkel.

Hibák: a csomag nem menthető. Figyelmeztetések (pl. ismeretlen kulcs): menthető.
Az útvonalak formája: ``cards[12].chapter``, ``tasks[0].source.table.rows[2]``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .text import normalize

SCHEMA = "tanulo-csomag/1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_ERRORS = 200

# Elemfajták, amelyek azonosítója a csomagon belül közös névtérben egyedi,
# és amelyekhez haladás köthető.
ITEM_KINDS = ("cards", "quiz", "tasks", "timeline", "traps")

KIND_LABEL = {
    "chapters": "fejezet",
    "cards": "kártya",
    "quiz": "kvízkérdés",
    "tasks": "feladat",
    "timeline": "idővonal-elem",
    "summary": "összefoglaló-fejezet",
    "traps": "csapda",
}


@dataclass
class Issue:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "text": f"{self.path}: {self.message}"}


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    data: dict[str, Any] | None = None
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors and self.data is not None

    def counts(self) -> dict[str, int]:
        d = self.data or {}
        out = {}
        for key in ("chapters", "cards", "quiz", "tasks", "timeline", "summary", "traps"):
            v = d.get(key)
            out[key] = len(v) if isinstance(v, list) else 0
        tasks = d.get("tasks") if isinstance(d.get("tasks"), list) else []
        out["task_questions"] = sum(
            len(t.get("questions", [])) for t in tasks
            if isinstance(t, dict) and isinstance(t.get("questions"), list)
        )
        return out

    def item_ids(self) -> dict[str, list[str]]:
        """Az elemazonosítók fajtánként (csak érvényes csomagnál értelmes)."""
        d = self.data or {}
        out: dict[str, list[str]] = {}
        for kind in ITEM_KINDS:
            items = d.get(kind) or []
            out[kind] = [it["id"] for it in items if isinstance(it, dict) and isinstance(it.get("id"), str)]
        return out

    def meta(self) -> dict[str, Any]:
        d = self.data or {}
        m = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        return {
            "id": m.get("id"),
            "title": m.get("title"),
            "topic": m.get("topic"),
            "subject": m.get("subject"),
            "tags": m.get("tags") if isinstance(m.get("tags"), list) else [],
            "level": m.get("level"),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [e.as_dict() for e in self.errors],
            "warnings": [w.as_dict() for w in self.warnings],
            "truncated": self.truncated,
            "counts": self.counts() if self.data is not None else None,
            "meta": self.meta() if self.data is not None else None,
        }


class _Stop(Exception):
    pass


class _Validator:
    def __init__(self) -> None:
        self.r = ValidationResult()
        self.chapter_ids: set[str] = set()

    # ----------------------------------------------------------- jelentés
    def err(self, path: str, msg: str) -> None:
        if len(self.r.errors) >= MAX_ERRORS:
            self.r.truncated = True
            raise _Stop()
        self.r.errors.append(Issue(path, msg))

    def warn(self, path: str, msg: str) -> None:
        if len(self.r.warnings) < MAX_ERRORS:
            self.r.warnings.append(Issue(path, msg))

    # ----------------------------------------------------------- típusok
    @staticmethod
    def _is_int(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool)

    @staticmethod
    def _type_name(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "logikai érték"
        if isinstance(v, (int, float)):
            return "szám"
        if isinstance(v, str):
            return "szöveg"
        if isinstance(v, list):
            return "tömb"
        if isinstance(v, dict):
            return "objektum"
        return type(v).__name__

    def obj(self, v: Any, path: str, allowed: set[str]) -> bool:
        if not isinstance(v, dict):
            self.err(path, f"objektum kell legyen, de {self._type_name(v)}")
            return False
        for k in v:
            if k not in allowed:
                self.warn(f"{path}.{k}" if path else k, "ismeretlen kulcs, figyelmen kívül marad")
        return True

    def string(self, o: dict, key: str, path: str, maxlen: int, required: bool = True) -> str | None:
        p = f"{path}.{key}" if path else key
        if key not in o or o[key] is None:
            if required:
                self.err(p, "kötelező mező hiányzik")
            return None
        v = o[key]
        if not isinstance(v, str):
            self.err(p, f"szöveg kell legyen, de {self._type_name(v)}")
            return None
        if required and not v.strip():
            self.err(p, "nem lehet üres")
            return None
        if len(v) > maxlen:
            self.err(p, f"túl hosszú: {len(v)} karakter (legfeljebb {maxlen})")
        return v

    def integer(self, o: dict, key: str, path: str, required: bool = True) -> int | None:
        p = f"{path}.{key}"
        if key not in o or o[key] is None:
            if required:
                self.err(p, "kötelező mező hiányzik")
            return None
        v = o[key]
        if not self._is_int(v):
            self.err(p, f"egész szám kell legyen, de {self._type_name(v)}")
            return None
        return v

    def ident(self, o: dict, key: str, path: str) -> str | None:
        p = f"{path}.{key}" if path else key
        if key not in o or o[key] is None:
            self.err(p, "kötelező mező hiányzik")
            return None
        v = o[key]
        if self._is_int(v):
            self.err(p, f"az azonosító szöveg kell legyen: írd idézőjelbe, \"{v}\"")
            return None
        if not isinstance(v, str):
            self.err(p, f"szöveg kell legyen, de {self._type_name(v)}")
            return None
        if not ID_RE.match(v):
            self.err(
                p,
                f'"{v}" érvénytelen azonosító (csak kisbetű, számjegy és kötőjel; '
                "betűvel vagy számmal kezdődik; legfeljebb 64 karakter)",
            )
            return None
        return v

    def chapter_ref(self, o: dict, path: str, required: bool = True) -> None:
        p = f"{path}.chapter"
        if "chapter" not in o or o["chapter"] is None:
            if required:
                self.err(p, "kötelező mező hiányzik")
            return
        v = o["chapter"]
        if self._is_int(v):
            v = str(v)
            self.err(p, f'a fejezethivatkozás szöveg kell legyen: írd idézőjelbe, "{v}"')
            return
        if not isinstance(v, str):
            self.err(p, f"szöveg kell legyen, de {self._type_name(v)}")
            return
        if v not in self.chapter_ids:
            self.err(p, f'"{v}" nem létező fejezet')

    def array(self, root: dict, key: str, required: bool = False) -> list:
        if key not in root or root[key] is None:
            if required:
                self.err(key, "kötelező mező hiányzik")
            return []
        v = root[key]
        if not isinstance(v, list):
            self.err(key, f"tömb kell legyen, de {self._type_name(v)}")
            return []
        return v

    # ----------------------------------------------------------- részek
    def run(self, data: Any) -> None:
        if not isinstance(data, dict):
            self.err("(gyökér)", f"a csomag JSON-objektum kell legyen, de {self._type_name(data)}")
            return
        self.obj(data, "", {"schema", "meta", "chapters", "cards", "quiz", "tasks", "timeline", "summary", "traps"})

        schema = data.get("schema")
        if schema is None:
            self.err("schema", f'kötelező mező hiányzik (értéke: "{SCHEMA}")')
        elif schema != SCHEMA:
            self.err("schema", f'"{schema}" nem támogatott formátum, pontosan "{SCHEMA}" kell')

        if "meta" not in data:
            self.err("meta", "kötelező mező hiányzik")
        else:
            self.meta(data["meta"])

        self.chapters(self.array(data, "chapters", required=True), "chapters" in data)

        item_seen: dict[str, str] = {}

        def unique(item_id: str | None, path: str) -> None:
            if item_id is None:
                return
            if item_id in item_seen:
                self.err(f"{path}.id", f'"{item_id}" azonosító már szerepel: {item_seen[item_id]}')
            else:
                item_seen[item_id] = path

        for i, c in enumerate(self.array(data, "cards")):
            p = f"cards[{i}]"
            if not self.obj(c, p, {"id", "chapter", "front", "back"}):
                continue
            unique(self.ident(c, "id", p), p)
            self.chapter_ref(c, p)
            self.string(c, "front", p, 300)
            self.string(c, "back", p, 1200)

        for i, q in enumerate(self.array(data, "quiz")):
            p = f"quiz[{i}]"
            if not self.obj(q, p, {"id", "chapter", "question", "options", "correct", "explanation"}):
                continue
            unique(self.ident(q, "id", p), p)
            self.chapter_ref(q, p)
            self.string(q, "question", p, 400)
            self.quiz_options(q, p)
            self.string(q, "explanation", p, 600)

        for i, t in enumerate(self.array(data, "tasks")):
            p = f"tasks[{i}]"
            if not self.obj(t, p, {"id", "chapter", "title", "source", "questions"}):
                continue
            unique(self.ident(t, "id", p), p)
            self.chapter_ref(t, p)
            self.string(t, "title", p, 160)
            self.task_source(t, p)
            self.task_questions(t, p)

        sort_keys: dict[int, str] = {}
        for i, e in enumerate(self.array(data, "timeline")):
            p = f"timeline[{i}]"
            if not self.obj(e, p, {"id", "date", "sort_key", "event", "chapter"}):
                continue
            unique(self.ident(e, "id", p), p)
            self.string(e, "date", p, 40)
            sk = self.integer(e, "sort_key", p)
            if sk is not None:
                sort_keys.setdefault(sk, p)
            self.string(e, "event", p, 300)
            self.chapter_ref(e, p, required=False)

        summary_seen: dict[str, str] = {}
        for i, s in enumerate(self.array(data, "summary")):
            p = f"summary[{i}]"
            if not self.obj(s, p, {"chapter", "blocks"}):
                continue
            self.chapter_ref(s, p)
            ch = s.get("chapter")
            if isinstance(ch, str):
                if ch in summary_seen:
                    self.warn(f"{p}.chapter", f'a(z) "{ch}" fejezethez már van összefoglaló: {summary_seen[ch]}')
                else:
                    summary_seen[ch] = p
            self.summary_blocks(s, p)

        for i, tr in enumerate(self.array(data, "traps")):
            p = f"traps[{i}]"
            if not self.obj(tr, p, {"id", "title", "explanation"}):
                continue
            unique(self.ident(tr, "id", p), p)
            self.string(tr, "title", p, 160)
            self.string(tr, "explanation", p, 500)

        has_content = any(
            isinstance(data.get(k), list) and data.get(k)
            for k in ("cards", "quiz", "tasks", "timeline", "summary", "traps")
        )
        if not has_content and not self.r.errors:
            self.warn("(gyökér)", "a csomagban nincs tanulnivaló (kártya, kvíz, feladat, idővonal, összefoglaló vagy csapda)")

    def meta(self, m: Any) -> None:
        allowed = {"id", "title", "topic", "subject", "tags", "level", "language",
                   "source_note", "exam_info", "generated_at"}
        if not self.obj(m, "meta", allowed):
            return
        self.ident(m, "id", "meta")
        self.string(m, "title", "meta", 120)
        self.string(m, "topic", "meta", 200)
        self.string(m, "subject", "meta", 60)
        self.string(m, "level", "meta", 40, required=False)
        self.string(m, "language", "meta", 10, required=False)
        self.string(m, "source_note", "meta", 300, required=False)
        self.string(m, "exam_info", "meta", 1500, required=False)
        tags = m.get("tags")
        if tags is not None:
            if not isinstance(tags, list):
                self.err("meta.tags", f"szövegtömb kell legyen, de {self._type_name(tags)}")
            else:
                if len(tags) > 10:
                    self.err("meta.tags", f"túl sok címke: {len(tags)} (legfeljebb 10)")
                seen: set[str] = set()
                for i, tg in enumerate(tags):
                    p = f"meta.tags[{i}]"
                    if not isinstance(tg, str):
                        self.err(p, f"szöveg kell legyen, de {self._type_name(tg)}")
                    elif not tg.strip():
                        self.err(p, "nem lehet üres")
                    elif len(tg) > 40:
                        self.err(p, f"túl hosszú: {len(tg)} karakter (legfeljebb 40)")
                    elif normalize(tg) in seen:
                        self.warn(p, f'"{tg}" címke kétszer szerepel')
                    else:
                        seen.add(normalize(tg))
        ga = m.get("generated_at")
        if ga is not None:
            ok = isinstance(ga, str)
            if ok:
                try:
                    datetime.fromisoformat(ga.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        date.fromisoformat(ga)
                    except ValueError:
                        ok = False
            if not ok:
                self.err("meta.generated_at", f"ISO dátum kell legyen (pl. 2026-10-08 vagy 2026-10-08T18:00:00Z), de: {ga!r}")

    def chapters(self, chapters: list, present: bool) -> None:
        if present and isinstance(chapters, list) and not chapters and "chapters" not in {e.path for e in self.r.errors}:
            self.err("chapters", "legalább egy fejezet kell")
        orders: dict[int, str] = {}
        seen: dict[str, str] = {}
        for i, c in enumerate(chapters):
            p = f"chapters[{i}]"
            if not self.obj(c, p, {"id", "title", "order"}):
                continue
            cid = self.ident(c, "id", p)
            if cid is not None:
                if cid in seen:
                    self.err(f"{p}.id", f'"{cid}" fejezetazonosító már szerepel: {seen[cid]}')
                else:
                    seen[cid] = p
                    self.chapter_ids.add(cid)
            self.string(c, "title", p, 160)
            order = self.integer(c, "order", p)
            if order is not None:
                if order in orders:
                    self.warn(f"{p}.order", f"ugyanaz a sorszám ({order}), mint itt: {orders[order]}")
                else:
                    orders[order] = p

    def quiz_options(self, q: dict, p: str) -> None:
        opts = q.get("options")
        if opts is None:
            self.err(f"{p}.options", "kötelező mező hiányzik")
            opts_ok = False
        elif not isinstance(opts, list):
            self.err(f"{p}.options", f"szövegtömb kell legyen, de {self._type_name(opts)}")
            opts_ok = False
        else:
            opts_ok = True
            if not 2 <= len(opts) <= 6:
                self.err(f"{p}.options", f"{len(opts)} opció van, 2 és 6 között kell lennie")
            seen: dict[str, int] = {}
            for j, o in enumerate(opts):
                op = f"{p}.options[{j}]"
                if not isinstance(o, str):
                    self.err(op, f"szöveg kell legyen, de {self._type_name(o)}")
                    continue
                if not o.strip():
                    self.err(op, "nem lehet üres")
                    continue
                if len(o) > 300:
                    self.err(op, f"túl hosszú: {len(o)} karakter (legfeljebb 300)")
                key = normalize(o)
                if key in seen:
                    self.err(op, f"azonos a(z) {p}.options[{seen[key]}] opcióval")
                else:
                    seen[key] = j
        correct = self.integer(q, "correct", p)
        if correct is not None and opts_ok and isinstance(opts, list) and opts:
            if not 0 <= correct < len(opts):
                self.err(f"{p}.correct", f"{correct} érvénytelen index: 0 és {len(opts) - 1} között kell lennie (0-tól számolva)")

    def task_source(self, t: dict, p: str) -> None:
        sp = f"{p}.source"
        if "source" not in t or t["source"] is None:
            self.err(sp, "kötelező mező hiányzik")
            return
        s = t["source"]
        if not self.obj(s, sp, {"caption", "type", "text", "excerpt", "table"}):
            return
        self.string(s, "caption", sp, 200)
        typ = s.get("type")
        if typ not in ("text", "table"):
            self.err(f"{sp}.type", f'"text" vagy "table" lehet, de: {json.dumps(typ, ensure_ascii=False)}')
            return
        if "excerpt" in s and s["excerpt"] is not None and not isinstance(s["excerpt"], bool):
            self.err(f"{sp}.excerpt", f"true vagy false lehet, de {self._type_name(s['excerpt'])}")
        if typ == "text":
            txt = self.string(s, "text", sp, 1500)
            if s.get("table") is not None:
                self.warn(f"{sp}.table", 'type="text" mellett a table figyelmen kívül marad')
            if isinstance(txt, str):
                words = len(txt.split())
                if words > 100:
                    self.warn(f"{sp}.text", f"a forrásrészlet {words} szó, a javasolt legfeljebb kb. 80")
        else:
            if s.get("text") is not None:
                self.warn(f"{sp}.text", 'type="table" mellett a text figyelmen kívül marad')
            self.task_table(s, sp)

    def task_table(self, s: dict, sp: str) -> None:
        tp = f"{sp}.table"
        if "table" not in s or s["table"] is None:
            self.err(tp, 'kötelező, ha type="table"')
            return
        tbl = s["table"]
        if not self.obj(tbl, tp, {"header", "rows"}):
            return
        header = tbl.get("header")
        ncols = None
        if not isinstance(header, list) or not header:
            self.err(f"{tp}.header", "nem üres szövegtömb kell legyen")
        else:
            ncols = len(header)
            for j, h in enumerate(header):
                if not isinstance(h, str):
                    self.err(f"{tp}.header[{j}]", f"szöveg kell legyen, de {self._type_name(h)}")
                elif len(h) > 200:
                    self.err(f"{tp}.header[{j}]", f"túl hosszú: {len(h)} karakter (legfeljebb 200)")
        rows = tbl.get("rows")
        if not isinstance(rows, list) or not rows:
            self.err(f"{tp}.rows", "legalább egy sor kell (tömbök tömbje)")
            return
        for r_i, row in enumerate(rows):
            rp = f"{tp}.rows[{r_i}]"
            if not isinstance(row, list):
                self.err(rp, f"tömb kell legyen, de {self._type_name(row)}")
                continue
            if ncols is not None and len(row) != ncols:
                self.err(rp, f"{len(row)} cella van, de a fejlécben {ncols} oszlop")
            for c_i, cell in enumerate(row):
                if not isinstance(cell, str):
                    self.err(f"{rp}[{c_i}]", f"szöveg kell legyen, de {self._type_name(cell)}")
                elif len(cell) > 500:
                    self.err(f"{rp}[{c_i}]", f"túl hosszú: {len(cell)} karakter (legfeljebb 500)")

    def task_questions(self, t: dict, p: str) -> None:
        qp = f"{p}.questions"
        qs = t.get("questions")
        if qs is None:
            self.err(qp, "kötelező mező hiányzik")
            return
        if not isinstance(qs, list):
            self.err(qp, f"tömb kell legyen, de {self._type_name(qs)}")
            return
        if not 3 <= len(qs) <= 8:
            self.err(qp, f"{len(qs)} kérdés van, 3 és 8 között kell lennie")
        seen: dict[str, str] = {}
        for j, q in enumerate(qs):
            pp = f"{qp}[{j}]"
            if not self.obj(q, pp, {"id", "prompt", "solution"}):
                continue
            qid = self.ident(q, "id", pp)
            if qid is not None:
                if qid in seen:
                    self.err(f"{pp}.id", f'"{qid}" kérdésazonosító már szerepel ebben a feladatban: {seen[qid]}')
                else:
                    seen[qid] = pp
            self.string(q, "prompt", pp, 400)
            self.string(q, "solution", pp, 800)

    def summary_blocks(self, s: dict, p: str) -> None:
        bp = f"{p}.blocks"
        blocks = s.get("blocks")
        if blocks is None:
            self.err(bp, "kötelező mező hiányzik")
            return
        if not isinstance(blocks, list):
            self.err(bp, f"tömb kell legyen, de {self._type_name(blocks)}")
            return
        if not blocks:
            self.warn(bp, "üres összefoglaló")
        for j, b in enumerate(blocks):
            pp = f"{bp}[{j}]"
            if not isinstance(b, dict):
                self.err(pp, f"objektum kell legyen, de {self._type_name(b)}")
                continue
            typ = b.get("type")
            if typ == "heading":
                self.obj(b, pp, {"type", "text"})
                self.string(b, "text", pp, 120)
            elif typ == "paragraph":
                self.obj(b, pp, {"type", "text"})
                self.string(b, "text", pp, 2000)
            elif typ == "list":
                self.obj(b, pp, {"type", "items"})
                items = b.get("items")
                if not isinstance(items, list) or not items:
                    self.err(f"{pp}.items", "nem üres szövegtömb kell legyen")
                    continue
                for k, it in enumerate(items):
                    if not isinstance(it, str):
                        self.err(f"{pp}.items[{k}]", f"szöveg kell legyen, de {self._type_name(it)}")
                    elif not it.strip():
                        self.err(f"{pp}.items[{k}]", "nem lehet üres")
                    elif len(it) > 1000:
                        self.err(f"{pp}.items[{k}]", f"túl hosszú: {len(it)} karakter (legfeljebb 1000)")
            else:
                self.err(f"{pp}.type", f'"heading", "paragraph" vagy "list" lehet, de: {json.dumps(typ, ensure_ascii=False)}')


def _no_dupes_hook(warnings: list[Issue]):
    def hook(pairs: list[tuple[str, Any]]) -> dict:
        out: dict = {}
        for k, v in pairs:
            if k in out:
                warnings.append(Issue(k, "a kulcs kétszer szerepel ugyanabban az objektumban, az utolsó érték számít"))
            out[k] = v
        return out
    return hook


def validate_data(data: Any) -> ValidationResult:
    v = _Validator()
    try:
        v.run(data)
    except _Stop:
        pass
    v.r.data = data if isinstance(data, dict) else None
    return v.r


def validate_text(raw: bytes | str, max_bytes: int) -> ValidationResult:
    """Nyers feltöltött szöveg ellenőrzése: méret, kódolás, JSON, majd séma."""
    if isinstance(raw, str):
        raw_bytes = raw.encode("utf-8")
    else:
        raw_bytes = raw
    if len(raw_bytes) > max_bytes:
        r = ValidationResult()
        r.errors.append(Issue("(fájl)", f"túl nagy: {len(raw_bytes) / 1024 / 1024:.2f} MB (legfeljebb {max_bytes / 1024 / 1024:.0f} MB)"))
        return r
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        r = ValidationResult()
        r.errors.append(Issue("(fájl)", f"nem UTF-8 kódolású (hibás bájt a(z) {e.start}. pozíción)"))
        return r
    if not text.strip():
        r = ValidationResult()
        r.errors.append(Issue("(fájl)", "üres"))
        return r
    dup_warnings: list[Issue] = []
    try:
        data = json.loads(text, object_pairs_hook=_no_dupes_hook(dup_warnings))
    except json.JSONDecodeError as e:
        r = ValidationResult()
        r.errors.append(Issue("(fájl)", f"érvénytelen JSON: {_json_msg(e.msg)} ({e.lineno}. sor, {e.colno}. oszlop)"))
        return r
    r = validate_data(data)
    r.warnings = dup_warnings + r.warnings
    return r


_JSON_MSGS = {
    "Expecting value": "érték hiányzik",
    "Expecting property name enclosed in double quotes": "kulcsnév hiányzik vagy nincs idézőjelben (vessző a lezárás előtt?)",
    "Expecting ',' delimiter": "vessző hiányzik",
    "Expecting ':' delimiter": "kettőspont hiányzik",
    "Extra data": "fölösleges adat a JSON vége után",
    "Unterminated string starting at": "lezáratlan szöveg",
    "Invalid control character at": "szabálytalan vezérlőkarakter (sortörés szövegben? használd: \\n)",
    "Invalid \\escape": "érvénytelen \\ escape",
    "Illegal trailing comma before end of object": "fölösleges vessző az objektum lezárása előtt",
    "Illegal trailing comma before end of array": "fölösleges vessző a tömb lezárása előtt",
}


def _json_msg(msg: str) -> str:
    return _JSON_MSGS.get(msg, msg)
