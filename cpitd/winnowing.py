"""Winnowing fingerprinting algorithm for clone detection.

Implements the winnowing algorithm from Schleimer, Wilkerson, and Aiken (2003).
Given a sequence of tokens, produces a set of position-tagged hash fingerprints
that guarantee detection of any shared substring of sufficient length.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from cpitd.tokenizer import Token


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """A positional hash fingerprint from the winnowing algorithm."""

    hash_value: int
    line: int
    column: int
    token_index: int


def _hash_kgram(tokens: Sequence[Token], start: int, k: int) -> int:
    """Compute a hash for a k-gram starting at the given index."""
    return hash(tuple(t.value for t in tokens[start : start + k]))


def fingerprint(
    tokens: Sequence[Token],
    *,
    k: int = 5,
    window_size: int = 4,
) -> list[Fingerprint]:
    """Compute winnowing fingerprints for a token sequence.

    The winnowing algorithm guarantees that any shared substring of length
    at least (k + window_size - 1) tokens will be detected.

    Args:
        tokens: Sequence of normalized tokens from the tokenizer.
        k: Size of k-grams (number of tokens per gram).
        window_size: Number of k-gram hashes per winnowing window.

    Returns:
        List of selected Fingerprint objects.
    """
    n = len(tokens)
    if n < k:
        return []

    num_kgrams = n - k + 1
    kgram_hashes = [_hash_kgram(tokens, i, k) for i in range(num_kgrams)]

    if num_kgrams < window_size:
        # Not enough k-grams for a full window; take the minimum
        min_idx = min(range(num_kgrams), key=lambda i: kgram_hashes[i])
        t = tokens[min_idx]
        return [
            Fingerprint(
                hash_value=kgram_hashes[min_idx],
                line=t.line,
                column=t.column,
                token_index=min_idx,
            )
        ]

    selected: list[Fingerprint] = []
    prev_selected_idx = -1

    for w_start in range(num_kgrams - window_size + 1):
        w_end = w_start + window_size

        # Find rightmost minimum in this window
        min_idx = w_start
        min_hash = kgram_hashes[w_start]
        for i in range(w_start + 1, w_end):
            if kgram_hashes[i] <= min_hash:
                min_idx = i
                min_hash = kgram_hashes[i]

        if min_idx != prev_selected_idx:
            t = tokens[min_idx]
            selected.append(
                Fingerprint(
                    hash_value=min_hash,
                    line=t.line,
                    column=t.column,
                    token_index=min_idx,
                )
            )
            prev_selected_idx = min_idx

    return selected
