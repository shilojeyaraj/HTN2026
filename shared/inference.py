"""Quota handling shared by direct vision and Backboard's embedded LLM errors."""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class InferenceUnavailable(RuntimeError):
    """Configured inference routes cannot recover automatically."""


def is_rate_limited(error) -> bool:
    return bool(re.search(r"resource_exhausted|rate[ _-]?limit|\b429\b|insufficient_quota", str(error), re.I))


def is_daily_quota(error) -> bool:
    return bool(re.search(r"perday|per_day|per day|daily|insufficient_quota", str(error), re.I))


def retry_delay(error, attempt: int, retry_after: str | None = None) -> float:
    """Honor the longest supplied delay; cap only our own exponential backoff."""
    delays = [min(5 * 2 ** min(attempt, 4), 60)]
    for amount, unit in re.findall(
        r"(?:retry[_ ]?delay|retry\s+(?:in|after))\D*?(\d+(?:\.\d+)?)\s*(ms|s)?",
        str(error), re.I,
    ):
        delays.append(float(amount) / (1000 if unit.lower() == "ms" else 1))
    if retry_after:
        try:
            delays.append(float(retry_after))
        except ValueError:
            try:
                delays.append((parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    # Avoid retrying just before a provider's rounded reset boundary.
    return max(delays) + 1
