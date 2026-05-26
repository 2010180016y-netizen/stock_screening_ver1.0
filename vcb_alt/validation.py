from __future__ import annotations

import re
from collections.abc import Iterable

from .errors import ValidationError

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def validate_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not ticker:
        raise ValidationError("Ticker is required.")
    if not TICKER_RE.fullmatch(ticker):
        raise ValidationError(
            "Ticker must be 1-10 characters and contain only letters, numbers, dot, or hyphen."
        )
    if ".." in ticker or "--" in ticker:
        raise ValidationError("Ticker contains an invalid repeated separator.")
    return ticker


def validate_tickers(values: Iterable[str]) -> list[str]:
    tickers = [validate_ticker(value) for value in values]
    if not tickers:
        raise ValidationError("At least one ticker is required.")
    return list(dict.fromkeys(tickers))


def validate_positive_number(value: float, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number.") from exc
    if number <= 0:
        raise ValidationError(f"{field_name} must be greater than 0.")
    return number


def validate_percentage(value: float, field_name: str, *, minimum: float = 0.0, maximum: float = 100.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number.") from exc
    if number < minimum or number > maximum:
        raise ValidationError(f"{field_name} must be between {minimum} and {maximum}.")
    return number


def require_delete_confirmation(value: str | None) -> None:
    if value != "DELETE_LOCAL_DATA":
        raise ValidationError("Destructive delete requires --confirm DELETE_LOCAL_DATA.")

