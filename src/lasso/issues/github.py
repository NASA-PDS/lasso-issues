"""GitHub stuff."""
import logging
import os
import sys

from github3 import login

_logger = logging.getLogger(__name__)


class GithubConnection:
    """A connection to GitHub."""

    gh = None

    @classmethod
    def get_connection(cls, token=None):
        """Get the connection."""
        if not cls.gh:
            token = token or os.environ.get("GITHUB_TOKEN")
            if not token:
                _logger.error("Github token must be provided or set as environment variable (GITHUB_TOKEN).")
                sys.exit(1)
            cls.gh = login(token=token)
        return cls.gh


def get_sub_issues(gh, owner, repo_name, issue_number):
    """Get sub-issues for an issue using GitHub's native sub-issues API.

    Args:
        gh: GitHub connection object from github3.py
        owner: Repository owner/organization
        repo_name: Repository name
        issue_number: Issue number

    Returns:
        list: List of sub-issue dicts, or empty list if none/error
    """
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{issue_number}/sub_issues"
    try:
        response = gh.session.get(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            _logger.debug(f"No sub-issues found for {owner}/{repo_name}#{issue_number}")
            return []
        else:
            _logger.warning(f"Error fetching sub-issues for {owner}/{repo_name}#{issue_number}: {response.status_code}")
            return []
    except Exception as e:
        _logger.debug(f"Exception fetching sub-issues for {owner}/{repo_name}#{issue_number}: {e}")
        return []


def get_parent_issue(gh, owner, repo_name, issue_number):
    """Get the parent issue of a sub-issue using GitHub's native API.

    Args:
        gh: GitHub connection object from github3.py
        owner: Repository owner/organization
        repo_name: Repository name
        issue_number: Issue number

    Returns:
        dict: Parent issue data, or None if no parent/error
    """
    url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{issue_number}/parent"
    try:
        response = gh.session.get(url)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            _logger.debug(f"No parent issue found for {owner}/{repo_name}#{issue_number}")
            return None
        else:
            _logger.warning(f"Error fetching parent for {owner}/{repo_name}#{issue_number}: {response.status_code}")
            return None
    except Exception as e:
        _logger.debug(f"Exception fetching parent issue for {owner}/{repo_name}#{issue_number}: {e}")
        return None
