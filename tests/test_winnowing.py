"""Tests for the winnowing fingerprinting algorithm."""

from cpitd.tokenizer import Token
from cpitd.winnowing import Fingerprint, fingerprint


def _make_tokens(values: list[str]) -> list[Token]:
    """Helper to create Token objects from a list of string values."""
    return [Token(value=v, line=1, column=i) for i, v in enumerate(values)]


class TestFingerprint:
    """Core winnowing algorithm tests."""

    def test_returns_fingerprints(self):
        tokens = _make_tokens(["a", "b", "c", "d", "e", "f", "g", "h"])
        result = fingerprint(tokens, k=3, window_size=4)
        assert len(result) > 0
        assert all(isinstance(fp, Fingerprint) for fp in result)

    def test_too_few_tokens_returns_empty(self):
        tokens = _make_tokens(["a", "b"])
        result = fingerprint(tokens, k=5, window_size=4)
        assert result == []

    def test_identical_sequences_produce_same_hashes(self):
        tokens_a = _make_tokens(["x", "=", "1", "+", "2", ";", "y", "=", "3"])
        tokens_b = _make_tokens(["x", "=", "1", "+", "2", ";", "y", "=", "3"])
        fp_a = fingerprint(tokens_a, k=3, window_size=2)
        fp_b = fingerprint(tokens_b, k=3, window_size=2)
        hashes_a = {fp.hash_value for fp in fp_a}
        hashes_b = {fp.hash_value for fp in fp_b}
        assert hashes_a == hashes_b

    def test_different_sequences_produce_different_hashes(self):
        tokens_a = _make_tokens(["a", "b", "c", "d", "e", "f", "g", "h"])
        tokens_b = _make_tokens(["z", "y", "x", "w", "v", "u", "t", "s"])
        fp_a = fingerprint(tokens_a, k=3, window_size=4)
        fp_b = fingerprint(tokens_b, k=3, window_size=4)
        hashes_a = {fp.hash_value for fp in fp_a}
        hashes_b = {fp.hash_value for fp in fp_b}
        assert hashes_a != hashes_b

    def test_fingerprints_have_position_info(self):
        tokens = _make_tokens(["a", "b", "c", "d", "e", "f"])
        result = fingerprint(tokens, k=3, window_size=2)
        for fp in result:
            assert fp.line >= 1
            assert fp.token_index >= 0

    def test_small_window_selects_more_fingerprints(self):
        tokens = _make_tokens(list("abcdefghijklmnop"))
        fp_small = fingerprint(tokens, k=3, window_size=2)
        fp_large = fingerprint(tokens, k=3, window_size=6)
        assert len(fp_small) >= len(fp_large)

    def test_fewer_kgrams_than_window(self):
        tokens = _make_tokens(["a", "b", "c", "d", "e"])
        result = fingerprint(tokens, k=4, window_size=10)
        # Should still return at least one fingerprint
        assert len(result) >= 1
