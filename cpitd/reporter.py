"""Output formatting for clone detection results."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import TextIO

from cpitd.indexer import ClonePair


@dataclass(frozen=True, slots=True)
class CloneReport:
    """Aggregated clone information between two files."""

    file_a: str
    file_b: str
    shared_hashes: int
    locations_a: list[tuple[int, int]]  # (line, column) pairs
    locations_b: list[tuple[int, int]]


def aggregate_clone_pairs(pairs: list[ClonePair]) -> list[CloneReport]:
    """Group raw clone pairs into per-file-pair reports.

    Args:
        pairs: Raw clone pairs from the indexer.

    Returns:
        Aggregated reports, one per unique file pair.
    """
    grouped: dict[tuple[str, str], list[ClonePair]] = defaultdict(list)

    for pair in pairs:
        key = tuple(sorted([pair.left.file_path, pair.right.file_path]))
        grouped[key].append(pair)

    reports = []
    for (file_a, file_b), group in sorted(grouped.items()):
        locs_a = []
        locs_b = []
        for p in group:
            if p.left.file_path == file_a:
                locs_a.append((p.left.fingerprint.line, p.left.fingerprint.column))
                locs_b.append((p.right.fingerprint.line, p.right.fingerprint.column))
            else:
                locs_a.append((p.right.fingerprint.line, p.right.fingerprint.column))
                locs_b.append((p.left.fingerprint.line, p.left.fingerprint.column))

        reports.append(
            CloneReport(
                file_a=file_a,
                file_b=file_b,
                shared_hashes=len(group),
                locations_a=sorted(set(locs_a)),
                locations_b=sorted(set(locs_b)),
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
        out.write(f"  {report.file_a}\n")
        out.write(f"  {report.file_b}\n")
        out.write(f"  Shared fingerprints: {report.shared_hashes}\n\n")


def format_json(reports: list[CloneReport], out: TextIO) -> None:
    """Write JSON-formatted clone report."""
    data = {
        "clone_pairs": [
            {
                "file_a": r.file_a,
                "file_b": r.file_b,
                "shared_fingerprints": r.shared_hashes,
                "locations_a": [{"line": l, "column": c} for l, c in r.locations_a],
                "locations_b": [{"line": l, "column": c} for l, c in r.locations_b],
            }
            for r in reports
        ],
        "total_pairs": len(reports),
    }
    json.dump(data, out, indent=2)
    out.write("\n")
