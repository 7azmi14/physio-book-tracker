from core.site import SiteItem, _hits_badge_url


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
    def __init__(self, site_base_url):
        self.site_base_url = site_base_url


def test_hits_badge_url_strips_scheme_and_adds_trailing_slash():
    url = _hits_badge_url(FakeConfig("https://example.github.io/physio-book-tracker"))
    assert url == "https://hits.sh/example.github.io/physio-book-tracker/.svg?style=flat-square&label=views"


def test_hits_badge_url_none_without_base_url():
    assert _hits_badge_url(FakeConfig("")) is None
