#!/usr/bin/env python3
"""Create release theme issues from a CSV schedule file.

This tool reads a CSV file containing release theme data and creates GitHub issues
for each theme in the specified repositories. It handles:
- Creating issues with descriptions and checklists
- Applying build labels (e.g., B17, B18)
- Adding issues to GitHub Projects
- Setting project metadata (Product, Start Date, End Date)
"""
import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from lasso.issues.argparse import add_standard_arguments

logger = logging.getLogger(__name__)


def parse_date(date_str):
    """Parse date from YYYY-MM-DD ISO format and validate.

    Args:
        date_str: Date string in YYYY-MM-DD format (e.g., '2025-09-05')

    Returns:
        str: ISO formatted date string (YYYY-MM-DD)
    """
    try:
        # Parse YYYY-MM-DD format and validate
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Failed to parse date '{date_str}': {e}")
        raise


def create_issue_body(description, checklist=None):
    """Create the issue body in markdown format.

    Args:
        description: Main description text
        checklist: Optional semicolon-delimited checklist items

    Returns:
        str: Formatted markdown issue body
    """
    body = f"""## Are you sure this is not a new requirement or bug?
Yes

## 💡 Description
{description}
"""

    if checklist and isinstance(checklist, str) and checklist.strip():
        body += "\n## ✅ Checklist\n"
        items = [item.strip() for item in checklist.split(";") if item.strip()]
        for item in items:
            body += f"- [ ] {item}\n"

    return body


def run_gh_command(args, input_data=None, check=True):
    """Run a GitHub CLI command.

    Args:
        args: List of command arguments
        input_data: Optional stdin input
        check: Whether to check return code

    Returns:
        subprocess.CompletedProcess: Command result
    """
    logger.debug(f"Running gh command: {' '.join(args)}")
    result = subprocess.run(
        ["gh"] + args,
        input=input_data,
        text=True,
        capture_output=True,
        check=check
    )
    if result.returncode != 0:
        logger.error(f"Command failed: {result.stderr}")
    return result


def ensure_label_exists(repo, label_name, dry_run=False):
    """Ensure a label exists in the repository.

    Args:
        repo: Repository name (org/repo format)
        label_name: Label to create
        dry_run: If True, don't actually create the label

    Returns:
        bool: True if label exists or was created
    """
    # Check if label exists
    result = run_gh_command(
        ["label", "list", "--repo", repo, "--limit", "1000"],
        check=False
    )

    if result.returncode == 0 and label_name in result.stdout:
        logger.debug(f"Label '{label_name}' already exists in {repo}")
        return True

    # Create label with default color
    logger.info(f"Creating label '{label_name}' in {repo}")
    if not dry_run:
        result = run_gh_command(
            ["label", "create", label_name, "--repo", repo, "--color", "0366d6"],
            check=False
        )
        return result.returncode == 0
    else:
        logger.info(f"[DRY RUN] Would create label '{label_name}' in {repo}")
        return True


def check_issue_exists(repo, title):
    """Check if an issue with the given title already exists in the repository.

    Args:
        repo: Repository name (org/repo format)
        title: Issue title to search for

    Returns:
        bool: True if issue exists, False otherwise
    """
    logger.debug(f"Checking if issue '{title}' exists in {repo}")

    # Search for issues with this exact title
    result = run_gh_command(
        ["issue", "list", "--repo", repo, "--search", title, "--limit", "100", "--json", "title"],
        check=False
    )

    if result.returncode != 0:
        logger.warning(f"Failed to search for existing issues in {repo}: {result.stderr}")
        return False

    import json
    try:
        issues = json.loads(result.stdout)
        for issue in issues:
            if issue.get("title") == title:
                logger.info(f"Issue with title '{title}' already exists in {repo}")
                return True
        return False
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse issue list: {e}")
        return False


def find_project_id(project_name):
    """Find GitHub Project ID by project name.

    Args:
        project_name: Project name (e.g., 'B17')

    Returns:
        tuple: (project_number, project_node_id) or (None, None) if not found
    """
    logger.debug(f"Searching for project '{project_name}'")

    # List projects for NASA-PDS organization
    result = run_gh_command(
        ["project", "list", "--owner", "NASA-PDS", "--format", "json"],
        check=False
    )

    if result.returncode != 0:
        logger.error(f"Failed to list projects: {result.stderr}")
        return None, None

    import json
    try:
        projects = json.loads(result.stdout)
        for project in projects.get("projects", []):
            if project.get("title") == project_name:
                project_number = str(project["number"])
                project_node_id = project.get("id")
                logger.info(f"Found project '{project_name}' with ID {project_number}")
                return project_number, project_node_id

        logger.warning(f"Project '{project_name}' not found")
        return None, None
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse project list: {e}")
        return None, None


def set_project_field(project_node_id, item_id, field_name, field_value):
    """Set a custom field value on a project item using GraphQL.

    Args:
        project_node_id: Project node ID (GraphQL ID)
        item_id: Project item node ID
        field_name: Field name (e.g., "Product", "Start Date")
        field_value: Value to set

    Returns:
        bool: True if successful, False otherwise
    """
    import json

    # First, get the project fields to find the field ID
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 20) {
            nodes {
              ... on ProjectV2Field {
                id
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                id
                name
                dataType
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """

    result = run_gh_command(
        ["api", "graphql", "-f", f"query={query}", "-f", f"projectId={project_node_id}"],
        check=False
    )

    if result.returncode != 0:
        logger.warning(f"Failed to get project fields: {result.stderr}")
        return False

    try:
        data = json.loads(result.stdout)
        fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])

        field_id = None
        option_id = None
        data_type = None

        for field in fields:
            if field.get("name") == field_name:
                field_id = field.get("id")
                data_type = field.get("dataType")
                logger.debug(f"Found field '{field_name}': id={field_id}, dataType={data_type}")
                # If it's a single select field, find the matching option
                if "options" in field:
                    for option in field.get("options", []):
                        if option.get("name") == field_value:
                            option_id = option.get("id")
                            logger.debug(f"Found option '{field_value}': id={option_id}")
                            break
                break

        if not field_id:
            logger.debug(f"Field '{field_name}' not found in project")
            return False

        # Set the field value using GraphQL mutation
        if option_id:
            # For single select fields
            mutation = """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: {singleSelectOptionId: $optionId}
              }) {
                projectV2Item {
                  id
                }
              }
            }
            """
            result = run_gh_command(
                [
                    "api", "graphql",
                    "-f", f"query={mutation}",
                    "-f", f"projectId={project_node_id}",
                    "-f", f"itemId={item_id}",
                    "-f", f"fieldId={field_id}",
                    "-f", f"optionId={option_id}"
                ],
                check=False
            )
        elif data_type == "DATE":
            # For date fields - use Date type instead of String
            logger.debug(f"Setting DATE field '{field_name}' to '{field_value}'")
            mutation = """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: Date!) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: {date: $value}
              }) {
                projectV2Item {
                  id
                }
              }
            }
            """
            logger.debug(f"GraphQL mutation params: projectId={project_node_id}, "
                         + f"itemId={item_id}, fieldId={field_id}, "
                         + f"value={field_value}")
            result = run_gh_command(
                [
                    "api", "graphql",
                    "-f", f"query={mutation}",
                    "-f", f"projectId={project_node_id}",
                    "-f", f"itemId={item_id}",
                    "-f", f"fieldId={field_id}",
                    "-f", f"value={field_value}"
                ],
                check=False
            )
            logger.debug(f"GraphQL response code: {result.returncode}, "
                         + f"stdout: {result.stdout[:200]}, "
                         + f"stderr: {result.stderr[:200]}")
        else:
            # For text fields
            mutation = """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: String!) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: {text: $value}
              }) {
                projectV2Item {
                  id
                }
              }
            }
            """
            result = run_gh_command(
                [
                    "api", "graphql",
                    "-f", f"query={mutation}",
                    "-f", f"projectId={project_node_id}",
                    "-f", f"itemId={item_id}",
                    "-f", f"fieldId={field_id}",
                    "-f", f"value={field_value}"
                ],
                check=False
            )

        if result.returncode == 0:
            logger.debug(f"Set field '{field_name}' to '{field_value}'")
            return True
        else:
            logger.warning(f"Failed to set field '{field_name}': {result.stderr}")
            return False

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse field data: {e}")
        return False


def get_project_item_id(issue_url, project_node_id):
    """Get the project item ID for an issue in a project.

    Args:
        issue_url: GitHub issue URL
        project_node_id: Project node ID

    Returns:
        str: Project item ID or None if not found
    """
    # Extract owner, repo, and issue number from URL
    # Format: https://github.com/NASA-PDS/repo-name/issues/123
    parts = issue_url.rstrip("/").split("/")
    issue_number = int(parts[-1])
    repo_name = parts[-3]
    owner = parts[-4]

    query = """
    query($owner: String!, $repo: String!, $issueNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        issue(number: $issueNumber) {
          projectItems(first: 10) {
            nodes {
              id
              project {
                id
              }
            }
          }
        }
      }
    }
    """

    result = run_gh_command(
        [
            "api", "graphql",
            "-f", f"query={query}",
            "-f", f"owner={owner}",
            "-f", f"repo={repo_name}",
            "-F", f"issueNumber={issue_number}"  # Use -F for integer type
        ],
        check=False
    )

    if result.returncode != 0:
        logger.warning(f"Failed to get project item ID: {result.stderr}")
        return None

    try:
        data = json.loads(result.stdout)
        items = data.get("data", {}).get("repository", {}).get("issue", {}).get("projectItems", {}).get("nodes", [])

        for item in items:
            if item.get("project", {}).get("id") == project_node_id:
                return item.get("id")

        logger.debug("Project item not found")
        return None

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse project item data: {e}")
        return None


def create_release_theme(row, build_number, dry_run=False):
    """Create a release theme issue from CSV row data.

    Args:
        row: pandas Series containing theme data
        build_number: Build number (e.g., 17 for B17)
        dry_run: If True, don't actually create issues

    Returns:
        str: Issue URL if created, None if skipped or failed
    """
    base_title = row["Title"]
    repo = row["Repo"]
    start_date = row["Start Date"]
    end_date = row["End Date"]
    description = row.get("Description", "")
    checklist = row.get("Checklist", "")
    product = row.get("GitHub Project Product", "")

    # Build label and full title with build prefix
    build_label = f"B{build_number}"
    title = f"{build_label} {base_title}"

    logger.info(f"Processing release theme: {title} in {repo}")

    # Check if issue already exists
    if not dry_run and check_issue_exists(repo, title):
        logger.info(f"Skipping '{title}' - issue already exists in {repo}")
        return "SKIPPED"

    # Parse dates
    try:
        start_date_iso = parse_date(start_date)
        end_date_iso = parse_date(end_date)
    except ValueError:
        logger.error(f"Skipping '{title}' due to invalid dates")
        return None

    # Ensure build label exists
    if not ensure_label_exists(repo, build_label, dry_run):
        logger.warning(f"Failed to ensure label '{build_label}' exists in {repo}")

    # Create issue body
    body = create_issue_body(description, checklist)

    # Build labels list
    labels = ["theme", "Epic", "i&t.skip", build_label]

    if dry_run:
        logger.info(f"[DRY RUN] Would create issue in {repo}:")
        logger.info(f"  Title: {title}")
        logger.info(f"  Labels: {','.join(labels)}")
        logger.info(f"  Build Project: {build_label}")
        if product:
            logger.info(f"  Product: {product}")
        logger.info(f"  Start Date: {start_date_iso}")
        logger.info(f"  End Date: {end_date_iso}")
        return f"https://github.com/{repo}/issues/DRY-RUN"

    # Create the issue (without project assignment to avoid failures)
    result = run_gh_command(
        [
            "issue", "create",
            "--repo", repo,
            "--title", title,
            "--body", body,
            "--label", ",".join(labels),
        ],
        check=False
    )

    if result.returncode != 0:
        logger.error(f"Failed to create issue '{title}' in {repo}")
        return None

    # Extract issue URL from output
    issue_url = result.stdout.strip()
    logger.info(f"Created issue: {issue_url}")

    # Add to build-specific project
    project_number, project_node_id = find_project_id(build_label)
    if project_number and project_node_id:
        result = run_gh_command(
            [
                "project", "item-add", project_number,
                "--owner", "NASA-PDS",
                "--url", issue_url
            ],
            check=False
        )
        if result.returncode == 0:
            logger.info(f"Added issue to project {build_label}")

            # Get the project item ID to set custom fields
            item_id = get_project_item_id(issue_url, project_node_id)
            if item_id:
                # Set product field if specified
                if product:
                    if set_project_field(project_node_id, item_id, "Product", product):
                        logger.info(f"Set Product field to '{product}'")
                    else:
                        logger.debug(f"Could not set Product field to '{product}'")

                # Set start date field (note: lowercase 'd' in 'date')
                if set_project_field(project_node_id, item_id, "Start date", start_date_iso):
                    logger.info(f"Set Start date to {start_date_iso}")
                else:
                    logger.debug(f"Could not set Start date to {start_date_iso}")

                # Set end date field (note: lowercase 'd' in 'date')
                if set_project_field(project_node_id, item_id, "End date", end_date_iso):
                    logger.info(f"Set End date to {end_date_iso}")
                else:
                    logger.debug(f"Could not set End date to {end_date_iso}")
            else:
                logger.warning("Could not get project item ID to set custom fields")
        else:
            logger.error(f"Failed to add issue to project {build_label}")
    else:
        logger.warning(f"Build project {build_label} not found, skipping project assignment")

    return issue_url


def main():
    """Main entry point for create-release-themes CLI."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__
    )

    add_standard_arguments(parser)

    parser.add_argument(
        "--csv-file",
        type=Path,
        required=True,
        help="Path to CSV file containing release theme schedule"
    )

    parser.add_argument(
        "--build-number",
        type=int,
        required=True,
        help="Build number (e.g., 17 for B17)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be created without actually creating issues"
    )

    parser.add_argument(
        "--token",
        help="GitHub token (optional, uses gh CLI authentication by default)"
    )

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format="%(levelname)s: %(message)s")

    # Check if CSV file exists
    if not args.csv_file.exists():
        logger.error(f"CSV file not found: {args.csv_file}")
        sys.exit(1)

    # Check if gh CLI is available
    result = subprocess.run(["gh", "--version"], capture_output=True, check=False)
    if result.returncode != 0:
        logger.error("GitHub CLI (gh) is not installed or not in PATH")
        logger.error("Install it from: https://cli.github.com/")
        sys.exit(1)

    # Read CSV file
    logger.info(f"Reading CSV file: {args.csv_file}")
    try:
        df = pd.read_csv(args.csv_file, encoding="utf-8-sig")  # Handle BOM if present
    except Exception as e:
        logger.error(f"Failed to read CSV file: {e}")
        sys.exit(1)

    # Filter out empty rows
    df = df.dropna(subset=["Title", "Repo"])

    logger.info(f"Found {len(df)} release themes to create")

    if args.dry_run:
        logger.info("=== DRY RUN MODE - No issues will be created ===")

    # Create issues
    created_issues = []
    skipped_issues = []
    failed_issues = []

    # Build label for display
    build_label = f"B{args.build_number}"

    for _, row in df.iterrows():
        try:
            result = create_release_theme(row, args.build_number, args.dry_run)
            full_title = f"{build_label} {row['Title']}"
            if result and result != "SKIPPED":
                created_issues.append((full_title, result))
            elif result == "SKIPPED":
                skipped_issues.append(full_title)
            else:
                failed_issues.append(full_title)
        except Exception as e:
            full_title = f"{build_label} {row['Title']}"
            logger.error(f"Error creating issue for '{full_title}': {e}")
            failed_issues.append(full_title)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info(f"Summary: {len(created_issues)} created, {len(skipped_issues)} skipped, {len(failed_issues)} failed")
    logger.info("=" * 60)

    if created_issues:
        logger.info("\nCreated issues:")
        for title, url in created_issues:
            logger.info(f"  ✓ {title}")
            logger.info(f"    {url}")

    if skipped_issues:
        logger.info("\nSkipped issues (already exist):")
        for title in skipped_issues:
            logger.info(f"  ⊙ {title}")

    if failed_issues:
        logger.info("\nFailed issues:")
        for title in failed_issues:
            logger.info(f"  ✗ {title}")

    sys.exit(0 if not failed_issues else 1)


if __name__ == "__main__":
    main()
