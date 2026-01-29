"""Tests for the tokenizer module."""

from cpitd.tokenizer import NormalizationLevel, Token, tokenize


class TestTokenizeExact:
    """Level 0: only strip whitespace and comments."""

    def test_simple_python(self):
        source = "x = 1\n"
        tokens = tokenize(source, filename="test.py", level=NormalizationLevel.EXACT)
        values = [t.value for t in tokens]
        assert "x" in values
        assert "=" in values
        assert "1" in values

    def test_strips_comments(self):
        source = "x = 1  # a comment\n"
        tokens = tokenize(source, filename="test.py", level=NormalizationLevel.EXACT)
        values = [t.value for t in tokens]
        assert "a comment" not in " ".join(values)
        assert "x" in values

    def test_strips_whitespace(self):
        source = "x  =  1\n"
        tokens = tokenize(source, filename="test.py", level=NormalizationLevel.EXACT)
        values = [t.value for t in tokens]
        assert " " not in values
        assert "  " not in values

    def test_returns_token_dataclass(self):
        source = "x = 1\n"
        tokens = tokenize(source, filename="test.py", level=NormalizationLevel.EXACT)
        assert all(isinstance(t, Token) for t in tokens)
        assert all(hasattr(t, "line") and hasattr(t, "column") for t in tokens)

    def test_empty_source(self):
        tokens = tokenize("", filename="test.py", level=NormalizationLevel.EXACT)
        assert tokens == []


class TestTokenizeIdentifiers:
    """Level 1: normalize identifiers to ID."""

    def test_identifiers_normalized(self):
        source = "foo = bar\n"
        tokens = tokenize(
            source, filename="test.py", level=NormalizationLevel.IDENTIFIERS
        )
        values = [t.value for t in tokens]
        assert "foo" not in values
        assert "bar" not in values
        assert "ID" in values

    def test_keywords_preserved(self):
        source = "if True:\n    pass\n"
        tokens = tokenize(
            source, filename="test.py", level=NormalizationLevel.IDENTIFIERS
        )
        values = [t.value for t in tokens]
        # Keywords should not be normalized
        assert "if" in values or "True" in values


class TestTokenizeLiterals:
    """Level 2: normalize both identifiers and literals."""

    def test_string_literals_normalized(self):
        source = 'x = "hello world"\n'
        tokens = tokenize(source, filename="test.py", level=NormalizationLevel.LITERALS)
        values = [t.value for t in tokens]
        assert "hello world" not in values

    def test_numeric_literals_normalized(self):
        source = "x = 42\n"
        tokens = tokenize(source, filename="test.py", level=NormalizationLevel.LITERALS)
        values = [t.value for t in tokens]
        assert "42" not in values
