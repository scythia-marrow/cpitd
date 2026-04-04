"""Integration tests for the end-to-end scan pipeline."""

import io
import json
import os
from pathlib import Path
from unittest.mock import patch

from cpitd.config import Config
from cpitd.pipeline import scan, scan_and_report
from cpitd.tokenizer import NormalizationLevel

FIXTURES = str(Path(__file__).parent / "fixtures")


def _files_in_clusters(clusters):
    """Extract all unique file basenames from clusters."""
    files = set()
    for c in clusters:
        for loc in c.locations:
            files.add(Path(loc.file).name)
    return files


def _cluster_contains_files(cluster, *names):
    """Check if a cluster contains locations with the given file basenames."""
    cluster_files = {Path(loc.file).name for loc in cluster.locations}
    return all(name in cluster_files for name in names)


class TestScan:
    def test_detects_clones_in_fixtures(self):
        config = Config(min_tokens=5)
        clusters, _ = scan(config, (FIXTURES,))
        clone_found = any(
            _cluster_contains_files(c, "clone_a.py", "clone_b.py") for c in clusters
        )
        assert clone_found, (
            f"Expected cluster with clone_a/clone_b, got files: "
            f"{[{Path(loc.file).name for loc in c.locations} for c in clusters]}"
        )

    def test_clone_cluster_has_locations(self):
        config = Config(min_tokens=5)
        clusters, _ = scan(config, (FIXTURES,))
        for c in clusters:
            if _cluster_contains_files(c, "clone_a.py", "clone_b.py"):
                assert len(c.locations) >= 2
                assert c.line_count > 0
                assert c.token_count > 0
                break

    def test_high_min_tokens_filters_small_files(self):
        config = Config(min_tokens=999999)
        clusters, _ = scan(config, (FIXTURES,))
        assert clusters == []

    def test_min_tokens_filters_clone_groups(self):
        """--min-tokens should filter clone groups, not just whole files."""
        low = Config(min_tokens=5)
        high = Config(min_tokens=200)
        clusters_low, _ = scan(low, (FIXTURES,))
        clusters_high, _ = scan(high, (FIXTURES,))
        assert len(clusters_low) > len(clusters_high)

    def test_normalization_affects_results(self):
        config_exact = Config(
            min_tokens=5,
            normalize=NormalizationLevel.EXACT,
        )
        config_norm = Config(
            min_tokens=5,
            normalize=NormalizationLevel.IDENTIFIERS,
        )
        clusters_exact, _ = scan(config_exact, (FIXTURES,))
        clusters_norm, _ = scan(config_norm, (FIXTURES,))
        # Normalizing identifiers should find at least as many clone locations
        exact_locs = sum(len(c.locations) for c in clusters_exact)
        norm_locs = sum(len(c.locations) for c in clusters_norm)
        assert norm_locs >= exact_locs

    def test_returns_file_token_counts(self):
        config = Config(min_tokens=5)
        _, file_token_counts = scan(config, (FIXTURES,))
        assert len(file_token_counts) > 0
        assert all(isinstance(v, int) and v > 0 for v in file_token_counts.values())


class TestScanWithSuppression:
    def test_abc_fixtures_detected_without_suppression(self):
        config = Config(min_tokens=5)
        clusters, _ = scan(config, (FIXTURES,))
        abc_found = any(
            _cluster_contains_files(c, "abc_a.py", "abc_b.py") for c in clusters
        )
        assert abc_found, (
            f"abc_a/abc_b should be detected as clones without suppression, "
            f"got: {[{Path(loc.file).name for loc in c.locations} for c in clusters]}"
        )

    def test_suppress_abstractmethod_clones(self):
        config = Config(
            min_tokens=5,
            suppress_patterns=("*@abstractmethod*",),
        )
        clusters, _ = scan(config, (FIXTURES,))
        for c in clusters:
            assert not _cluster_contains_files(c, "abc_a.py", "abc_b.py"), (
                f"abc_a/abc_b should be suppressed, got cluster with: "
                f"{[Path(loc.file).name for loc in c.locations]}"
            )

    def test_suppress_does_not_affect_real_clones(self):
        config = Config(
            min_tokens=5,
            suppress_patterns=("*@abstractmethod*",),
        )
        clusters, _ = scan(config, (FIXTURES,))
        clone_found = any(
            _cluster_contains_files(c, "clone_a.py", "clone_b.py") for c in clusters
        )
        assert clone_found, (
            f"Expected clone_a/clone_b cluster, "
            f"got: {[{Path(loc.file).name for loc in c.locations} for c in clusters]}"
        )


class TestScanAndReport:
    def test_human_output(self):
        config = Config(min_tokens=5, output_format="human")
        out = io.StringIO()
        clusters, _ = scan_and_report(config, (FIXTURES,), out=out)
        output = out.getvalue()
        if clusters:
            assert "clone group" in output.lower()
        else:
            assert "No clones detected" in output

    def test_human_output_includes_file_stats(self):
        config = Config(min_tokens=5, output_format="human")
        out = io.StringIO()
        clusters, _ = scan_and_report(config, (FIXTURES,), out=out)
        output = out.getvalue()
        if clusters:
            assert "File duplication:" in output
            assert "% duplicated" in output

    def test_json_output(self):
        config = Config(min_tokens=5, output_format="json")
        out = io.StringIO()
        scan_and_report(config, (FIXTURES,), out=out)
        data = json.loads(out.getvalue())
        assert "clone_reports" in data
        assert "total_groups" in data

    def test_json_output_has_locations(self):
        config = Config(min_tokens=5, output_format="json")
        out = io.StringIO()
        scan_and_report(config, (FIXTURES,), out=out)
        data = json.loads(out.getvalue())
        for group in data["clone_reports"]:
            assert "locations" in group
            assert "line_count" in group
            assert "token_count" in group
            for loc in group["locations"]:
                assert "file" in loc
                assert "lines" in loc

    def test_json_output_has_file_stats(self):
        config = Config(min_tokens=5, output_format="json")
        out = io.StringIO()
        scan_and_report(config, (FIXTURES,), out=out)
        data = json.loads(out.getvalue())
        assert "file_stats" in data
        for fs in data["file_stats"]:
            assert "file" in fs
            assert "total_tokens" in fs
            assert "duplicated_tokens" in fs
            assert "duplication_pct" in fs

    def test_human_output_includes_text_by_default(self):
        config = Config(min_tokens=5, output_format="human")
        out = io.StringIO()
        clusters, _ = scan_and_report(config, (FIXTURES,), out=out)
        if clusters:
            assert "|" in out.getvalue()

    def test_json_output_includes_text_by_default(self):
        config = Config(min_tokens=5, output_format="json")
        out = io.StringIO()
        clusters, _ = scan_and_report(config, (FIXTURES,), out=out)
        if clusters:
            data = json.loads(out.getvalue())
            assert "text" in data["clone_reports"][0]

    def test_no_text_suppresses_source(self):
        config = Config(min_tokens=5, output_format="human", show_text=False)
        out = io.StringIO()
        clusters, _ = scan_and_report(config, (FIXTURES,), out=out)
        if clusters:
            assert "|" not in out.getvalue()

    def test_no_text_suppresses_json_text(self):
        config = Config(min_tokens=5, output_format="json", show_text=False)
        out = io.StringIO()
        clusters, _ = scan_and_report(config, (FIXTURES,), out=out)
        if clusters:
            data = json.loads(out.getvalue())
            assert "text" not in data["clone_reports"][0]

    def test_empty_directory(self, tmp_path):
        config = Config(min_tokens=5)
        out = io.StringIO()
        clusters, file_token_counts = scan_and_report(config, (str(tmp_path),), out=out)
        assert clusters == []
        assert file_token_counts == {}
        assert "No clones detected" in out.getvalue()


class TestErrorHandling:
    def test_unreadable_file_skipped_with_verbose_warning(self, tmp_path, capsys):
        """Files that can't be read are skipped and warned about in verbose mode."""
        src = tmp_path / "good.py"
        src.write_text("x = 1\ny = 2\n")
        bad = tmp_path / "bad.py"
        bad.write_text("z = 3\n")
        bad.chmod(0o000)

        config = Config(min_tokens=5, verbose=True)
        try:
            scan(config, (str(tmp_path),))
        finally:
            bad.chmod(0o644)

        stderr = capsys.readouterr().err
        assert "skipping" in stderr
        assert "bad.py" in stderr

    def test_unreadable_file_silent_without_verbose(self, tmp_path, capsys):
        """Without --verbose, unreadable files are silently skipped."""
        bad = tmp_path / "bad.py"
        bad.write_text("z = 3\n")
        bad.chmod(0o000)

        config = Config(min_tokens=5, verbose=False)
        try:
            scan(config, (str(tmp_path),))
        finally:
            bad.chmod(0o644)

        stderr = capsys.readouterr().err
        assert stderr == ""

    def test_tokenizer_error_skipped_gracefully(self, tmp_path, capsys):
        """If the tokenizer raises, the file is skipped with a warning."""
        src = tmp_path / "example.py"
        src.write_text("x = 1\n" * 20)

        config = Config(min_tokens=5, verbose=True)

        # Force serial mode (workers=0) so the mock applies in-process.
        with (
            patch("cpitd.pipeline._max_workers", return_value=0),
            patch("cpitd.pipeline.tokenize", side_effect=RuntimeError("lex boom")),
        ):
            clusters, _ = scan(config, (str(tmp_path),))

        assert clusters == []
        stderr = capsys.readouterr().err
        assert "tokenizer error" in stderr
        assert "lex boom" in stderr

    def test_skipped_count_reported_in_verbose(self, tmp_path, capsys):
        """Verbose mode reports total count of skipped files."""
        for name in ("a.py", "b.py"):
            f = tmp_path / name
            f.write_text("x = 1\n")
            f.chmod(0o000)

        config = Config(min_tokens=5, verbose=True)
        try:
            scan(config, (str(tmp_path),))
        finally:
            for name in ("a.py", "b.py"):
                (tmp_path / name).chmod(0o644)

        stderr = capsys.readouterr().err
        assert "2 file(s) skipped" in stderr
