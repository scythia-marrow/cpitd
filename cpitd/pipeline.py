"""Scan pipeline — wires tokenizer, hash tree, indexer, and reporter together."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from cpitd.config import Config
from cpitd.discovery import discover_files
from cpitd.filter import filter_reports
from cpitd.indexer import LineHashIndex
from cpitd.reporter import CloneReport, aggregate_clone_matches, format_human, format_json
from cpitd.tokenizer import NormalizationLevel, tokenize
from cpitd.types import Paths
from cpitd.winnowing import build_hash_tree, hash_lines


def scan(config: Config, paths: Paths) -> list[CloneReport]:
    """Run the full clone detection pipeline.

    Args:
        config: Runtime configuration controlling thresholds and normalization.
        paths: File or directory paths to scan.

    Returns:
        Aggregated clone reports for all detected clone pairs.
    """
    files = discover_files(
        paths,
        ignore_patterns=config.ignore_patterns,
        languages=config.languages,
    )

    level = NormalizationLevel(config.normalize)
    index = LineHashIndex()

    for file_path in files:
        source = _read_file(file_path)
        if source is None:
            continue

        tokens = tokenize(source, filename=file_path.name, level=level)
        if len(tokens) < config.min_tokens:
            continue

        line_hashes = hash_lines(tokens)
        tree = build_hash_tree(line_hashes)
        index.add(str(file_path), tree)

    matches = index.find_clones()
    reports = aggregate_clone_matches(matches)
    if config.suppress_patterns:
        reports = filter_reports(reports, config.suppress_patterns, _read_file_str)
    return reports


def scan_and_report(
    config: Config,
    paths: Paths,
    out: TextIO = sys.stdout,
) -> list[CloneReport]:
    """Run scan and write formatted output.

    Args:
        config: Runtime configuration.
        paths: File or directory paths to scan.
        out: Output stream for the report.

    Returns:
        The clone reports (also written to out).
    """
    reports = scan(config, paths)

    if config.output_format == "json":
        format_json(reports, out)
    else:
        format_human(reports, out)

    return reports


def _read_file(path: Path) -> str | None:
    """Read a file's contents, returning None on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_file_str(path: str) -> str | None:
    """String-path wrapper around _read_file for use with filter_reports."""
    return _read_file(Path(path))
