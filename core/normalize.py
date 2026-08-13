"""Title/author normalisation shared by dedupe and watchlist edition matching."""
from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# Edition/volume/possessive noise that shows up inline in book titles and
# would otherwise break equality matching between sources.
_EDITION_NOISE_RE = re.compile(
    r"\b(\d+(st|nd|rd|th)\s+ed(ition)?\.?|edition|e-?book)\b", re.IGNORECASE
)


def strip_subtitle(title: str) -> str:
    """Drop everything after the first colon/em-dash — subtitles vary wildly
    between catalogue records for the same book."""
    for sep in (":", " — ", " – ", " - "):
        if sep in title:
            return title.split(sep, 1)[0]
    return title


def normalize_title(title: str, *, keep_subtitle: bool = False) -> str:
    if not title:
        return ""
    t = title if keep_subtitle else strip_subtitle(title)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = _EDITION_NOISE_RE.sub(" ", t)
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip().lower()
    return t


def normalize_author_surname(author: str) -> str:
    """Best-effort surname extraction. Handles 'Kisner, Carolyn' and
    'Carolyn Kisner' forms; falls back to the whole string normalised."""
    if not author:
        return ""
    a = unicodedata.normalize("NFKD", author).encode("ascii", "ignore").decode("ascii")
    a = a.strip()
    if "," in a:
        surname = a.split(",", 1)[0]
    else:
        parts = a.split()
        surname = parts[-1] if parts else a
    surname = _PUNCT_RE.sub(" ", surname)
    return _WS_RE.sub(" ", surname).strip().lower()


_CONCAT_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def normalize_publisher(name: str | None) -> str | None:
    """Some CrossRef deposits concatenate the publisher name and a
    place/imprint field with no separator (e.g. "Oxford University
    PressOxford"). Any lowercase letter directly followed by an uppercase
    one with no space is always such a concatenation — legitimate English
    publisher names never do this — so insert ", " at each occurrence."""
    if not name:
        return name
    return _CONCAT_BOUNDARY_RE.sub(", ", name)


def normalize_isbn13(isbn: str | None) -> str | None:
    if not isbn:
        return None
    digits = re.sub(r"[^0-9Xx]", "", isbn)
    if len(digits) == 10:
        # crude ISBN-10 -> ISBN-13 conversion (978 prefix, recompute check digit)
        core = "978" + digits[:9]
        total = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(core))
        check = (10 - (total % 10)) % 10
        return core + str(check)
    if len(digits) == 13:
        return digits
    return None
