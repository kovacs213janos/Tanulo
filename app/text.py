"""Szövegnormalizálás a kereséshez: kisbetű, ékezet nélkül."""
from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """'Társadalomtörténet' -> 'tarsadalomtortenet'. Ő/ű is lefedve (NFKD)."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.split())


def search_terms(q: str) -> list[str]:
    return [t for t in normalize(q).split(" ") if t]


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
