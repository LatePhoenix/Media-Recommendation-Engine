"""Pure text-normalization helpers for canonical identity (Phase 4).

No DB, no imports beyond stdlib — unit-testable in isolation. Used to collapse
title/name/tag variants across import sources into stable canonical keys.
"""

from __future__ import annotations

import re
import unicodedata

_ARTICLES = ("the ", "a ", "an ")
_TRAILING_ARTICLE = re.compile(r"^(.*),\s*(the|a|an)$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_title(title: str | None) -> str:
    """Canonical comparison key for a title.

    Lowercases, strips accents/punctuation, and normalizes leading/trailing
    articles so "The Matrix", "Matrix, The", and "matrix" all collapse to "matrix".
    """
    if not title:
        return ""
    s = _strip_accents(str(title)).lower().strip()
    m = _TRAILING_ARTICLE.match(s)
    if m:
        s = f"{m.group(2)} {m.group(1)}"
    for art in _ARTICLES:
        if s.startswith(art):
            s = s[len(art):]
            break
    s = _NON_ALNUM.sub(" ", s).strip()
    return _WS.sub(" ", s)


def normalize_name(name: str | None) -> str:
    """Canonical key for a person/creator or series name (no article handling)."""
    if not name:
        return ""
    s = _strip_accents(str(name)).lower()
    s = _NON_ALNUM.sub(" ", s).strip()
    return _WS.sub(" ", s)


def slugify(value: str | None) -> str:
    """Hyphenated slug for tags / stable identifiers."""
    n = normalize_name(value)
    return _WS.sub("-", n)
