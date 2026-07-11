"""Issue→PR→Release correlation engine (issue #64).

Links collected issues, PRs, and releases using body-text parsing:
  1. PR body references (closes #N, fixes #N, resolves #N) → link PR to issue
  2. Release body references (#N) → link release to PRs
  3. Transitive: if an issue's closing PR is included in a release, link issue to release

All artifacts are retained even if unlinked. A correlation log is returned
alongside the updated artifact lists.
"""
import logging
import re
from copy import deepcopy
from typing import List

_logger = logging.getLogger(__name__)

# Matches "closes #42", "fixes #7", "resolves #123" (case-insensitive, optional "GH-")
_CLOSES_RE = re.compile(
    r'(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)',
    re.IGNORECASE,
)

# Matches any bare "#123" reference in release body
_PR_REF_RE = re.compile(r'#(\d+)')


def correlate(issues: list, prs: list, releases: list) -> tuple:
    """Cross-reference issues, PRs, and releases.

    Modifies copies of the input lists to populate ``linked_prs``,
    ``linked_releases``, and ``closing_release`` fields.

    Args:
        issues: List of EvidenceIssue dicts
        prs: List of EvidencePR dicts
        releases: List of EvidenceRelease dicts

    Returns:
        tuple: (correlated_issues, correlated_prs, correlated_releases, log)
            where log is a list of human-readable linkage strings.
    """
    corr_issues = deepcopy(issues)
    corr_prs = deepcopy(prs)
    corr_releases = deepcopy(releases)
    log: List[str] = []

    # Build lookup maps
    issue_by_repo_num = {(i['repo'], i['number']): i for i in corr_issues}
    pr_by_repo_num = {(p['repo'], p['number']): p for p in corr_prs}
    # tag → published_at for chronological closing_release selection
    release_published_at = {r['tag']: (r['published_at'] or '') for r in corr_releases}

    # --- Strategy 1: PR body → issue ---
    for pr in corr_prs:
        closing_nums = _extract_closing_issue_numbers(pr.get('body', ''))
        for issue_num in closing_nums:
            issue = issue_by_repo_num.get((pr['repo'], issue_num))
            if issue is None:
                # Try cross-repo (less common, but body may reference another repo)
                _logger.debug("PR %s#%d references issue #%d not in collected set", pr['repo'], pr['number'], issue_num)
                continue

            if pr['number'] not in issue['linked_prs']:
                issue['linked_prs'].append(pr['number'])
                log.append(
                    f"Issue {issue['repo']}#{issue_num} linked to PR #{pr['number']} via PR body reference"
                )

            if issue['number'] not in pr['linked_issues']:
                pr['linked_issues'].append(issue['number'])

    # --- Strategy 2: Release body → PRs ---
    for release in corr_releases:
        body = release.get('body_summary', '')
        candidate_nums = _extract_pr_numbers(body)
        for pr_num in candidate_nums:
            pr = pr_by_repo_num.get((release['repo'], pr_num))
            if pr is None:
                continue

            if pr_num not in release['linked_prs']:
                release['linked_prs'].append(pr_num)
                log.append(
                    f"Release {release['repo']}@{release['tag']} linked to PR #{pr_num} via release body reference"
                )

            if release['tag'] not in pr['linked_releases']:
                pr['linked_releases'].append(release['tag'])

    # --- Strategy 3: Transitive issue→release via closing PR ---
    for pr in corr_prs:
        if not pr['linked_releases']:
            continue
        for issue_num in pr['linked_issues']:
            issue = issue_by_repo_num.get((pr['repo'], issue_num))
            if issue is None:
                continue
            for rel_tag in pr['linked_releases']:
                if rel_tag not in issue['linked_releases']:
                    issue['linked_releases'].append(rel_tag)
                    log.append(
                        f"Issue {issue['repo']}#{issue_num} transitively linked to release {rel_tag} "
                        f"via closing PR #{pr['number']}"
                    )
                # Set closing_release to the chronologically earliest release
                current = issue['closing_release']
                if current is None or (
                    release_published_at.get(rel_tag, '') < release_published_at.get(current, '')
                ):
                    issue['closing_release'] = rel_tag

    _logger.info(
        "Correlation complete: %d link(s) established across %d issues, %d PRs, %d releases",
        len(log), len(corr_issues), len(corr_prs), len(corr_releases),
    )
    return corr_issues, corr_prs, corr_releases, log


def _extract_closing_issue_numbers(body: str) -> list:
    """Extract issue numbers from 'closes #N' / 'fixes #N' / 'resolves #N' patterns."""
    return [int(m) for m in _CLOSES_RE.findall(body or '')]


def _extract_pr_numbers(body: str) -> list:
    """Extract all #N references from a release body."""
    return [int(m) for m in _PR_REF_RE.findall(body or '')]
