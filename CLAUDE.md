# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PDS Lasso Issues is a Python package for handling GitHub issues for the Planetary Data System (PDS). It provides CLI tools for milestone management, issue reporting, label management, and issue migration across repositories.

## Development Commands

### Setup

The dev virtualenv lives at `/Users/jpadams/.virtualenvs/pdsen`. Always activate it before running any dev commands — `tox`, `pytest`, `pre-commit`, and the `pds-*` CLIs are all installed there.

```bash
# Activate the dev virtualenv (required before any command below)
source /Users/jpadams/.virtualenvs/pdsen/bin/activate

# Install in editable mode with dev dependencies
pip install --editable '.[dev]'

# Set up pre-commit hooks (required for contributing; run once after checkout)
pre-commit install
pre-commit install -t pre-push
pre-commit install -t prepare-commit-msg
pre-commit install -t commit-msg
```

### Testing
```bash
# Activate first, then run tox (preferred — matches CI)
source /Users/jpadams/.virtualenvs/pdsen/bin/activate
tox -e py313

# Quick unit-test run (skips integration tests that need GITHUB_TOKEN)
python -m pytest tests/ -m "not integration" -p no:asyncio

# Run a single test file
python -m pytest tests/activity/test_correlator.py

# Integration tests (require GITHUB_TOKEN)
GITHUB_TOKEN=<token> python -m pytest tests/ -m integration -v
```

### Linting
```bash
source /Users/jpadams/.virtualenvs/pdsen/bin/activate
# Run all linters via tox
tox -e lint

# Run individual linters
flake8 src
mypy src  # Note: currently disabled due to missing type hints in github3.py
```

### Documentation
```bash
source /Users/jpadams/.virtualenvs/pdsen/bin/activate
tox -e docs
# Output: docs/build/index.html
```

### Using tox to create dev environment
```bash
# Create a development environment with all dependencies
tox --devenv venv -e dev
```

## Architecture

### Package Structure
The codebase follows a namespace package structure under `src/lasso/issues/`:

- **`github.py`**: Singleton `GithubConnection` class that manages GitHub API authentication via `github3.py`. Uses `GITHUB_TOKEN` environment variable or token parameter.

- **`argparse.py`**: Shared argument parsing utilities. The `add_standard_arguments()` function provides common CLI options (version, debug/quiet logging) used across all commands.

- **`milestones/milestones.py`**: Milestone management including closing milestones and moving open issues to next milestone with delay labels (`d.running-late`, `d.getting-later`, `d.dont-forget-me`).

- **`issues/`** subpackage:
  - **`issues.py`**: Main issue reporting command. Generates markdown reports (planning or known bugs) for repositories, with issue categorization by type (bug, enhancement, requirement, theme).
  - **`utils.py`**: Core utilities for issue processing including type detection, priority extraction, and filtering. Defines `ISSUE_TYPES`, `TOP_PRIORITIES`, and `IGNORE_LABELS` constants.
  - **`RstRddReport.py`**: Complex reStructuredText report generation with ZenHub integration. Produces Release Definition Documents (RDD) with hierarchical issue organization. Note: monkey-patches `rstcloth._indent` function for table formatting.
  - **`labels.py`**: Bulk label management across organization repositories. Can create/update/delete labels using YAML config files.
  - **`move_issues.py`**: Migrates issues between repositories using GitHub's issue import API, preserving labels, assignees, milestones, and comments.
  - **`add_version_label_to_open_bugs.py`**: Specialized utility for adding version labels to open bugs.

### Key Design Patterns

1. **Singleton GitHub Connection**: `GithubConnection.get_connection()` ensures a single authenticated session is reused across operations.

2. **Console Scripts**: All commands are registered as console scripts in `setup.cfg` under `[options.entry_points]`, making them available as standalone CLI tools after installation.

3. **Issue Classification**: Issues are categorized by labels into types (`bug`, `enhancement`, `requirement`, `theme`) and priorities (`p.must-have`, `s.high`, `s.critical`).

4. **Report Generation**: Multiple report formats supported (Markdown, reStructuredText/RDD, CSV) with modular report functions following naming convention `convert_issues_to_{report_type}_report`.

## Configuration & Dependencies

### Python Version
Requires Python >= 3.13 (strictly enforced in setup.cfg)

### Critical Dependencies
- `github3.py == 4.0.1`: GitHub API client (version must match github-actions-base)
- `pandas == 2.3.0`: DataFrame operations (version must match github-actions-base)
- `pyzenhub ~= 0.3.2`: ZenHub API integration for RDD reports
- `rstcloth ~= 0.6.0`: reStructuredText generation (with monkey-patched indentation)
- `mdutils ~= 1.8.0`: Markdown utilities

### Code Style
- **Line length**: 120 characters (flake8 max-line-length)
- **Formatter**: Black is disabled to avoid conflicts with `reorder_python_imports`
- **Import ordering**: Enforced by `reorder_python_imports` pre-commit hook
- **Docstring style**: Google format (docstring_convention in flake8)

### Pre-commit Hooks
- Runs on commit: trailing-whitespace, end-of-file-fixer, check-executables-have-shebangs, check-merge-conflict, debug-statements, check-yaml, reorder-python-imports, flake8, detect-secrets
- Runs on push: pytest (full test suite)

## Authentication

All commands require GitHub authentication via `GITHUB_TOKEN` environment variable or `--token` argument. The connection will fail with exit code 1 if neither is provided.

## Default Organization

Most commands default to `NASA-PDS` organization but can be overridden with `--github-org` or similar parameters.
