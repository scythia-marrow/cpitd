"""Configuration handling for cpitd."""

from __future__ import annotations

from dataclasses import dataclass

from cpitd.tokenizer import NormalizationLevel


@dataclass(frozen=True, slots=True)
class Config:
    """Runtime configuration for a cpitd analysis run."""

    min_tokens: int = 50
    normalize: NormalizationLevel = NormalizationLevel.EXACT
    output_format: str = "human"
    ignore_patterns: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
