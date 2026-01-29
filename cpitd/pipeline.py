"""Scan pipeline — wires tokenizer, winnowing, indexer, and reporter together."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from cpitd.config import Config
from cpitd.discovery import discover_files
from cpitd.indexer import FingerprintIndex
from cpitd.reporter import CloneReport, aggregate_clone_pairs, format_human, format_json
from cpitd.tokenizer import NormalizationLevel, tokenize
from cpitd.winnowing import fingerprint


def scan(config: Config, paths: tuple[str, ...]) -> list[CloneReport]:
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
    index = FingerprintIndex()

    for file_path in files:
        source = _read_file(file_path)
        if source is None:
            continue

        tokens = tokenize(source, filename=file_path.name, level=level)
        if len(tokens) < config.min_tokens:
            continue

        fps = fingerprint(tokens, k=config.k_gram_size, window_size=config.window_size)
        index.add(str(file_path), fps)

    pairs = index.find_clones()
    return aggregate_clone_pairs(pairs)


def scan_and_report(
    config: Config,
    paths: tuple[str, ...],
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
