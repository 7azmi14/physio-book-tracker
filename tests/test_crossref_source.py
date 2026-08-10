"""Offline tests for CrossRef item parsing — no network calls.

Uses fixtures/crossref_items.json, trimmed-down real CrossRef `message.items`
entries, to lock down title unescaping, ISBN extraction, edition-number
parsing, and the published-date fallback chain.
"""
import json
from pathlib import Path

import pytest

from sources.crossref import _extract_date, _item_to_record

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "crossref_items.json").read_text(encoding="utf-8")
)


def test_html_entities_in_title_are_unescaped():
    record = _item_to_record(FIXTURES["plain_book"])
    assert record.title == "Oxford Handbook of Sport & Exercise Medicine"


def test_basic_fields_extracted():
    record = _item_to_record(FIXTURES["plain_book"])
    assert record.source == "crossref"
    assert record.authors == ["Jane Doe"]
    assert record.publisher == "Oxford University Press"
    assert record.isbn13 == "9780198854166"
    assert record.published_date == "2026-08-01"


def test_edition_number_and_subtitle_parsed():
    record = _item_to_record(FIXTURES["watchlist_new_edition"])
    assert record.edition == 8
    assert record.subtitle == "8th Edition"
    assert record.authors == ["David J. Magee", "Robert C. Manske"]
    assert record.published_date == "2026-04-03"


def test_missing_isbn_and_authors_do_not_crash():
    record = _item_to_record(FIXTURES["no_isbn_no_authors"])
    assert record.isbn13 is None
    assert record.authors == []
    assert record.edition is None


@pytest.mark.parametrize(
    "item,expected",
    [
        ({"issued": {"date-parts": [[2026]]}}, "2026-01-01"),
        ({"issued": {"date-parts": [[2026, 5]]}}, "2026-05-01"),
        ({"published-print": {"date-parts": [[2026, 5, 20]]}}, "2026-05-20"),
        ({}, None),
    ],
)
def test_date_fallback_chain(item, expected):
    assert _extract_date(item) == expected
