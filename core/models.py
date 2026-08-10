"""Shared data types passed between sources, dedup, scoring, and the state store."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class BookRecord:
    """A single book/edition as reported by one data source.

    Only `title` and `source` are required — everything else is whatever the
    source could give us. Downstream code (dedupe, scoring, edition
    matching) must tolerate missing fields.
    """

    title: str
    source: str

    subtitle: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    publisher: Optional[str] = None
    published_date: Optional[str] = None  # ISO 8601, as precise as the source gives us
    isbn13: Optional[str] = None
    doi: Optional[str] = None
    edition: Optional[int] = None  # parsed edition number, if any
    subjects: list[str] = field(default_factory=list)
    description: Optional[str] = None
    url: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BookRecord":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
