"""Tests for the fingerprint indexer."""

from cpitd.indexer import ClonePair, FingerprintIndex, FingerprintLocation
from cpitd.winnowing import Fingerprint


def _fp(hash_value: int, line: int = 1) -> Fingerprint:
    """Helper to create a Fingerprint."""
    return Fingerprint(hash_value=hash_value, line=line, column=0, token_index=0)


class TestFingerprintIndex:
    def test_no_clones_single_file(self):
        index = FingerprintIndex()
        index.add("a.py", [_fp(1), _fp(2), _fp(3)])
        pairs = index.find_clones()
        assert pairs == []

    def test_detects_cross_file_clone(self):
        index = FingerprintIndex()
        index.add("a.py", [_fp(1), _fp(2)])
        index.add("b.py", [_fp(2), _fp(3)])
        pairs = index.find_clones()
        assert len(pairs) == 1
        assert pairs[0].shared_hash == 2

    def test_no_self_clones(self):
        index = FingerprintIndex()
        index.add("a.py", [_fp(1), _fp(1)])  # same hash twice in one file
        pairs = index.find_clones()
        assert pairs == []

    def test_multiple_shared_hashes(self):
        index = FingerprintIndex()
        index.add("a.py", [_fp(10), _fp(20), _fp(30)])
        index.add("b.py", [_fp(10), _fp(20), _fp(40)])
        pairs = index.find_clones()
        shared_hashes = {p.shared_hash for p in pairs}
        assert shared_hashes == {10, 20}

    def test_three_files_pairwise(self):
        index = FingerprintIndex()
        index.add("a.py", [_fp(1)])
        index.add("b.py", [_fp(1)])
        index.add("c.py", [_fp(1)])
        pairs = index.find_clones()
        # Should find 3 pairs: (a,b), (a,c), (b,c)
        assert len(pairs) == 3
