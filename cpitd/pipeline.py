"""Scan pipeline — wires tokenizer, hash tree, indexer, and reporter together."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from cpitd.config import Config
from cpitd.discovery import discover_files
from cpitd.filter import build_filter_stages, run_filters
from cpitd.indexer import LineHashIndex
from cpitd.reporter import (
    CloneCluster,
    aggregate_clone_groups,
    compute_file_stats,
    format_human,
    format_json,
)
from cpitd.tokenizer import NormalizationLevel, tokenize
from cpitd.types import Paths
from cpitd.winnowing import build_hash_tree, hash_lines


def _warn(msg: str, *, verbose: bool) -> None:
    """Write a warning to stderr when verbose mode is enabled."""
    if verbose:
        print(f"cpitd: warning: {msg}", file=sys.stderr)


def scan(config: Config, paths: Paths) -> tuple[list[CloneCluster], dict[str, int]]:
    """Run the full clone detection pipeline.

    Args:
        config: Runtime configuration controlling thresholds and normalization.
        paths: File or directory paths to scan.

    Returns:
        A tuple of (clone clusters, file token counts).
    """
    verbose = config.verbose

    files = discover_files(
        paths,
        ignore_patterns=config.ignore_patterns,
        languages=config.languages,
    )

    level = NormalizationLevel(config.normalize)
    index = LineHashIndex()
    file_token_counts: dict[str, int] = {}
    skipped = 0

    for file_path in files:
        source = _read_file(file_path, verbose=verbose)
        if source is None:
            skipped += 1
            continue

        try:
            tokens = tokenize(source, filename=file_path.name, level=level)
        except (ValueError, TypeError, LookupError, RuntimeError) as exc:
            _warn(f"skipping {file_path}: tokenizer error: {exc}", verbose=verbose)
            skipped += 1
            continue

        if len(tokens) < config.min_tokens:
            continue

        file_key = str(file_path)
        file_token_counts[file_key] = len(tokens)
        line_hashes = hash_lines(tokens)
        tree = build_hash_tree(line_hashes)
        index.add(file_key, tree)

    if skipped:
        _warn(f"{skipped} file(s) skipped due to read/parse errors", verbose=verbose)

    match_groups = index.find_clones()
    clusters = aggregate_clone_groups(
        match_groups,
        min_group_tokens=config.min_tokens,
    )
    degenerate = [c for c in clusters if len(c.locations) < 2]
    if degenerate:
        _warn(
            f"{len(degenerate)} cluster(s) dropped: fewer than 2 locations",
            verbose=verbose,
        )
        clusters = [c for c in clusters if len(c.locations) >= 2]
    stages = build_filter_stages(config)
    if stages:
        clusters = run_filters(clusters, stages, _read_file_str)
    return clusters, file_token_counts


def scan_and_report(
    config: Config,
    paths: Paths,
    out: TextIO = sys.stdout,
) -> list[CloneCluster]:
    """Run scan and write formatted output.

    Args:
        config: Runtime configuration.
        paths: File or directory paths to scan.
        out: Output stream for the report.

    Returns:
        The clone clusters (also written to out).
    """
    clusters, file_token_counts = scan(config, paths)
    file_stats = compute_file_stats(clusters, file_token_counts)
    read_fn = _read_file_str if config.show_text else None

    if config.output_format == "json":
        format_json(clusters, out, file_stats=file_stats, read_fn=read_fn)
    else:
        format_human(clusters, out, file_stats=file_stats, read_fn=read_fn)

    return clusters


def _read_file(path: Path, *, verbose: bool = False) -> str | None:
    """Read a file's contents, returning None on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _warn(f"skipping {path}: {exc}", verbose=verbose)
        return None


def _read_file_str(path: str) -> str | None:
    """String-path wrapper around _read_file for use with filters."""
    return _read_file(Path(path))
