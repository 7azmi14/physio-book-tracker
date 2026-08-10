"""Offline tests for the Google Books source — no real network calls.
get_json is monkeypatched with canned responses built from
fixtures/google_books_items.json.
"""
import json
from datetime import date
from pathlib import Path

import sources.google_books as gb
from core.config import Config, SourceConfig
from core.edition import WatchlistEntry
from sources.google_books import (
    GoogleBooksSource,
    _extract_isbn13,
    _normalize_published_date,
    _volume_to_record,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "google_books_items.json").read_text(encoding="utf-8")
)


def make_config(**source_options) -> Config:
    return Config(
        include_keywords=["physiotherapy"],
        exclude_keywords=[],
        lookback_days=30,
        sources={"google_books": SourceConfig(enabled=True, options=source_options)},
        email_enabled=False,
        email_recipients=[],
        email_from="x@example.com",
        send_empty_digest=False,
        min_relevance_score=0,
        site_title="Test",
        site_base_url="",
        site_github_repo="",
    )


def test_normalize_published_date_full():
    assert _normalize_published_date("2026-04-03") == "2026-04-03"


def test_normalize_published_date_year_month():
    assert _normalize_published_date("2026-05") == "2026-05-01"


def test_normalize_published_date_year_only():
    assert _normalize_published_date("2026") == "2026-01-01"


def test_normalize_published_date_none_and_invalid():
    assert _normalize_published_date(None) is None
    assert _normalize_published_date("not-a-date") is None


def test_extract_isbn13_prefers_isbn13():
    ids = FIXTURES["full_item"]["volumeInfo"]["industryIdentifiers"]
    assert _extract_isbn13(ids) == "9780443128646"


def test_extract_isbn13_falls_back_to_isbn10():
    ids = FIXTURES["isbn10_only"]["volumeInfo"]["industryIdentifiers"]
    result = _extract_isbn13(ids)
    assert result is not None
    assert len(result) == 13


def test_extract_isbn13_none_when_missing():
    assert _extract_isbn13([]) is None


def test_volume_to_record_maps_fields_and_parses_edition():
    record = _volume_to_record(FIXTURES["full_item"])
    assert record.title == "Orthopedic Physical Assessment"
    assert record.subtitle == "8th Edition"
    assert record.authors == ["David J. Magee", "Robert C. Manske"]
    assert record.isbn13 == "9780443128646"
    assert record.published_date == "2026-04-03"
    assert record.edition == 8
    assert record.source == "google_books"
    assert record.doi is None


def test_volume_to_record_returns_none_without_title():
    assert _volume_to_record(FIXTURES["no_date_no_title"]) is None


def test_fetch_builds_subject_and_watchlist_queries_dedupes_and_filters_by_date(monkeypatch):
    calls = []

    def fake_get_json(url, *, params, **kwargs):
        calls.append(params["q"])
        if "Magee" in params["q"]:
            return {"items": [FIXTURES["full_item"]]}
        if "subject" in params["q"]:
            # Same volume returned by both subject queries -> must dedupe by id.
            return {"items": [FIXTURES["partial_date"], FIXTURES["partial_date"]]}
        return {"items": []}

    monkeypatch.setattr(gb, "get_json", fake_get_json)
    monkeypatch.setattr(gb, "DELAY_BETWEEN_QUERIES", 0)

    watchlist = [
        WatchlistEntry(
            short_title="Magee",
            title="Orthopedic Physical Assessment",
            authors=["Magee"],
            publisher="Elsevier",
            current_edition=7,
        )
    ]
    config = make_config()
    records = GoogleBooksSource().fetch(since=date(2026, 1, 1), config=config, watchlist=watchlist)

    # 2 subject queries + 1 watchlist query = 3 queries total.
    assert len(calls) == 3
    assert any('inauthor:"Magee"' in q for q in calls)
    # partial_date volume appeared twice across subject queries but should dedupe to one.
    titles = [r.title for r in records]
    assert titles.count("Rehabilitation Basics") == 1
    assert "Orthopedic Physical Assessment" in titles


def test_fetch_excludes_items_older_than_since(monkeypatch):
    old_item = {
        "id": "vol-old",
        "volumeInfo": {"title": "Old Book", "publishedDate": "2020-01-01"},
    }

    def fake_get_json(url, *, params, **kwargs):
        return {"items": [old_item]}

    monkeypatch.setattr(gb, "get_json", fake_get_json)
    monkeypatch.setattr(gb, "DELAY_BETWEEN_QUERIES", 0)

    config = make_config()
    records = GoogleBooksSource().fetch(since=date(2026, 1, 1), config=config, watchlist=[])
    assert records == []


def test_fetch_continues_when_one_query_fails(monkeypatch):
    from core.http import SourceError

    call_count = {"n": 0}

    def fake_get_json(url, *, params, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise SourceError("boom")
        return {"items": [FIXTURES["partial_date"]]}

    monkeypatch.setattr(gb, "get_json", fake_get_json)
    monkeypatch.setattr(gb, "DELAY_BETWEEN_QUERIES", 0)

    config = make_config()
    records = GoogleBooksSource().fetch(since=date(2026, 1, 1), config=config, watchlist=[])
    assert len(records) >= 1
