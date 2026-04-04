"""Post-aggregation filters for suppressing benign clone clusters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Callable, Protocol

from cpitd.reporter import CloneCluster

ReadFn = Callable[[str], str | None]

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

    def __call__(
        self, clusters: list[CloneCluster], ctx: FilterContext
    ) -> list[CloneCluster]: ...


class PatternMatchStage:
    """Remove clusters where any location's source lines match fnmatch patterns.

    Includes one line of context above each chunk to catch decorators
    like ``@abstractmethod``.  Adds all locations from suppressed clusters
    to ``ctx.suppressed_locations``.
    """

    def __init__(self, suppress_patterns: tuple[str, ...]) -> None:
        self._patterns = suppress_patterns

    def _cluster_matches(
        self,
        cluster: CloneCluster,
        ctx: FilterContext,
    ) -> bool:
        for loc in cluster.locations:
            # Use pre-populated text (includes 1 context line above)
            # when available; fall back to file read for backwards compat.
            if loc.text is not None:
                lines = loc.text.splitlines()
            else:
                if loc.file not in ctx.cache:
                    ctx.cache[loc.file] = ctx.read_fn(loc.file)
                source = ctx.cache[loc.file]
                if source is None:
                    continue
                lines = _extract_lines(source, loc.lines, context_above=1)
            for line in lines:
                for pat in self._patterns:
                    if fnmatch(line, pat):
                        return True
        return False

    def __call__(
        self, clusters: list[CloneCluster], ctx: FilterContext
    ) -> list[CloneCluster]:
        suppressed: set[Location] = set()
        result: list[CloneCluster] = []

        for cluster in clusters:
            if self._cluster_matches(cluster, ctx):
                for loc in cluster.locations:
                    suppressed.add((loc.file, loc.lines))
            else:
                result.append(cluster)

        ctx.suppressed_locations.update(suppressed)
        return result


class SiblingStage:
    """Suppress clusters where all locations overlap with previously-suppressed locations."""

    def __call__(
        self, clusters: list[CloneCluster], ctx: FilterContext
    ) -> list[CloneCluster]:
        locs = ctx.suppressed_locations
        return [
            c
            for c in clusters
            if not all(
                _location_overlaps((loc.file, loc.lines), locs) for loc in c.locations
            )
        ]


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def run_filters(
    clusters: list[CloneCluster],
    stages: Sequence[FilterStage],
    read_fn: ReadFn,
) -> list[CloneCluster]:
    """Run *clusters* through a sequence of filter stages."""
    ctx = FilterContext(read_fn=read_fn)
    for stage in stages:
        clusters = stage(clusters, ctx)
    return clusters


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


def filter_clusters(
    clusters: list[CloneCluster],
    suppress_patterns: tuple[str, ...],
    read_fn: ReadFn,
) -> list[CloneCluster]:
    """Remove clone clusters whose source lines match any suppress pattern.

    Convenience wrapper around :func:`run_filters` with
    :class:`PatternMatchStage` and :class:`SiblingStage`.
    """
    if not suppress_patterns:
        return clusters
    stages: list[FilterStage] = [
        PatternMatchStage(suppress_patterns),
        SiblingStage(),
    ]
    return run_filters(clusters, stages, read_fn)
