"""Post-aggregation filters for suppressing benign clone groups."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Callable

from cpitd.reporter import CloneGroup, CloneReport

ReadFn = Callable[[str], str | None]


def _extract_lines(
    source: str,
    line_range: tuple[int, int],
    context_above: int = 0,
) -> list[str]:
    """Return the source lines for the given 1-based inclusive range.

    Args:
        source: Full file contents.
        line_range: 1-based inclusive (start, end) line range.
        context_above: Extra lines to include before the chunk start,
            clamped to the beginning of the file.
    """
    lines = source.splitlines()
    start, end = line_range
    start = max(1, start - context_above)
    return lines[start - 1 : end]


def _group_matches(
    group: CloneGroup,
    patterns: tuple[str, ...],
    read_fn: ReadFn,
    cache: dict[str, str | None],
) -> bool:
    """Return True if any source line in either chunk matches any pattern.

    Includes one line of context above each chunk to catch decorators
    like ``@abstractmethod``.
    """
    for file_path, line_range in (
        (group.file_a, group.lines_a),
        (group.file_b, group.lines_b),
    ):
        if file_path not in cache:
            cache[file_path] = read_fn(file_path)
        source = cache[file_path]
        if source is None:
            continue
        for line in _extract_lines(source, line_range, context_above=1):
            for pat in patterns:
                if fnmatch(line, pat):
                    return True
    return False


def _location_overlaps(
    loc: tuple[str, tuple[int, int]],
    suppressed: set[tuple[str, tuple[int, int]]],
) -> bool:
    """Return True if *loc* overlaps any range in *suppressed* for the same file."""
    file_path, (start, end) = loc
    for s_file, (s_start, s_end) in suppressed:
        if s_file == file_path and start <= s_end and s_start <= end:
            return True
    return False


def filter_reports(
    reports: list[CloneReport],
    suppress_patterns: tuple[str, ...],
    read_fn: ReadFn,
) -> list[CloneReport]:
    """Remove clone groups whose source lines match any suppress pattern.

    Uses two-pass sibling-aware suppression:

    1. **Direct pass**: Groups where a source line (or one line of context
       above) matches a suppress pattern are removed.  All file/line
       locations from these groups are recorded as *suppressed locations*.
    2. **Sibling pass**: Remaining groups where *both* sides overlap with
       suppressed locations are also removed.  This catches implementation-
       vs-implementation clones when both sides implement an abstract method
       that was already suppressed.

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

    # --- Pass 1: direct pattern matching ---
    suppressed_locations: set[tuple[str, tuple[int, int]]] = set()
    after_direct: list[tuple[CloneReport, list[CloneGroup]]] = []

    for report in reports:
        kept: list[CloneGroup] = []
        for g in report.groups:
            if _group_matches(g, suppress_patterns, read_fn, cache):
                suppressed_locations.add((g.file_a, g.lines_a))
                suppressed_locations.add((g.file_b, g.lines_b))
            else:
                kept.append(g)
        after_direct.append((report, kept))

    # --- Pass 2: sibling suppression ---
    filtered: list[CloneReport] = []

    for report, kept_groups in after_direct:
        surviving = [
            g
            for g in kept_groups
            if not (
                _location_overlaps((g.file_a, g.lines_a), suppressed_locations)
                and _location_overlaps((g.file_b, g.lines_b), suppressed_locations)
            )
        ]
        if not surviving:
            continue
        total_lines = sum(g.line_count for g in surviving)
        filtered.append(
            CloneReport(
                file_a=report.file_a,
                file_b=report.file_b,
                groups=surviving,
                total_cloned_lines=total_lines,
            )
        )

    return filtered
