# Code Clone Detection CLI Tool

## Project Overview
A permissively-licensed (MIT/Apache 2.0), language-agnostic static analysis tool for detecting copy-pasted code across a codebase. Fills a gap in the current tooling landscape where existing solutions are either copyleft (GPL), language-specific, or commercial.

## MVP Goals
- **Primary**: Detect Type-1 clones (exact/whitespace-normalized duplicates)
- **Secondary**: Basic Type-2 clone detection (duplicates with renamed identifiers/literals)
- CLI tool for batch analysis (not real-time/LSP)
- Fast enough for pre-commit hooks
- JSON output for CI/CD integration
- Human-readable reports

## Best Practices

Use feature branches, pull requests, and the chainlink cli issue tracker.

A general session will proceed as follows:

1) Start a chainlink session, decide which issue to work on
2) Mark the issue as active
3) Create or checkout an associated issue branch named CPITD-<num>\_description
4) Work on the issue until completion
5) Create a PR to main
6) Retrieve merge review comments from the request, implement fixes. Remember to read both general comments from the PR page as well as individual code critiques.
7) Verify that the PR has been merged
8) Close the chainlink issue
9) Add any new issues discovered / out of scope for this session
10) End the session

Be conscientious, NEVER close an issue before the request has been merged.

Separate concerns in both planning and code. ALWAYS have only one concern per PR. NEVER submit PR that depends on another PR.

Prefer functional programming style to OOP style.

Support dependency injection! This means NEVER construct a component class directly, ALWAYS take component classes as arguments. Keep argument lists short. If argument lists get too unweildy that means we need to either use configuration files or restructure the code.

Don't Repeat Yourself (DRY).

## Technical Approach

### Core Algorithm: Winnowing
Using the winnowing fingerprinting algorithm (from MOSS plagiarism detector):
1. Tokenize source files using pygments (500+ language support)
2. Generate k-grams (sliding windows of k tokens)
3. Hash each k-gram
4. Select minimum hash in each window (guarantees clone detection)
5. Index by hash fingerprint
6. Report hash collisions as potential clones

**Key properties:**
- O(n) in file size
- Noise-resistant (handles whitespace/comment variations)
- No expensive AST construction
- Provably detects clones above threshold

### Technology Stack
- **Python** - for rapid development, ecosystem access
- **pygments** - multi-language lexical analysis
- **Click** - CLI framework
- **License**: MIT or Apache 2.0 (TBD)

### Deferred Complexity
- Tree-sitter integration (for Type-3 structural clones)
- Incremental analysis
- LSP server functionality
- GUI/web interface

## Design Decisions

### Variable Name Sensitivity
Configurable behavior for when to care about identifier names:
- **Strict mode**: Flag even common patterns like `for (int i = 0; i < n; i++)` 
  - Rationale: Lazy naming is worth flagging; modern idioms prefer foreach
- **Lenient mode**: Normalize all identifiers to generic tokens
- Allow per-project configuration

### Token Normalization Levels
1. **Level 0** (exact): Only whitespace/comment normalization
2. **Level 1** (identifiers): ID tokens → `ID`, preserve structure
3. **Level 2** (literals): literals → `LIT`, identifiers → `ID`

### Output Formats
- Human-readable: File pairs, line numbers, similarity percentage
- JSON: Structured data for CI/CD pipelines
- Diff-style: Show actual code side-by-side (stretch goal)

## Configuration Parameters
- `--min-tokens`: Minimum token sequence length to report (default: 50)
- `--k-gram-size`: Size of k-gram for fingerprinting (default: 5)
- `--window-size`: Winnowing window size (default: 4)
- `--normalize`: Token normalization level (0-2)
- `--ignore`: Patterns to exclude (e.g., `tests/**`, `vendor/**`)
- `--languages`: Restrict analysis to specific languages
- `--format`: Output format (human/json)

## Project Structure (Proposed)
```
cpitd/
├── cpitd/
│   ├── __init__.py
│   ├── cli.py              # Click CLI interface
│   ├── tokenizer.py        # Pygments wrapper + normalization
│   ├── winnowing.py        # Core fingerprinting algorithm
│   ├── indexer.py          # Hash collision detection
│   ├── reporter.py         # Output formatting
│   └── config.py           # Configuration handling
├── tests/
│   ├── test_tokenizer.py
│   ├── test_winnowing.py
│   └── fixtures/           # Sample code with known clones
├── LICENSE
├── README.md
├── pyproject.toml
└── CLAUDE.md               # This file
```

## Implementation Phases

### Phase 1: Core Detection (MVP)
- [ ] Basic tokenization with pygments
- [ ] Winnowing algorithm implementation
- [ ] Simple hash collision indexing
- [ ] CLI skeleton with Click
- [ ] Plain text output

### Phase 2: Usability
- [ ] JSON output format
- [ ] Configurable thresholds
- [ ] File ignore patterns
- [ ] Better error handling
- [ ] Performance optimization

### Phase 3: Quality of Life
- [ ] Detailed similarity metrics
- [ ] Side-by-side diff output
- [ ] Configuration file support
- [ ] CI/CD examples
- [ ] Documentation

### Phase 4: Advanced Features (Maybe)
- [ ] Type-2 clone detection with normalization
- [ ] Cross-project clone detection
- [ ] Clone evolution tracking
- [ ] Tree-sitter integration for Type-3

## Open Questions
1. License choice: MIT vs Apache 2.0?
2. Tool name? (clonedetect, dupefinder, winnow, ?)
3. Should we support remote repository analysis (clone from git URL)?
4. Handling of generated code (protobuf, parser generators)?
5. Database backend for large codebases, or pure in-memory?

## Related Work
- **Dolos**: MIT-licensed, tree-sitter based, web-focused
- **MOSS**: Original winnowing implementation, proprietary
- **CCFinder**: Fast but language-specific lexers
- **SourcererCC**: Java-based, scalable but heavyweight
- **CCDetect-lsp**: GPL-licensed, LSP server
- **Academic**: Various research tools, typically unlicensed/abandoned

## Success Metrics
- Can detect clones in medium-sized projects (<100k LOC) in <10 seconds
- False positive rate low enough for daily use
- Zero external dependencies beyond Python stdlib + pygments
- Clear, actionable output

## Notes
- Pygments handles 500+ languages with consistent API
- Winnowing guarantees detection with bounded false negatives
- Line-based grep approach considered but lacks context/thresholds
- Tree-sitter complexity avoided for MVP
- Focus on developer workflow integration (pre-commit, CI)
