"""Issue collector for the PDS EN Activity Collector (issue #61).

Provides repo discovery and issue collection across NASA-PDS GitHub org.
"""
import logging
import time

import github3.exceptions

from lasso.issues.activity.schema import ActivityIssue
from lasso.issues.activity.schema import normalize_issue
from lasso.issues.github import get_parent_issue
from lasso.issues.issues.utils import get_ignored_repos
from lasso.issues.issues.utils import load_products_config

_logger = logging.getLogger(__name__)

_RETRY_STATUSES = {500, 502, 503, 504}
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 2.0  # seconds; doubles each attempt


def _is_retryable(exc: github3.exceptions.GitHubException) -> bool:
    """Return True for transient server-side errors worth retrying."""
    if isinstance(exc, github3.exceptions.ConnectionError):
        return True
    if isinstance(exc, github3.exceptions.ServerError):
        status = getattr(exc.response, "status_code", None)
        return status in _RETRY_STATUSES
    return False


def _retry_github(action, description: str):
    """Call *action()* with exponential backoff on transient GitHub errors.

    Args:
        action: Zero-argument callable that performs the GitHub operation.
        description: Human-readable label used in log messages.

    Returns:
        Whatever *action()* returns.

    Raises:
        github3.exceptions.GitHubException: Re-raised after all retries
            are exhausted, or immediately for non-retryable errors.
    """
    delay = _RETRY_BASE_DELAY
    for attempt in range(1, _MAX_RETRIES + 2):  # +2: attempt 1…N+1, fail on last
        try:
            return action()
        except github3.exceptions.GitHubException as exc:
            if not _is_retryable(exc):
                raise
            if attempt > _MAX_RETRIES:
                _logger.error("Giving up on %s after %d attempts: %s", description, _MAX_RETRIES, exc)
                raise
            _logger.warning(
                "Transient error on %s (attempt %d/%d): %s — retrying in %.0fs",
                description,
                attempt,
                _MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)
            delay *= 2


def discover_repos(gh, org: str, repos_filter=None, exclude_config_path=None):
    """Discover repositories to collect activity from.

    Args:
        gh: Authenticated github3.py GitHub object
        org: GitHub organization name
        repos_filter: Optional list of repo names to restrict to. If None, all org repos are used.
        exclude_config_path: Optional path to a pds-products.yaml-style YAML file.
            Repos under products marked ``ignore: true`` are excluded.

    Returns:
        list[str]: Sorted list of repository names to collect from.
    """
    ignored = set()
    if exclude_config_path:
        config = load_products_config(config_path=exclude_config_path)
        if config:
            ignored = get_ignored_repos(config)
            if ignored:
                _logger.info("Excluding %d repositories from exclude config", len(ignored))

    if repos_filter:
        repos = [r for r in repos_filter if r not in ignored]
        _logger.info("Using %d explicitly specified repos (after exclusion)", len(repos))
        return sorted(repos)

    _logger.info("Discovering all repos in org %s", org)
    repo_names = []

    def _list_repos():
        names = []
        organization = gh.organization(org)
        for repo in organization.repositories():
            if repo.name not in ignored:
                names.append(repo.name)
        return names

    try:
        repo_names = _retry_github(_list_repos, f"list repos for {org}")
    except github3.exceptions.GitHubException as exc:
        _logger.error("Failed to list repositories for org %s: %s", org, exc)
        raise

    _logger.info("Discovered %d repositories in %s", len(repo_names), org)
    return sorted(repo_names)


def collect_issues(gh, org: str, repos, start_date: str, end_date: str) -> list:
    """Collect and normalize issues closed within the date range.

    Searches for closed issues using GitHub's search API (``is:closed
    closed:{start}..{end}``). Note: GitHub's search API caps results at
    1000 per query. For orgs with very high issue volume, narrow the date
    range or restrict to specific repos via ``repos`` to stay under the limit.
    A warning is logged when the result count reaches the cap.

    Args:
        gh: Authenticated github3.py GitHub object
        org: GitHub organization name
        repos: List of repo names to restrict to (None = whole org)
        start_date: ISO 8601 date string (YYYY-MM-DD), inclusive start
        end_date: ISO 8601 date string (YYYY-MM-DD), inclusive end

    Returns:
        list[ActivityIssue]: Normalized issue records, sorted by (repo, number).
    """
    repos_set = set(repos) if repos else None

    # Always query the whole org — repo: qualifiers balloon the URL and cause 502s at scale.
    query = f"org:{org} is:issue is:closed closed:{start_date}..{end_date}"
    _logger.debug("Issue search query: %s", query)

    def _search_all():
        results = []
        seen: set[int] = set()
        for search_issue in gh.search_issues(query):
            if search_issue.id in seen:
                continue
            seen.add(search_issue.id)
            repo_name = _repo_name_from_url(search_issue.html_url)
            if not repo_name:
                _logger.warning("Could not determine repo for issue %s", search_issue.html_url)
                continue
            if repos_set is not None and repo_name not in repos_set:
                continue
            parent = get_parent_issue(gh, org, repo_name, search_issue.number)
            results.append(normalize_issue(search_issue, repo_name, parent=parent))
        return results

    try:
        issues: list[ActivityIssue] = _retry_github(_search_all, f"search issues ({query!r})")
    except github3.exceptions.GitHubException as exc:
        _logger.error("Error searching issues with query '%s': %s", query, exc)
        raise

    issues.sort(key=lambda i: (i['repo'], i['number']))
    if len(issues) >= 1000:
        _logger.warning(
            "Collected %d issues — GitHub search caps results at 1000. "
            "Results may be incomplete. Narrow the date range or use --repos to limit scope.",
            len(issues),
        )
    _logger.info("Collected %d closed issues", len(issues))
    return issues


def _repo_name_from_url(html_url: str) -> str:
    """Extract repo name from a GitHub issue/PR URL.

    URL format: https://github.com/ORG/REPO/issues/N
    """
    try:
        parts = html_url.rstrip('/').split('/')
        return parts[-3]
    except (IndexError, AttributeError):
        return ''
