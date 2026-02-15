"""Tests for cpitd.filter — clone group suppression."""

from __future__ import annotations

from cpitd.filter import filter_reports
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

    def test_unreadable_file_not_suppressed(self) -> None:
        """Groups referencing unreadable files are kept (not suppressed)."""
        group = _make_group(file_a="missing.py", file_b="also_missing.py")
        report = _make_report([group], file_a="missing.py", file_b="also_missing.py")
        result = filter_reports([report], ("*@abstractmethod*",), _read)
        assert len(result) == 1
