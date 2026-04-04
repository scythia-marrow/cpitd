"""Scan pipeline — wires tokenizer, hash tree, indexer, and reporter together."""

from __future__ import annotations

import enum
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    populate_text,
)
from cpitd.tokenizer import NormalizationLevel, tokenize
from cpitd.types import Paths
from cpitd.winnowing import build_hash_tree, hash_lines


def _warn(msg: str, *, verbose: bool) -> None:
    """Write a warning to stderr when verbose mode is enabled."""
    if verbose:
        print(f"cpitd: warning: {msg}", file=sys.stderr)


class _FileResult(enum.Enum):
    """Outcome tags for per-file processing in worker processes."""

    OK = "ok"
    READ_ERR = "read_err"
    TOK_ERR = "tok_err"
    SKIP = "skip"


def _process_file(
    args: tuple[str, str, int, int],
) -> tuple:
    """Process a single file: read, tokenize, hash, build tree.

    Runs in a worker process. Returns a tagged tuple:
    - (_FileResult.OK, file_key, token_count, tree) on success
    - (_FileResult.READ_ERR, file_key, error_message) on read error
    - (_FileResult.TOK_ERR, file_key, error_message) on tokenizer error
    - (_FileResult.SKIP,) when below min_tokens threshold
    """
    file_path_str, filename, min_tokens, level_int = args
    try:
        source = Path(file_path_str).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return (_FileResult.READ_ERR, file_path_str, str(exc))

    try:
        tokens = tokenize(
            source, filename=filename, level=NormalizationLevel(level_int)
        )
    except (ValueError, TypeError, LookupError, RuntimeError) as exc:
        return (_FileResult.TOK_ERR, file_path_str, str(exc))

    if len(tokens) < min_tokens:
        return (_FileResult.SKIP,)

    line_hashes = hash_lines(tokens)
    tree = build_hash_tree(line_hashes)
    return (_FileResult.OK, file_path_str, len(tokens), tree)


def _max_workers() -> int:
    """Return number of worker processes: CPU count minus 1, minimum 1."""
    return max(1, (os.cpu_count() or 1) - 1)


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

    # Sort largest files first so they start processing early,
    # avoiding tail latency when a big file lands in the last batch.
    work_items = sorted(
        ((str(fp), fp.name, config.min_tokens, int(level)) for fp in files),
        key=lambda item: Path(item[0]).stat().st_size,
        reverse=True,
    )

    workers = _max_workers()
    if workers < 1:
        results: list[tuple] = [_process_file(item) for item in work_items]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_file, item): item[0] for item in work_items}
            results = [f.result() for f in as_completed(futures)]

    # Sort results by file path for deterministic index insertion order.
    # as_completed() returns in arrival order which varies between runs;
    # without this sort, dict iteration in find_clones() is non-deterministic.
    results.sort(key=lambda r: r[1] if len(r) > 1 and isinstance(r[1], str) else "")

    for result in results:
        tag = result[0]
        if tag == _FileResult.SKIP:
            continue
        if tag == _FileResult.READ_ERR:
            _, file_key, error_msg = result
            _warn(f"skipping {file_key}: {error_msg}", verbose=verbose)
            skipped += 1
            continue
        if tag == _FileResult.TOK_ERR:
            _, file_key, error_msg = result
            _warn(
                f"skipping {file_key}: tokenizer error: {error_msg}",
                verbose=verbose,
            )
            skipped += 1
            continue
        _, file_key, token_count, tree = result
        file_token_counts[file_key] = token_count
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
        # This should never happen — a cluster with <2 locations indicates
        # a bug in the indexer or aggregation logic.
        print(
            f"cpitd: error: {len(degenerate)} cluster(s) with fewer than 2 "
            f"locations (this is a bug — please report it at "
            f"https://github.com/scythia-marrow/cpitd/issues)",
            file=sys.stderr,
        )
        clusters = [c for c in clusters if len(c.locations) >= 2]
    clusters = populate_text(clusters, _read_file_str)
    stages = build_filter_stages(config)
    if stages:
        clusters = run_filters(clusters, stages)
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

    if config.output_format == "json":
        format_json(clusters, out, file_stats=file_stats, show_text=config.show_text)
    else:
        format_human(clusters, out, file_stats=file_stats, show_text=config.show_text)

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
