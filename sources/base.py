"""Common interface every data source implements.

Adding a source means writing a new module with a class implementing
`BaseSource` and registering it in main.py's `SOURCE_REGISTRY` — nothing
else in the pipeline (dedupe, scoring, state, site, email) needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from core.config import Config
from core.edition import WatchlistEntry
from core.models import BookRecord


class BaseSource(ABC):
    #: short machine name, used in config.yaml's `sources:` map and stored
    #: on each BookRecord.source
    name: str

    @abstractmethod
    def fetch(
        self, *, since: date, config: Config, watchlist: list[WatchlistEntry]
    ) -> list[BookRecord]:
        """Return every candidate book record published/announced on or
        after `since`. Sources should NOT apply relevance scoring or
        dedupe themselves — that happens centrally in main.py.

        `watchlist` is passed through so a source can query watchlist titles
        directly if that's a better way to catch new editions than generic
        keyword search (see sources/google_books.py) — sources that don't
        need it can just ignore the parameter.

        Raise core.http.SourceError (or let it propagate from core.http.get_json)
        on unrecoverable failure; the caller catches it per-source so one
        broken source doesn't abort the whole run.
        """
        raise NotImplementedError
