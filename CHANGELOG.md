# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Add sibling-aware clone suppression for abstract method implementations (#29)
- Add clone suppression filters for benign patterns like @abstractmethod (#28)
- Add default scan of current directory when no paths are provided (#6)

### Fixed

### Changed
- Configure pytest, black, and sphinx dev tooling (#4)
- Create cpitd package directory with module stubs (#3)
- Add pyproject.toml with project metadata and dependencies (#2)
