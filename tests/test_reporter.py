"""Tests for the reporter module."""

import io
import json

from cpitd.indexer import CloneMatch, NodeLocation
from cpitd.reporter import (
    CloneGroup,
    CloneReport,
    aggregate_clone_matches,
    format_human,
    format_json,
)
from cpitd.winnowing import HashTreeNode


def _node(hash_value: int, start: int, end: int, level: int = 0, tokens: int = 12):
    return HashTreeNode(
        hash_value=hash_value,
        start_line=start,
        end_line=end,
        level=level,
        token_count=tokens,
    )


def _match(
    file_a: str,
    start_a: int,
    file_b: str,
    start_b: int,
    hash_value: int = 1,
    level: int = 0,
    tokens: int = 12,
) -> CloneMatch:
    return CloneMatch(
        left=NodeLocation(file_a, _node(hash_value, start_a, start_a, level, tokens)),
        right=NodeLocation(file_b, _node(hash_value, start_b, start_b, level, tokens)),
        level=level,
        shared_hash=hash_value,
    )


class TestMergeConsecutive:
    def test_consecutive_lines_merged(self):
        matches = [
            _match("a.py", 1, "b.py", 10, hash_value=1),
            _match("a.py", 2, "b.py", 11, hash_value=2),
            _match("a.py", 3, "b.py", 12, hash_value=3),
        ]
        reports = aggregate_clone_matches(matches, min_group_tokens=1)
        assert len(reports) == 1
        assert len(reports[0].groups) == 1
        g = reports[0].groups[0]
        assert g.lines_a == (1, 3)
        assert g.lines_b == (10, 12)
        assert g.line_count == 3

    def test_non_consecutive_not_merged(self):
        matches = [
            _match("a.py", 1, "b.py", 10, hash_value=1),
            _match("a.py", 5, "b.py", 20, hash_value=2),
        ]
        reports = aggregate_clone_matches(matches, min_group_tokens=1)
        assert len(reports) == 1
        assert len(reports[0].groups) == 2

    def test_empty_matches(self):
        reports = aggregate_clone_matches([])
        assert reports == []


class TestDeduplication:
    def test_subsumed_group_removed(self):
        # Level-0 match within a level-1 match → only the larger survives
        matches = [
            _match("a.py", 1, "b.py", 1, hash_value=1, level=0, tokens=12),
            _match("a.py", 2, "b.py", 2, hash_value=2, level=0, tokens=12),
            # Level-1 match covering lines 1-2
            CloneMatch(
                left=NodeLocation("a.py", _node(99, 1, 2, level=1, tokens=24)),
                right=NodeLocation("b.py", _node(99, 1, 2, level=1, tokens=24)),
                level=1,
                shared_hash=99,
            ),
        ]
        reports = aggregate_clone_matches(matches, min_group_tokens=1)
        assert len(reports) == 1
        # The merged level-0 group (1-2) is subsumed by the level-1 group (1-2)
        assert len(reports[0].groups) == 1
        assert reports[0].groups[0].line_count == 2


class TestMinGroupTokens:
    def test_small_groups_filtered(self):
        matches = [_match("a.py", 1, "b.py", 1, tokens=5)]
        reports = aggregate_clone_matches(matches, min_group_tokens=10)
        assert reports == []

    def test_large_groups_kept(self):
        matches = [_match("a.py", 1, "b.py", 1, tokens=20)]
        reports = aggregate_clone_matches(matches, min_group_tokens=10)
        assert len(reports) == 1


class TestFormatHuman:
    def test_no_clones_message(self):
        out = io.StringIO()
        format_human([], out)
        assert "No clones detected" in out.getvalue()

    def test_reports_line_ranges(self):
        group = CloneGroup(
            file_a="a.py",
            lines_a=(10, 25),
            file_b="b.py",
            lines_b=(50, 65),
            line_count=16,
            token_count=80,
        )
        report = CloneReport(
            file_a="a.py",
            file_b="b.py",
            groups=[group],
            total_cloned_lines=16,
        )
        out = io.StringIO()
        format_human([report], out)
        output = out.getvalue()
        assert "a.py" in output
        assert "b.py" in output
        assert "Lines 10-25" in output
        assert "Lines 50-65" in output
        assert "16 lines" in output


class TestFormatJson:
    def test_valid_json(self):
        group = CloneGroup(
            file_a="a.py",
            lines_a=(1, 5),
            file_b="b.py",
            lines_b=(10, 14),
            line_count=5,
            token_count=30,
        )
        report = CloneReport(
            file_a="a.py",
            file_b="b.py",
            groups=[group],
            total_cloned_lines=5,
        )
        out = io.StringIO()
        format_json([report], out)
        data = json.loads(out.getvalue())
        assert data["total_pairs"] == 1
        assert len(data["clone_reports"]) == 1
        cr = data["clone_reports"][0]
        assert cr["file_a"] == "a.py"
        assert cr["groups"][0]["lines_a"] == [1, 5]
        assert cr["groups"][0]["line_count"] == 5

    def test_empty_reports_json(self):
        out = io.StringIO()
        format_json([], out)
        data = json.loads(out.getvalue())
        assert data["total_pairs"] == 0
