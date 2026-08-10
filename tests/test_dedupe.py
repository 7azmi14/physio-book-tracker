from core.dedupe import dedupe, identity_key
from core.models import BookRecord


def make(**kwargs) -> BookRecord:
    kwargs.setdefault("title", "Some Book")
    kwargs.setdefault("source", "test")
    return BookRecord(**kwargs)


def test_identity_key_prefers_isbn13():
    r = make(isbn13="9780323625395", doi="10.1000/xyz")
    assert identity_key(r) == ("isbn13", "9780323625395")


def test_identity_key_normalizes_isbn10_to_13():
    r = make(isbn13="0-323-62539-8")
    kind, value = identity_key(r)
    assert kind == "isbn13"
    assert len(value) == 13


def test_identity_key_falls_back_to_doi_when_no_isbn():
    r = make(doi="10.1000/ABC")
    assert identity_key(r) == ("doi", "10.1000/abc")


def test_identity_key_falls_back_to_title_author_year():
    r = make(title="Therapeutic Exercise", authors=["Carolyn Kisner"], published_date="2023-01-01")
    kind, value = identity_key(r)
    assert kind == "title_author_year"
    assert "therapeutic exercise" in value
    assert "kisner" in value
    assert "2023" in value


def test_dedupe_merges_same_isbn_from_different_sources():
    a = make(title="Clinical Sports Medicine", source="crossref", isbn13="9781743761380", doi=None)
    b = make(
        title="Clinical Sports Medicine",
        source="google_books",
        isbn13="9781743761380",
        description="A comprehensive text.",
    )
    merged = dedupe([a, b])
    assert len(merged) == 1
    result = merged[0]
    assert result.description == "A comprehensive text."  # filled from b
    assert "crossref" in result.source and "google_books" in result.source


def test_dedupe_keeps_distinct_books_separate():
    a = make(title="Book One", isbn13="9780000000002")
    b = make(title="Book Two", isbn13="9780000000019")
    assert len(dedupe([a, b])) == 2


def test_dedupe_first_record_wins_on_conflicting_scalar_fields():
    a = make(title="Book", isbn13="9780000000002", publisher="First Publisher")
    b = make(title="Book", isbn13="9780000000002", publisher="Second Publisher")
    merged = dedupe([a, b])
    assert merged[0].publisher == "First Publisher"


def test_dedupe_merges_author_lists_without_duplicates():
    a = make(isbn13="9780000000002", authors=["Alice Smith"])
    b = make(isbn13="9780000000002", authors=["Alice Smith", "Bob Jones"])
    merged = dedupe([a, b])
    assert merged[0].authors == ["Alice Smith", "Bob Jones"]
