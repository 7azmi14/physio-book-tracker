"""Static site generator: renders site/index.html, one page per book, and
feed.xml / feed.json from the state store. Pure read of state.json — this
module never fetches anything, so it can be re-run any time for free.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape as xml_escape

import jinja2

from .config import Config
from .tags import derive_tags

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
FEED_ITEM_LIMIT = 100


@dataclass
class SiteItem:
    key: str
    slug: str
    title: str
    subtitle: str | None
    authors: list[str]
    publisher: str | None
    published_date: str | None
    isbn13: str | None
    doi: str | None
    url: str | None
    source: str
    first_seen: str
    tags: list[str] = field(default_factory=list)
    is_new_edition: bool = False
    watchlist_short_title: str | None = None
    watchlist_current_edition: int | None = None
    edition: int | None = None
    permalink: str | None = None  # set in build_site() once config.site_base_url is known

    @property
    def full_title(self) -> str:
        return f"{self.title}: {self.subtitle}" if self.subtitle else self.title

    @property
    def cover_url(self) -> str | None:
        # OpenLibrary's cover API is a free, keyless, ISBN-keyed image CDN —
        # no build-time API call needed, the browser just requests it
        # directly. Missing covers are handled client-side (see book_cover
        # onerror in the templates), since OpenLibrary doesn't cover every
        # ISBN, especially very recent ones.
        return f"https://covers.openlibrary.org/b/isbn/{self.isbn13}-M.jpg" if self.isbn13 else None

    @property
    def share_link(self) -> str | None:
        """Best available link for this book: the publisher/DOI link if the
        source gave us one, otherwise our own permalink (once deployed)."""
        return self.url or self.permalink

    @property
    def tweet_text(self) -> str:
        bits = [self.full_title]
        if self.authors:
            names = ", ".join(self.authors[:2]) + (" et al." if len(self.authors) > 2 else "")
            bits.append(f"by {names}")
        if self.is_new_edition and self.watchlist_short_title:
            bits.append(f"— new edition ({self.edition}) of {self.watchlist_short_title}!")
        bits.append("#physiotherapy #PT")
        return " ".join(bits)

    @property
    def tweet_url(self) -> str:
        params = {"text": self.tweet_text}
        if self.share_link:
            params["url"] = self.share_link
        return "https://twitter.com/intent/tweet?" + urlencode(params)


def _slug_for(key: str) -> str:
    return sha1(key.encode("utf-8")).hexdigest()[:16]


def load_items(state_items: dict[str, dict]) -> list[SiteItem]:
    items = []
    for key, entry in state_items.items():
        record = entry.get("record") or {}
        items.append(
            SiteItem(
                key=key,
                slug=_slug_for(key),
                title=record.get("title") or "(untitled)",
                subtitle=record.get("subtitle"),
                authors=record.get("authors") or [],
                publisher=record.get("publisher"),
                published_date=record.get("published_date"),
                isbn13=record.get("isbn13"),
                doi=record.get("doi"),
                url=record.get("url"),
                source=record.get("source") or "",
                first_seen=entry.get("first_seen") or "",
                tags=derive_tags(entry.get("matched_keywords") or []),
                is_new_edition=bool(entry.get("is_new_edition")),
                watchlist_short_title=entry.get("watchlist_short_title"),
                edition=record.get("edition"),
            )
        )
    return items


def _sort_key(item: SiteItem) -> str:
    return item.published_date or item.first_seen or ""


def build_site(
    *, state_items: dict[str, dict], config: Config, watchlist_by_short_title: dict[str, int],
    out_dir: str | Path,
) -> None:
    out_dir = Path(out_dir)
    (out_dir / "books").mkdir(parents=True, exist_ok=True)

    items = load_items(state_items)
    for item in items:
        if item.watchlist_short_title:
            item.watchlist_current_edition = watchlist_by_short_title.get(item.watchlist_short_title)
        item.permalink = _item_url(config, item)
    items.sort(key=_sort_key, reverse=True)

    new_editions = [i for i in items if i.is_new_edition]
    all_tags = sorted({t for i in items for t in i.tags})

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    actions_url = (
        f"https://github.com/{config.site_github_repo}/actions/workflows/monthly.yml"
        if config.site_github_repo
        else None
    )
    common = {
        "site_title": config.site_title,
        "generated_at": generated_at,
        "total_known": len(items),
        "actions_url": actions_url,
    }

    index_html = env.get_template("index.html").render(
        items=items, new_editions=new_editions, all_tags=all_tags, **common
    )
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    book_template = env.get_template("book.html")
    for item in items:
        page_html = book_template.render(item=item, **common)
        (out_dir / "books" / f"{item.slug}.html").write_text(page_html, encoding="utf-8")

    _write_rss(items, config, out_dir / "feed.xml")
    _write_json_feed(items, config, out_dir / "feed.json")


def _item_url(config: Config, item: SiteItem) -> str:
    base = config.site_base_url or "."
    return f"{base}/books/{item.slug}.html"


def _write_rss(items: list[SiteItem], config: Config, path: Path) -> None:
    feed_items = sorted(items, key=lambda i: i.first_seen, reverse=True)[:FEED_ITEM_LIMIT]
    now = format_datetime(datetime.now(timezone.utc))

    entries = []
    for item in feed_items:
        try:
            pub_dt = datetime.fromisoformat(item.first_seen).replace(tzinfo=timezone.utc)
        except ValueError:
            pub_dt = datetime.now(timezone.utc)
        description = xml_escape(
            f"{', '.join(item.authors) or 'Unknown author'} — {item.publisher or 'Unknown publisher'}"
            + (f" — new edition ({item.edition})" if item.is_new_edition else "")
        )
        entries.append(
            "  <item>\n"
            f"    <title>{xml_escape(item.full_title)}</title>\n"
            f"    <link>{xml_escape(_item_url(config, item))}</link>\n"
            f"    <guid isPermaLink=\"false\">{xml_escape(item.key)}</guid>\n"
            f"    <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            f"    <description>{description}</description>\n"
            "  </item>"
        )

    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        f"  <title>{xml_escape(config.site_title)}</title>\n"
        f"  <link>{xml_escape(config.site_base_url or '.')}</link>\n"
        "  <description>New physiotherapy and rehabilitation books, and new editions of watchlist texts.</description>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(entries)
        + "\n</channel></rss>\n"
    )
    path.write_text(rss, encoding="utf-8")


def _write_json_feed(items: list[SiteItem], config: Config, path: Path) -> None:
    feed_items = sorted(items, key=lambda i: i.first_seen, reverse=True)[:FEED_ITEM_LIMIT]
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": config.site_title,
        "home_page_url": config.site_base_url or ".",
        "feed_url": f"{config.site_base_url}/feed.json" if config.site_base_url else "feed.json",
        "items": [
            {
                "id": item.key,
                "url": _item_url(config, item),
                "title": item.full_title,
                "content_text": (
                    f"{', '.join(item.authors) or 'Unknown author'} — "
                    f"{item.publisher or 'Unknown publisher'}"
                    + (f" — new edition ({item.edition})" if item.is_new_edition else "")
                ),
                "date_published": f"{item.first_seen}T00:00:00Z" if item.first_seen else None,
                "tags": item.tags,
            }
            for item in feed_items
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
