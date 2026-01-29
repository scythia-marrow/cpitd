"""File discovery — walk directories and collect source files for analysis."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from pygments.lexers import get_lexer_for_filename
from pygments.util import ClassNotFound


def discover_files(
    paths: tuple[str, ...],
    *,
    ignore_patterns: tuple[str, ...] = (),
    languages: tuple[str, ...] = (),
) -> list[Path]:
    """Collect source files from the given paths.

    Recursively walks directories, filters by ignore patterns and language
    restrictions, and returns files that pygments can tokenize.

    Args:
        paths: File or directory paths to scan.
        ignore_patterns: Glob patterns for files/dirs to skip.
        languages: If non-empty, only include files matching these language names.

    Returns:
        Sorted list of Path objects for files to analyze.
    """
    collected: list[Path] = []

    for raw_path in paths:
        p = Path(raw_path)
        if p.is_file():
            if _should_include(p, ignore_patterns, languages):
                collected.append(p)
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and _should_include(
                    child, ignore_patterns, languages
                ):
                    collected.append(child)

    return sorted(set(collected))


def _should_include(
    path: Path,
    ignore_patterns: tuple[str, ...],
    languages: tuple[str, ...],
) -> bool:
    """Determine if a file should be included in analysis."""
    path_str = str(path)

    for pattern in ignore_patterns:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
            return False

    try:
        lexer = get_lexer_for_filename(path.name)
    except ClassNotFound:
        return False

    if languages:
        lexer_name = lexer.name.lower()
        lexer_aliases = {a.lower() for a in lexer.aliases}
        language_set = {lang.lower() for lang in languages}
        if not (language_set & ({lexer_name} | lexer_aliases)):
            return False

    return True
