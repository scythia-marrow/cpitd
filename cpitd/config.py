"""Configuration handling for cpitd."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from cpitd.tokenizer import NormalizationLevel
from cpitd.types import frozen_slots


@frozen_slots
class Config:
    """Runtime configuration for a cpitd analysis run."""

    min_tokens: int = 50
    normalize: NormalizationLevel = NormalizationLevel.EXACT
    output_format: str = "human"
    ignore_patterns: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()


class ConfigFileError(Exception):
    """Raised when pyproject.toml contains invalid cpitd configuration."""


_TOML_KEY_TO_FIELD: dict[str, str] = {
    "min-tokens": "min_tokens",
    "normalize": "normalize",
    "format": "output_format",
    "ignore": "ignore_patterns",
    "languages": "languages",
}

_TUPLE_FIELDS = frozenset({"ignore_patterns", "languages"})


def _require_strict_int(toml_key: str, value: object, hint: str = "") -> int:
    """Raise ConfigFileError unless *value* is an int (not bool)."""
    if isinstance(value, bool) or not isinstance(value, int):
        label = f"an integer{hint}" if hint else "an integer"
        raise ConfigFileError(
            f"[tool.cpitd] '{toml_key}' must be {label}, got {type(value).__name__}"
        )
    return value


def _convert_value(toml_key: str, field_name: str, value: object) -> object:
    """Validate and convert a single TOML value to its Config-compatible type."""
    if field_name == "min_tokens":
        return _require_strict_int(toml_key, value)

    if field_name == "normalize":
        _require_strict_int(toml_key, value, hint=" (0-2)")
        try:
            return NormalizationLevel(value)
        except ValueError:
            raise ConfigFileError(
                f"[tool.cpitd] '{toml_key}' must be 0, 1, or 2, got {value}"
            ) from None

    if field_name == "output_format":
        if not isinstance(value, str):
            raise ConfigFileError(
                f"[tool.cpitd] '{toml_key}' must be a string, got {type(value).__name__}"
            )
        if value not in {"human", "json"}:
            raise ConfigFileError(
                f"[tool.cpitd] '{toml_key}' must be 'human' or 'json', got '{value}'"
            )
        return value

    if field_name in _TUPLE_FIELDS:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigFileError(
                f"[tool.cpitd] '{toml_key}' must be a list of strings"
            )
        return tuple(value)

    raise ConfigFileError(f"[tool.cpitd] unhandled field '{toml_key}'")


def _parse_toml_section(section: dict[str, Any]) -> dict[str, object]:
    """Validate and convert a [tool.cpitd] dict into Config-compatible fields."""
    result: dict[str, object] = {}
    for toml_key, value in section.items():
        field_name = _TOML_KEY_TO_FIELD.get(toml_key)
        if field_name is None:
            raise ConfigFileError(
                f"[tool.cpitd] unknown key '{toml_key}'"
            )
        result[field_name] = _convert_value(toml_key, field_name, value)
    return result


def load_file_config(path: Path | None = None) -> dict[str, object]:
    """Read [tool.cpitd] from pyproject.toml, returning Config-compatible dict.

    Returns an empty dict if the file doesn't exist or has no [tool.cpitd] section.
    """
    if path is None:
        path = Path("pyproject.toml")
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigFileError(f"Invalid TOML in {path}: {exc}") from None
    section = data.get("tool", {}).get("cpitd")
    if section is None:
        return {}
    return _parse_toml_section(section)


def build_config(
    cli_overrides: dict[str, object],
    file_config: dict[str, object],
) -> Config:
    """Merge file config and CLI overrides into a Config instance.

    CLI values always win. For tuple fields (ignore_patterns, languages),
    CLI values are appended to file values rather than replacing them.
    """
    merged: dict[str, object] = {}
    merged.update(file_config)

    for key, cli_val in cli_overrides.items():
        if key in _TUPLE_FIELDS and key in file_config:
            file_val = file_config[key]
            assert isinstance(file_val, tuple)
            assert isinstance(cli_val, tuple)
            merged[key] = file_val + cli_val
        else:
            merged[key] = cli_val

    return Config(**merged)
