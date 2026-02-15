"""Shared type definitions and utilities for cpitd."""

from __future__ import annotations

from dataclasses import dataclass

# Reusable decorator for immutable, slot-based dataclasses.
frozen_slots = dataclass(frozen=True, slots=True)

# Semantic alias for CLI positional path arguments.
Paths = tuple[str, ...]
