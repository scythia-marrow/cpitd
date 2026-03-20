"""Tests for the line-hash indexer."""

from cpitd.indexer import CloneMatchGroup, LineHashIndex, NodeLocation
from cpitd.winnowing import HashTreeNode, LineHash, build_hash_tree, hash_lines


def _node(hash_value: int, start: int, end: int, level: int = 0, tokens: int = 10):
    """Helper to create a HashTreeNode."""
    return HashTreeNode(
        hash_value=hash_value,
        start_line=start,
        end_line=end,
        level=level,
        token_count=tokens,
    )


def _single_level_tree(nodes: list[HashTreeNode]) -> list[list[HashTreeNode]]:
    """Wrap nodes as a single-level tree."""
    return [nodes]


class TestLineHashIndex:
    def test_no_clones_single_file(self):
        index = LineHashIndex()
        tree = _single_level_tree([_node(1, 1, 1), _node(2, 2, 2), _node(3, 3, 3)])
        index.add("a.py", tree)
        groups = index.find_clones()
        assert groups == []

    def test_detects_cross_file_clone(self):
        index = LineHashIndex()
        index.add("a.py", _single_level_tree([_node(1, 1, 1), _node(2, 2, 2)]))
        index.add("b.py", _single_level_tree([_node(2, 1, 1), _node(3, 2, 2)]))
        groups = index.find_clones()
        assert len(groups) == 1
        assert groups[0].shared_hash == 2
        assert len(groups[0].locations) == 2

    def test_same_file_non_overlapping(self):
        """Same-file matches with non-overlapping ranges are kept in the group."""
        index = LineHashIndex()
        tree = _single_level_tree([_node(42, 1, 1), _node(42, 10, 10)])
        index.add("a.py", tree)
        groups = index.find_clones()
        assert len(groups) == 1
        assert len(groups[0].locations) == 2

    def test_min_token_count_filters(self):
        """Nodes below min_token_count are excluded."""
        index = LineHashIndex()
        index.add("a.py", _single_level_tree([_node(1, 1, 1, tokens=3)]))
        index.add("b.py", _single_level_tree([_node(1, 1, 1, tokens=3)]))
        groups = index.find_clones(min_token_count=10)
        assert groups == []

    def test_noise_bucket_filtered(self):
        """Buckets exceeding _MAX_BUCKET_SIZE are skipped."""
        index = LineHashIndex()
        for i in range(101):
            index.add(f"file_{i}.py", _single_level_tree([_node(99, 1, 1)]))
        groups = index.find_clones()
        assert groups == []

    def test_multiple_shared_hashes(self):
        index = LineHashIndex()
        index.add("a.py", _single_level_tree([_node(10, 1, 1), _node(20, 2, 2)]))
        index.add("b.py", _single_level_tree([_node(10, 1, 1), _node(20, 2, 2)]))
        groups = index.find_clones()
        shared = {g.shared_hash for g in groups}
        assert shared == {10, 20}

    def test_three_files_single_group(self):
        """Three files sharing a hash produce one group with 3 locations, not 3 pairs."""
        index = LineHashIndex()
        index.add("a.py", _single_level_tree([_node(1, 1, 1)]))
        index.add("b.py", _single_level_tree([_node(1, 1, 1)]))
        index.add("c.py", _single_level_tree([_node(1, 1, 1)]))
        groups = index.find_clones()
        assert len(groups) == 1
        assert len(groups[0].locations) == 3

    def test_multi_level_tree(self):
        """Nodes from higher tree levels are also indexed."""
        lhs = [
            LineHash(hash_value=10, line=1, token_count=10),
            LineHash(hash_value=20, line=2, token_count=10),
        ]
        tree = build_hash_tree(lhs)
        index = LineHashIndex()
        index.add("a.py", tree)
        index.add("b.py", tree)
        groups = index.find_clones()
        levels = {g.level for g in groups}
        assert 0 in levels
        assert 1 in levels
