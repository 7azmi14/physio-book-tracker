"""Loaders for config.yaml and watchlist.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .edition import WatchlistEntry


@dataclass
class SourceConfig:
    enabled: bool = False
    options: dict = field(default_factory=dict)


@dataclass
class Config:
    include_keywords: list[str]
    exclude_keywords: list[str]
    lookback_days: int
    sources: dict[str, SourceConfig]
    email_enabled: bool
    email_recipients: list[str]
    email_from: str
    send_empty_digest: bool
    min_relevance_score: int
    site_title: str
    site_base_url: str

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        sources = {}
        for name, opts in (raw.get("sources") or {}).items():
            opts = opts or {}
            sources[name] = SourceConfig(
                enabled=bool(opts.get("enabled", False)),
                options={k: v for k, v in opts.items() if k != "enabled"},
            )
        email = raw.get("email") or {}
        site = raw.get("site") or {}
        return cls(
            include_keywords=raw.get("include_keywords") or [],
            exclude_keywords=raw.get("exclude_keywords") or [],
            lookback_days=int(raw.get("lookback_days", 30)),
            sources=sources,
            email_enabled=bool(email.get("enabled", False)),
            email_recipients=email.get("recipients") or [],
            email_from=email.get("from") or "Physio Book Tracker <onboarding@resend.dev>",
            send_empty_digest=bool(email.get("send_empty_digest", False)),
            min_relevance_score=int(raw.get("min_relevance_score", 0)),
            site_title=site.get("title") or "Physio Book Tracker",
            site_base_url=(site.get("base_url") or "").rstrip("/"),
        )


def load_watchlist(path: str | Path) -> list[WatchlistEntry]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return [WatchlistEntry.from_dict(entry) for entry in raw]
