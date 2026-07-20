"""PR collector for the PDS EN Activity Collector (issue #62).

Collects merged pull requests for a date range across discovered repos.
"""
import logging

import github3.exceptions
import requests.exceptions

from lasso.issues.activity.collector_issues import _repo_name_from_url
from lasso.issues.activity.schema import ActivityPR
from lasso.issues.activity.schema import normalize_pr

_logger = logging.getLogger(__name__)


def collect_prs(gh, org: str, repos, start_date: str, end_date: str) -> list:
    """Collect and normalize merged pull requests across the given repositories.

    Uses GitHub search to find PRs merged within the date range. Drafts are
    excluded. Full PR data (author, body) is fetched via the REST API for
    each result.

    Args:
        gh: Authenticated github3.py GitHub object
        org: GitHub organization name
        repos: List of repo names to restrict to (None = whole org)
        start_date: ISO 8601 date string (YYYY-MM-DD), inclusive start
        end_date: ISO 8601 date string (YYYY-MM-DD), inclusive end

    Returns:
        list[ActivityPR]: Normalized PR records, sorted by (repo, number).
    """
    repos_set = set(repos) if repos else None
    # Always query the whole org — repo: qualifiers balloon the URL and cause 502s at scale.
    query = f"org:{org} is:pr is:merged merged:{start_date}..{end_date}"
    _logger.debug("PR search query: %s", query)

    prs: list[ActivityPR] = []
    seen_ids: set[int] = set()

    try:
        for search_pr in gh.search_issues(query):
            if search_pr.id in seen_ids:
                continue
            seen_ids.add(search_pr.id)

            repo_name = _repo_name_from_url(search_pr.html_url)
            if not repo_name:
                _logger.warning("Could not determine repo for PR %s", search_pr.html_url)
                continue
            if repos_set is not None and repo_name not in repos_set:
                continue

            pr_number = search_pr.number
            pr_data = _fetch_pr_data(gh, org, repo_name, pr_number)
            if pr_data is None:
                continue

            # Skip draft PRs
            if pr_data.get('draft', False):
                _logger.debug("Skipping draft PR %s/%s#%d", org, repo_name, pr_number)
                continue

            prs.append(normalize_pr(pr_data, repo_name))

    except (github3.exceptions.GitHubException, requests.exceptions.RequestException) as exc:
        _logger.error("Error searching PRs with query '%s': %s", query, exc)
        raise

    prs.sort(key=lambda p: (p['repo'], p['number']))
    _logger.info("Collected %d merged PRs", len(prs))
    return prs


def _fetch_pr_data(gh, org: str, repo_name: str, pr_number: int):
    """Fetch full PR data from the REST API.

    Args:
        gh: Authenticated github3.py GitHub object
        org: Organization name
        repo_name: Repository name
        pr_number: PR number

    Returns:
        dict: PR data dict, or None on error.
    """
    url = f"https://api.github.com/repos/{org}/{repo_name}/pulls/{pr_number}"
    try:
        response = gh.session.get(url)
        if response.status_code == 200:
            return response.json()
        _logger.warning("Could not fetch PR %s/%s#%d: HTTP %d", org, repo_name, pr_number, response.status_code)
        return None
    except (github3.exceptions.GitHubException, requests.exceptions.RequestException) as exc:
        _logger.warning("Exception fetching PR %s/%s#%d: %s", org, repo_name, pr_number, exc)
        return None
