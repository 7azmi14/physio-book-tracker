"""Google Books API source.

Two query strategies, per spec:
1. Fixed subject searches (`subject:"Physical Therapy"`, `subject:"Rehabilitation"`)
   for discovering new titles generally.
2. A direct title+author query per watchlist entry — this is what actually
   catches new editions reliably, since CrossRef's keyword search alone
   won't surface a book like "Orthopedic Physical Assessment" that doesn't
   contain any of the tracked subject keywords in its own title.

The Volumes API has no server-side "published after X" filter, so
`publishedDate` is filtered client-side against `since` after fetching.

Docs: https://developers.google.com/books/docs/v1/using
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date

from core.config import Config
from core.edition import WatchlistEntry, parse_edition
from core.http import SourceError, get_json
from core.models import BookRecord
from core.normalize import normalize_isbn13
from .base import BaseSource

logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/books/v1/volumes"
SUBJECT_QUERIES = ['subject:"Physical Therapy"', 'subject:"Rehabilitation"']
MAX_RESULTS = 40
DELAY_BETWEEN_QUERIES = 0.5  # seconds; polite pacing across queries


class GoogleBooksSource(BaseSource):
    name = "google_books"

    def fetch(
        self, *, since: date, config: Config, watchlist: list[WatchlistEntry]
    ) -> list[BookRecord]:
        source_cfg = config.sources.get(self.name)
        # Prefer the env var (GitHub Actions secret) over config.yaml's
        # api_key field — config.yaml is committed to the repo, so a real
        # key belongs in a secret, not there.
        api_key = os.environ.get("GOOGLE_BOOKS_API_KEY") or (
            source_cfg.options.get("api_key") if source_cfg else None
        )

        queries = list(SUBJECT_QUERIES)
        for entry in watchlist:
            query = f'intitle:"{entry.title}"'
            if entry.authors:
                query += f' inauthor:"{entry.authors[0]}"'
            queries.append(query)

        records: list[BookRecord] = []
        seen_ids: set[str] = set()

        for i, query in enumerate(queries):
            params = {"q": query, "maxResults": MAX_RESULTS, "printType": "books", "orderBy": "newest"}
            if api_key:
                params["key"] = api_key

            try:
                data = get_json(BASE_URL, params=params)
            except SourceError as exc:
                logger.warning("google_books query %r failed: %s", query, exc)
                continue

            for item in data.get("items") or []:
                volume_id = item.get("id")
                if volume_id:
                    if volume_id in seen_ids:
                        continue
                    seen_ids.add(volume_id)
                record = _volume_to_record(item)
                if record is None:
                    continue
                if record.published_date and record.published_date >= since.isoformat():
                    records.append(record)

            if i < len(queries) - 1:
                time.sleep(DELAY_BETWEEN_QUERIES)

        return records


def _normalize_published_date(raw: str | None) -> str | None:
    """Google Books gives publishedDate as 'YYYY', 'YYYY-MM', or
    'YYYY-MM-DD' — pad to a full date so string comparison against
    since.isoformat() works."""
    if not raw:
        return None
    parts = raw.split("-")
    try:
        year = int(parts[0])
    except ValueError:
        return None
    month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
    day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _extract_isbn13(identifiers: list[dict]) -> str | None:
    for ident in identifiers or []:
        if ident.get("type") == "ISBN_13":
            normalized = normalize_isbn13(ident.get("identifier"))
            if normalized:
                return normalized
    for ident in identifiers or []:
        if ident.get("type") == "ISBN_10":
            normalized = normalize_isbn13(ident.get("identifier"))
            if normalized:
                return normalized
    return None


def _volume_to_record(item: dict) -> BookRecord | None:
    info = item.get("volumeInfo") or {}
    title = info.get("title")
    if not title:
        return None

    subtitle = info.get("subtitle")
    return BookRecord(
        title=title,
        source="google_books",
        subtitle=subtitle,
        authors=info.get("authors") or [],
        publisher=info.get("publisher"),
        published_date=_normalize_published_date(info.get("publishedDate")),
        isbn13=_extract_isbn13(info.get("industryIdentifiers") or []),
        doi=None,
        edition=parse_edition(title, subtitle, info.get("description")),
        subjects=info.get("categories") or [],
        description=info.get("description"),
        url=info.get("infoLink"),
    )
