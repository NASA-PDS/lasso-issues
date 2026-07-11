"""Release/Tag collector for the PDS EN Evidence Collector (issue #63).

Collects GitHub Releases (with tag fallback) for a date range.
"""
import logging
from datetime import datetime
from datetime import timezone

import github3.exceptions
import requests.exceptions

from lasso.issues.evidence.schema import EvidenceRelease
from lasso.issues.evidence.schema import normalize_release

_logger = logging.getLogger(__name__)


def collect_releases(gh, org: str, repos, start_date: str, end_date: str) -> list:
    """Collect and normalize releases across the given repositories.

    For each repo, tries GitHub Releases first. Where no releases exist,
    falls back to collecting version tags. Only records published within
    [start_date, end_date] are included. Pre-releases are flagged but kept.

    Args:
        gh: Authenticated github3.py GitHub object
        org: GitHub organization name
        repos: List of repo names to collect from
        start_date: ISO 8601 date string (YYYY-MM-DD), inclusive start
        end_date: ISO 8601 date string (YYYY-MM-DD), inclusive end

    Returns:
        list[EvidenceRelease]: Normalized release records, sorted by (repo, published_at).
    """
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date, end_of_day=True)

    releases: list[EvidenceRelease] = []

    for repo_name in sorted(repos):
        try:
            repo_releases = _collect_repo_releases(gh, org, repo_name, start_dt, end_dt)
            releases.extend(repo_releases)
        except (github3.exceptions.GitHubException, requests.exceptions.RequestException) as exc:
            _logger.warning("Skipping releases for %s/%s: %s", org, repo_name, exc)

    releases.sort(key=lambda r: (r['repo'], r['published_at'] or ''))
    _logger.info("Collected %d releases/tags across %d repos", len(releases), len(repos))
    return releases


def _collect_repo_releases(gh, org: str, repo_name: str, start_dt: datetime, end_dt: datetime) -> list:
    """Collect releases for a single repository.

    Tries formal releases first; falls back to tags if none are found.
    Paginates through all pages of the releases endpoint.
    """
    url = f"https://api.github.com/repos/{org}/{repo_name}/releases"
    try:
        all_releases = _paginate(gh, url)
        if all_releases is None:
            return _collect_repo_tags(gh, org, repo_name, start_dt, end_dt)
        if not all_releases:
            return _collect_repo_tags(gh, org, repo_name, start_dt, end_dt)

        results = []
        for rel_data in all_releases:
            published_at = rel_data.get('published_at')
            if not published_at:
                continue
            pub_dt = _parse_iso(published_at)
            if pub_dt and start_dt <= pub_dt <= end_dt:
                results.append(normalize_release(rel_data, repo_name))

        return results

    except (github3.exceptions.GitHubException, requests.exceptions.RequestException) as exc:
        _logger.warning("Exception fetching releases for %s/%s: %s", org, repo_name, exc)
        return []


def _collect_repo_tags(gh, org: str, repo_name: str, start_dt: datetime, end_dt: datetime) -> list:
    """Fallback: collect version tags when a repo has no formal releases."""
    url = f"https://api.github.com/repos/{org}/{repo_name}/tags"
    try:
        tags = _paginate(gh, url)
        if tags is None:
            return []
        results = []
        for tag_data in tags:
            # Tags don't have a published_at — fetch the commit to get the date
            commit_url = tag_data.get('commit', {}).get('url', '')
            committed_at = _fetch_commit_date(gh, commit_url)
            if not committed_at:
                continue
            commit_dt = _parse_iso(committed_at)
            if commit_dt and start_dt <= commit_dt <= end_dt:
                tag_data_with_date = dict(tag_data)
                tag_data_with_date.setdefault('commit', {})['committed_date'] = committed_at
                results.append(normalize_release(tag_data_with_date, repo_name, is_tag_fallback=True))

        return results

    except (github3.exceptions.GitHubException, requests.exceptions.RequestException) as exc:
        _logger.warning("Exception fetching tags for %s/%s: %s", org, repo_name, exc)
        return []


def _paginate(gh, url: str) -> list:
    """Fetch all pages from a GitHub list endpoint.

    Args:
        gh: Authenticated github3.py GitHub object
        url: Endpoint URL (without pagination params)

    Returns:
        list: All items across all pages, or None if the initial request fails.

    Raises:
        requests.exceptions.RequestException: on network failure
        github3.exceptions.GitHubException: on GitHub API error
    """
    results = []
    page = 1
    while True:
        response = gh.session.get(url, params={"per_page": 100, "page": page})
        if response.status_code != 200:
            if page == 1:
                return None
            break
        page_data = response.json()
        if not page_data:
            break
        results.extend(page_data)
        # Stop if fewer than a full page returned (last page)
        if len(page_data) < 100:
            break
        page += 1
    return results


def _fetch_commit_date(gh, commit_url: str) -> str:
    """Fetch the committed date for a commit URL."""
    if not commit_url:
        return ''
    try:
        resp = gh.session.get(commit_url)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('commit', {}).get('committer', {}).get('date', '')
        return ''
    except (github3.exceptions.GitHubException, requests.exceptions.RequestException):
        return ''


def _parse_date(date_str: str, end_of_day: bool = False) -> datetime:
    """Parse a YYYY-MM-DD date string into a UTC-aware datetime."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=timezone.utc)


def _parse_iso(iso_str: str) -> datetime:
    """Parse an ISO 8601 timestamp to a UTC-aware datetime, or None on failure."""
    try:
        normalized = iso_str.replace('Z', '+00:00')
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
