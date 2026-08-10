"""Relevance scoring from config.yaml's include/exclude keyword lists.

Field weights reflect how strongly a match there implies relevance: a
keyword in the title is a much stronger signal than one buried in an
abstract. Any exclude-keyword hit anywhere zeroes the score outright,
regardless of how many include keywords also matched.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import BookRecord

_FIELD_WEIGHTS = {
    "title": 3,
    "subtitle": 2,
    "subjects": 2,
    "description": 1,
}


@dataclass
class ScoreResult:
    score: int
    excluded: bool
    matched_include: list[str] = field(default_factory=list)
    matched_exclude: list[str] = field(default_factory=list)


def _fields(record: BookRecord) -> dict[str, str]:
    return {
        "title": record.title or "",
        "subtitle": record.subtitle or "",
        "subjects": " ".join(record.subjects or []),
        "description": record.description or "",
    }


def score_record(
    record: BookRecord, include_keywords: list[str], exclude_keywords: list[str]
) -> ScoreResult:
    fields_text = _fields(record)
    combined = " ".join(fields_text.values()).lower()

    matched_exclude = [kw for kw in exclude_keywords if kw.lower() in combined]
    if matched_exclude:
        return ScoreResult(score=0, excluded=True, matched_exclude=matched_exclude)

    score = 0
    matched_include: list[str] = []
    for field_name, text in fields_text.items():
        text_lower = text.lower()
        weight = _FIELD_WEIGHTS[field_name]
        for kw in include_keywords:
            if kw.lower() in text_lower:
                score += weight
                if kw not in matched_include:
                    matched_include.append(kw)

    return ScoreResult(score=score, excluded=False, matched_include=matched_include)
