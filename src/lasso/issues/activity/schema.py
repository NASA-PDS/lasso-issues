"""Canonical activity schema for the PDS EN Activity Collector.

TypedDicts define the structure of activity.json. normalize_* functions
convert github3.py objects into these dicts.
"""
from typing import List
from typing import Optional
from typing import TypedDict


class ActivityIssue(TypedDict):
    """A normalized GitHub issue record."""

    id: int
    repo: str
    number: int
    title: str
    state: str
    labels: List[str]
    opened_at: Optional[str]
    closed_at: Optional[str]
    html_url: str
    linked_prs: List[int]
    linked_releases: List[str]
    closing_release: Optional[str]


class ActivityPR(TypedDict):
    """A normalized merged pull request record."""

    id: int
    repo: str
    number: int
    title: str
    state: str
    merged_at: Optional[str]
    author: Optional[str]
    html_url: str
    body: str
    linked_issues: List[int]
    linked_releases: List[str]


class ActivityRelease(TypedDict):
    """A normalized GitHub Release or tag record."""

    id: Optional[int]
    repo: str
    tag: str
    name: str
    published_at: Optional[str]
    body_summary: str
    linked_prs: List[int]
    is_prerelease: bool
    html_url: str


class ActivityMetadata(TypedDict):
    """Metadata block describing the collection run."""

    org: str
    start_date: str
    end_date: str
    generated_at: str
    tool_version: str
    repo_count: int


class ActivityDocument(TypedDict):
    """Top-level activity.json structure."""

    metadata: ActivityMetadata
    issues: List[ActivityIssue]
    pull_requests: List[ActivityPR]
    releases: List[ActivityRelease]
    correlation_log: List[str]


def _isoformat(dt) -> Optional[str]:
    """Convert a datetime (or None) to ISO 8601 string."""
    if dt is None:
        return None
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)


def normalize_issue(gh_issue, repo_name: str) -> ActivityIssue:
    """Normalize a github3.py issue object to ActivityIssue.

    Args:
        gh_issue: github3.py Issue or SearchIssue object
        repo_name: repository name (e.g. 'lasso-issues')

    Returns:
        ActivityIssue dict
    """
    labels = []
    raw_labels = gh_issue.labels if isinstance(gh_issue.labels, list) else list(gh_issue.labels())
    for lbl in raw_labels:
        name = lbl.get('name') if isinstance(lbl, dict) else lbl.name
        if name:
            labels.append(name)

    return ActivityIssue(
        id=gh_issue.id,
        repo=repo_name,
        number=gh_issue.number,
        title=gh_issue.title,
        state=gh_issue.state,
        labels=labels,
        opened_at=_isoformat(gh_issue.created_at),
        closed_at=_isoformat(gh_issue.closed_at),
        html_url=gh_issue.html_url,
        linked_prs=[],
        linked_releases=[],
        closing_release=None,
    )


def normalize_pr(gh_pr_data: dict, repo_name: str) -> ActivityPR:
    """Normalize a PR data dict (from GitHub REST API) to ActivityPR.

    Args:
        gh_pr_data: dict from GET /repos/{owner}/{repo}/pulls/{number}
        repo_name: repository name

    Returns:
        ActivityPR dict
    """
    author = None
    if gh_pr_data.get('user'):
        author = gh_pr_data['user'].get('login')

    return ActivityPR(
        id=gh_pr_data['id'],
        repo=repo_name,
        number=gh_pr_data['number'],
        title=gh_pr_data.get('title', ''),
        state=gh_pr_data.get('state', ''),
        merged_at=gh_pr_data.get('merged_at'),
        author=author,
        html_url=gh_pr_data.get('html_url', ''),
        body=gh_pr_data.get('body') or '',
        linked_issues=[],
        linked_releases=[],
    )


def normalize_release(gh_release_data: dict, repo_name: str, *, is_tag_fallback: bool = False) -> ActivityRelease:
    """Normalize a release data dict (from GitHub REST API) to ActivityRelease.

    Args:
        gh_release_data: dict from GET /repos/{owner}/{repo}/releases or /tags
        repo_name: repository name
        is_tag_fallback: True when this record came from the tags API (no formal release)

    Returns:
        ActivityRelease dict
    """
    if is_tag_fallback:
        tag = gh_release_data.get('name', '')
        return ActivityRelease(
            id=None,
            repo=repo_name,
            tag=tag,
            name=tag,
            published_at=gh_release_data.get('commit', {}).get('committed_date'),
            body_summary='',
            linked_prs=[],
            is_prerelease=False,
            html_url=gh_release_data.get('url', ''),
        )

    body = gh_release_data.get('body') or ''
    body_summary = body[:500].strip()

    return ActivityRelease(
        id=gh_release_data.get('id'),
        repo=repo_name,
        tag=gh_release_data.get('tag_name', ''),
        name=gh_release_data.get('name') or gh_release_data.get('tag_name', ''),
        published_at=gh_release_data.get('published_at'),
        body_summary=body_summary,
        linked_prs=[],
        is_prerelease=gh_release_data.get('prerelease', False),
        html_url=gh_release_data.get('html_url', ''),
    )
