"""Output formatting for clone detection results.

Converts raw hash-index match groups into deduplicated clone clusters
and formats them for human or JSON consumption.
"""

from __future__ import annotations

import json
from bisect import bisect_right, insort
from collections import defaultdict
from typing import Callable, TextIO

from cpitd.indexer import CloneMatchGroup, NodeLocation
from cpitd.types import frozen_slots, protocol_impl


@frozen_slots
class CloneLocation:
    """A single location where cloned code appears."""

    file: str
    lines: tuple[int, int]  # (start_line, end_line)
    text: str | None = None  # clone lines + 1 context line above


@frozen_slots
class CloneCluster:
    """A group of locations that all share the same cloned code."""

    locations: tuple[CloneLocation, ...]
    line_count: int
    token_count: int
    text: str | None = None  # display text from first sorted location


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
    # line_count is provisional; populate_text() will derive it from
    # the actual source text of the first sorted location.
    loc0 = locations[0]
    line_count = loc0.lines[1] - loc0.lines[0] + 1
    return CloneCluster(
        locations=locations,
        line_count=line_count,
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


def _deduplicate_clusters(clusters: list[CloneCluster]) -> list[CloneCluster]:
    """Remove clusters fully subsumed by a larger cluster.

    Uses a per-file sorted interval index with bisect for the first
    location lookup, and a per-cluster index for fast verification of
    subsequent locations.  Locations are checked cheapest-file-first to
    minimize scan work.
    """
    by_size = sorted(clusters, key=lambda c: c.token_count, reverse=True)

    # Per-file index: file -> sorted list of (start, end, kept_index)
    file_intervals: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    # Per-cluster index: kidx -> {file: [(start, end), ...]}
    cluster_locs: dict[int, dict[str, list[tuple[int, int]]]] = {}
    kept: list[CloneCluster] = []

    _INF = float("inf")

    for c in by_size:
        # Check cheapest file first to minimise scan work.
        locs = sorted(
            c.locations,
            key=lambda loc: len(file_intervals.get(loc.file, ())),
        )

        covering: set[int] | None = None

        for loc in locs:
            s, e = loc.lines

            if covering is None:
                # First location: scan the file interval index.
                entries = file_intervals.get(loc.file)
                if not entries:
                    break

                # bisect: only entries with start <= s
                pos = bisect_right(entries, (s, _INF, _INF))
                loc_covering = {kidx for start, end, kidx in entries[:pos] if end >= e}
                if not loc_covering:
                    break
                covering = loc_covering
            else:
                # Subsequent locations: verify only the covering set.
                still_covering = set()
                for kidx in covering:
                    kloc = cluster_locs[kidx].get(loc.file)
                    if kloc and any(cs <= s and e <= ce for cs, ce in kloc):
                        still_covering.add(kidx)
                covering = still_covering
                if not covering:
                    break
        else:
            if covering:
                continue

        kidx = len(kept)
        kept.append(c)
        cloc: dict[str, list[tuple[int, int]]] = {}
        for loc in c.locations:
            s, e = loc.lines
            insort(file_intervals[loc.file], (s, e, kidx))
            cloc.setdefault(loc.file, []).append((s, e))
        cluster_locs[kidx] = cloc

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


WarnFn = Callable[[str], None]


def populate_text(
    clusters: list[CloneCluster],
    read_fn: ReadFn,
    warn_fn: WarnFn | None = None,
) -> list[CloneCluster]:
    """Attach source text to locations and clusters, reading each file once.

    Per-location text includes 1 line of context above the clone region
    (for suppression pattern matching).  Per-cluster text is the display
    text from the first sorted location (no context).  ``line_count`` is
    derived from the display text so it always matches what is shown.

    If a file cannot be read (e.g. deleted between discovery and text
    extraction), the location's text is set to None and a warning is
    emitted via *warn_fn*.
    """
    cache: dict[str, str | None] = {}
    warned: set[str] = set()

    def _read(path: str) -> str | None:
        if path not in cache:
            cache[path] = read_fn(path)
            if cache[path] is None and path not in warned:
                warned.add(path)
                if warn_fn is not None:
                    warn_fn(
                        f"cannot read {path} for text extraction "
                        f"(file may have been deleted since scan started)"
                    )
        return cache[path]

    result: list[CloneCluster] = []
    for c in clusters:
        new_locs: list[CloneLocation] = []
        for loc in c.locations:
            source = _read(loc.file)
            if source is not None:
                start, end = loc.lines
                context_start = max(1, start - 1)
                lines = source.splitlines()
                loc_text = "\n".join(lines[context_start - 1 : end])
            else:
                loc_text = None
            new_locs.append(
                CloneLocation(file=loc.file, lines=loc.lines, text=loc_text)
            )

        loc0 = new_locs[0]
        if loc0.text is not None:
            # Strip the context line to get display text.
            start = loc0.lines[0]
            context_start = max(1, start - 1)
            context_lines = start - context_start
            display_lines = loc0.text.splitlines()[context_lines:]
            display_text = "\n".join(display_lines)
            line_count = len(display_lines)
        else:
            display_text = None
            line_count = c.line_count

        result.append(
            CloneCluster(
                locations=tuple(new_locs),
                line_count=line_count,
                token_count=c.token_count,
                text=display_text,
            )
        )
    return result


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


@protocol_impl("Formatter")
def format_human(
    clusters: list[CloneCluster],
    out: TextIO,
    file_stats: list[FileStat] | None = None,
    *,
    show_text: bool = True,
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
        if show_text and cluster.text is not None:
            out.write("\n")
            for line in cluster.text.splitlines():
                out.write(f"    | {line}\n")
        out.write("\n")

    if file_stats:
        out.write("File duplication:\n")
        for fs in file_stats:
            out.write(
                f"  {fs.file}: {fs.duplication_pct}% duplicated"
                f" ({fs.duplicated_tokens}/{fs.total_tokens} tokens)\n"
            )


@protocol_impl("Formatter")
def format_json(
    clusters: list[CloneCluster],
    out: TextIO,
    file_stats: list[FileStat] | None = None,
    *,
    show_text: bool = True,
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
        if show_text and c.text is not None:
            group["text"] = c.text
        groups.append(group)
    data: dict[str, object] = {
        "clone_reports": groups,
        "total_groups": len(clusters),
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
    _write_json(data, out)


def _write_json(data: object, out: TextIO) -> None:
    """Serialize *data* as indented JSON followed by a trailing newline."""
    json.dump(data, out, indent=2)
    out.write("\n")


def _sarif_physical_location(loc: CloneLocation) -> dict[str, object]:
    """Build a SARIF physicalLocation dict for a clone location."""
    return {
        "artifactLocation": {"uri": loc.file},
        "region": {"startLine": loc.lines[0], "endLine": loc.lines[1]},
    }


@protocol_impl("Formatter")
def format_sarif(
    clusters: list[CloneCluster],
    out: TextIO,
    file_stats: list[FileStat] | None = None,
    *,
    show_text: bool = True,
    tool_version: str = "",
) -> None:
    """Write SARIF v2.1.0 formatted clone report.

    Produces output compatible with GitHub Code Scanning, GitLab SAST,
    and other SARIF consumers.  Each clone cluster becomes one ``result``
    with all clone locations listed as ``locations`` and cross-referenced
    via ``relatedLocations``.
    """
    results: list[dict[str, object]] = []
    for c in clusters:
        # Primary location is the first; all locations listed under locations[]
        locations: list[dict] = [
            {"physicalLocation": _sarif_physical_location(loc)} for loc in c.locations
        ]

        # relatedLocations cross-reference all locations with an id
        related: list[dict] = [
            {
                "id": idx,
                "physicalLocation": _sarif_physical_location(loc),
                "message": {
                    "text": f"Clone location {idx + 1}: {loc.file} "
                    f"lines {loc.lines[0]}-{loc.lines[1]}",
                },
            }
            for idx, loc in enumerate(c.locations)
        ]

        loc_summary = ", ".join(
            f"{loc.file}:{loc.lines[0]}-{loc.lines[1]}" for loc in c.locations
        )
        message = (
            f"Code clone ({c.line_count} lines, {c.token_count} tokens) "
            f"found in {len(c.locations)} locations: {loc_summary}"
        )

        result: dict[str, object] = {
            "ruleId": "cpitd/clone-group",
            "ruleIndex": 0,
            "level": "warning",
            "message": {"text": message},
            "locations": locations,
            "relatedLocations": related,
        }
        results.append(result)

    sarif: dict[str, object] = {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "cpitd",
                        "semanticVersion": tool_version,
                        "informationUri": "https://github.com/scythia-marrow/cpitd",
                        "rules": [
                            {
                                "id": "cpitd/clone-group",
                                "shortDescription": {
                                    "text": "Duplicated code clone group",
                                },
                                "fullDescription": {
                                    "text": "A group of code locations that share "
                                    "identical or near-identical token sequences, "
                                    "indicating copy-pasted code.",
                                },
                                "defaultConfiguration": {"level": "warning"},
                                "helpUri": "https://github.com/scythia-marrow/cpitd#readme",
                            },
                        ],
                    },
                },
                "results": results,
            },
        ],
    }

    _write_json(sarif, out)
