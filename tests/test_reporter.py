"""Tests for the reporter module."""

import io
import json

from cpitd.indexer import CloneMatchGroup, NodeLocation
from cpitd.reporter import (
    CloneCluster,
    CloneLocation,
    aggregate_clone_groups,
    compute_file_stats,
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


def _loc(
    file_path: str,
    hash_value: int,
    start: int,
    end: int = -1,
    level: int = 0,
    tokens: int = 12,
) -> NodeLocation:
    if end == -1:
        end = start
    return NodeLocation(
        file_path=file_path,
        node=_node(hash_value, start, end, level, tokens),
    )


def _group(
    locations: list[NodeLocation],
    level: int = 0,
    shared_hash: int = 1,
) -> CloneMatchGroup:
    return CloneMatchGroup(
        locations=tuple(locations),
        level=level,
        shared_hash=shared_hash,
    )


class TestMergeConsecutiveGroups:
    def test_consecutive_lines_merged(self):
        groups = [
            _group([_loc("a.py", 1, 1), _loc("b.py", 1, 10)], shared_hash=1),
            _group([_loc("a.py", 2, 2), _loc("b.py", 2, 11)], shared_hash=2),
            _group([_loc("a.py", 3, 3), _loc("b.py", 3, 12)], shared_hash=3),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 1
        assert clusters[0].line_count == 3
        # Should have 2 locations (a.py and b.py)
        assert len(clusters[0].locations) == 2

    def test_non_consecutive_not_merged(self):
        groups = [
            _group([_loc("a.py", 1, 1), _loc("b.py", 1, 10)], shared_hash=1),
            _group([_loc("a.py", 2, 5), _loc("b.py", 2, 20)], shared_hash=2),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 2

    def test_empty_groups(self):
        clusters = aggregate_clone_groups([])
        assert clusters == []

    def test_different_file_sets_not_merged(self):
        """Groups with different file sets stay separate even if lines are consecutive."""
        groups = [
            _group([_loc("a.py", 1, 1), _loc("b.py", 1, 1)], shared_hash=1),
            _group([_loc("a.py", 2, 2), _loc("c.py", 2, 2)], shared_hash=2),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 2

    def test_three_files_merged(self):
        """Three files sharing consecutive lines merge into one cluster."""
        groups = [
            _group(
                [
                    _loc("a.py", 1, 1),
                    _loc("b.py", 1, 1),
                    _loc("c.py", 1, 1),
                ],
                shared_hash=1,
            ),
            _group(
                [
                    _loc("a.py", 2, 2),
                    _loc("b.py", 2, 2),
                    _loc("c.py", 2, 2),
                ],
                shared_hash=2,
            ),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 1
        assert len(clusters[0].locations) == 3
        assert clusters[0].line_count == 2

    def test_intra_file_clone_preserves_both_locations(self):
        """Two locations in the same file should produce a cluster with 2 locations."""
        groups = [
            _group([_loc("a.py", 1, 1), _loc("a.py", 1, 10)], shared_hash=1),
            _group([_loc("a.py", 2, 2), _loc("a.py", 2, 11)], shared_hash=2),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 1
        assert len(clusters[0].locations) == 2
        assert clusters[0].line_count == 2
        lines = sorted(loc.lines for loc in clusters[0].locations)
        assert lines == [(1, 2), (10, 11)]

    def test_single_location_passes_through(self):
        """Single-location clusters pass through reporter; pipeline filters them."""
        groups = [
            _group([_loc("a.py", 1, 1)], shared_hash=1),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 1
        assert len(clusters[0].locations) == 1


class TestDeduplication:
    def test_subsumed_cluster_removed(self):
        # Level-0 merged cluster within a level-1 cluster → only the larger survives
        groups = [
            _group([_loc("a.py", 1, 1), _loc("b.py", 1, 1)], level=0, shared_hash=1),
            _group([_loc("a.py", 2, 2), _loc("b.py", 2, 2)], level=0, shared_hash=2),
            # Level-1 group covering lines 1-2
            _group(
                [
                    _loc("a.py", 99, 1, 2, level=1, tokens=24),
                    _loc("b.py", 99, 1, 2, level=1, tokens=24),
                ],
                level=1,
                shared_hash=99,
            ),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=1)
        assert len(clusters) == 1
        assert clusters[0].line_count == 2


class TestMinGroupTokens:
    def test_small_groups_filtered(self):
        groups = [
            _group(
                [_loc("a.py", 1, 1, tokens=5), _loc("b.py", 1, 1, tokens=5)],
                shared_hash=1,
            ),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=10)
        assert clusters == []

    def test_large_groups_kept(self):
        groups = [
            _group(
                [_loc("a.py", 1, 1, tokens=20), _loc("b.py", 1, 1, tokens=20)],
                shared_hash=1,
            ),
        ]
        clusters = aggregate_clone_groups(groups, min_group_tokens=10)
        assert len(clusters) == 1


class TestFormatHuman:
    def test_no_clones_message(self):
        out = io.StringIO()
        format_human([], out)
        assert "No clones detected" in out.getvalue()

    def test_reports_locations(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(10, 25)),
                CloneLocation(file="b.py", lines=(50, 65)),
            ),
            line_count=16,
            token_count=80,
        )
        out = io.StringIO()
        format_human([cluster], out)
        output = out.getvalue()
        assert "a.py" in output
        assert "b.py" in output
        assert "Lines 10-25" in output
        assert "Lines 50-65" in output
        assert "16 lines" in output
        assert "80 tokens" in output
        assert "1 clone group" in output

    def test_verbose_shows_source_text(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(2, 3)),
                CloneLocation(file="b.py", lines=(5, 6)),
            ),
            line_count=2,
            token_count=20,
        )
        source = "line1\nalpha\nbeta\nline4\n"

        def read_fn(path: str) -> str | None:
            return source if path == "a.py" else None

        out = io.StringIO()
        format_human([cluster], out, read_fn=read_fn)
        output = out.getvalue()
        assert "| alpha" in output
        assert "| beta" in output

    def test_no_source_text_without_read_fn(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 2)),
                CloneLocation(file="b.py", lines=(1, 2)),
            ),
            line_count=2,
            token_count=20,
        )
        out = io.StringIO()
        format_human([cluster], out)
        assert "|" not in out.getvalue()

    def test_multiple_locations_in_cluster(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 10)),
                CloneLocation(file="b.py", lines=(1, 10)),
                CloneLocation(file="c.py", lines=(5, 15)),
            ),
            line_count=10,
            token_count=50,
        )
        out = io.StringIO()
        format_human([cluster], out)
        output = out.getvalue()
        assert "a.py" in output
        assert "b.py" in output
        assert "c.py" in output


class TestFormatJson:
    def test_valid_json(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 5)),
                CloneLocation(file="b.py", lines=(10, 14)),
            ),
            line_count=5,
            token_count=30,
        )
        out = io.StringIO()
        format_json([cluster], out)
        data = json.loads(out.getvalue())
        assert data["total_groups"] == 1
        assert len(data["clone_reports"]) == 1
        cg = data["clone_reports"][0]
        assert cg["line_count"] == 5
        assert cg["token_count"] == 30
        assert len(cg["locations"]) == 2
        assert cg["locations"][0]["file"] == "a.py"
        assert cg["locations"][0]["lines"] == [1, 5]

    def test_deprecated_keys_present(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 5)),
                CloneLocation(file="b.py", lines=(10, 14)),
            ),
            line_count=5,
            token_count=30,
        )
        out = io.StringIO()
        format_json([cluster], out)
        data = json.loads(out.getvalue())
        # Deprecated aliases still present for backward compatibility
        assert data["clone_reports"] == data["clone_reports"]
        assert data["total_pairs"] == data["total_groups"]

    def test_verbose_includes_text(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 2)),
                CloneLocation(file="b.py", lines=(3, 4)),
            ),
            line_count=2,
            token_count=20,
        )
        source = "alpha\nbeta\ngamma\n"

        def read_fn(path: str) -> str | None:
            return source if path == "a.py" else None

        out = io.StringIO()
        format_json([cluster], out, read_fn=read_fn)
        data = json.loads(out.getvalue())
        assert data["clone_reports"][0]["text"] == "alpha\nbeta"

    def test_no_text_without_read_fn(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 2)),
                CloneLocation(file="b.py", lines=(1, 2)),
            ),
            line_count=2,
            token_count=20,
        )
        out = io.StringIO()
        format_json([cluster], out)
        data = json.loads(out.getvalue())
        assert "text" not in data["clone_reports"][0]

    def test_empty_reports_json(self):
        out = io.StringIO()
        format_json([], out)
        data = json.loads(out.getvalue())
        assert data["total_groups"] == 0
        assert data["total_pairs"] == 0


class TestComputeFileStats:
    def test_basic_stats(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 10)),
                CloneLocation(file="b.py", lines=(1, 10)),
            ),
            line_count=10,
            token_count=60,
        )
        stats = compute_file_stats(
            [cluster],
            {"a.py": 100, "b.py": 200},
        )
        assert len(stats) == 2
        a_stat = next(s for s in stats if s.file == "a.py")
        b_stat = next(s for s in stats if s.file == "b.py")
        assert a_stat.duplicated_tokens == 60
        assert a_stat.duplication_pct == 60.0
        assert b_stat.duplicated_tokens == 60
        assert b_stat.duplication_pct == 30.0

    def test_multiple_clusters_sum_tokens(self):
        c1 = CloneCluster(
            locations=(CloneLocation(file="a.py", lines=(1, 5)),),
            line_count=5,
            token_count=30,
        )
        c2 = CloneCluster(
            locations=(CloneLocation(file="a.py", lines=(10, 15)),),
            line_count=6,
            token_count=40,
        )
        stats = compute_file_stats([c1, c2], {"a.py": 100})
        assert len(stats) == 1
        assert stats[0].duplicated_tokens == 70
        assert stats[0].duplication_pct == 70.0

    def test_capped_at_total_tokens(self):
        cluster = CloneCluster(
            locations=(CloneLocation(file="a.py", lines=(1, 10)),),
            line_count=10,
            token_count=200,
        )
        stats = compute_file_stats([cluster], {"a.py": 100})
        assert stats[0].duplicated_tokens == 100
        assert stats[0].duplication_pct == 100.0

    def test_missing_file_in_counts_skipped(self):
        cluster = CloneCluster(
            locations=(CloneLocation(file="unknown.py", lines=(1, 5)),),
            line_count=5,
            token_count=30,
        )
        stats = compute_file_stats([cluster], {})
        assert stats == []

    def test_sorted_by_descending_pct(self):
        cluster = CloneCluster(
            locations=(
                CloneLocation(file="a.py", lines=(1, 5)),
                CloneLocation(file="b.py", lines=(1, 5)),
            ),
            line_count=5,
            token_count=50,
        )
        stats = compute_file_stats(
            [cluster],
            {"a.py": 100, "b.py": 50},
        )
        assert stats[0].file == "b.py"  # 100%
        assert stats[1].file == "a.py"  # 50%

    def test_empty_clusters(self):
        stats = compute_file_stats([], {"a.py": 100})
        assert stats == []
