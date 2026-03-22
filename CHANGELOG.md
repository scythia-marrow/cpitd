# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Add parallel file processing for tokenization and hashing (#51)
- Add warning when safety filter drops single-location clusters (#45)

### Changed
- Optimize clone cluster deduplication with per-file interval index and bisect lookups (#53, #54)
- Improve parallel scheduling with largest-first sorting and per-file task dispatch (#52)
- Improve performance with lexer caching and token type set lookups (#48)
- Add --no-text flag and show clone source text by default (#43)
- Add per-location line ranges and verbose clone text to output (#42)
- Add per-file duplication percentage to clone reports (#41)
- Improve clone detection pipeline to use group-based processing instead of pair-based (#40)
- Improve clone output to report duplicate groups instead of pairs (#38)
- Add detailed similarity metrics (#18)
- Improve error handling (#16)
- Remove CLAUDE.md from git tracking (#27)
- Add sibling-aware clone suppression for abstract method implementations (#29)
- Add clone suppression filters for benign patterns like @abstractmethod (#28)
- Add default scan of current directory when no paths are provided (#6)

### Fixed
- Fix intra-file clones losing locations during consecutive group merging (#44)
- Fix --min-tokens to filter clone groups instead of only whole files (#32)
- Fix filtered clone reports losing token counts and similarity metrics (#32)

### Changed
- Refactor README for external users with install, pre-commit, and per-language suppress guides (#31)
- Configure pytest, black, and sphinx dev tooling (#4)
- Create cpitd package directory with module stubs (#3)
- Add pyproject.toml with project metadata and dependencies (#2)
