# CPITD: Copy Paste Is The Devil

A static code analysis tool that rakes you over the coals for using copy/paste. Because copy/paste is the devil. Language agnostic, and blazingly fast.

---

## Installation

```bash
pip install cpitd
```

Requires Python 3.10+.

### Development

For development (linting, tests, docs):

```bash
git clone https://github.com/scythia-marrow/cpitd.git
cd cpitd
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

---

## Quick Start

```bash
# Scan current directory
cpitd

# Scan specific paths
cpitd src/ lib/

# JSON output for CI pipelines
cpitd --format json src/ | jq '.clone_reports'

# SARIF output for GitHub Code Scanning
cpitd --format sarif src/ > results.sarif

# Normalize identifiers to catch renamed clones
cpitd --normalize 1 src/

# Speed up repeated scans with caching (git compatible!)
cpitd --cache src/
```

---

## Configuration

Settings can live in `pyproject.toml` so you don't repeat yourself on every invocation:

```toml
[tool.cpitd]
format = "human"
normalize = 1
ignore = ["tests/fixtures/*", "vendor/*"]
suppress = ["*@abstractmethod*"]
```

CLI flags always override file config. For list options (`ignore`, `suppress`, `languages`), CLI values are appended to file values rather than replacing them.

---

## Suppressing False Positives

Some clones are intentional—boilerplate required by a language or framework. Use `--suppress` to silence them.

`--suppress PATTERN` accepts [fnmatch](https://docs.python.org/3/library/fnmatch.html) glob patterns matched against raw source lines (including one line of context above each clone chunk, to catch decorators). If any line in either side of a clone pair matches, the group is suppressed.

You can also annotate specific sites inline—the filter reads raw source, so comments are visible even though the tokenizer strips them. Add a suppression comment to any line inside or immediately above a clone:

| Language | Inline annotation              |
|----------|-------------------------------|
| Python   | `# cpitd: suppress`           |
| C/C++    | `// cpitd: suppress`          |
| Rust     | `// cpitd: suppress`          |

Then pass `--suppress "*cpitd: suppress*"` (or set it in `pyproject.toml`).

### Python

**Abstract base class implementations** — ABCs force you to repeat method signatures across subclasses. Suppress them with:

```bash
cpitd src/ --suppress "*@abstractmethod*"
```

Or in `pyproject.toml`:

```toml
[tool.cpitd]
suppress = ["*@abstractmethod*", "*@override*"]
```

**Protocol / interface boilerplate** — if you use a decorator to mark protocol implementations (e.g. `@protocol_impl`), pass that pattern:

```bash
cpitd src/ --suppress "*@protocol_impl*"
```

### C / C++

**Header guards** — every `.h` file has them. Suppress both styles:

```bash
cpitd src/ \
  --suppress "*#ifndef *_H*" \
  --suppress "*#pragma once*"
```

Or in `pyproject.toml`:

```toml
[tool.cpitd]
suppress = ["*#ifndef *_H*", "*#pragma once*"]
ignore = ["**/*.h"]   # alternatively, just skip headers entirely
```

### Rust

**Trait implementations** — implementing the same trait for multiple types produces near-identical `impl` blocks. Suppress by matching the `impl ... for ...` line:

```bash
cpitd src/ --suppress "*impl * for *"
```

**Derive macros** — `#[derive(Debug, Clone, PartialEq)]` lines repeat everywhere but are rarely meaningful clones. Suppress them:

```bash
cpitd src/ --suppress "*#[derive(*"
```

In `pyproject.toml`:

```toml
[tool.cpitd]
suppress = [
    "*impl*Display*for*",
    "*impl*From*for*",
    "*#[derive(*",
]
```

---

## Caching

cpitd can cache per-file tokenization and indexing results to speed up repeated scans. The cache uses git blob SHAs to detect file changes, so unchanged files reuse their cached hash trees instead of re-tokenizing — but they still participate fully in cross-file clone matching.

```bash
# Enable caching (stores .cpitd-cache.json in the scan root)
cpitd --cache src/

# Use a custom cache path
cpitd --cache --cache-path /tmp/cpitd.json src/
```

In non-git directories, cpitd falls back to SHA-256 content hashes. The cache is automatically invalidated when the cpitd version, normalization level, or minimum token threshold changes.

---

## CI Integration

### Fail Thresholds

Use `--fail-above-pct` and `--fail-above-count` to gate CI on clone metrics. cpitd exits with code 1 when a threshold is exceeded:

```bash
# Fail if any file exceeds 15% duplication
cpitd --fail-above-pct 15 src/

# Fail if more than 5 clone groups are found
cpitd --fail-above-count 5 src/

# Both thresholds together (either triggers failure)
cpitd --fail-above-pct 15 --fail-above-count 5 src/
```

### GitHub Actions

cpitd can upload SARIF results to GitHub Code Scanning, showing clone detections inline on pull requests:

```yaml
name: Clone Detection

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  security-events: write

jobs:
  cpitd:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install cpitd
        run: pip install cpitd

      - name: Restore cpitd cache
        uses: actions/cache@v4
        with:
          path: .cpitd-cache.json
          key: cpitd-${{ github.sha }}
          restore-keys: cpitd-

      - name: Run clone detection
        run: cpitd --cache --format sarif > results.sarif || true

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: results.sarif
          category: clone-detection
```

Configure thresholds and suppression patterns in `pyproject.toml` to keep the workflow clean:

```toml
[tool.cpitd]
suppress = ["*@protocol_impl*"]
```

---

## Pre-commit Hook

Add cpitd to `.pre-commit-config.yaml` as a local hook (cpitd must be installed in the environment where hooks run):

```yaml
repos:
  - repo: local
    hooks:
      - id: cpitd-clone-detection
        name: cpitd (clone detection)
        entry: cpitd src/
        language: system
        pass_filenames: false
        always_run: true
```

Then install the hook:

```bash
pre-commit install
```

The hook runs `cpitd` on every commit. Tune `entry` with `--suppress` or any other flag -- or lean on `[tool.cpitd]` in `pyproject.toml` so the hook entry stays short.

To run the hook manually without committing:

```bash
pre-commit run cpitd-clone-detection
```

---

## CLI Options Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--min-tokens N` | `20` | Minimum token count to report a clone group |
| `--normalize {0,1,2}` | `0` | Token normalization level (0=exact, 1=identifiers, 2=literals+identifiers) |
| `--format {human,json,sarif}` | `human` | Output format |
| `--ignore PATTERN` | — | Glob patterns to exclude files (repeatable) |
| `--languages LANG` | — | Restrict to specific languages (repeatable) |
| `--suppress PATTERN` | — | Suppress clones whose source lines match (repeatable) |
| `--cache` | off | Cache per-file index data to speed up repeated scans |
| `--cache-path PATH` | `.cpitd-cache.json` | Custom path for the cache file |
| `--fail-above-pct N` | — | Exit 1 if any file's duplication % exceeds threshold |
| `--fail-above-count N` | — | Exit 1 if total clone groups exceed threshold |
| `--no-text` | off | Suppress clone source text from output |
| `--verbose` | off | Print diagnostic warnings to stderr |
