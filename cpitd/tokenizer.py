"""Pygments-based tokenizer with configurable normalization levels."""

from __future__ import annotations

from enum import IntEnum

import pygments.token as token_types
from pygments import lex
from pygments.lexers import get_lexer_for_filename, guess_lexer
from pygments.util import ClassNotFound

from cpitd.types import frozen_slots


class NormalizationLevel(IntEnum):
    """How aggressively to normalize tokens for comparison."""

    EXACT = 0  # Only strip whitespace/comments
    IDENTIFIERS = 1  # Normalize identifiers to generic ID token
    LITERALS = 2  # Normalize both identifiers and literals


@frozen_slots
class Token:
    """A normalized source token with location info."""

    value: str
    line: int
    column: int


def _expand_token_types(roots: frozenset) -> frozenset:
    """Expand a set of token types to include all descendants.

    Pygments token types form a hierarchy where ``Token.Name.Variable in
    Token.Name`` is True. This function walks that hierarchy so we can
    replace the O(N) ancestry check with a single O(1) set lookup.
    """
    expanded: set = set()

    def _walk(ttype) -> None:
        expanded.add(ttype)
        for child in ttype.subtypes:
            _walk(child)

    for root in roots:
        _walk(root)
    return frozenset(expanded)


# Token categories we always discard (whitespace, comments).
# Roots only — _expand_token_types adds all descendants.
_SKIP_TYPES = _expand_token_types(
    frozenset({token_types.Token.Text, token_types.Token.Comment})
)

_IDENTIFIER_TYPES = _expand_token_types(frozenset({token_types.Token.Name}))

_LITERAL_TYPES = _expand_token_types(frozenset({token_types.Token.Literal}))

_ID_PLACEHOLDER = "ID"
_LIT_PLACEHOLDER = "LIT"


def _advance_position(
    line: int, col: int, value: str, newlines: int
) -> tuple[int, int]:
    """Update line/column tracking after consuming a token value."""
    if newlines:
        return line + newlines, len(value.rsplit("\n", 1)[-1])
    return line, col + len(value)


def _normalize_value(ttype, value, level):
    """Return the normalized token value based on normalization level."""
    if level >= NormalizationLevel.IDENTIFIERS and ttype in _IDENTIFIER_TYPES:
        return _ID_PLACEHOLDER
    if level >= NormalizationLevel.LITERALS and ttype in _LITERAL_TYPES:
        return _LIT_PLACEHOLDER
    return value


# Lexer cache keyed by file suffix to avoid repeated entry_points iteration.
_lexer_cache: dict[str, object | None] = {}

_SENTINEL = object()


def _get_lexer(filename: str):
    """Get a pygments lexer for a filename, using a suffix-based cache."""
    # Extract suffix (e.g. ".py") for cache key
    dot = filename.rfind(".")
    suffix = filename[dot:] if dot >= 0 else ""

    cached = _lexer_cache.get(suffix, _SENTINEL)
    if cached is not _SENTINEL:
        if cached is None:
            raise ClassNotFound(f"no lexer for {filename!r}")
        # Clone the cached lexer class with stripall=True
        return cached.__class__(stripall=True)

    try:
        lexer = get_lexer_for_filename(filename, stripall=True)
    except ClassNotFound:
        _lexer_cache[suffix] = None
        raise
    _lexer_cache[suffix] = lexer
    return lexer


def tokenize(
    source: str,
    *,
    filename: str | None = None,
    level: NormalizationLevel = NormalizationLevel.EXACT,
) -> list[Token]:
    """Tokenize source code and return normalized tokens.

    Args:
        source: The source code text to tokenize.
        filename: Optional filename hint for language detection.
        level: How aggressively to normalize tokens.

    Returns:
        List of Token objects with whitespace/comments stripped.
    """
    if filename:
        lexer = _get_lexer(filename)
    else:
        lexer = guess_lexer(source)

    tokens = []
    line = 1
    col = 0

    for ttype, value in lex(source, lexer):
        newlines = value.count("\n")

        if ttype not in _SKIP_TYPES:
            normalized = _normalize_value(ttype, value, level)
            tokens.append(Token(value=normalized, line=line, column=col))

        line, col = _advance_position(line, col, value, newlines)

    return tokens
