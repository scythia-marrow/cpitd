"""Tests for the index cache module."""

from __future__ import annotations

import json
from pathlib import Path

from cpitd.cache import (
    IndexCache,
    _deserialize_tree,
    _serialize_tree,
    blob_hash,
    blob_hash_file,
    collect_blob_shas,
    load_cache,
    save_cache,
)
from cpitd.winnowing import HashTreeNode

_VERSION = "0.3.1"
_NORMALIZE = 0
_MIN_TOKENS = 20


def _make_tree() -> list[list[HashTreeNode]]:
    """Build a small 2-level hash tree for testing."""
    level_0 = [
        HashTreeNode(hash_value=111, start_line=1, end_line=1, level=0, token_count=5),
        HashTreeNode(hash_value=222, start_line=2, end_line=2, level=0, token_count=7),
    ]
    level_1 = [
        HashTreeNode(hash_value=333, start_line=1, end_line=2, level=1, token_count=12),
    ]
    return [level_0, level_1]


class TestBlobHash:
    def test_matches_git_format(self):
        # "blob {size}\0{content}" hashed with SHA-1
        data = b"hello world\n"
        result = blob_hash(data)
        # Verified against: echo "hello world" | git hash-object --stdin
        assert result == "3b18e512dba79e4c8300dd08aeb37f8e728b8dad"

    def test_empty_file(self):
        result = blob_hash(b"")
        # git hash-object /dev/null → e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
        assert result == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

    def test_blob_hash_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world\n")
        assert blob_hash_file(str(f)) == blob_hash(b"hello world\n")

    def test_blob_hash_file_missing(self, tmp_path: Path):
        assert blob_hash_file(str(tmp_path / "nope.txt")) is None


class TestCollectBlobShas:
    def test_non_git_falls_back_to_content_hash(self, tmp_path: Path):
        f = tmp_path / "foo.py"
        f.write_text("x = 1\n")
        result = collect_blob_shas([f], str(tmp_path))
        abs_path = str(f.resolve())
        assert abs_path in result
        assert result[abs_path] == blob_hash(b"x = 1\n")

    def test_git_repo_uses_git_shas(self):
        # Run on our own repo — cpitd/__init__.py is tracked
        from cpitd.discovery import discover_files

        files = list(discover_files(("cpitd/",), ignore_patterns=(), languages=()))
        result = collect_blob_shas(files, str(Path.cwd()))
        init_path = str(Path("cpitd/__init__.py").resolve())
        assert init_path in result
        # Should be a 40-char hex SHA-1
        assert len(result[init_path]) == 40


class TestSerializeTree:
    def test_round_trip(self):
        tree = _make_tree()
        serialized = _serialize_tree(tree)
        restored = _deserialize_tree(serialized)
        assert len(restored) == len(tree)
        for orig_level, rest_level in zip(tree, restored):
            assert len(orig_level) == len(rest_level)
            for orig, rest in zip(orig_level, rest_level):
                assert orig == rest

    def test_serialized_is_json_compatible(self):
        tree = _make_tree()
        serialized = _serialize_tree(tree)
        json_str = json.dumps(serialized)
        restored = _deserialize_tree(json.loads(json_str))
        assert restored[0][0] == tree[0][0]


class TestIndexCache:
    def test_lookup_hit(self):
        tree = _make_tree()
        cache = IndexCache({"foo.py": ("abc123", 50, tree)})
        result = cache.lookup("foo.py", "abc123")
        assert result is not None
        token_count, cached_tree = result
        assert token_count == 50
        assert cached_tree is tree

    def test_lookup_miss_wrong_sha(self):
        tree = _make_tree()
        cache = IndexCache({"foo.py": ("abc123", 50, tree)})
        assert cache.lookup("foo.py", "different_sha") is None

    def test_lookup_miss_no_entry(self):
        cache = IndexCache({})
        assert cache.lookup("foo.py", "abc123") is None

    def test_store_and_lookup(self):
        cache = IndexCache({})
        tree = _make_tree()
        cache.store("bar.py", "sha456", 30, tree)
        result = cache.lookup("bar.py", "sha456")
        assert result is not None
        assert result[0] == 30


class TestLoadSaveCache:
    def test_round_trip(self, tmp_path: Path):
        tree = _make_tree()
        cache = IndexCache({"a.py": ("sha_a", 40, tree)})
        cache_path = tmp_path / "cache.json"

        save_cache(cache, cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)
        loaded = load_cache(cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)

        result = loaded.lookup("a.py", "sha_a")
        assert result is not None
        token_count, loaded_tree = result
        assert token_count == 40
        assert len(loaded_tree) == 2
        assert loaded_tree[0][0].hash_value == 111

    def test_metadata_mismatch_returns_empty(self, tmp_path: Path):
        tree = _make_tree()
        cache = IndexCache({"a.py": ("sha_a", 40, tree)})
        cache_path = tmp_path / "cache.json"

        save_cache(cache, cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)
        # Load with different normalize level — should invalidate.
        loaded = load_cache(cache_path, _VERSION, 1, _MIN_TOKENS)
        assert loaded.lookup("a.py", "sha_a") is None

    def test_version_mismatch_returns_empty(self, tmp_path: Path):
        tree = _make_tree()
        cache = IndexCache({"a.py": ("sha_a", 40, tree)})
        cache_path = tmp_path / "cache.json"

        save_cache(cache, cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)
        loaded = load_cache(cache_path, "9.9.9", _NORMALIZE, _MIN_TOKENS)
        assert loaded.lookup("a.py", "sha_a") is None

    def test_missing_file_returns_empty(self, tmp_path: Path):
        cache_path = tmp_path / "nonexistent.json"
        loaded = load_cache(cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)
        assert loaded.entries == {}

    def test_corrupt_file_returns_empty(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not json at all")
        loaded = load_cache(cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)
        assert loaded.entries == {}

    def test_prunes_deleted_files(self, tmp_path: Path):
        tree = _make_tree()
        cache = IndexCache(
            {
                "keep.py": ("sha_k", 10, tree),
                "gone.py": ("sha_g", 20, tree),
            }
        )
        cache_path = tmp_path / "cache.json"

        save_cache(
            cache,
            cache_path,
            _VERSION,
            _NORMALIZE,
            _MIN_TOKENS,
            current_files={"keep.py"},
        )
        loaded = load_cache(cache_path, _VERSION, _NORMALIZE, _MIN_TOKENS)
        assert loaded.lookup("keep.py", "sha_k") is not None
        assert loaded.lookup("gone.py", "sha_g") is None
