"""Winnowing fingerprinting algorithm and line-hash tree for clone detection.

Implements the winnowing algorithm from Schleimer, Wilkerson, and Aiken (2003)
and a line-based hash tree for detecting copy-pasted code regions.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from cpitd.tokenizer import Token
from cpitd.types import frozen_slots

# Algorithm internals — not exposed as CLI options.
_K_GRAM_SIZE = 5
_WINDOW_SIZE = 4
_MAX_TREE_LEVEL = 8  # 2^8 = 256 lines max group


@frozen_slots
class Fingerprint:
    """A positional hash fingerprint from the winnowing algorithm."""

    hash_value: int
    line: int
    column: int
    token_index: int


def _make_fingerprint(
    tokens: Sequence[Token], idx: int, hash_value: int
) -> Fingerprint:
    """Build a Fingerprint from a token index and its hash."""
    t = tokens[idx]
    return Fingerprint(
        hash_value=hash_value, line=t.line, column=t.column, token_index=idx
    )


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
        return [_make_fingerprint(tokens, min_idx, kgram_hashes[min_idx])]

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
            selected.append(_make_fingerprint(tokens, min_idx, min_hash))
            prev_selected_idx = min_idx

    return selected


# ---------------------------------------------------------------------------
# Line-hash tree — per-line hashing with a binary tree for group detection
# ---------------------------------------------------------------------------


@frozen_slots
class LineHash:
    """Hash of a single source line's tokens."""

    hash_value: int
    line: int
    token_count: int


@frozen_slots
class HashTreeNode:
    """A node in the binary hash tree covering a contiguous range of lines."""

    hash_value: int
    start_line: int
    end_line: int
    level: int
    token_count: int


def hash_lines(tokens: Sequence[Token]) -> list[LineHash]:
    """Group tokens by source line and produce a hash for each line.

    Args:
        tokens: Sequence of tokens (whitespace/comments already stripped).

    Returns:
        One ``LineHash`` per source line that contains at least one token,
        ordered by line number.
    """
    by_line: dict[int, list[str]] = defaultdict(list)
    for t in tokens:
        by_line[t.line].append(t.value)

    return [
        LineHash(
            hash_value=hash(tuple(values)),
            line=line,
            token_count=len(values),
        )
        for line, values in sorted(by_line.items())
    ]


def build_hash_tree(line_hashes: list[LineHash]) -> list[list[HashTreeNode]]:
    """Build a fixed-alignment binary hash tree over line hashes.

    Level 0 contains one leaf node per line hash.  Each subsequent level
    pairs adjacent nodes (fixed alignment: indices 0-1, 2-3, …) and
    hashes their combined values.  An odd trailing node does not promote.

    Args:
        line_hashes: Per-line hashes from :func:`hash_lines`.

    Returns:
        List of levels, where ``levels[k]`` contains nodes spanning 2^k
        consecutive lines.  Capped at ``_MAX_TREE_LEVEL``.
    """
    if not line_hashes:
        return []

    # Level 0: leaves
    level_0 = [
        HashTreeNode(
            hash_value=lh.hash_value,
            start_line=lh.line,
            end_line=lh.line,
            level=0,
            token_count=lh.token_count,
        )
        for lh in line_hashes
    ]

    levels: list[list[HashTreeNode]] = [level_0]

    for lvl in range(1, _MAX_TREE_LEVEL + 1):
        prev = levels[lvl - 1]
        if len(prev) < 2:
            break

        current: list[HashTreeNode] = []
        for i in range(0, len(prev) - 1, 2):
            left, right = prev[i], prev[i + 1]
            current.append(
                HashTreeNode(
                    hash_value=hash((left.hash_value, right.hash_value)),
                    start_line=left.start_line,
                    end_line=right.end_line,
                    level=lvl,
                    token_count=left.token_count + right.token_count,
                )
            )
        levels.append(current)

    return levels
