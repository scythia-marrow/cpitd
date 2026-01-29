"""Tests for the file discovery module."""

from pathlib import Path

from cpitd.discovery import discover_files

FIXTURES = str(Path(__file__).parent / "fixtures")


class TestDiscoverFiles:
    def test_finds_python_files_in_directory(self):
        files = discover_files((FIXTURES,))
        names = {f.name for f in files}
        assert "clone_a.py" in names
        assert "clone_b.py" in names
        assert "unique.py" in names

    def test_single_file_path(self):
        single = str(Path(__file__).parent / "fixtures" / "clone_a.py")
        files = discover_files((single,))
        assert len(files) == 1
        assert files[0].name == "clone_a.py"

    def test_ignore_pattern_excludes_files(self):
        files = discover_files((FIXTURES,), ignore_patterns=("*unique*",))
        names = {f.name for f in files}
        assert "unique.py" not in names
        assert "clone_a.py" in names

    def test_language_filter(self):
        files = discover_files((FIXTURES,), languages=("python",))
        assert len(files) >= 1
        assert all(f.suffix == ".py" for f in files)

    def test_nonexistent_language_returns_empty(self):
        files = discover_files((FIXTURES,), languages=("cobol",))
        assert files == []

    def test_returns_sorted_unique(self):
        files = discover_files((FIXTURES, FIXTURES))
        assert files == sorted(set(files))
