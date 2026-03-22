"""Tests for cpitd.filter — clone cluster suppression."""

from __future__ import annotations

from cpitd.filter import (
    FilterContext,
    PatternMatchStage,
    SiblingStage,
    filter_clusters,
    run_filters,
)
from cpitd.reporter import CloneCluster, CloneLocation


def _make_cluster(
    locations: list[tuple[str, tuple[int, int]]] | None = None,
    line_count: int = 5,
    token_count: int = 20,
) -> CloneCluster:
    if locations is None:
        locations = [("a.py", (1, 5)), ("b.py", (1, 5))]
    return CloneCluster(
        locations=tuple(CloneLocation(file=f, lines=lines) for f, lines in locations),
        line_count=line_count,
        token_count=token_count,
    )


FILES: dict[str, str] = {
    "a.py": (
        "class Foo:\n"
        "    @abstractmethod\n"
        "    def do_thing(self):\n"
        "        pass\n"
        "    def normal(self):\n"
        "        return 42\n"
    ),
    "b.py": (
        "class Bar:\n"
        "    @abstractmethod\n"
        "    def do_thing(self):\n"
        "        pass\n"
        "    def other(self):\n"
        "        return 99\n"
    ),
    # ABC + two concrete implementations for sibling suppression tests
    "abc.py": (
        "from abc import ABC, abstractmethod\n"
        "\n"
        "class Animal(ABC):\n"
        "    @abstractmethod\n"
        "    def speak(self):\n"
        "        raise NotImplementedError\n"
    ),
    "impl_a.py": (
        "from animals import Animal\n"
        "\n"
        "class Dog(Animal):\n"
        "    def speak(self):\n"
        "        return 'woof'\n"
    ),
    "impl_b.py": (
        "from animals import Animal\n"
        "\n"
        "class Cat(Animal):\n"
        "    def speak(self):\n"
        "        return 'meow'\n"
    ),
}


def _read(path: str) -> str | None:
    return FILES.get(path)


class TestFilterClusters:
    def test_empty_patterns_no_filtering(self) -> None:
        cluster = _make_cluster()
        result = filter_clusters([cluster], (), _read)
        assert result == [cluster]

    def test_matching_cluster_suppressed(self) -> None:
        cluster = _make_cluster(
            [("a.py", (1, 4)), ("b.py", (1, 4))],
            line_count=4,
        )
        result = filter_clusters([cluster], ("*@abstractmethod*",), _read)
        assert result == []

    def test_non_matching_cluster_kept(self) -> None:
        cluster = _make_cluster(
            [("a.py", (5, 6)), ("b.py", (5, 6))],
            line_count=2,
        )
        result = filter_clusters([cluster], ("*@abstractmethod*",), _read)
        assert len(result) == 1
        assert result[0] == cluster

    def test_only_matching_cluster_removed(self) -> None:
        matching = _make_cluster(
            [("a.py", (1, 4)), ("b.py", (1, 4))],
            line_count=4,
        )
        kept = _make_cluster(
            [("a.py", (5, 6)), ("b.py", (5, 6))],
            line_count=2,
        )
        result = filter_clusters([matching, kept], ("*@abstractmethod*",), _read)
        assert len(result) == 1
        assert result[0] == kept

    def test_multi_pattern_any_matches(self) -> None:
        cluster = _make_cluster(
            [("a.py", (5, 6)), ("b.py", (5, 6))],
            line_count=2,
        )
        result = filter_clusters(
            [cluster],
            ("*@abstractmethod*", "*return 42*"),
            _read,
        )
        assert result == []

    def test_decorator_above_chunk_suppresses(self) -> None:
        """A suppress pattern matching the line above the chunk suppresses it."""
        cluster = _make_cluster(
            [("a.py", (3, 3)), ("b.py", (3, 3))],
            line_count=1,
        )
        result = filter_clusters([cluster], ("*@abstractmethod*",), _read)
        assert result == []

    def test_context_above_clamped_at_file_start(self) -> None:
        """Context above doesn't go before line 1."""
        cluster = _make_cluster(
            [("a.py", (1, 1)), ("b.py", (1, 1))],
            line_count=1,
        )
        result = filter_clusters([cluster], ("*@abstractmethod*",), _read)
        assert len(result) == 1

    def test_unreadable_file_not_suppressed(self) -> None:
        """Clusters referencing unreadable files are kept (not suppressed)."""
        cluster = _make_cluster(
            [("missing.py", (1, 5)), ("also_missing.py", (1, 5))],
        )
        result = filter_clusters([cluster], ("*@abstractmethod*",), _read)
        assert len(result) == 1


class TestSiblingSupression:
    """Sibling suppression: if all locations of a cluster appeared in directly-
    suppressed clusters, suppress the cluster even without a direct pattern match."""

    def test_impl_vs_impl_suppressed_via_siblings(self) -> None:
        """Two implementations of an abstract method should be suppressed
        when each was individually suppressed against the ABC."""
        abc_cluster = _make_cluster(
            [("abc.py", (5, 5)), ("impl_a.py", (4, 4)), ("impl_b.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        # This cluster only has impl_a and impl_b (no abc)
        impl_cluster = _make_cluster(
            [("impl_a.py", (4, 4)), ("impl_b.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        result = filter_clusters(
            [abc_cluster, impl_cluster],
            ("*@abstractmethod*",),
            _read,
        )
        assert result == []

    def test_sibling_suppression_only_when_both_sides_known(self) -> None:
        """A cluster is only sibling-suppressed when ALL locations appeared in
        directly-suppressed clusters. One side known is not enough."""
        abc_cluster = _make_cluster(
            [("abc.py", (5, 5)), ("impl_a.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        mixed = _make_cluster(
            [("impl_a.py", (4, 4)), ("b.py", (5, 5))],
            line_count=1,
            token_count=10,
        )
        result = filter_clusters(
            [abc_cluster, mixed],
            ("*@abstractmethod*",),
            _read,
        )
        assert len(result) == 1
        assert result[0] == mixed

    def test_sibling_suppression_with_overlapping_ranges(self) -> None:
        """Sibling suppression works when line ranges overlap but aren't
        exactly equal."""
        abc_cluster = _make_cluster(
            [("abc.py", (4, 6)), ("impl_a.py", (3, 5)), ("impl_b.py", (3, 5))],
            line_count=3,
            token_count=15,
        )
        impl_cluster = _make_cluster(
            [("impl_a.py", (4, 5)), ("impl_b.py", (4, 5))],
            line_count=2,
            token_count=10,
        )
        result = filter_clusters(
            [abc_cluster, impl_cluster],
            ("*@abstractmethod*",),
            _read,
        )
        assert result == []


class TestPatternMatchStageIsolation:
    """Test PatternMatchStage in isolation (without SiblingStage)."""

    def test_suppresses_matching_cluster(self) -> None:
        cluster = _make_cluster(
            [("a.py", (1, 4)), ("b.py", (1, 4))],
            line_count=4,
        )
        result = run_filters(
            [cluster],
            [PatternMatchStage(("*@abstractmethod*",))],
            _read,
        )
        assert result == []

    def test_keeps_non_matching_cluster(self) -> None:
        cluster = _make_cluster(
            [("a.py", (5, 6)), ("b.py", (5, 6))],
            line_count=2,
        )
        result = run_filters(
            [cluster],
            [PatternMatchStage(("*@abstractmethod*",))],
            _read,
        )
        assert len(result) == 1
        assert result[0] == cluster

    def test_populates_suppressed_locations(self) -> None:
        """PatternMatchStage records suppressed locations in the context."""
        cluster = _make_cluster(
            [("a.py", (1, 4)), ("b.py", (1, 4))],
            line_count=4,
        )
        ctx = FilterContext(read_fn=_read)
        PatternMatchStage(("*@abstractmethod*",))([cluster], ctx)
        assert ("a.py", (1, 4)) in ctx.suppressed_locations
        assert ("b.py", (1, 4)) in ctx.suppressed_locations


class TestSiblingStageIsolation:
    """Test SiblingStage in isolation with pre-populated suppressed locations."""

    def test_suppresses_when_all_locations_known(self) -> None:
        cluster = _make_cluster(
            [("impl_a.py", (4, 4)), ("impl_b.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        ctx = FilterContext(read_fn=_read)
        ctx.suppressed_locations = {
            ("impl_a.py", (4, 4)),
            ("impl_b.py", (4, 4)),
        }
        result = SiblingStage()([cluster], ctx)
        assert result == []

    def test_keeps_when_one_location_unknown(self) -> None:
        cluster = _make_cluster(
            [("impl_a.py", (4, 4)), ("b.py", (5, 5))],
            line_count=1,
            token_count=10,
        )
        ctx = FilterContext(read_fn=_read)
        ctx.suppressed_locations = {("impl_a.py", (4, 4))}
        result = SiblingStage()([cluster], ctx)
        assert len(result) == 1
        assert result[0] == cluster

    def test_no_suppression_with_empty_locations(self) -> None:
        cluster = _make_cluster()
        ctx = FilterContext(read_fn=_read)
        result = SiblingStage()([cluster], ctx)
        assert len(result) == 1


class TestStageComposition:
    """Test that stages compose correctly via run_filters."""

    def test_pattern_then_sibling_full_pipeline(self) -> None:
        """PatternMatchStage + SiblingStage together replicate filter_clusters."""
        abc_cluster = _make_cluster(
            [("abc.py", (5, 5)), ("impl_a.py", (4, 4)), ("impl_b.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        impl_cluster = _make_cluster(
            [("impl_a.py", (4, 4)), ("impl_b.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        stages = [PatternMatchStage(("*@abstractmethod*",)), SiblingStage()]
        result = run_filters([abc_cluster, impl_cluster], stages, _read)
        assert result == []

    def test_pattern_only_leaves_sibling_clusters(self) -> None:
        """Without SiblingStage, impl-vs-impl clusters survive."""
        abc_cluster = _make_cluster(
            [("abc.py", (5, 5)), ("impl_a.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        impl_cluster = _make_cluster(
            [("impl_a.py", (4, 4)), ("impl_b.py", (4, 4))],
            line_count=1,
            token_count=10,
        )
        result = run_filters(
            [abc_cluster, impl_cluster],
            [PatternMatchStage(("*@abstractmethod*",))],
            _read,
        )
        assert len(result) == 1
        assert result[0] == impl_cluster

    def test_empty_stage_list_is_noop(self) -> None:
        cluster = _make_cluster()
        result = run_filters([cluster], [], _read)
        assert result == [cluster]
