"""Configuration handling for cpitd."""

from __future__ import annotations

from cpitd.tokenizer import NormalizationLevel
from cpitd.types import frozen_slots


@frozen_slots
class Config:
    """Runtime configuration for a cpitd analysis run."""

    min_tokens: int = 50
    normalize: NormalizationLevel = NormalizationLevel.EXACT
    output_format: str = "human"
    ignore_patterns: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
