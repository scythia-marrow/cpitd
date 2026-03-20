"""Output formatting for clone detection results.

Converts raw hash-index match groups into deduplicated clone clusters
and formats them for human or JSON consumption.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Callable, TextIO

from cpitd.indexer import CloneMatchGroup, NodeLocation
from cpitd.types import frozen_slots


@frozen_slots
class CloneLocation:
    """A single location where cloned code appears."""

    file: str
    lines: tuple[int, int]  # (start_line, end_line)


@frozen_slots
class CloneCluster:
    """A group of locations that all share the same cloned code."""

    locations: tuple[CloneLocation, ...]
    line_count: int
    token_count: int


def _group_to_cluster(g: CloneMatchGroup) -> CloneCluster:
    """Convert a higher-level match group directly to a CloneCluster."""
    locations = tuple(
        sorted(
            (
                CloneLocation(
                    file=loc.file_path,
                    lines=(loc.node.start_line, loc.node.end_line),
                )
                for loc in g.locations
            ),
            key=lambda loc: (loc.file, loc.lines),
        )
    )
    return CloneCluster(
        locations=locations,
        line_count=g.locations[0].node.end_line - g.locations[0].node.start_line + 1,
        token_count=g.locations[0].node.token_count,
    )


def _sorted_locs(g: CloneMatchGroup) -> list[NodeLocation]:
    """Return group locations sorted by (file_path, start_line)."""
    return sorted(g.locations, key=lambda loc: (loc.file_path, loc.node.start_line))


def _merge_consecutive_groups(groups: list[CloneMatchGroup]) -> list[CloneCluster]:
    """Merge level-0 match groups whose locations all increment by 1.

    Groups are bucketed by their location shape (sorted file paths,
    preserving multiplicity for intra-file clones). Within each bucket,
    groups are sorted by the first location's line number and merged
    when every location increments by exactly 1.
    """
    if not groups:
        return []

    by_shape: dict[tuple[str, ...], list[CloneMatchGroup]] = defaultdict(list)
    for g in groups:
        shape = tuple(loc.file_path for loc in _sorted_locs(g))
        by_shape[shape].append(g)

    clusters: list[CloneCluster] = []

    for shape, shape_groups in by_shape.items():
        n = len(shape)

        shape_groups.sort(key=lambda g: _sorted_locs(g)[0].node.start_line)

        prev = _sorted_locs(shape_groups[0])
        run_start: list[int] = [loc.node.start_line for loc in prev]
        run_end: list[int] = [loc.node.end_line for loc in prev]
        run_tokens = shape_groups[0].locations[0].node.token_count
        run_count = 1

        def _flush() -> None:
            locs = tuple(
                sorted(
                    (
                        CloneLocation(
                            file=shape[i],
                            lines=(run_start[i], run_end[i]),
                        )
                        for i in range(n)
                    ),
                    key=lambda loc: (loc.file, loc.lines),
                )
            )
            clusters.append(
                CloneCluster(
                    locations=locs,
                    line_count=run_count,
                    token_count=run_tokens,
                )
            )

        for g in shape_groups[1:]:
            cur = _sorted_locs(g)
            if all(cur[i].node.start_line == run_end[i] + 1 for i in range(n)):
                for i in range(n):
                    run_end[i] = cur[i].node.end_line
                run_tokens += g.locations[0].node.token_count
                run_count += 1
            else:
                _flush()
                run_start = [loc.node.start_line for loc in cur]
                run_end = [loc.node.end_line for loc in cur]
                run_tokens = g.locations[0].node.token_count
                run_count = 1

        _flush()

    return clusters


def _cluster_subsumed(small: CloneCluster, big: CloneCluster) -> bool:
    """Return True if every location in *small* is contained within a location in *big*."""
    for s_loc in small.locations:
        if not any(
            b_loc.file == s_loc.file
            and b_loc.lines[0] <= s_loc.lines[0]
            and s_loc.lines[1] <= b_loc.lines[1]
            for b_loc in big.locations
        ):
            return False
    return True


def _deduplicate_clusters(clusters: list[CloneCluster]) -> list[CloneCluster]:
    """Remove clusters fully subsumed by a larger cluster."""
    by_size = sorted(clusters, key=lambda c: c.token_count, reverse=True)
    kept: list[CloneCluster] = []
    for c in by_size:
        if any(_cluster_subsumed(c, k) for k in kept):
            continue
        kept.append(c)
    return kept


def aggregate_clone_groups(
    groups: list[CloneMatchGroup],
    *,
    min_group_tokens: int = 10,
) -> list[CloneCluster]:
    """Convert raw match groups into deduplicated clone clusters.

    Level-0 groups with the same file set are merged when their line
    positions are consecutive. Higher-level groups become clusters
    directly. Subsumed clusters are removed.

    Args:
        groups: Raw match groups from the indexer.
        min_group_tokens: Drop clusters with fewer tokens.

    Returns:
        Deduplicated clusters sorted by descending token count.
    """
    level_0 = [g for g in groups if g.level == 0]
    higher = [g for g in groups if g.level > 0]

    clusters: list[CloneCluster] = []
    clusters.extend(_merge_consecutive_groups(level_0))
    clusters.extend(_group_to_cluster(g) for g in higher)

    clusters = [c for c in clusters if c.token_count >= min_group_tokens]
    clusters = _deduplicate_clusters(clusters)

    return sorted(clusters, key=lambda c: (-c.token_count, -c.line_count))


@frozen_slots
class FileStat:
    """Per-file duplication statistics."""

    file: str
    total_tokens: int
    duplicated_tokens: int
    duplication_pct: float


def compute_file_stats(
    clusters: list[CloneCluster],
    file_token_counts: dict[str, int],
) -> list[FileStat]:
    """Compute per-file duplication percentages from non-suppressed clusters.

    For each file appearing in any cluster, sums the token counts of all
    cluster locations in that file (capped at the file's total tokens)
    and computes the duplication percentage.

    Args:
        clusters: Final (post-filter) clone clusters.
        file_token_counts: Mapping of file path to total token count.

    Returns:
        Per-file stats sorted by descending duplication percentage.
    """
    duplicated: dict[str, int] = defaultdict(int)
    for cluster in clusters:
        for loc in cluster.locations:
            duplicated[loc.file] += cluster.token_count

    stats: list[FileStat] = []
    for file_path, dup_tokens in duplicated.items():
        total = file_token_counts.get(file_path, 0)
        if total <= 0:
            continue
        capped = min(dup_tokens, total)
        stats.append(
            FileStat(
                file=file_path,
                total_tokens=total,
                duplicated_tokens=capped,
                duplication_pct=round(capped / total * 100, 1),
            )
        )

    return sorted(stats, key=lambda s: (-s.duplication_pct, s.file))


ReadFn = Callable[[str], str | None]


def _extract_lines(source: str, start: int, end: int) -> str:
    """Extract lines start..end (1-based, inclusive) from source text."""
    lines = source.splitlines()
    return "\n".join(lines[start - 1 : end])


def format_human(
    clusters: list[CloneCluster],
    out: TextIO,
    file_stats: list[FileStat] | None = None,
    read_fn: ReadFn | None = None,
) -> None:
    """Write human-readable clone report."""
    if not clusters:
        out.write("No clones detected.\n")
        return

    out.write(f"Found {len(clusters)} clone group(s):\n\n")
    for i, cluster in enumerate(clusters, 1):
        out.write(
            f"  Clone #{i} ({cluster.line_count} lines,"
            f" {cluster.token_count} tokens):\n"
        )
        for loc in cluster.locations:
            out.write(f"    {loc.file}: Lines {loc.lines[0]}-{loc.lines[1]}\n")
        if read_fn is not None:
            source = read_fn(cluster.locations[0].file)
            if source is not None:
                loc0 = cluster.locations[0]
                text = _extract_lines(source, loc0.lines[0], loc0.lines[1])
                out.write("\n")
                for line in text.splitlines():
                    out.write(f"    | {line}\n")
        out.write("\n")

    if file_stats:
        out.write("File duplication:\n")
        for fs in file_stats:
            out.write(
                f"  {fs.file}: {fs.duplication_pct}% duplicated"
                f" ({fs.duplicated_tokens}/{fs.total_tokens} tokens)\n"
            )


def format_json(
    clusters: list[CloneCluster],
    out: TextIO,
    file_stats: list[FileStat] | None = None,
    read_fn: ReadFn | None = None,
) -> None:
    """Write JSON-formatted clone report."""
    groups: list[dict[str, object]] = []
    for c in clusters:
        group: dict[str, object] = {
            "line_count": c.line_count,
            "token_count": c.token_count,
            "locations": [
                {"file": loc.file, "lines": list(loc.lines)} for loc in c.locations
            ],
        }
        if read_fn is not None:
            source = read_fn(c.locations[0].file)
            if source is not None:
                loc0 = c.locations[0]
                group["text"] = _extract_lines(source, loc0.lines[0], loc0.lines[1])
        groups.append(group)
    data: dict[str, object] = {
        "clone_reports": groups,
        "total_groups": len(clusters),
        # Deprecated: use clone_groups/total_groups instead.
        # These aliases will be removed in the next minor version.
        "total_pairs": len(clusters),
    }
    if file_stats:
        data["file_stats"] = [
            {
                "file": fs.file,
                "total_tokens": fs.total_tokens,
                "duplicated_tokens": fs.duplicated_tokens,
                "duplication_pct": fs.duplication_pct,
            }
            for fs in file_stats
        ]
    json.dump(data, out, indent=2)
    out.write("\n")
