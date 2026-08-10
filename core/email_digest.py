"""Monthly email digest: renders the same "new editions first, then new
titles grouped by subspecialty" content as the site, as an HTML+text email,
and sends it via the Resend API.

If nothing new was found, main.py simply never calls send_via_resend — per
spec, no digest is sent rather than an empty one.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import jinja2
import requests

from .config import Config
from .edition import WatchlistEntry
from .models import BookRecord

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
RESEND_URL = "https://api.resend.com/emails"


class EmailError(Exception):
    """Raised when the digest can't be sent. Callers catch this and log a
    warning rather than aborting the run — a failed send shouldn't lose the
    state/site updates that already happened."""


def has_digest_content(
    new_editions: list[tuple[BookRecord, WatchlistEntry]],
    new_titles: list[tuple[BookRecord, list[str]]],
) -> bool:
    return bool(new_editions) or bool(new_titles)


def group_titles(
    new_titles: list[tuple[BookRecord, list[str]]]
) -> list[tuple[str, list[BookRecord]]]:
    """Group by each record's primary (first, alphabetically) subspecialty
    tag. 'general' (no specific subspecialty matched) always sorts last."""
    groups: dict[str, list[BookRecord]] = {}
    for record, tags in new_titles:
        primary = tags[0] if tags else "general"
        groups.setdefault(primary, []).append(record)

    ordered_keys = sorted(k for k in groups if k != "general")
    if "general" in groups:
        ordered_keys.append("general")
    return [(key, groups[key]) for key in ordered_keys]


def render_subject(
    new_editions: list[tuple[BookRecord, WatchlistEntry]],
    new_titles: list[tuple[BookRecord, list[str]]],
) -> str:
    parts = []
    if new_editions:
        parts.append(f"{len(new_editions)} new edition" + ("s" if len(new_editions) != 1 else ""))
    if new_titles:
        parts.append(f"{len(new_titles)} new title" + ("s" if len(new_titles) != 1 else ""))
    return "Physio Book Tracker: " + ", ".join(parts) if parts else "Physio Book Tracker"


def render_text(
    new_editions: list[tuple[BookRecord, WatchlistEntry]],
    grouped_titles: list[tuple[str, list[BookRecord]]],
) -> str:
    lines: list[str] = []
    if new_editions:
        lines.append("NEW EDITIONS OF YOUR REFERENCE TEXTS")
        for record, entry in new_editions:
            lines.append(
                f"- {record.title} — {entry.short_title}, edition {record.edition} "
                f"(you have {entry.current_edition})"
            )
            if record.url:
                lines.append(f"  {record.url}")
        lines.append("")

    if grouped_titles:
        lines.append("NEW TITLES")
        for group_name, records in grouped_titles:
            lines.append(f"\n{group_name.title()}")
            for record in records:
                authors = ", ".join(record.authors) if record.authors else "no author listed"
                lines.append(
                    f"- {record.title} ({authors}) — {record.publisher or '?'}, "
                    f"{record.published_date or '?'}"
                )
                if record.url:
                    lines.append(f"  {record.url}")

    return "\n".join(lines)


def render_email(
    new_editions: list[tuple[BookRecord, WatchlistEntry]],
    new_titles: list[tuple[BookRecord, list[str]]],
    config: Config,
) -> tuple[str, str, str]:
    """Returns (subject, html, text)."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html"]),
    )
    grouped = group_titles(new_titles)
    html = env.get_template("email.html").render(
        site_title=config.site_title,
        site_base_url=config.site_base_url,
        run_date=date.today().isoformat(),
        new_editions=new_editions,
        grouped_titles=grouped,
    )
    text = render_text(new_editions, grouped)
    subject = render_subject(new_editions, new_titles)
    return subject, html, text


def send_via_resend(
    subject: str,
    html: str,
    text: str,
    config: Config,
    *,
    api_key: str | None = None,
    http_post=requests.post,
) -> None:
    key = api_key or os.environ.get("RESEND_API_KEY")
    if not key:
        raise EmailError("RESEND_API_KEY is not set — skipping email send")
    if not config.email_recipients:
        raise EmailError("email.recipients is empty in config.yaml — skipping email send")

    payload = {
        "from": config.email_from,
        "to": config.email_recipients,
        "subject": subject,
        "html": html,
        "text": text,
    }
    resp = http_post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    if resp.status_code >= 300:
        raise EmailError(f"Resend API returned {resp.status_code}: {resp.text[:200]}")
