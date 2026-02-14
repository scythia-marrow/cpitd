"""Tests for the winnowing fingerprinting algorithm and line-hash tree."""

from cpitd.tokenizer import Token
from cpitd.winnowing import (
    Fingerprint,
    HashTreeNode,
    LineHash,
    build_hash_tree,
    fingerprint,
    hash_lines,
)


def _make_tokens(values: list[str]) -> list[Token]:
    """Helper to create Token objects from a list of string values."""
    return [Token(value=v, line=1, column=i) for i, v in enumerate(values)]


def _make_tokens_multiline(lines: list[list[str]]) -> list[Token]:
    """Helper to create tokens spread across multiple lines."""
    tokens = []
    for line_num, values in enumerate(lines, start=1):
        for col, v in enumerate(values):
            tokens.append(Token(value=v, line=line_num, column=col))
    return tokens


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


class TestHashLines:
    """Tests for per-line token hashing."""

    def test_single_line(self):
        tokens = _make_tokens(["x", "=", "1"])
        result = hash_lines(tokens)
        assert len(result) == 1
        assert result[0].line == 1
        assert result[0].token_count == 3

    def test_multiple_lines(self):
        tokens = _make_tokens_multiline([
            ["x", "=", "1"],
            ["y", "=", "2"],
            ["z", "=", "3"],
        ])
        result = hash_lines(tokens)
        assert len(result) == 3
        assert [lh.line for lh in result] == [1, 2, 3]

    def test_identical_lines_same_hash(self):
        tokens = _make_tokens_multiline([
            ["x", "=", "1"],
            ["x", "=", "1"],
        ])
        result = hash_lines(tokens)
        assert result[0].hash_value == result[1].hash_value

    def test_different_lines_different_hash(self):
        tokens = _make_tokens_multiline([
            ["x", "=", "1"],
            ["y", "=", "2"],
        ])
        result = hash_lines(tokens)
        assert result[0].hash_value != result[1].hash_value

    def test_empty_tokens(self):
        result = hash_lines([])
        assert result == []

    def test_token_count_per_line(self):
        tokens = _make_tokens_multiline([
            ["a", "b"],
            ["c", "d", "e"],
        ])
        result = hash_lines(tokens)
        assert result[0].token_count == 2
        assert result[1].token_count == 3


class TestBuildHashTree:
    """Tests for the binary hash tree."""

    def test_empty_input(self):
        result = build_hash_tree([])
        assert result == []

    def test_single_line(self):
        lh = [LineHash(hash_value=42, line=1, token_count=5)]
        result = build_hash_tree(lh)
        assert len(result) == 1  # only level 0
        assert len(result[0]) == 1
        assert result[0][0].level == 0
        assert result[0][0].start_line == 1
        assert result[0][0].end_line == 1

    def test_two_lines_produce_two_levels(self):
        lhs = [
            LineHash(hash_value=1, line=1, token_count=3),
            LineHash(hash_value=2, line=2, token_count=4),
        ]
        result = build_hash_tree(lhs)
        assert len(result) == 2  # level 0 and level 1
        assert len(result[0]) == 2  # two leaves
        assert len(result[1]) == 1  # one parent
        parent = result[1][0]
        assert parent.start_line == 1
        assert parent.end_line == 2
        assert parent.level == 1
        assert parent.token_count == 7

    def test_odd_trailing_node_does_not_promote(self):
        lhs = [
            LineHash(hash_value=1, line=1, token_count=2),
            LineHash(hash_value=2, line=2, token_count=2),
            LineHash(hash_value=3, line=3, token_count=2),
        ]
        result = build_hash_tree(lhs)
        assert len(result[0]) == 3  # three leaves
        assert len(result[1]) == 1  # only one pair promotes

    def test_four_lines_three_levels(self):
        lhs = [
            LineHash(hash_value=i, line=i, token_count=2)
            for i in range(1, 5)
        ]
        result = build_hash_tree(lhs)
        assert len(result) >= 3
        assert len(result[0]) == 4
        assert len(result[1]) == 2
        assert len(result[2]) == 1
        top = result[2][0]
        assert top.start_line == 1
        assert top.end_line == 4
        assert top.token_count == 8

    def test_identical_subtrees_same_hash(self):
        lhs = [
            LineHash(hash_value=10, line=1, token_count=2),
            LineHash(hash_value=20, line=2, token_count=2),
            LineHash(hash_value=10, line=3, token_count=2),
            LineHash(hash_value=20, line=4, token_count=2),
        ]
        result = build_hash_tree(lhs)
        # Level 1 pairs (1,2) and (3,4) should have the same hash
        assert result[1][0].hash_value == result[1][1].hash_value

    def test_level_cap(self):
        # 512 lines → should cap at _MAX_TREE_LEVEL = 8
        lhs = [
            LineHash(hash_value=i, line=i, token_count=1)
            for i in range(1, 513)
        ]
        result = build_hash_tree(lhs)
        assert len(result) <= 9  # levels 0..8
