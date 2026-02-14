"""Output formatting for clone detection results."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import TextIO

from cpitd.indexer import CloneMatch


@dataclass(frozen=True, slots=True)
class CloneGroup:
    """A contiguous range of cloned lines between two locations."""

    file_a: str
    lines_a: tuple[int, int]  # (start_line, end_line)
    file_b: str
    lines_b: tuple[int, int]
    line_count: int
    token_count: int


@dataclass(frozen=True, slots=True)
class CloneReport:
    """All clone groups between two file locations."""

    file_a: str
    file_b: str
    groups: list[CloneGroup]
    total_cloned_lines: int


def _normalize_file_pair(
    file_a: str, file_b: str
) -> tuple[str, str, bool]:
    """Return (smaller, larger, swapped) for consistent ordering."""
    if file_a <= file_b:
        return file_a, file_b, False
    return file_b, file_a, True


def _merge_consecutive_matches(
    matches: list[CloneMatch],
) -> list[CloneGroup]:
    """Merge level-0 matches whose line numbers increment by 1 on both sides.

    Assumes all matches share the same normalized file pair.
    """
    if not matches:
        return []

    # Sort by (left line, right line)
    sorted_matches = sorted(
        matches, key=lambda m: (m.left.node.start_line, m.right.node.start_line)
    )

    groups: list[CloneGroup] = []
    m = sorted_matches[0]
    cur_a_start = m.left.node.start_line
    cur_a_end = m.left.node.end_line
    cur_b_start = m.right.node.start_line
    cur_b_end = m.right.node.end_line
    cur_tokens = m.left.node.token_count
    file_a = m.left.file_path
    file_b = m.right.file_path

    for m in sorted_matches[1:]:
        a_line = m.left.node.start_line
        b_line = m.right.node.start_line
        # Consecutive if both sides increment by exactly 1
        if a_line == cur_a_end + 1 and b_line == cur_b_end + 1:
            cur_a_end = a_line
            cur_b_end = b_line
            cur_tokens += m.left.node.token_count
        else:
            groups.append(
                CloneGroup(
                    file_a=file_a,
                    lines_a=(cur_a_start, cur_a_end),
                    file_b=file_b,
                    lines_b=(cur_b_start, cur_b_end),
                    line_count=cur_a_end - cur_a_start + 1,
                    token_count=cur_tokens,
                )
            )
            cur_a_start = a_line
            cur_a_end = m.left.node.end_line
            cur_b_start = b_line
            cur_b_end = m.right.node.end_line
            cur_tokens = m.left.node.token_count
            file_a = m.left.file_path
            file_b = m.right.file_path

    groups.append(
        CloneGroup(
            file_a=file_a,
            lines_a=(cur_a_start, cur_a_end),
            file_b=file_b,
            lines_b=(cur_b_start, cur_b_end),
            line_count=cur_a_end - cur_a_start + 1,
            token_count=cur_tokens,
        )
    )
    return groups


def _higher_level_to_group(m: CloneMatch) -> CloneGroup:
    """Convert a higher-level match directly to a CloneGroup."""
    return CloneGroup(
        file_a=m.left.file_path,
        lines_a=(m.left.node.start_line, m.left.node.end_line),
        file_b=m.right.file_path,
        lines_b=(m.right.node.start_line, m.right.node.end_line),
        line_count=m.left.node.end_line - m.left.node.start_line + 1,
        token_count=m.left.node.token_count,
    )


def _deduplicate_groups(groups: list[CloneGroup]) -> list[CloneGroup]:
    """Remove groups fully subsumed by a larger group."""
    # Sort largest first so we can check subsumption efficiently
    by_size = sorted(groups, key=lambda g: g.line_count, reverse=True)
    kept: list[CloneGroup] = []

    for g in by_size:
        subsumed = False
        for k in kept:
            if (
                g.file_a == k.file_a
                and g.file_b == k.file_b
                and k.lines_a[0] <= g.lines_a[0]
                and g.lines_a[1] <= k.lines_a[1]
                and k.lines_b[0] <= g.lines_b[0]
                and g.lines_b[1] <= k.lines_b[1]
            ):
                subsumed = True
                break
        if not subsumed:
            kept.append(g)

    return sorted(kept, key=lambda g: (g.file_a, g.lines_a))


def aggregate_clone_matches(
    matches: list[CloneMatch],
    *,
    min_group_tokens: int = 10,
) -> list[CloneReport]:
    """Group raw clone matches into per-file-pair reports.

    Level-0 matches are merged when consecutive on both sides.
    Higher-level matches become groups directly.  Subsumed groups
    are deduplicated.

    Args:
        matches: Raw matches from the indexer.
        min_group_tokens: Drop groups with fewer tokens.

    Returns:
        Aggregated reports, one per unique file pair.
    """
    # Bucket by normalized file pair
    by_pair: dict[tuple[str, str], list[CloneMatch]] = defaultdict(list)

    for m in matches:
        fa, fb, swapped = _normalize_file_pair(
            m.left.file_path, m.right.file_path
        )
        if swapped:
            m = CloneMatch(
                left=m.right, right=m.left, level=m.level, shared_hash=m.shared_hash
            )
        by_pair[(fa, fb)].append(m)

    reports: list[CloneReport] = []
    for (file_a, file_b), pair_matches in sorted(by_pair.items()):
        level_0 = [m for m in pair_matches if m.level == 0]
        higher = [m for m in pair_matches if m.level > 0]

        groups: list[CloneGroup] = []
        groups.extend(_merge_consecutive_matches(level_0))
        groups.extend(_higher_level_to_group(m) for m in higher)

        # Filter small groups
        groups = [g for g in groups if g.token_count >= min_group_tokens]
        groups = _deduplicate_groups(groups)

        if not groups:
            continue

        total_lines = sum(g.line_count for g in groups)
        reports.append(
            CloneReport(
                file_a=file_a,
                file_b=file_b,
                groups=groups,
                total_cloned_lines=total_lines,
            )
        )

    return reports


def format_human(reports: list[CloneReport], out: TextIO) -> None:
    """Write human-readable clone report."""
    if not reports:
        out.write("No clones detected.\n")
        return

    out.write(f"Found potential clones in {len(reports)} file pair(s):\n\n")
    for report in reports:
        out.write(f"  {report.file_a}  <->  {report.file_b}\n")
        for g in report.groups:
            out.write(
                f"    Lines {g.lines_a[0]}-{g.lines_a[1]}"
                f" <-> Lines {g.lines_b[0]}-{g.lines_b[1]}"
                f" ({g.line_count} lines, {g.token_count} tokens)\n"
            )
        out.write(f"    Total cloned lines: {report.total_cloned_lines}\n\n")


def format_json(reports: list[CloneReport], out: TextIO) -> None:
    """Write JSON-formatted clone report."""
    data = {
        "clone_reports": [
            {
                "file_a": r.file_a,
                "file_b": r.file_b,
                "total_cloned_lines": r.total_cloned_lines,
                "groups": [
                    {
                        "lines_a": list(g.lines_a),
                        "lines_b": list(g.lines_b),
                        "line_count": g.line_count,
                        "token_count": g.token_count,
                    }
                    for g in r.groups
                ],
            }
            for r in reports
        ],
        "total_pairs": len(reports),
    }
    json.dump(data, out, indent=2)
    out.write("\n")
