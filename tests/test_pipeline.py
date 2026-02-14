"""Integration tests for the end-to-end scan pipeline."""

import io
import json
from pathlib import Path

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
