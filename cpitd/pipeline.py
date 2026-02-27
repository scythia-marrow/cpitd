"""Scan pipeline — wires tokenizer, hash tree, indexer, and reporter together."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from cpitd.config import Config
from cpitd.discovery import discover_files
from cpitd.filter import build_filter_stages, run_filters
from cpitd.indexer import LineHashIndex
from cpitd.reporter import CloneReport, aggregate_clone_matches, format_human, format_json
from cpitd.tokenizer import NormalizationLevel, tokenize
from cpitd.types import Paths
from cpitd.winnowing import build_hash_tree, hash_lines


def _warn(msg: str, *, verbose: bool) -> None:
    """Write a warning to stderr when verbose mode is enabled."""
    if verbose:
        print(f"cpitd: warning: {msg}", file=sys.stderr)


def scan(config: Config, paths: Paths) -> list[CloneReport]:
    """Run the full clone detection pipeline.

    Args:
        config: Runtime configuration controlling thresholds and normalization.
        paths: File or directory paths to scan.

    Returns:
        Aggregated clone reports for all detected clone pairs.
    """
    verbose = config.verbose

    files = discover_files(
        paths,
        ignore_patterns=config.ignore_patterns,
        languages=config.languages,
    )

    level = NormalizationLevel(config.normalize)
    index = LineHashIndex()
    skipped = 0

    for file_path in files:
        source = _read_file(file_path, verbose=verbose)
        if source is None:
            skipped += 1
            continue

        try:
            tokens = tokenize(source, filename=file_path.name, level=level)
        except Exception as exc:
            _warn(f"skipping {file_path}: tokenizer error: {exc}", verbose=verbose)
            skipped += 1
            continue

        if len(tokens) < config.min_tokens:
            continue

        line_hashes = hash_lines(tokens)
        tree = build_hash_tree(line_hashes)
        index.add(str(file_path), tree)

    if skipped:
        _warn(f"{skipped} file(s) skipped due to read/parse errors", verbose=verbose)

    matches = index.find_clones()
    reports = aggregate_clone_matches(matches)
    stages = build_filter_stages(config)
    if stages:
        reports = run_filters(reports, stages, _read_file_str)
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


def _read_file(path: Path, *, verbose: bool = False) -> str | None:
    """Read a file's contents, returning None on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _warn(f"skipping {path}: {exc}", verbose=verbose)
        return None


def _read_file_str(path: str) -> str | None:
    """String-path wrapper around _read_file for use with filter_reports."""
    return _read_file(Path(path))
