import json

from core.site import SiteItem, _hits_badge_url, _slug_for, _write_index_json, build_site


def make_item(**kwargs) -> SiteItem:
    kwargs.setdefault("key", "isbn13:9780000000002")
    kwargs.setdefault("slug", "abc123")
    kwargs.setdefault("title", "Some Book")
    kwargs.setdefault("subtitle", None)
    kwargs.setdefault("authors", [])
    kwargs.setdefault("publisher", None)
    kwargs.setdefault("published_date", None)
    kwargs.setdefault("isbn13", None)
    kwargs.setdefault("doi", None)
    kwargs.setdefault("url", None)
    kwargs.setdefault("source", "crossref")
    kwargs.setdefault("first_seen", "2026-08-01")
    return SiteItem(**kwargs)


def test_cover_url_uses_isbn13():
    item = make_item(isbn13="9780443128646")
    assert item.cover_url == "https://covers.openlibrary.org/b/isbn/9780443128646-M.jpg?default=false"


def test_cover_url_none_without_isbn():
    assert make_item(isbn13=None).cover_url is None


def test_share_link_prefers_source_url_over_permalink():
    item = make_item(url="https://doi.org/10.1000/x", permalink="https://example.com/books/abc.html")
    assert item.share_link == "https://doi.org/10.1000/x"


def test_share_link_falls_back_to_permalink():
    item = make_item(url=None, permalink="https://example.com/books/abc.html")
    assert item.share_link == "https://example.com/books/abc.html"


def test_tweet_url_encodes_text_and_omits_url_param_when_no_link():
    item = make_item(title="Manual Therapy Techniques", authors=["Jane Doe"])
    url = item.tweet_url
    assert url.startswith("https://twitter.com/intent/tweet?text=")
    assert "url=" not in url
    assert "Manual" in url  # loosely present, exact encoding not asserted here


def test_tweet_url_includes_url_param_when_link_available():
    item = make_item(title="Book", url="https://doi.org/10.1000/x")
    assert "url=https%3A%2F%2Fdoi.org%2F10.1000%2Fx" in item.tweet_url


def test_tweet_text_flags_new_edition():
    item = make_item(
        title="Orthopedic Physical Assessment",
        is_new_edition=True,
        edition=8,
        watchlist_short_title="Magee",
    )
    assert "new edition (8) of Magee" in item.tweet_text


class FakeConfig:
    def __init__(self, site_base_url="", site_title="Test Site"):
        self.site_base_url = site_base_url
        self.site_title = site_title


def test_hits_badge_url_strips_scheme_and_adds_trailing_slash():
    url = _hits_badge_url(FakeConfig("https://example.github.io/physio-book-tracker"))
    assert url == "https://hits.sh/example.github.io/physio-book-tracker/.svg?style=flat-square&label=views"


def test_hits_badge_url_none_without_base_url():
    assert _hits_badge_url(FakeConfig("")) is None


def _state_entry(title, isbn13):
    return {
        "first_seen": "2026-08-01",
        "record": {"title": title, "source": "crossref", "isbn13": isbn13},
        "matched_keywords": [],
        "is_new_edition": False,
        "watchlist_short_title": None,
    }


def test_build_site_removes_orphaned_book_pages_for_purged_items(tmp_path):
    key_a, key_b = "isbn13:1111111111111", "isbn13:2222222222222"
    slug_a, slug_b = _slug_for(key_a), _slug_for(key_b)
    state_items = {key_a: _state_entry("Book A", "1111111111111"), key_b: _state_entry("Book B", "2222222222222")}

    build_site(state_items=state_items, config=FakeConfig(), watchlist_by_short_title={}, out_dir=tmp_path)
    assert (tmp_path / "books" / f"{slug_a}.html").exists()
    assert (tmp_path / "books" / f"{slug_b}.html").exists()

    # Simulate purging "Book B" from state (out of scope, removed by hand).
    del state_items[key_b]
    build_site(state_items=state_items, config=FakeConfig(), watchlist_by_short_title={}, out_dir=tmp_path)
    assert (tmp_path / "books" / f"{slug_a}.html").exists()
    assert not (tmp_path / "books" / f"{slug_b}.html").exists()


def test_write_index_json_matches_external_consumer_schema(tmp_path):
    item = make_item(
        key="isbn13:9780443128646",
        title="Orthopedic Physical Assessment",
        subtitle="8th Edition",
        authors=["David J. Magee", "Robert C. Manske"],
        isbn13="9780443128646",
        doi=None,
        published_date="2026-04-03",
        permalink="https://physio-book-tracker.pages.dev/books/abc123.html",
        description="A" * 500,  # long description, should get truncated
        is_new_edition=True,
    )
    path = tmp_path / "index.json"
    _write_index_json([item], path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert len(payload) == 1
    entry = payload[0]
    assert entry["id"] == "isbn13:9780443128646"
    assert entry["title"] == "Orthopedic Physical Assessment: 8th Edition"
    assert entry["authors"] == "David J. Magee, Robert C. Manske"
    assert entry["year"] == "2026"
    assert entry["doi"] == "9780443128646"  # falls back to ISBN when no DOI
    assert entry["url"] == "https://physio-book-tracker.pages.dev/books/abc123.html"
    assert len(entry["summary"]) <= 301  # 300 chars + ellipsis
    assert entry["summary"].endswith("…")
    assert entry["is_new_edition"] is True
    assert "confidence" not in entry


def test_write_index_json_handles_missing_optional_fields(tmp_path):
    item = make_item(title="Bare Book", url=None)
    path = tmp_path / "index.json"
    _write_index_json([item], path)
    entry = json.loads(path.read_text(encoding="utf-8"))[0]

    assert entry["year"] is None
    assert entry["doi"] is None
    assert entry["summary"] == ""
    assert entry["authors"] == ""


def test_write_index_json_prefers_real_doi_over_isbn(tmp_path):
    item = make_item(doi="10.1000/xyz", isbn13="9780443128646")
    path = tmp_path / "index.json"
    _write_index_json([item], path)
    entry = json.loads(path.read_text(encoding="utf-8"))[0]
    assert entry["doi"] == "10.1000/xyz"
