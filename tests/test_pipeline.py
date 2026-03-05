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


class TestScan:
    def test_detects_clones_in_fixtures(self):
        config = Config(min_tokens=5)
        reports = scan(config, (FIXTURES,))
        # clone_a.py and clone_b.py share substantial code
        file_pairs = {(r.file_a, r.file_b) for r in reports}
        clone_pair_found = any(
            "clone_a.py" in a
            and "clone_b.py" in b
            or "clone_b.py" in a
            and "clone_a.py" in b
            for a, b in file_pairs
        )
        assert clone_pair_found, f"Expected clone_a/clone_b pair, got: {file_pairs}"

    def test_clone_pair_has_groups(self):
        config = Config(min_tokens=5)
        reports = scan(config, (FIXTURES,))
        for r in reports:
            if "clone_a.py" in r.file_a and "clone_b.py" in r.file_b:
                assert len(r.groups) > 0
                assert r.total_cloned_lines > 0
                break

    def test_high_min_tokens_filters_small_files(self):
        config = Config(min_tokens=999999)
        reports = scan(config, (FIXTURES,))
        assert reports == []

    def test_min_tokens_filters_clone_groups(self):
        """--min-tokens should filter clone groups, not just whole files."""
        low = Config(min_tokens=5)
        high = Config(min_tokens=200)
        reports_low = scan(low, (FIXTURES,))
        reports_high = scan(high, (FIXTURES,))
        # With a high threshold, small clone groups should be filtered out
        low_groups = sum(len(r.groups) for r in reports_low)
        high_groups = sum(len(r.groups) for r in reports_high)
        assert low_groups > high_groups

    def test_normalization_affects_results(self):
        config_exact = Config(
            min_tokens=5,
            normalize=NormalizationLevel.EXACT,
        )
        config_norm = Config(
            min_tokens=5,
            normalize=NormalizationLevel.IDENTIFIERS,
        )
        reports_exact = scan(config_exact, (FIXTURES,))
        reports_norm = scan(config_norm, (FIXTURES,))
        # Normalizing identifiers should find at least as many clones
        exact_lines = sum(r.total_cloned_lines for r in reports_exact)
        norm_lines = sum(r.total_cloned_lines for r in reports_norm)
        assert norm_lines >= exact_lines


class TestScanWithSuppression:
    def test_abc_fixtures_detected_without_suppression(self):
        config = Config(min_tokens=5)
        reports = scan(config, (FIXTURES,))
        abc_pair_found = any(
            "abc_a.py" in r.file_a and "abc_b.py" in r.file_b
            or "abc_b.py" in r.file_a and "abc_a.py" in r.file_b
            for r in reports
        )
        assert abc_pair_found, (
            f"abc_a/abc_b should be detected as clones without suppression, "
            f"got: {[(r.file_a, r.file_b) for r in reports]}"
        )

    def test_suppress_abstractmethod_clones(self):
        config = Config(
            min_tokens=5,
            suppress_patterns=("*@abstractmethod*",),
        )
        reports = scan(config, (FIXTURES,))
        # abc_a.py and abc_b.py share @abstractmethod stubs, which should
        # be suppressed. Verify no report pairs them together.
        for r in reports:
            pair = (r.file_a, r.file_b)
            assert not (
                "abc_a.py" in pair[0] and "abc_b.py" in pair[1]
                or "abc_b.py" in pair[0] and "abc_a.py" in pair[1]
            ), f"abc_a/abc_b pair should be suppressed, got: {pair}"

    def test_suppress_does_not_affect_real_clones(self):
        config = Config(
            min_tokens=5,
            suppress_patterns=("*@abstractmethod*",),
        )
        reports = scan(config, (FIXTURES,))
        # clone_a.py / clone_b.py should still be detected
        clone_pair_found = any(
            "clone_a.py" in r.file_a and "clone_b.py" in r.file_b
            or "clone_b.py" in r.file_a and "clone_a.py" in r.file_b
            for r in reports
        )
        assert clone_pair_found, f"Expected clone_a/clone_b pair, got: {[(r.file_a, r.file_b) for r in reports]}"


class TestSimilarityMetrics:
    def test_reports_include_similarity_pct(self):
        config = Config(min_tokens=5)
        reports = scan(config, (FIXTURES,))
        for r in reports:
            if "clone_a.py" in r.file_a and "clone_b.py" in r.file_b:
                assert r.total_cloned_tokens > 0
                assert r.similarity_pct > 0
                break
        else:
            raise AssertionError("Expected clone_a/clone_b pair in reports")

    def test_json_output_includes_similarity(self):
        config = Config(min_tokens=5, output_format="json")
        out = io.StringIO()
        scan_and_report(config, (FIXTURES,), out=out)
        data = json.loads(out.getvalue())
        for cr in data["clone_reports"]:
            assert "similarity_pct" in cr
            assert "total_cloned_tokens" in cr


class TestScanAndReport:
    def test_human_output(self):
        config = Config(min_tokens=5, output_format="human")
        out = io.StringIO()
        reports = scan_and_report(config, (FIXTURES,), out=out)
        output = out.getvalue()
        if reports:
            assert "clone" in output.lower() or "file pair" in output.lower()
        else:
            assert "No clones detected" in output

    def test_json_output(self):
        config = Config(min_tokens=5, output_format="json")
        out = io.StringIO()
        scan_and_report(config, (FIXTURES,), out=out)
        data = json.loads(out.getvalue())
        assert "clone_reports" in data
        assert "total_pairs" in data

    def test_empty_directory(self, tmp_path):
        config = Config(min_tokens=5)
        out = io.StringIO()
        reports = scan_and_report(config, (str(tmp_path),), out=out)
        assert reports == []
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

        with patch("cpitd.pipeline.tokenize", side_effect=RuntimeError("lex boom")):
            reports = scan(config, (str(tmp_path),))

        assert reports == []
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
