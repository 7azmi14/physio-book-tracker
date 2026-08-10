"""CrossRef REST API source — the primary source. Elsevier, Springer,
Taylor & Francis and Wiley all deposit book metadata here, so this single
API covers most of the watchlist's publishers.

Docs: https://api.crossref.org/swagger-ui/index.html
"""
from __future__ import annotations

import html
import logging
import time
from datetime import date

from core.config import Config
from core.http import SourceError, get_json
from core.models import BookRecord
from core.normalize import normalize_isbn13
from .base import BaseSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.crossref.org/works"
BOOK_TYPES = ("book", "monograph", "book-set")
ROWS_PER_QUERY = 50
DELAY_BETWEEN_QUERIES = 0.5  # seconds; polite pacing across per-keyword queries


class CrossRefSource(BaseSource):
    name = "crossref"

    def fetch(self, *, since: date, config: Config) -> list[BookRecord]:
        source_cfg = config.sources.get(self.name)
        mailto = (source_cfg.options.get("mailto") if source_cfg else None)
        keywords = config.include_keywords or [""]

        filter_val = ",".join(
            [f"type:{t}" for t in BOOK_TYPES]
            + [f"from-pub-date:{since.isoformat()}", f"until-pub-date:{date.today().isoformat()}"]
        )

        records: list[BookRecord] = []
        seen_dois: set[str] = set()

        for i, keyword in enumerate(keywords):
            params = {
                "query.bibliographic": keyword,
                "filter": filter_val,
                "rows": ROWS_PER_QUERY,
            }
            if mailto:
                params["mailto"] = mailto

            try:
                data = get_json(BASE_URL, params=params)
            except SourceError as exc:
                logger.warning("crossref query %r failed: %s", keyword, exc)
                continue

            items = (data.get("message") or {}).get("items") or []
            for item in items:
                doi = item.get("DOI")
                if doi:
                    if doi in seen_dois:
                        continue
                    seen_dois.add(doi)
                records.append(_item_to_record(item))

            if i < len(keywords) - 1:
                time.sleep(DELAY_BETWEEN_QUERIES)

        return records


def _date_from_parts(obj: dict | None) -> str | None:
    parts = ((obj or {}).get("date-parts") or [None])[0]
    if not parts:
        return None
    y = parts[0]
    m = parts[1] if len(parts) > 1 and parts[1] else 1
    d = parts[2] if len(parts) > 2 and parts[2] else 1
    try:
        return date(y, m, d).isoformat()
    except (TypeError, ValueError):
        return f"{y:04d}-{m:02d}-{d:02d}" if y else None


def _extract_date(item: dict) -> str | None:
    for key in ("published-print", "published-online", "published", "issued"):
        result = _date_from_parts(item.get(key))
        if result:
            return result
    return None


def _extract_isbn13(item: dict) -> str | None:
    for isbn in item.get("ISBN") or []:
        normalized = normalize_isbn13(isbn)
        if normalized:
            return normalized
    return None


def _extract_authors(item: dict) -> list[str]:
    authors = []
    for a in item.get("author") or []:
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if not name:
            name = a.get("name", "")
        if name:
            authors.append(name)
    return authors


def _item_to_record(item: dict) -> BookRecord:
    titles = item.get("title") or []
    subtitles = item.get("subtitle") or []
    edition_raw = item.get("edition-number")
    edition = None
    if edition_raw is not None:
        try:
            edition = int(edition_raw)
        except (TypeError, ValueError):
            edition = None

    return BookRecord(
        title=html.unescape(titles[0]) if titles else "(untitled)",
        source="crossref",
        subtitle=html.unescape(subtitles[0]) if subtitles else None,
        authors=_extract_authors(item),
        publisher=item.get("publisher"),
        published_date=_extract_date(item),
        isbn13=_extract_isbn13(item),
        doi=item.get("DOI"),
        edition=edition,
        subjects=item.get("subject") or [],
        description=item.get("abstract"),
        url=item.get("URL"),
    )
