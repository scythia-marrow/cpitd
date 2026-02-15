"""Post-aggregation filters for suppressing benign clone groups."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Callable

from cpitd.reporter import CloneGroup, CloneReport


def _extract_lines(
    source: str,
    line_range: tuple[int, int],
) -> list[str]:
    """Return the source lines for the given 1-based inclusive range."""
    lines = source.splitlines()
    start, end = line_range
    return lines[start - 1 : end]


def _group_matches(
    group: CloneGroup,
    patterns: tuple[str, ...],
    read_fn: Callable[[str], str | None],
    cache: dict[str, str | None],
) -> bool:
    """Return True if any source line in either chunk matches any pattern."""
    for file_path, line_range in (
        (group.file_a, group.lines_a),
        (group.file_b, group.lines_b),
    ):
        if file_path not in cache:
            cache[file_path] = read_fn(file_path)
        source = cache[file_path]
        if source is None:
            continue
        for line in _extract_lines(source, line_range):
            for pat in patterns:
                if fnmatch(line, pat):
                    return True
    return False


def filter_reports(
    reports: list[CloneReport],
    suppress_patterns: tuple[str, ...],
    read_fn: Callable[[str], str | None],
) -> list[CloneReport]:
    """Remove clone groups whose source lines match any suppress pattern.

    Args:
        reports: Aggregated clone reports from the pipeline.
        suppress_patterns: fnmatch glob patterns to check against source lines.
        read_fn: Dependency-injected file reader returning contents or None.

    Returns:
        Filtered reports with matching groups removed. Reports with no
        remaining groups are dropped entirely.
    """
    if not suppress_patterns:
        return reports

    cache: dict[str, str | None] = {}
    filtered: list[CloneReport] = []

    for report in reports:
        kept_groups = [
            g
            for g in report.groups
            if not _group_matches(g, suppress_patterns, read_fn, cache)
        ]
        if not kept_groups:
            continue
        total_lines = sum(g.line_count for g in kept_groups)
        filtered.append(
            CloneReport(
                file_a=report.file_a,
                file_b=report.file_b,
                groups=kept_groups,
                total_cloned_lines=total_lines,
            )
        )

    return filtered
