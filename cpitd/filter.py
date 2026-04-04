"""Post-aggregation filters for suppressing benign clone clusters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Protocol

from cpitd.reporter import CloneCluster

Location = tuple[str, tuple[int, int]]  # (file_path, (start_line, end_line))


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

    suppressed_locations: set[Location] = field(default_factory=set)


class FilterStage(Protocol):
    """Protocol for a single filter pass."""

    def __call__(
        self, clusters: list[CloneCluster], ctx: FilterContext
    ) -> list[CloneCluster]: ...


class PatternMatchStage:
    """Remove clusters where any location's pre-populated text matches patterns.

    Location text includes one line of context above each chunk to catch
    decorators like ``@abstractmethod``.  Adds all locations from
    suppressed clusters to ``ctx.suppressed_locations``.
    """

    def __init__(self, suppress_patterns: tuple[str, ...]) -> None:
        self._patterns = suppress_patterns

    def _cluster_matches(
        self,
        cluster: CloneCluster,
        ctx: FilterContext,
    ) -> bool:
        for loc in cluster.locations:
            if loc.text is None:
                continue
            for line in loc.text.splitlines():
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
) -> list[CloneCluster]:
    """Run *clusters* through a sequence of filter stages."""
    ctx = FilterContext()
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
    return run_filters(clusters, stages)
