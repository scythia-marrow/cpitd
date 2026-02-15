"""Pygments-based tokenizer with configurable normalization levels."""

from __future__ import annotations

from enum import IntEnum

import pygments.token as token_types
from pygments import lex
from pygments.lexers import get_lexer_for_filename, guess_lexer

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


# Token categories we always discard (whitespace, comments)
_SKIP_TYPES = frozenset(
    {
        token_types.Token.Text,
        token_types.Token.Text.Whitespace,
        token_types.Token.Comment,
        token_types.Token.Comment.Single,
        token_types.Token.Comment.Multiline,
        token_types.Token.Comment.Preproc,
        token_types.Token.Comment.PreprocFile,
        token_types.Token.Comment.Special,
        token_types.Token.Comment.Hashbang,
    }
)

_IDENTIFIER_TYPES = frozenset(
    {
        token_types.Token.Name,
        token_types.Token.Name.Variable,
        token_types.Token.Name.Function,
        token_types.Token.Name.Class,
        token_types.Token.Name.Attribute,
        token_types.Token.Name.Other,
    }
)

_LITERAL_TYPES = frozenset(
    {
        token_types.Token.Literal,
        token_types.Token.Literal.String,
        token_types.Token.Literal.String.Single,
        token_types.Token.Literal.String.Double,
        token_types.Token.Literal.String.Backtick,
        token_types.Token.Literal.Number,
        token_types.Token.Literal.Number.Integer,
        token_types.Token.Literal.Number.Float,
        token_types.Token.Literal.Number.Hex,
    }
)

_ID_PLACEHOLDER = "ID"
_LIT_PLACEHOLDER = "LIT"


def _is_subtype(ttype, parent_set):
    """Check if a token type is a subtype of any type in the set."""
    return any(ttype is parent or ttype in parent for parent in parent_set)


def _advance_position(
    line: int, col: int, value: str, newlines: int
) -> tuple[int, int]:
    """Update line/column tracking after consuming a token value."""
    if newlines:
        return line + newlines, len(value.rsplit("\n", 1)[-1])
    return line, col + len(value)


def _normalize_value(ttype, value, level):
    """Return the normalized token value based on normalization level."""
    if level >= NormalizationLevel.IDENTIFIERS and _is_subtype(
        ttype, _IDENTIFIER_TYPES
    ):
        return _ID_PLACEHOLDER
    if level >= NormalizationLevel.LITERALS and _is_subtype(ttype, _LITERAL_TYPES):
        return _LIT_PLACEHOLDER
    return value


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
        lexer = get_lexer_for_filename(filename, stripall=True)
    else:
        lexer = guess_lexer(source)

    tokens = []
    line = 1
    col = 0

    for ttype, value in lex(source, lexer):
        newlines = value.count("\n")

        if not _is_subtype(ttype, _SKIP_TYPES):
            normalized = _normalize_value(ttype, value, level)
            tokens.append(Token(value=normalized, line=line, column=col))

        line, col = _advance_position(line, col, value, newlines)

    return tokens
