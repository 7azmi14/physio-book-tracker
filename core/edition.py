"""Parse edition numbers out of catalogue metadata and match records against
the watchlist (core/state.py:Watchlist / watchlist.yaml)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import BookRecord
from .normalize import normalize_author_surname, normalize_title

_WORD_NUMBERS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20,
}

_DIGIT_ORDINAL_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s*ed(?:ition|\.)?\b", re.IGNORECASE)
_ED_THEN_DIGIT_RE = re.compile(r"\bed(?:ition|\.)?\s*(\d{1,2})\b", re.IGNORECASE)
_SHORTHAND_RE = re.compile(r"\b(\d{1,2})e\b")  # Elsevier-style "8e"
_WORD_ORDINAL_RE = re.compile(
    r"\b(" + "|".join(_WORD_NUMBERS) + r")\s+ed(?:ition|\.)?\b", re.IGNORECASE
)


def parse_edition(*texts: Optional[str]) -> Optional[int]:
    """Try each pattern against each given text (title, subtitle,
    description, ...) in order and return the first edition number found."""
    for text in texts:
        if not text:
            continue
        m = _DIGIT_ORDINAL_RE.search(text)
        if m:
            return int(m.group(1))
        m = _WORD_ORDINAL_RE.search(text)
        if m:
            return _WORD_NUMBERS[m.group(1).lower()]
        m = _ED_THEN_DIGIT_RE.search(text)
        if m:
            return int(m.group(1))
        m = _SHORTHAND_RE.search(text)
        if m:
            return int(m.group(1))
    return None


@dataclass
class WatchlistEntry:
    short_title: str
    title: str
    authors: list[str]
    publisher: Optional[str]
    current_edition: int

    @classmethod
    def from_dict(cls, d: dict) -> "WatchlistEntry":
        return cls(
            short_title=d.get("short_title") or d["title"],
            title=d["title"],
            authors=d.get("authors") or [],
            publisher=d.get("publisher"),
            current_edition=int(d["current_edition"]),
        )


def _title_matches(record_title_norm: str, entry_title_norm: str) -> bool:
    if not record_title_norm or not entry_title_norm:
        return False
    if record_title_norm == entry_title_norm:
        return True
    # Tolerate one being a prefix/substring of the other (catalogue titles
    # often carry an extra qualifier like a possessive editor's name), but
    # require a reasonable overlap to avoid matching on a stray short word.
    shorter, longer = sorted([record_title_norm, entry_title_norm], key=len)
    return len(shorter) >= 8 and shorter in longer


def match_watchlist_entry(
    record: BookRecord, watchlist: list[WatchlistEntry]
) -> Optional[WatchlistEntry]:
    """Return the watchlist entry this record identifies as, or None.

    Matches on normalised title plus at least one overlapping author
    surname, per the spec ("normalised title plus author surname").
    """
    record_title_norm = normalize_title(record.title)
    record_surnames = {normalize_author_surname(a) for a in record.authors if a}

    for entry in watchlist:
        entry_title_norm = normalize_title(entry.title)
        if not _title_matches(record_title_norm, entry_title_norm):
            continue
        entry_surnames = {normalize_author_surname(a) for a in entry.authors if a}
        if record_surnames and entry_surnames and not (record_surnames & entry_surnames):
            continue
        return entry
    return None


def is_newer_edition(record: BookRecord, entry: WatchlistEntry) -> bool:
    edition = record.edition or parse_edition(record.title, record.subtitle, record.description)
    if edition is None:
        return False
    return edition > entry.current_edition
