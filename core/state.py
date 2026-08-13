"""Persistent JSON state store: every book ever seen, keyed by its dedupe
identity, with the date it first appeared. This is what makes each digest
report only genuinely new items and guarantees no ISBN is ever reported
twice.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from .dedupe import identity_key
from .models import BookRecord
from .normalize import normalize_publisher

STATE_VERSION = 1


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.version = STATE_VERSION
        self.items: dict[str, dict] = {}

    @classmethod
    def load(cls, path: str | Path) -> "StateStore":
        store = cls(path)
        if store.path.exists():
            data = json.loads(store.path.read_text(encoding="utf-8"))
            store.version = data.get("version", STATE_VERSION)
            store.items = data.get("items", {})
        return store

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.version, "items": self.items}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _key(record: BookRecord) -> str:
        kind, value = identity_key(record)
        return f"{kind}:{value}"

    def is_new(self, record: BookRecord) -> bool:
        return self._key(record) not in self.items

    def get(self, record: BookRecord) -> dict | None:
        return self.items.get(self._key(record))

    def mark_seen(
        self,
        record: BookRecord,
        *,
        seen_on: date | None = None,
        score: int | None = None,
        matched_keywords: list[str] | None = None,
        watchlist_short_title: str | None = None,
        is_new_edition: bool = False,
    ) -> None:
        """Record a book as seen, along with the derived metadata the site
        and email digest need (relevance score, which keywords matched —
        used for the subspecialty filter — and watchlist edition status)."""
        key = self._key(record)
        seen_date = (seen_on or datetime.now(timezone.utc).date()).isoformat()
        existing = self.items.get(key)
        record_dict = record.as_dict()
        extra = {
            "score": score,
            "matched_keywords": matched_keywords or [],
            "watchlist_short_title": watchlist_short_title,
            "is_new_edition": is_new_edition,
        }
        if existing:
            # Keep the original first-seen date; refresh the stored metadata
            # in case a later source filled in fields the first one lacked.
            existing["record"] = record_dict
            existing.update(extra)
        else:
            self.items[key] = {"first_seen": seen_date, "record": record_dict, **extra}

    def filter_new(self, records: list[BookRecord]) -> list[BookRecord]:
        return [r for r in records if self.is_new(r)]

    def retag(self, include_keywords: list[str], exclude_keywords: list[str]) -> int:
        """Recompute matched_keywords (subspecialty tags) and clean up the
        stored publisher name for every already-stored item using the
        CURRENT config. Scoring normally only happens once at ingestion, so
        editing config.yaml's keywords otherwise only affects items fetched
        afterward — this is what makes an edit apply retroactively too.
        Never removes or excludes items, even ones that would now score as
        excluded; that stays a deliberate, separate operation.
        Returns how many items actually changed."""
        from .scoring import score_record  # local import: scoring doesn't depend on state

        updated = 0
        for entry in self.items.values():
            record = BookRecord.from_dict(entry["record"])
            new_matched = score_record(record, include_keywords, exclude_keywords).matched_include
            new_publisher = normalize_publisher(record.publisher)
            if new_matched != entry.get("matched_keywords") or new_publisher != record.publisher:
                entry["matched_keywords"] = new_matched
                entry["record"]["publisher"] = new_publisher
                updated += 1
        return updated

    def __len__(self) -> int:
        return len(self.items)
