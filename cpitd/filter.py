"""Post-aggregation filters for suppressing benign clone groups."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Callable, Protocol

from cpitd.reporter import CloneGroup, CloneReport

F = Callable[..., object]
ReadFn = Callable[[str], str | None]


def protocol_impl(fn: F) -> F:
    """Mark a method as a protocol implementation (identity decorator)."""
    return fn
Location = tuple[str, tuple[int, int]]  # (file_path, (start_line, end_line))


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


def _location_overlaps(
    loc: Location,
    suppressed: set[Location],
) -> bool:
    """Return True if *loc* overlaps any range in *suppressed* for the same file."""
    file_path, (start, end) = loc
    for s_file, (s_start, s_end) in suppressed:
        if s_file == file_path and start <= s_end and s_start <= end:
            return True
    return False


def _filter_groups(
    reports: list[CloneReport],
    keep: Callable[[CloneGroup], bool],
) -> list[CloneReport]:
    """Return reports with only the groups for which *keep* returns True."""
    filtered: list[CloneReport] = []
    for report in reports:
        groups = [g for g in report.groups if keep(g)]
        if not groups:
            continue
        filtered.append(
            CloneReport(
                file_a=report.file_a,
                file_b=report.file_b,
                groups=groups,
                total_cloned_lines=sum(g.line_count for g in groups),
            )
        )
    return filtered


# ---------------------------------------------------------------------------
# Multi-stage filter framework
# ---------------------------------------------------------------------------


@dataclass
class FilterContext:
    """Mutable shared state passed between filter stages."""

    read_fn: ReadFn
    cache: dict[str, str | None] = field(default_factory=dict)
    suppressed_locations: set[Location] = field(default_factory=set)


class FilterStage(Protocol):
    """Protocol for a single filter pass."""

    def __call__(self, reports: list[CloneReport], ctx: FilterContext) -> list[CloneReport]: ...


class PatternMatchStage:
    """Remove groups whose source lines match fnmatch patterns.

    Includes one line of context above each chunk to catch decorators
    like ``@abstractmethod``.  Adds all locations from suppressed groups
    to ``ctx.suppressed_locations``.
    """

    def __init__(self, suppress_patterns: tuple[str, ...]) -> None:
        self._patterns = suppress_patterns

    def _group_matches(
        self, group: CloneGroup, ctx: FilterContext,
    ) -> bool:
        for file_path, line_range in (
            (group.file_a, group.lines_a),
            (group.file_b, group.lines_b),
        ):
            if file_path not in ctx.cache:
                ctx.cache[file_path] = ctx.read_fn(file_path)
            source = ctx.cache[file_path]
            if source is None:
                continue
            for line in _extract_lines(source, line_range, context_above=1):
                for pat in self._patterns:
                    if fnmatch(line, pat):
                        return True
        return False

    @protocol_impl
    def __call__(self, reports: list[CloneReport], ctx: FilterContext) -> list[CloneReport]:
        suppressed: set[Location] = set()

        def keep(g: CloneGroup) -> bool:
            if self._group_matches(g, ctx):
                suppressed.add((g.file_a, g.lines_a))
                suppressed.add((g.file_b, g.lines_b))
                return False
            return True

        result = _filter_groups(reports, keep)
        ctx.suppressed_locations.update(suppressed)
        return result


class SiblingStage:
    """Suppress groups where both sides overlap with previously-suppressed locations."""

    @protocol_impl
    def __call__(self, reports: list[CloneReport], ctx: FilterContext) -> list[CloneReport]:
        locs = ctx.suppressed_locations
        return _filter_groups(
            reports,
            lambda g: not (
                _location_overlaps((g.file_a, g.lines_a), locs)
                and _location_overlaps((g.file_b, g.lines_b), locs)
            ),
        )


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def run_filters(
    reports: list[CloneReport],
    stages: Sequence[FilterStage],
    read_fn: ReadFn,
) -> list[CloneReport]:
    """Run *reports* through a sequence of filter stages."""
    ctx = FilterContext(read_fn=read_fn)
    for stage in stages:
        reports = stage(reports, ctx)
    return reports


def build_filter_stages(config: object) -> list[FilterStage]:
    """Construct the filter stage list from a Config object.

    Currently builds PatternMatchStage + SiblingStage when suppress_patterns
    is non-empty.
    """
    stages: list[FilterStage] = []
    suppress_patterns = getattr(config, "suppress_patterns", None)
    if suppress_patterns:
        stages.append(PatternMatchStage(suppress_patterns))
        stages.append(SiblingStage())
    return stages


def filter_reports(
    reports: list[CloneReport],
    suppress_patterns: tuple[str, ...],
    read_fn: ReadFn,
) -> list[CloneReport]:
    """Remove clone groups whose source lines match any suppress pattern.

    This is a backward-compatible wrapper around :func:`run_filters` with
    :class:`PatternMatchStage` and :class:`SiblingStage`.
    """
    if not suppress_patterns:
        return reports
    stages: list[FilterStage] = [
        PatternMatchStage(suppress_patterns),
        SiblingStage(),
    ]
    return run_filters(reports, stages, read_fn)
