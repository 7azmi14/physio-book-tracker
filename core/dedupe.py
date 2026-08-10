"""Cross-source deduplication.

Two records are the same book if, in priority order, they share an ISBN-13,
then a DOI, then (normalised title, normalised first-author surname, year).
The same key function is used both to merge same-run results from multiple
sources and to check incoming records against the state store, so "have we
seen this ISBN/DOI/title-author-year before" always means one thing.
"""
from __future__ import annotations

from .models import BookRecord
from .normalize import normalize_author_surname, normalize_isbn13, normalize_title


def _year_of(record: BookRecord) -> str:
    if record.published_date:
        return record.published_date[:4]
    return ""


def identity_key(record: BookRecord) -> tuple[str, str]:
    """Return a (kind, value) key identifying this book's real-world identity.

    `kind` tells you which tier matched, which is useful for debugging why
    two records were considered the same (or weren't).
    """
    isbn = normalize_isbn13(record.isbn13)
    if isbn:
        return ("isbn13", isbn)
    if record.doi:
        return ("doi", record.doi.strip().lower())
    first_author = normalize_author_surname(record.authors[0]) if record.authors else ""
    title_key = normalize_title(record.title)
    return ("title_author_year", f"{title_key}|{first_author}|{_year_of(record)}")


def _merge(base: BookRecord, extra: BookRecord) -> BookRecord:
    """Fill gaps in `base` from `extra`; `base` wins on conflicts. Sources
    that ran earlier in the priority order (CrossRef first) end up as
    `base` because dedupe() folds records in source-priority order."""
    merged = BookRecord(title=base.title, source=base.source)
    for f in BookRecord.__dataclass_fields__:
        base_val = getattr(base, f)
        extra_val = getattr(extra, f)
        if f in ("authors", "subjects"):
            merged_list = list(base_val) if base_val else []
            for item in extra_val or []:
                if item not in merged_list:
                    merged_list.append(item)
            setattr(merged, f, merged_list)
        elif f == "source":
            sources = {s.strip() for s in str(base_val).split(",")}
            sources |= {s.strip() for s in str(extra_val).split(",")}
            setattr(merged, f, ",".join(sorted(sources)))
        else:
            setattr(merged, f, base_val if base_val not in (None, "") else extra_val)
    return merged


def dedupe(records: list[BookRecord]) -> list[BookRecord]:
    """Merge records that identify as the same book, preserving input order
    for which record's fields win on conflict (first occurrence wins)."""
    order: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], BookRecord] = {}
    for record in records:
        key = identity_key(record)
        if key not in groups:
            groups[key] = record
            order.append(key)
        else:
            groups[key] = _merge(groups[key], record)
    return [groups[k] for k in order]
