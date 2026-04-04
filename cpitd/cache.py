"""Index cache for skipping tokenization of unchanged files.

Caches per-file hash trees keyed by git blob SHA (``SHA-1("blob {size}\\0{content}")``).
In a git repo, blob SHAs for all tracked files are read in bulk via
``git ls-tree`` (sub-millisecond, zero file I/O).  Outside a git repo,
the same hash is computed per-file from the file contents.  Either way
the cache format is identical.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from cpitd.winnowing import HashTreeNode, _K_GRAM_SIZE, _MAX_TREE_LEVEL, _WINDOW_SIZE

# Cache format version — bump when serialization format changes.
_CACHE_FORMAT = 1


def blob_hash(data: bytes) -> str:
    """Compute the git blob SHA-1 for raw file contents.

    Identical to ``git hash-object``: ``SHA-1("blob {size}\\0" + data)``.
    """
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def blob_hash_file(path: str) -> str | None:
    """Return the git blob SHA-1 of a file, or None on read error."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return blob_hash(data)


def _git_repo_root(cwd: str) -> str | None:
    """Return the absolute path of the git repository root, or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_blob_shas(repo_root: str) -> dict[str, str] | None:
    """Return {absolute_path: blob_sha} via ``git ls-tree``, or None."""
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    # Default output format: "<mode> <type> <sha>\t<path>"
    root = Path(repo_root)
    shas: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, rel_path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3:
            shas[str(root / rel_path)] = parts[2]
    return shas


def collect_blob_shas(files: list[Path], scan_root: str) -> dict[str, str]:
    """Return {absolute_path: blob_sha} for all *files*.

    Tries ``git ls-tree`` first for tracked files (bulk, no file I/O).
    Any files not covered by git (untracked, or not in a repo) get their
    blob SHA computed from file contents.
    """
    abs_paths = {str(fp.resolve()): fp for fp in files}
    result: dict[str, str] = {}

    # Try git bulk lookup.
    repo_root = _git_repo_root(scan_root)
    if repo_root is not None:
        git_shas = _git_blob_shas(repo_root)
        if git_shas is not None:
            for abs_path in abs_paths:
                sha = git_shas.get(abs_path)
                if sha is not None:
                    result[abs_path] = sha

    # Fall back to per-file hashing for anything git didn't cover.
    for abs_path in abs_paths:
        if abs_path not in result:
            sha = blob_hash_file(abs_path)
            if sha is not None:
                result[abs_path] = sha

    return result


def _serialize_tree(tree: list[list[HashTreeNode]]) -> list[list[list[int]]]:
    """Convert a hash tree to a JSON-serializable nested list.

    Each node becomes [hash_value, start_line, end_line, level, token_count].
    """
    return [
        [
            [n.hash_value, n.start_line, n.end_line, n.level, n.token_count]
            for n in level
        ]
        for level in tree
    ]


def _deserialize_tree(data: list[list[list[int]]]) -> list[list[HashTreeNode]]:
    """Reconstruct a hash tree from its serialized form."""
    return [
        [
            HashTreeNode(
                hash_value=n[0],
                start_line=n[1],
                end_line=n[2],
                level=n[3],
                token_count=n[4],
            )
            for n in level
        ]
        for level in data
    ]


class IndexCache:
    """In-memory representation of a cpitd index cache.

    Attributes:
        entries: Mapping of file path to (blob_sha, token_count, tree).
    """

    def __init__(
        self,
        entries: dict[str, tuple[str, int, list[list[HashTreeNode]]]],
    ) -> None:
        self.entries = entries

    def lookup(
        self, path: str, blob_sha: str
    ) -> tuple[int, list[list[HashTreeNode]]] | None:
        """Return (token_count, tree) if *path* is cached with matching blob SHA."""
        entry = self.entries.get(path)
        if entry is not None and entry[0] == blob_sha:
            return entry[1], entry[2]
        return None

    def store(
        self,
        path: str,
        blob_sha: str,
        token_count: int,
        tree: list[list[HashTreeNode]],
    ) -> None:
        """Add or update a cache entry."""
        self.entries[path] = (blob_sha, token_count, tree)


def _make_metadata(
    cpitd_version: str,
    normalize: int,
    min_tokens: int,
) -> dict[str, Any]:
    """Build the metadata header for cache validation."""
    return {
        "cache_format": _CACHE_FORMAT,
        "cpitd_version": cpitd_version,
        "normalize": normalize,
        "min_tokens": min_tokens,
        "k_gram_size": _K_GRAM_SIZE,
        "window_size": _WINDOW_SIZE,
        "max_tree_level": _MAX_TREE_LEVEL,
    }


def load_cache(
    path: Path,
    cpitd_version: str,
    normalize: int,
    min_tokens: int,
) -> IndexCache:
    """Load a cache file, returning an empty cache on any mismatch or error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return IndexCache({})

    expected = _make_metadata(cpitd_version, normalize, min_tokens)
    if data.get("metadata") != expected:
        return IndexCache({})

    entries: dict[str, tuple[str, int, list[list[HashTreeNode]]]] = {}
    for file_path, entry in data.get("files", {}).items():
        try:
            blob_sha = entry["sha"]
            token_count = entry["tokens"]
            tree = _deserialize_tree(entry["tree"])
            entries[file_path] = (blob_sha, token_count, tree)
        except (KeyError, TypeError, IndexError):
            continue

    return IndexCache(entries)


def save_cache(
    cache: IndexCache,
    path: Path,
    cpitd_version: str,
    normalize: int,
    min_tokens: int,
    current_files: set[str] | None = None,
) -> None:
    """Write cache to disk, pruning entries not in *current_files*."""
    metadata = _make_metadata(cpitd_version, normalize, min_tokens)

    files: dict[str, Any] = {}
    for file_path, (blob_sha, token_count, tree) in cache.entries.items():
        if current_files is not None and file_path not in current_files:
            continue
        files[file_path] = {
            "sha": blob_sha,
            "tokens": token_count,
            "tree": _serialize_tree(tree),
        }

    data = {"metadata": metadata, "files": files}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
        f.write("\n")
