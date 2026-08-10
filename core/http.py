"""Shared HTTP helper: retry with exponential backoff on 429/5xx, honouring
Retry-After when the server sends one. Used by every source so backoff
behaviour is consistent and only written once.
"""
from __future__ import annotations

import logging
import random
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "physio-book-tracker/0.1 "
    "(personal reference-book tracker; contact via GitHub repo issues)"
)


class SourceError(Exception):
    """Raised when a source exhausts retries or hits an unrecoverable error.
    Callers catch this per-source so one failing source doesn't abort the run.
    """


def get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 20.0,
    max_retries: int = 5,
    backoff_base: float = 1.5,
) -> dict:
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    merged_headers.update(headers or {})

    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.get(url, params=params, headers=merged_headers, timeout=timeout)
        except requests.RequestException as exc:
            if attempt > max_retries:
                raise SourceError(f"request failed after {attempt} attempts: {exc}") from exc
            _sleep_backoff(attempt, backoff_base)
            continue

        if resp.status_code == 200:
            return resp.json()

        retryable = resp.status_code == 429 or 500 <= resp.status_code < 600
        if not retryable or attempt > max_retries:
            raise SourceError(
                f"GET {url} returned {resp.status_code} after {attempt} attempt(s): "
                f"{resp.text[:200]}"
            )

        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = backoff_base ** attempt
        else:
            delay = backoff_base ** attempt
        logger.warning(
            "GET %s -> %s (attempt %d/%d), retrying in %.1fs",
            url, resp.status_code, attempt, max_retries, delay,
        )
        time.sleep(delay)


def _sleep_backoff(attempt: int, backoff_base: float) -> None:
    delay = backoff_base ** attempt + random.uniform(0, 0.5)
    logger.warning("request error, retrying in %.1fs (attempt %d)", delay, attempt)
    time.sleep(delay)
