"""Strict JSON parse hooks shared by the advisory tools/ validators: a
duplicate object key or a non-finite constant (NaN, Infinity) is an error
instead of being silently resolved."""

from __future__ import annotations

from typing import Any, Dict, Sequence, Tuple


class StrictJsonError(ValueError):
    """Raised when local JSON is malformed or contains duplicate keys."""


def reject_duplicates(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("duplicate object key {!r}".format(key))
        result[key] = value
    return result


def reject_nonfinite(value: str) -> None:
    raise StrictJsonError("non-finite JSON constant {!r}".format(value))
