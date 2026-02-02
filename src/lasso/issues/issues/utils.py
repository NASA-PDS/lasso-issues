"""Utilities."""
import logging
import os

import yaml

_logger = logging.getLogger(__name__)

# Common acronyms/abbreviations that should be uppercase
ACRONYMS = {"pds", "pds4", "api", "doi", "im", "ldd", "mcp", "ui", "wp", "swg", "i&t"}

ISSUE_TYPES = ["bug", "enhancement", "requirement", "theme", "task"]
TOP_PRIORITIES = ["p.must-have", "s.high", "s.critical"]
IGNORE_LABELS = ["wontfix", "duplicate", "invalid"]


def get_label_name(label):
    """Get the name from a label object or dict.

    Args:
        label: Label object (has .name attribute) or dict (has 'name' key)

    Returns:
        str: Label name
    """
    if isinstance(label, dict):
        return label.get('name', '')
    return label.name


def get_labels_list(issue):
    """Get labels as a list from an issue object.

    Handles both regular Issue objects (labels is a method) and
    SearchIssue objects (labels is a property/list).

    Args:
        issue: GitHub issue object (Issue or SearchIssue)

    Returns:
        list: List of label objects or dicts
    """
    return issue.labels if isinstance(issue.labels, list) else issue.labels()


def get_issue_type(issue):
    """Get issue type."""
    for label in get_labels_list(issue):
        label_name = get_label_name(label)
        if label_name in ISSUE_TYPES:
            return label_name


def get_issue_priority(short_issue):
    """Get issue priority."""
    for label in get_labels_list(short_issue):
        label_name = get_label_name(label)
        if "p." in label_name or "s." in label_name:
            return label_name

    return "unknown"


def ignore_issue(labels, ignore_labels=IGNORE_LABELS):
    """Ignore issue."""
    for label in labels:
        label_name = get_label_name(label)
        if label_name in ignore_labels:
            return True

    return False


def get_issues_groupby_type(repo, state="all", start_time=None, end_time=None, ignore_types=None):
    """Get issues grouped by type for a specific repository.

    DEPRECATED: This function iterates through each repository individually.
    Consider using get_org_issues_groupby_type_and_repo() for better performance.

    Args:
        repo: GitHub repository object
        state: Issue state filter ("open", "closed", "all")
        start_time: Start datetime for filtering issues (ISO 8601 format)
        end_time: End datetime for filtering issues (ISO 8601 format)
        ignore_types: List of issue types to ignore

    Returns:
        dict: Issues grouped by type
    """
    from datetime import datetime

    issues = {}
    for t in ISSUE_TYPES:
        print(f"++++++++{t}")
        if ignore_types and t in ignore_types:
            continue

        issues[t] = []
        for issue in repo.issues(state=state, labels=t, direction="asc", since=start_time):
            if not ignore_issue(issue.labels()):
                # Apply end_time filter if specified
                if end_time:
                    # For closed issues, check closed_at; for others check updated_at
                    check_time = issue.closed_at if state == "closed" and issue.closed_at else issue.updated_at
                    if check_time:
                        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        if check_time > end_dt:
                            continue
                issues[t].append(issue)

    return issues


def get_org_issues_groupby_type_and_repo(
    gh, org, repos_filter=None, state="all", start_time=None, end_time=None, ignore_types=None
):
    """Get issues grouped by type and repository using organization-level search.

    This is more efficient than iterating through each repository.

    Args:
        gh: GitHub connection object
        org: Organization name
        repos_filter: List of repository names to include (None = all)
        state: Issue state filter ("open", "closed", "all")
        start_time: Start datetime for filtering issues (ISO 8601 format)
        end_time: End datetime for filtering issues (ISO 8601 format)
        ignore_types: List of issue types to ignore

    Returns:
        dict: Nested dict of {repo_name: {issue_type: [issues]}}
    """
    from datetime import datetime

    all_repos_issues = {}  # repo_name -> {issue_type -> [issues]}

    for issue_type in ISSUE_TYPES:
        if ignore_types and issue_type in ignore_types:
            continue

        print(f"++++++++{issue_type}")

        # Build GitHub search query
        query_parts = [f"org:{org}", f"label:{issue_type}", "is:issue"]

        # Add state filter
        if state != "all":
            query_parts.append(f"is:{state}")

        # Add date filters using GitHub search syntax
        if state == "closed" and start_time and end_time:
            # For closed issues, use closed date range
            start_date = start_time.split("T")[0]  # Extract YYYY-MM-DD
            end_date = end_time.split("T")[0]
            query_parts.append(f"closed:{start_date}..{end_date}")
        elif start_time:
            # For open or all issues, use updated date
            start_date = start_time.split("T")[0]
            query_parts.append(f"updated:>={start_date}")

        query = " ".join(query_parts)
        _logger = __import__('logging').getLogger(__name__)
        _logger.debug(f"Searching with query: {query}")

        # Search for issues
        try:
            for issue in gh.search_issues(query):
                # Get repository name from issue URL (most reliable method)
                # URL format: https://github.com/NASA-PDS/repo-name/issues/123
                try:
                    url_parts = issue.html_url.split('/')
                    repo_name = url_parts[-3]
                except Exception as e:
                    _logger.warning(f"Could not determine repository for issue {issue.number}: {e}")
                    continue

                # Filter by repository if specified
                if repos_filter and repo_name not in repos_filter:
                    continue

                # Skip ignored issues
                if ignore_issue(get_labels_list(issue)):
                    continue

                # Apply end_time filter more precisely (GitHub search only supports date, not datetime)
                if end_time:
                    check_time = issue.closed_at if state == "closed" and issue.closed_at else issue.updated_at
                    if check_time:
                        # Ensure both sides are datetime objects with same timezone awareness
                        if isinstance(check_time, str):
                            check_time = datetime.fromisoformat(check_time.replace("Z", "+00:00"))

                        # Make check_time timezone-naive if it's timezone-aware (for comparison)
                        if hasattr(check_time, 'tzinfo') and check_time.tzinfo is not None:
                            check_time = check_time.replace(tzinfo=None)

                        # Parse end_time as naive datetime
                        end_dt = datetime.fromisoformat(end_time.split('+')[0].split('Z')[0])

                        if check_time > end_dt:
                            continue

                # Initialize repo dict if needed
                if repo_name not in all_repos_issues:
                    all_repos_issues[repo_name] = {t: [] for t in ISSUE_TYPES}

                # Add issue to the appropriate type
                all_repos_issues[repo_name][issue_type].append(issue)

        except Exception as e:
            _logger.error(f"Error searching for issues with query '{query}': {e}")
            import traceback
            _logger.debug(traceback.format_exc())
            continue

    return all_repos_issues


def get_labels(gh_issue):
    """Get Label Names.

    Return list of label names for easier access.
    """
    labels = []
    for label in get_labels_list(gh_issue):
        labels.append(get_label_name(label))

    return labels


def has_label(gh_issue, label_name):
    """Has label."""
    for _label in get_labels_list(gh_issue):
        if get_label_name(_label) == label_name:
            return True
    return False


def is_theme(labels):
    """Check If Issue Is a Release Theme.

    Checks if the issue contains a `theme` label.

    Args:
        labels: List of label names

    Returns:
        bool: True if issue has 'theme' label
    """
    return "theme" in labels


def issue_is_pull_request(issue_number, pull_request):
    """Check If Issue Is A Pull Request.

    Use the input ShortIssue object's number and its associated Pull Request object.
    If the PR object exists and its number is the same as the issue's number, the issue is a pull request.

    https://github3.readthedocs.io/en/latest/api-reference/issues.html#github3.issues.issue.ShortIssue.pull_request
    https://github3.readthedocs.io/en/latest/api-reference/pulls.html#github3.pulls.ShortPullRequest.number

    NOTE: use `number` attribute instead of `id` because all IDs are unique, so they will differ
    """
    if pull_request is not None:
        if issue_number == pull_request.number:
            return True
        else:
            return False
    else:
        return False


def format_component_name(name):
    """Format a component name for display with proper title case and acronym handling.

    Converts hyphenated names to title case while preserving common acronyms.

    Args:
        name: Component name (e.g., 'cloud-platform-engineering', 'pds4-information-model')

    Returns:
        str: Formatted name (e.g., 'Cloud Platform Engineering', 'PDS4 Information Model')
    """
    words = name.replace("-", " ").split()
    formatted_words = []
    for word in words:
        if word.lower() in ACRONYMS:
            formatted_words.append(word.upper())
        else:
            formatted_words.append(word.capitalize())
    return " ".join(formatted_words)


def load_products_config(config_path=None):
    """Load PDS products configuration from YAML file.

    Args:
        config_path: Path to the config file. If None, tries conf/pds-products.yaml
                     relative to the current working directory.

    Returns:
        dict: Products configuration, or None if not found or invalid.
    """
    if config_path is None:
        config_path = os.path.join(os.getcwd(), "conf", "pds-products.yaml")

    if not os.path.exists(config_path):
        _logger.warning("Products config file not found: %s", config_path)
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            if config and "products" in config:
                return config
            else:
                _logger.warning("Invalid products config: missing 'products' key")
                return None
    except Exception as e:
        _logger.warning("Error loading products config: %s", e)
        return None


def build_repo_to_product_map(products_config):
    """Build mapping from repo name to product name and info.

    Args:
        products_config: Products configuration dict from load_products_config()

    Returns:
        dict: {repo_name: (product_name, product_info)} where product_info includes
              description, github_project_name, etc.
    """
    if not products_config or "products" not in products_config:
        return {}

    repo_to_product = {}
    for product_name, product_info in products_config["products"].items():
        # Skip ignored products
        if product_info.get("ignore", False):
            continue

        repositories = product_info.get("repositories", [])
        for repo_name in repositories:
            repo_to_product[repo_name] = (product_name, product_info)

    return repo_to_product
