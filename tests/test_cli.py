"""Tests for the CLI interface."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cpitd.cli import _expand_cli_param, main
from cpitd.tokenizer import NormalizationLevel

FIXTURES = str(Path(__file__).parent / "fixtures")


class TestExpandCliParam:
    def test_normalize_converts_to_enum(self):
        key, val = _expand_cli_param("normalize", 1)
        assert key == "normalize"
        assert val is NormalizationLevel.IDENTIFIERS

    def test_ignore_maps_to_ignore_patterns(self):
        key, val = _expand_cli_param("ignore", ("*.pyc",))
        assert key == "ignore_patterns"
        assert val == ("*.pyc",)

    def test_suppress_maps_to_suppress_patterns(self):
        key, val = _expand_cli_param("suppress", ("*pass*",))
        assert key == "suppress_patterns"
        assert val == ("*pass*",)

    def test_languages_keeps_name(self):
        key, val = _expand_cli_param("languages", ("python",))
        assert key == "languages"
        assert val == ("python",)

    def test_passthrough_for_other_params(self):
        key, val = _expand_cli_param("min_tokens", 100)
        assert key == "min_tokens"
        assert val == 100


class TestCliExitCodes:
    def test_exit_1_when_clones_found(self):
        runner = CliRunner()
        result = runner.invoke(main, [FIXTURES, "--min-tokens", "5"])
        assert result.exit_code == 1

    def test_exit_0_when_no_clones(self, tmp_path):
        (tmp_path / "solo.py").write_text("x = 1\n")
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path), "--min-tokens", "5"])
        assert result.exit_code == 0

    def test_exit_0_with_high_min_tokens(self):
        runner = CliRunner()
        result = runner.invoke(main, [FIXTURES, "--min-tokens", "999999"])
        assert result.exit_code == 0


class TestCliOutput:
    def test_json_output_is_valid(self):
        runner = CliRunner()
        result = runner.invoke(
            main, [FIXTURES, "--min-tokens", "5", "--format", "json"]
        )
        data = json.loads(result.output)
        assert "clone_reports" in data
        assert "total_groups" in data
        # Deprecated aliases still present
        assert "total_pairs" in data

    def test_human_output_mentions_clones(self):
        runner = CliRunner()
        result = runner.invoke(main, [FIXTURES, "--min-tokens", "5"])
        assert "clone" in result.output.lower()

    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "cpitd" in result.output

    def test_nonexistent_path_errors(self):
        runner = CliRunner()
        result = runner.invoke(main, ["/nonexistent/path"])
        assert result.exit_code != 0


class TestCliOptions:
    def test_normalize_option(self):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [FIXTURES, "--min-tokens", "5", "--normalize", "1", "--format", "json"],
        )
        data = json.loads(result.output)
        assert data["total_groups"] >= 1

    def test_ignore_option(self):
        runner = CliRunner()
        # Ignore all Python files — should find no clones
        result = runner.invoke(
            main, [FIXTURES, "--min-tokens", "5", "--ignore", "*.py"]
        )
        assert result.exit_code == 0

    def test_suppress_option(self):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                FIXTURES,
                "--min-tokens",
                "5",
                "--suppress",
                "*@abstractmethod*",
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        # No cluster should contain both abc_a and abc_b
        for group in data["clone_reports"]:
            files = {loc["file"] for loc in group["locations"]}
            has_abc_a = any("abc_a" in f for f in files)
            has_abc_b = any("abc_b" in f for f in files)
            assert not (has_abc_a and has_abc_b)

    def test_verbose_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, [FIXTURES, "--min-tokens", "5", "--verbose"])
        # Should not crash; exit code depends on clones found
        assert result.exit_code in (0, 1)

    def test_no_text_suppresses_source(self):
        runner = CliRunner()
        result = runner.invoke(main, [FIXTURES, "--min-tokens", "5", "--no-text"])
        assert result.exit_code in (0, 1)
        assert "|" not in result.output

    def test_default_human_includes_source_text(self):
        runner = CliRunner()
        result = runner.invoke(main, [FIXTURES, "--min-tokens", "5"])
        assert result.exit_code == 1  # clones found
        assert "|" in result.output
