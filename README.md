# PDS Lasso Issues

The PDS Lasso Issues package provides utilities handle issues on GitHub. It provides these commands:

- `milestones`
- `pds-issues`
- `move-issues`
- `pds-labels`
- `add-version-label-to-open-bugs`
- `pds-scheduler-themes`

Please visit our website at: https://nasa-pds.github.io/lasso-issues

It may have useful information for developers and end-users.


## Prerequisites

Installing this software requires `git` to be present on the target systme.


## User Quickstart

Install with:

    pip install lasso-issues


### Using pds-scheduler-themes

### pds-issues

Generate issue reports in various formats (Markdown, RST, CSV).

```bash
# Set your GitHub token
export GITHUB_TOKEN=your_token_here

# Generate a Markdown planning report
pds-issues --format=md --github-org=NASA-PDS

# Generate an RST Release Description Document (RDD)
pds-issues --format=rst --build=B15.1 --github-org=NASA-PDS

# Generate an RST RDD with component grouping (groups repos by product)
pds-issues --format=rst --build=B15.1 --github-org=NASA-PDS --group-by-component

# Generate for specific repositories only
pds-issues --format=rst --build=B15.1 --github-org=NASA-PDS --github-repos validate registry
```

#### Component Grouping

When using `--group-by-component`, repositories are grouped by their product/component as defined in `conf/pds-products.yaml`. This produces a hierarchical document structure:

- **Component sections** (H2) containing related repositories
- **Repository sections** (H3) with their issues
- **Summary metrics table** at the end showing issue counts by component

#### Output Formats

- `--format=md`: Markdown planning or known bugs report
- `--format=rst`: reStructuredText Release Description Document with theme trees
- `--format=metrics`: Summary metrics output
- `--format=csv`: CSV export for test management (TestRail integration)

### milestones

Manage GitHub milestones across repositories.

### move-issues

Migrate issues between repositories.

### pds-labels

Bulk label management across organization repositories
The `pds-scheduler-themes` command automates creation of release theme issues from CSV schedule files.

**Prerequisites:**
- GitHub CLI (`gh`) must be installed and authenticated
- Write access to target NASA-PDS repositories

**Basic Usage:**

```bash
# Preview what would be created (dry-run mode)
pds-scheduler-themes --csv-file schedule.csv --build-number 17 --dry-run

# Create the issues
pds-scheduler-themes --csv-file schedule.csv --build-number 17

# With debug logging
pds-scheduler-themes --csv-file schedule.csv --build-number 17 --debug
```

**CSV Format:**

The CSV file should contain these columns:
- **Title**: Issue title (will be prefixed with build number, e.g., "B17 Release Planning")
- **Repo**: Repository name in format `NASA-PDS/repo-name`
- **Start Date**: Start date in YYYY-MM-DD format (e.g., "2025-09-05")
- **End Date**: End date in YYYY-MM-DD format (e.g., "2025-10-16")
- **Description**: Issue description text
- **Checklist**: Semicolon-delimited checklist items (e.g., "Task 1;Task 2;Task 3")
- **GitHub Project Product**: Product name for project metadata (optional)

**Features:**
- Automatically prefixes issue titles with build number (e.g., "B17")
- Checks for duplicate issues and skips if already exists
- Creates build labels (e.g., "B17") if they don't exist
- Adds issues to NASA-PDS/6 project and build-specific projects
- Applies labels: `theme`, `Epic`, `i&t.skip`, and build label
- Converts checklist items to markdown checkboxes

**Output:**

The tool provides a summary showing:
- ✓ Created issues with URLs
- ⊙ Skipped issues (already exist)
- ✗ Failed issues

See `examples/b17_schedule_prep_spreadsheet.csv` for a sample CSV file.


## Code of Conduct

All users and developers of the NASA-PDS software are expected to abide by our [Code of Conduct](https://github.com/NASA-PDS/.github/blob/main/CODE_OF_CONDUCT.md). Please read this to ensure you understand the expectations of our community.


## Development

To develop this project, use your favorite text editor, or an integrated development environment with Python support, such as [PyCharm](https://www.jetbrains.com/pycharm/).


### Contributing

For information on how to contribute to NASA-PDS codebases please take a look at our [Contributing guidelines](https://github.com/NASA-PDS/.github/blob/main/CONTRIBUTING.md).


### Installation

Install in editable mode and with extra developer dependencies into your virtual environment of choice:

    pip install --editable '.[dev]'

Configure the `pre-commit` hooks:

    pre-commit install
    pre-commit install -t pre-push
    pre-commit install -t prepare-commit-msg
    pre-commit install -t commit-msg

These hooks check code formatting and also aborts commits that contain secrets such as passwords or API keys. However, a one time setup is required in your global Git configuration. See [the wiki entry on Git Secrets](https://github.com/NASA-PDS/nasa-pds.github.io/wiki/Git-and-Github-Guide#git-secrets) to learn how.


### Packaging

To isolate and be able to re-produce the environment for this package, you should use a [Python Virtual Environment](https://docs.python.org/3/tutorial/venv.html). To do so, run:

    python3 -m venv venv

Then exclusively use `venv/bin/python`, `venv/bin/pip`, etc. Or, "activate" the virtual environment by sourcing the appropriate script in the `venv/bin` directory.

If you have `tox` installed and would like it to create your environment and install dependencies for you run:

    tox --devenv <name you'd like for env> -e dev

Dependencies for development are specified as the `dev` `extras_require` in `setup.cfg`; they are installed into the virtual environment as follows:

    pip install --editable '.[dev]'

All the source code is in a sub-directory under `src`.


### Tooling

The `dev` `extras_require` included in the template repo installs `black`, `flake8` (plus some plugins), and `mypy` along with default configuration for all of them. You can run all of these (and more!) with:

    tox -e lint
