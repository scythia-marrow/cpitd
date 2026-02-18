# CPITD: Copy Paste Is The Devil

A static code analysis tool that rakes you over the coals for using copy/paste. Because copy/paste is the devil. Language agnostic, and blazingly fast.

---

## Installation

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
cpitd --format json src/ | jq '.[]'
```

---

## Configuration

Settings can live in `pyproject.toml` so you don't repeat yourself on every invocation:

```toml
[tool.cpitd]
format = "human"
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

## Pre-commit Hook

Add cpitd to `.pre-commit-config.yaml` as a local hook (cpitd must be installed in the environment where hooks run):

```yaml
repos:
  - repo: local
    hooks:
      - id: cpitd-clone-detection
        name: cpitd (clone detection)
        entry: cpitd src/ --ignore "tests/fixtures/*"
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
| `--format human\|json` | `human` | Output format |
| `--ignore PATTERN` | — | Glob patterns to exclude (repeatable) |
| `--languages LANG` | — | Restrict to specific languages (repeatable) |
| `--suppress PATTERN` | — | Suppress clones whose source lines match (repeatable) |
