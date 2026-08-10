import pytest

from core.edition import (
    WatchlistEntry,
    is_newer_edition,
    match_watchlist_entry,
    parse_edition,
)
from core.models import BookRecord


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Therapeutic Exercise: Foundations and Techniques, 9th Edition", 9),
        ("Orthopedic Physical Assessment, 8e", 8),
        ("Tidy's Physiotherapy: Edition 15", 15),
        ("Clinical Sports Medicine, Third Edition", 3),
        ("A Book With No Edition Mentioned", None),
        ("8th ed.", 8),
    ],
)
def test_parse_edition(text, expected):
    assert parse_edition(text) == expected


def test_parse_edition_checks_multiple_fields_in_order():
    assert parse_edition(None, "no edition here", "Now in its 4th edition") == 4


def watchlist():
    return [
        WatchlistEntry(
            short_title="Kisner & Colby",
            title="Therapeutic Exercise: Foundations and Techniques",
            authors=["Kisner", "Colby", "Borstad"],
            publisher="F.A. Davis",
            current_edition=8,
        ),
        WatchlistEntry(
            short_title="Tidy's",
            title="Tidy's Physiotherapy",
            authors=["Porter"],
            publisher="Elsevier",
            current_edition=15,
        ),
    ]


def test_match_watchlist_entry_by_title_and_author():
    r = BookRecord(
        title="Therapeutic Exercise",
        subtitle="Foundations and Techniques",
        source="crossref",
        authors=["Carolyn Kisner", "John Borstad"],
    )
    entry = match_watchlist_entry(r, watchlist())
    assert entry is not None
    assert entry.short_title == "Kisner & Colby"


def test_match_watchlist_entry_rejects_title_match_with_wrong_author():
    r = BookRecord(
        title="Therapeutic Exercise: Foundations and Techniques",
        source="crossref",
        authors=["Someone Unrelated"],
    )
    assert match_watchlist_entry(r, watchlist()) is None


def test_match_watchlist_entry_no_match_for_unrelated_book():
    r = BookRecord(title="Gray's Anatomy", source="crossref", authors=["Henry Gray"])
    assert match_watchlist_entry(r, watchlist()) is None


def test_is_newer_edition_true_when_ahead():
    entry = watchlist()[0]
    r = BookRecord(title="Therapeutic Exercise", source="crossref", edition=9)
    assert is_newer_edition(r, entry) is True


def test_is_newer_edition_false_when_same_or_older():
    entry = watchlist()[0]
    same = BookRecord(title="Therapeutic Exercise", source="crossref", edition=8)
    older = BookRecord(title="Therapeutic Exercise", source="crossref", edition=7)
    assert is_newer_edition(same, entry) is False
    assert is_newer_edition(older, entry) is False


def test_is_newer_edition_parses_edition_from_title_if_field_missing():
    entry = watchlist()[1]
    r = BookRecord(title="Tidy's Physiotherapy, 16th Edition", source="crossref", edition=None)
    assert is_newer_edition(r, entry) is True


def test_is_newer_edition_false_when_no_edition_found_anywhere():
    entry = watchlist()[0]
    r = BookRecord(title="Therapeutic Exercise", source="crossref", edition=None)
    assert is_newer_edition(r, entry) is False
