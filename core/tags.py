"""Subspecialty tag derivation, shared by the site and the email digest so
both group books into subspecialties identically.
"""
from __future__ import annotations

# The three umbrella terms describe the whole tracker, not a subspecialty —
# excluded so filter chips / email groupings stay meaningful.
GENERIC_KEYWORDS = {"physiotherapy", "physical therapy", "rehabilitation"}


def derive_tags(matched_keywords: list[str]) -> list[str]:
    specific = sorted({kw for kw in matched_keywords if kw.lower() not in GENERIC_KEYWORDS})
    return specific or ["general"]
