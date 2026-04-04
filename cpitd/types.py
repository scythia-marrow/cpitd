"""Shared type definitions and utilities for cpitd."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

# Reusable decorator for immutable, slot-based dataclasses.
frozen_slots = dataclass(frozen=True, slots=True)

# Semantic alias for CLI positional path arguments.
Paths = tuple[str, ...]

_F = TypeVar("_F")


def protocol_impl(name: str) -> Callable[[_F], _F]:
    """Mark a function as implementing a shared interface called *name*.

    Identity decorator — returns the function unchanged.  Its presence
    on the ``@protocol_impl`` line lets ``--suppress "*@protocol_impl*"``
    filter out intentionally-shared signatures from clone reports.

    Usage::

        @protocol_impl("Formatter")
        def format_json(...) -> None: ...
    """

    def _identity(fn: _F) -> _F:
        return fn

    return _identity
