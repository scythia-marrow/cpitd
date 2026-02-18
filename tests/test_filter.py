"""Tests for cpitd.filter — clone group suppression."""

from __future__ import annotations

from cpitd.filter import (
    FilterContext,
    PatternMatchStage,
    SiblingStage,
    filter_reports,
    run_filters,
)
from cpitd.reporter import CloneGroup, CloneReport


def _make_group(
    file_a: str = "a.py",
    lines_a: tuple[int, int] = (1, 5),
    file_b: str = "b.py",
    lines_b: tuple[int, int] = (1, 5),
    line_count: int = 5,
    token_count: int = 20,
) -> CloneGroup:
    return CloneGroup(
        file_a=file_a,
        lines_a=lines_a,
        file_b=file_b,
        lines_b=lines_b,
        line_count=line_count,
        token_count=token_count,
    )


def _make_report(
    groups: list[CloneGroup],
    file_a: str = "a.py",
    file_b: str = "b.py",
) -> CloneReport:
    return CloneReport(
        file_a=file_a,
        file_b=file_b,
        groups=groups,
        total_cloned_lines=sum(g.line_count for g in groups),
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


class TestFilterReports:
    def test_empty_patterns_no_filtering(self) -> None:
        group = _make_group()
        report = _make_report([group])
        result = filter_reports([report], (), _read)
        assert result == [report]

    def test_matching_group_suppressed(self) -> None:
        group = _make_group(lines_a=(1, 4), lines_b=(1, 4), line_count=4)
        report = _make_report([group])
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert result == []

    def test_non_matching_group_kept(self) -> None:
        group = _make_group(lines_a=(5, 6), lines_b=(5, 6), line_count=2)
        report = _make_report([group])
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert len(result) == 1
        assert result[0].groups == [group]

    def test_only_matching_group_removed(self) -> None:
        matching = _make_group(lines_a=(1, 4), lines_b=(1, 4), line_count=4)
        kept = _make_group(lines_a=(5, 6), lines_b=(5, 6), line_count=2)
        report = _make_report([matching, kept])
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert len(result) == 1
        assert result[0].groups == [kept]
        assert result[0].total_cloned_lines == 2

    def test_multi_pattern_any_matches(self) -> None:
        group = _make_group(lines_a=(5, 6), lines_b=(5, 6), line_count=2)
        report = _make_report([group])
        result = filter_reports(
            [report], ("*@abstractmethod*", "*return 42*"), _read
        )
        assert result == []

    def test_decorator_above_chunk_suppresses(self) -> None:
        """A suppress pattern matching the line above the chunk suppresses it."""
        group = _make_group(lines_a=(3, 3), lines_b=(3, 3), line_count=1)
        report = _make_report([group])
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert result == []

    def test_context_above_clamped_at_file_start(self) -> None:
        """Context above doesn't go before line 1."""
        group = _make_group(lines_a=(1, 1), lines_b=(1, 1), line_count=1)
        report = _make_report([group])
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert len(result) == 1

    def test_unreadable_file_not_suppressed(self) -> None:
        """Groups referencing unreadable files are kept (not suppressed)."""
        group = _make_group(file_a="missing.py", file_b="also_missing.py")
        report = _make_report([group], file_a="missing.py", file_b="also_missing.py")
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert len(result) == 1


class TestSiblingSupression:
    """Sibling suppression: if both sides of a group appeared in directly-
    suppressed groups, suppress the group even without a direct pattern match."""

    def test_impl_vs_impl_suppressed_via_siblings(self) -> None:
        """Two implementations of an abstract method should be suppressed
        when each was individually suppressed against the ABC."""
        abc_vs_a = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_a.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        abc_vs_b = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        impl_vs_impl = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )

        reports = [
            _make_report([abc_vs_a], file_a="abc.py", file_b="impl_a.py"),
            _make_report([abc_vs_b], file_a="abc.py", file_b="impl_b.py"),
            _make_report([impl_vs_impl], file_a="impl_a.py", file_b="impl_b.py"),
        ]
        result = filter_reports(reports, ("*@abstractmethod*",), _read)
        assert result == []

    def test_sibling_suppression_only_when_both_sides_known(self) -> None:
        """A group is only sibling-suppressed when BOTH sides appeared in
        directly-suppressed groups. One side known is not enough."""
        abc_vs_a = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_a.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        mixed = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="b.py", lines_b=(5, 5),
            line_count=1, token_count=10,
        )

        reports = [
            _make_report([abc_vs_a], file_a="abc.py", file_b="impl_a.py"),
            _make_report([mixed], file_a="impl_a.py", file_b="b.py"),
        ]
        result = filter_reports(reports, ("*@abstractmethod*",), _read)
        assert len(result) == 1
        assert result[0].groups == [mixed]

    def test_sibling_suppression_with_overlapping_ranges(self) -> None:
        """Sibling suppression works when line ranges overlap but aren't
        exactly equal."""
        abc_vs_a = _make_group(
            file_a="abc.py", lines_a=(4, 6),
            file_b="impl_a.py", lines_b=(3, 5),
            line_count=3, token_count=15,
        )
        abc_vs_b = _make_group(
            file_a="abc.py", lines_a=(4, 6),
            file_b="impl_b.py", lines_b=(3, 5),
            line_count=3, token_count=15,
        )
        impl_vs_impl = _make_group(
            file_a="impl_a.py", lines_a=(4, 5),
            file_b="impl_b.py", lines_b=(4, 5),
            line_count=2, token_count=10,
        )

        reports = [
            _make_report([abc_vs_a], file_a="abc.py", file_b="impl_a.py"),
            _make_report([abc_vs_b], file_a="abc.py", file_b="impl_b.py"),
            _make_report([impl_vs_impl], file_a="impl_a.py", file_b="impl_b.py"),
        ]
        result = filter_reports(reports, ("*@abstractmethod*",), _read)
        assert result == []

    def test_non_sibling_groups_preserved_alongside_suppressed(self) -> None:
        """Within a report, only sibling-suppressed groups are removed;
        unrelated groups survive."""
        abc_vs_a = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_a.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        abc_vs_b = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        sibling = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        unrelated = _make_group(
            file_a="impl_a.py", lines_a=(1, 1),
            file_b="impl_b.py", lines_b=(1, 1),
            line_count=1, token_count=10,
        )

        reports = [
            _make_report([abc_vs_a], file_a="abc.py", file_b="impl_a.py"),
            _make_report([abc_vs_b], file_a="abc.py", file_b="impl_b.py"),
            _make_report([sibling, unrelated], file_a="impl_a.py", file_b="impl_b.py"),
        ]
        result = filter_reports(reports, ("*@abstractmethod*",), _read)
        assert len(result) == 1
        assert result[0].groups == [unrelated]
        assert result[0].total_cloned_lines == 1


class TestPatternMatchStageIsolation:
    """Test PatternMatchStage in isolation (without SiblingStage)."""

    def test_suppresses_matching_group(self) -> None:
        group = _make_group(lines_a=(1, 4), lines_b=(1, 4), line_count=4)
        report = _make_report([group])
        result = run_filters([report], [PatternMatchStage(("*@abstractmethod*",))], _read)
        assert result == []

    def test_keeps_non_matching_group(self) -> None:
        group = _make_group(lines_a=(5, 6), lines_b=(5, 6), line_count=2)
        report = _make_report([group])
        result = run_filters([report], [PatternMatchStage(("*@abstractmethod*",))], _read)
        assert len(result) == 1
        assert result[0].groups == [group]

    def test_populates_suppressed_locations(self) -> None:
        """PatternMatchStage records suppressed locations in the context."""
        group = _make_group(lines_a=(1, 4), lines_b=(1, 4), line_count=4)
        report = _make_report([group])
        ctx = FilterContext(read_fn=_read)
        PatternMatchStage(("*@abstractmethod*",))([report], ctx)
        assert ("a.py", (1, 4)) in ctx.suppressed_locations
        assert ("b.py", (1, 4)) in ctx.suppressed_locations


class TestSiblingStageIsolation:
    """Test SiblingStage in isolation with pre-populated suppressed locations."""

    def test_suppresses_when_both_sides_known(self) -> None:
        group = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        report = _make_report([group], file_a="impl_a.py", file_b="impl_b.py")
        ctx = FilterContext(read_fn=_read)
        ctx.suppressed_locations = {
            ("impl_a.py", (4, 4)),
            ("impl_b.py", (4, 4)),
        }
        result = SiblingStage()([report], ctx)
        assert result == []

    def test_keeps_when_one_side_unknown(self) -> None:
        group = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="b.py", lines_b=(5, 5),
            line_count=1, token_count=10,
        )
        report = _make_report([group], file_a="impl_a.py", file_b="b.py")
        ctx = FilterContext(read_fn=_read)
        ctx.suppressed_locations = {("impl_a.py", (4, 4))}
        result = SiblingStage()([report], ctx)
        assert len(result) == 1
        assert result[0].groups == [group]

    def test_no_suppression_with_empty_locations(self) -> None:
        group = _make_group()
        report = _make_report([group])
        ctx = FilterContext(read_fn=_read)
        result = SiblingStage()([report], ctx)
        assert len(result) == 1


class TestStageComposition:
    """Test that stages compose correctly via run_filters."""

    def test_pattern_then_sibling_full_pipeline(self) -> None:
        """PatternMatchStage + SiblingStage together replicate filter_reports."""
        abc_vs_a = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_a.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        abc_vs_b = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        impl_vs_impl = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )

        reports = [
            _make_report([abc_vs_a], file_a="abc.py", file_b="impl_a.py"),
            _make_report([abc_vs_b], file_a="abc.py", file_b="impl_b.py"),
            _make_report([impl_vs_impl], file_a="impl_a.py", file_b="impl_b.py"),
        ]

        stages = [PatternMatchStage(("*@abstractmethod*",)), SiblingStage()]
        result = run_filters(reports, stages, _read)
        assert result == []

    def test_pattern_only_leaves_sibling_groups(self) -> None:
        """Without SiblingStage, impl-vs-impl groups survive."""
        abc_vs_a = _make_group(
            file_a="abc.py", lines_a=(5, 5),
            file_b="impl_a.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )
        impl_vs_impl = _make_group(
            file_a="impl_a.py", lines_a=(4, 4),
            file_b="impl_b.py", lines_b=(4, 4),
            line_count=1, token_count=10,
        )

        reports = [
            _make_report([abc_vs_a], file_a="abc.py", file_b="impl_a.py"),
            _make_report([impl_vs_impl], file_a="impl_a.py", file_b="impl_b.py"),
        ]

        result = run_filters(reports, [PatternMatchStage(("*@abstractmethod*",))], _read)
        assert len(result) == 1
        assert result[0].groups == [impl_vs_impl]

    def test_empty_stage_list_is_noop(self) -> None:
        group = _make_group()
        report = _make_report([group])
        result = run_filters([report], [], _read)
        assert result == [report]
