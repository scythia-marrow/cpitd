"""Tests for cpitd.config — file loading, validation, and merging."""

from __future__ import annotations

from pathlib import Path

import pytest

from cpitd.config import (
    Config,
    ConfigFileError,
    build_config,
    load_file_config,
)
from cpitd.tokenizer import NormalizationLevel


# ---------------------------------------------------------------------------
# load_file_config
# ---------------------------------------------------------------------------


class TestLoadFileConfig:
    """Tests for reading [tool.cpitd] from pyproject.toml."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_file_config(tmp_path / "nonexistent.toml") == {}

    def test_no_tool_section_returns_empty(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[project]\nname = 'foo'\n")
        assert load_file_config(toml) == {}

    def test_no_cpitd_section_returns_empty(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[tool.black]\nline-length = 88\n")
        assert load_file_config(toml) == {}

    def test_valid_full_section(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[tool.cpitd]\n'
            'min-tokens = 30\n'
            'normalize = 1\n'
            'format = "json"\n'
            'ignore = ["tests/*", "vendor/*"]\n'
            'languages = ["python"]\n'
        )
        result = load_file_config(toml)
        assert result == {
            "min_tokens": 30,
            "normalize": NormalizationLevel.IDENTIFIERS,
            "output_format": "json",
            "ignore_patterns": ("tests/*", "vendor/*"),
            "languages": ("python",),
        }

    def test_partial_section(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[tool.cpitd]\nmin-tokens = 100\n")
        assert load_file_config(toml) == {"min_tokens": 100}

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[tool.cpitd\n")  # malformed
        with pytest.raises(ConfigFileError, match="Invalid TOML"):
            load_file_config(toml)

    def test_unknown_key_raises(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[tool.cpitd]\nbogus = 42\n")
        with pytest.raises(ConfigFileError, match="unknown key 'bogus'"):
            load_file_config(toml)


# ---------------------------------------------------------------------------
# Value validation
# ---------------------------------------------------------------------------


class TestValueValidation:
    """Tests for type/value checking of individual config fields."""

    def _load(self, tmp_path: Path, body: str) -> dict[str, object]:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(f"[tool.cpitd]\n{body}\n")
        return load_file_config(toml)

    def test_min_tokens_bool_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be an integer"):
            self._load(tmp_path, "min-tokens = true")

    def test_min_tokens_string_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be an integer"):
            self._load(tmp_path, 'min-tokens = "50"')

    def test_normalize_out_of_range(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be 0, 1, or 2"):
            self._load(tmp_path, "normalize = 5")

    def test_normalize_bool_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be an integer"):
            self._load(tmp_path, "normalize = false")

    def test_format_invalid_choice(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be 'human' or 'json'"):
            self._load(tmp_path, 'format = "xml"')

    def test_format_non_string_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be a string"):
            self._load(tmp_path, "format = 42")

    def test_ignore_non_list_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be a list of strings"):
            self._load(tmp_path, 'ignore = "foo"')

    def test_ignore_non_string_elements_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be a list of strings"):
            self._load(tmp_path, "ignore = [1, 2]")

    def test_languages_non_list_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigFileError, match="must be a list of strings"):
            self._load(tmp_path, 'languages = "python"')


# ---------------------------------------------------------------------------
# build_config
# ---------------------------------------------------------------------------


class TestBuildConfig:
    """Tests for merging file config and CLI overrides."""

    def test_defaults_when_both_empty(self) -> None:
        cfg = build_config({}, {})
        assert cfg == Config()

    def test_file_config_applied(self) -> None:
        cfg = build_config({}, {"min_tokens": 30, "output_format": "json"})
        assert cfg.min_tokens == 30
        assert cfg.output_format == "json"

    def test_cli_overrides_file(self) -> None:
        cfg = build_config(
            {"min_tokens": 10},
            {"min_tokens": 30},
        )
        assert cfg.min_tokens == 10

    def test_tuple_fields_append(self) -> None:
        cfg = build_config(
            {"ignore_patterns": ("cli/*",)},
            {"ignore_patterns": ("vendor/*",)},
        )
        assert cfg.ignore_patterns == ("vendor/*", "cli/*")

    def test_tuple_fields_cli_only(self) -> None:
        cfg = build_config({"languages": ("python",)}, {})
        assert cfg.languages == ("python",)

    def test_tuple_fields_file_only(self) -> None:
        cfg = build_config({}, {"languages": ("python",)})
        assert cfg.languages == ("python",)

    def test_full_merge(self) -> None:
        file_cfg = {
            "min_tokens": 30,
            "normalize": NormalizationLevel.IDENTIFIERS,
            "ignore_patterns": ("vendor/*",),
        }
        cli = {
            "min_tokens": 10,
            "ignore_patterns": ("tests/*",),
            "languages": ("python",),
        }
        cfg = build_config(cli, file_cfg)
        assert cfg.min_tokens == 10
        assert cfg.normalize == NormalizationLevel.IDENTIFIERS
        assert cfg.ignore_patterns == ("vendor/*", "tests/*")
        assert cfg.languages == ("python",)
        assert cfg.output_format == "human"
