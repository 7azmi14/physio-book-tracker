#!/usr/bin/env python3
"""Run one tracking cycle: fetch from enabled sources, dedupe, score, check
the watchlist for new editions, update state, print a report, regenerate
the static site, and send the email digest if anything new was found.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from core.config import Config, load_watchlist
from core.dedupe import dedupe
from core.edition import is_newer_edition, match_watchlist_entry
from core.email_digest import EmailError, has_digest_content, render_email, send_via_resend
from core.models import BookRecord
from core.scoring import score_record
from core.site import build_site
from core.state import StateStore
from core.tags import derive_tags
from sources.base import BaseSource
from sources.crossref import CrossRefSource
from sources.google_books import GoogleBooksSource

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

# Windows terminals often default to a legacy codepage (e.g. cp1252) that
# can't encode author/publisher names from non-English catalogues. Force
# UTF-8 on stdout/stderr where the runtime allows it; harmless no-op on
# platforms (Linux CI) that are already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    "crossref": CrossRefSource,
    "google_books": GoogleBooksSource,
    # openlibrary, springer added in a later build phase
}

ROOT = Path(__file__).parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=ROOT / "config.yaml")
    p.add_argument("--watchlist", default=ROOT / "watchlist.yaml")
    p.add_argument("--state", default=ROOT / "state.json")
    p.add_argument(
        "--lookback-days", type=int, default=None,
        help="Override config.yaml's lookback_days for this run.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Fetch, score, and print as usual, but don't write state.json.",
    )
    p.add_argument("--site-dir", default=ROOT / "site")
    p.add_argument(
        "--no-site", action="store_true",
        help="Skip regenerating the static site after processing.",
    )
    p.add_argument(
        "--no-email", action="store_true",
        help="Skip sending the email digest even if config.yaml has email.enabled: true.",
    )
    return p.parse_args()


def run_sources(
    config: Config, since: date, watchlist: list
) -> tuple[list[BookRecord], dict[str, str]]:
    """Returns (all_records, source_status). source_status maps source name
    to 'ok (N items)' or an error description, so gaps can be reported."""
    all_records: list[BookRecord] = []
    status: dict[str, str] = {}

    for name, source_cfg in config.sources.items():
        if not source_cfg.enabled:
            status[name] = "disabled"
            continue
        source_cls = SOURCE_REGISTRY.get(name)
        if source_cls is None:
            status[name] = "enabled in config but not implemented yet"
            continue
        try:
            records = source_cls().fetch(since=since, config=config, watchlist=watchlist)
        except Exception as exc:  # noqa: BLE001 - a source must never abort the run
            logger.error("source %r failed: %s", name, exc)
            status[name] = f"FAILED: {exc}"
            continue
        status[name] = f"ok ({len(records)} raw items)"
        all_records.extend(records)

    return all_records, status


def process(
    records: list[BookRecord], config: Config, watchlist, state: StateStore
) -> dict:
    deduped = dedupe(records)
    new_candidates = state.filter_new(deduped)

    new_editions = []  # list of (record, watchlist_entry)
    new_titles = []
    excluded_count = 0
    below_threshold_count = 0

    for record in new_candidates:
        result = score_record(record, config.include_keywords, config.exclude_keywords)
        if result.excluded:
            excluded_count += 1
            continue
        if result.score < config.min_relevance_score:
            below_threshold_count += 1
            continue

        entry = match_watchlist_entry(record, watchlist)
        is_new_edition = entry is not None and is_newer_edition(record, entry)
        tags = derive_tags(result.matched_include)
        if is_new_edition:
            new_editions.append((record, entry))
        else:
            new_titles.append((record, tags))
        state.mark_seen(
            record,
            score=result.score,
            matched_keywords=result.matched_include,
            watchlist_short_title=entry.short_title if entry else None,
            is_new_edition=is_new_edition,
        )

    new_editions.sort(key=lambda pair: pair[0].published_date or "", reverse=True)
    new_titles.sort(key=lambda pair: pair[0].published_date or "", reverse=True)

    return {
        "raw_count": len(records),
        "deduped_count": len(deduped),
        "new_candidate_count": len(new_candidates),
        "excluded_count": excluded_count,
        "below_threshold_count": below_threshold_count,
        "new_editions": new_editions,
        "new_titles": new_titles,
    }


def print_report(since: date, source_status: dict[str, str], result: dict) -> None:
    print(f"\nPhysio Book Tracker — run {date.today().isoformat()}")
    print(f"Lookback: since {since.isoformat()}\n")

    print("Sources:")
    for name, status in source_status.items():
        print(f"  - {name}: {status}")
    print()

    print(
        f"Fetched {result['raw_count']} raw items -> {result['deduped_count']} after dedupe "
        f"-> {result['new_candidate_count']} not seen before"
    )
    print(
        f"Discarded: {result['excluded_count']} excluded by keyword, "
        f"{result['below_threshold_count']} below relevance threshold\n"
    )

    editions = result["new_editions"]
    print(f"=== New editions of your reference texts ({len(editions)}) ===")
    if not editions:
        print("  (none)")
    for record, entry in editions:
        edition_num = record.edition
        print(f"\n  [{entry.short_title}] NEW EDITION: {edition_num} (you have {entry.current_edition})")
        _print_record_detail(record)

    titles = result["new_titles"]
    print(f"\n=== New titles ({len(titles)}) ===")
    if not titles:
        print("  (none)")
    for record, tags in titles:
        print()
        _print_record_detail(record)
    print()


def _print_record_detail(record: BookRecord) -> None:
    full_title = record.title + (f": {record.subtitle}" if record.subtitle else "")
    print(f"  {full_title}")
    authors = ", ".join(record.authors) if record.authors else "(no author listed)"
    print(f"    Authors: {authors}")
    print(
        f"    Publisher: {record.publisher or '?'} | "
        f"Published: {record.published_date or '?'} | "
        f"ISBN-13: {record.isbn13 or '?'}"
    )
    if record.url:
        print(f"    {record.url}")


def main() -> int:
    args = parse_args()
    config = Config.load(args.config)
    watchlist = load_watchlist(args.watchlist)
    state = StateStore.load(args.state)

    lookback_days = args.lookback_days if args.lookback_days is not None else config.lookback_days
    since = date.today() - timedelta(days=lookback_days)

    records, source_status = run_sources(config, since, watchlist)
    result = process(records, config, watchlist, state)
    print_report(since, source_status, result)

    if not args.dry_run:
        state.save()
        print(f"State saved to {args.state} ({len(state)} items total known)")
    else:
        print("(dry run — state.json not written)")

    if not args.no_site:
        watchlist_by_short_title = {e.short_title: e.current_edition for e in watchlist}
        build_site(
            state_items=state.items,
            config=config,
            watchlist_by_short_title=watchlist_by_short_title,
            out_dir=args.site_dir,
        )
        print(f"Site regenerated at {args.site_dir} ({len(state)} pages)")

    new_editions, new_titles = result["new_editions"], result["new_titles"]
    if args.dry_run or args.no_email:
        print("(email digest skipped — dry run or --no-email)")
    elif not config.email_enabled:
        print("(email digest skipped — email.enabled is false in config.yaml)")
    elif not has_digest_content(new_editions, new_titles):
        print("(email digest skipped — nothing new to report this run)")
    else:
        subject, html, text = render_email(new_editions, new_titles, config)
        try:
            send_via_resend(subject, html, text, config)
            print(f"Email digest sent to {', '.join(config.email_recipients)}: {subject!r}")
        except EmailError as exc:
            logger.error("failed to send email digest: %s", exc)
            print(f"Email digest FAILED to send: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
