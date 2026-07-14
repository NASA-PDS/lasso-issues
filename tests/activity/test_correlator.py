"""Unit tests for correlator.py (issue #64)."""
import unittest

from lasso.issues.activity.correlator import _extract_closing_issue_numbers
from lasso.issues.activity.correlator import _extract_pr_numbers
from lasso.issues.activity.correlator import correlate


def _issue(number, repo="testrepo"):
    return {
        "id": 1000 + number, "repo": repo, "number": number,
        "title": f"Issue {number}", "state": "closed",
        "labels": [], "opened_at": "2026-06-01T00:00:00+00:00",
        "closed_at": "2026-06-10T00:00:00+00:00",
        "html_url": f"https://github.com/NASA-PDS/{repo}/issues/{number}",
        "linked_prs": [], "linked_releases": [], "closing_release": None,
    }


def _pr(number, repo="testrepo", body=""):
    return {
        "id": 2000 + number, "repo": repo, "number": number,
        "title": f"PR {number}", "state": "closed",
        "merged_at": "2026-06-15T00:00:00Z", "author": "dev",
        "html_url": f"https://github.com/NASA-PDS/{repo}/pull/{number}",
        "body": body,
        "linked_issues": [], "linked_releases": [],
    }


def _release(tag, repo="testrepo", body_summary=""):
    return {
        "id": 3000, "repo": repo, "tag": tag,
        "name": tag, "published_at": "2026-07-01T00:00:00Z",
        "body_summary": body_summary,
        "linked_prs": [], "is_prerelease": False,
        "html_url": f"https://github.com/NASA-PDS/{repo}/releases/tag/{tag}",
    }


class TestExtractClosingNumbers(unittest.TestCase):
    """Tests for _extract_closing_issue_numbers."""

    def test_closes(self):
        self.assertEqual(_extract_closing_issue_numbers("closes #42"), [42])

    def test_fixes(self):
        self.assertEqual(_extract_closing_issue_numbers("fixes #7"), [7])

    def test_resolves(self):
        self.assertEqual(_extract_closing_issue_numbers("resolves #100"), [100])

    def test_case_insensitive(self):
        self.assertEqual(_extract_closing_issue_numbers("Closes #3"), [3])

    def test_multiple_in_body(self):
        body = "This closes #1 and also fixes #2"
        result = _extract_closing_issue_numbers(body)
        self.assertIn(1, result)
        self.assertIn(2, result)

    def test_no_match_returns_empty(self):
        self.assertEqual(_extract_closing_issue_numbers("see #5 for context"), [])

    def test_empty_body(self):
        self.assertEqual(_extract_closing_issue_numbers(""), [])

    def test_none_body(self):
        self.assertEqual(_extract_closing_issue_numbers(None), [])


class TestExtractPrNumbers(unittest.TestCase):
    """Tests for _extract_pr_numbers."""

    def test_single_reference(self):
        self.assertEqual(_extract_pr_numbers("Merged #15"), [15])

    def test_multiple_references(self):
        result = _extract_pr_numbers("Includes #3 and #8")
        self.assertIn(3, result)
        self.assertIn(8, result)

    def test_empty_body(self):
        self.assertEqual(_extract_pr_numbers(""), [])


class TestCorrelateStrategy1(unittest.TestCase):
    """Strategy 1: PR body closes #N → link PR to issue."""

    def test_pr_linked_to_issue_via_closes(self):
        issues = [_issue(5)]
        prs = [_pr(10, body="closes #5")]
        corr_issues, corr_prs, _, log = correlate(issues, prs, [])

        self.assertIn(10, corr_issues[0]['linked_prs'])
        self.assertIn(5, corr_prs[0]['linked_issues'])
        self.assertTrue(any("Issue testrepo#5" in entry for entry in log))

    def test_pr_referencing_missing_issue_silently_skipped(self):
        issues = []
        prs = [_pr(10, body="closes #99")]
        corr_issues, corr_prs, _, log = correlate(issues, prs, [])
        # No crash, no log entry for missing issue
        self.assertEqual(corr_prs[0]['linked_issues'], [])

    def test_no_duplicate_links(self):
        issues = [_issue(5)]
        prs = [_pr(10, body="closes #5 and also fixes #5")]
        corr_issues, corr_prs, _, _ = correlate(issues, prs, [])
        self.assertEqual(corr_issues[0]['linked_prs'].count(10), 1)


class TestCorrelateStrategy2(unittest.TestCase):
    """Strategy 2: Release body #N → link release to PRs."""

    def test_release_linked_to_pr_via_body(self):
        prs = [_pr(20)]
        releases = [_release("v1.0.0", body_summary="What's changed: #20")]
        _, corr_prs, corr_releases, log = correlate([], prs, releases)

        self.assertIn(20, corr_releases[0]['linked_prs'])
        self.assertIn("v1.0.0", corr_prs[0]['linked_releases'])
        self.assertTrue(any("v1.0.0" in entry for entry in log))

    def test_pr_not_in_collection_silently_skipped(self):
        releases = [_release("v1.0.0", body_summary="#999")]
        _, _, corr_releases, _ = correlate([], [], releases)
        self.assertEqual(corr_releases[0]['linked_prs'], [])


class TestCorrelateTransitive(unittest.TestCase):
    """Transitive: issue→PR→release links issue to release."""

    def test_issue_gets_closing_release(self):
        issues = [_issue(5)]
        prs = [_pr(10, body="closes #5")]
        releases = [_release("v1.0.0", body_summary="includes #10")]

        corr_issues, _, _, log = correlate(issues, prs, releases)

        self.assertEqual(corr_issues[0]['closing_release'], "v1.0.0")
        self.assertIn("v1.0.0", corr_issues[0]['linked_releases'])
        self.assertTrue(any("transitively" in entry for entry in log))

    def test_closing_release_uses_chronological_not_lexicographic_order(self):
        """v1.10.0 published before v1.9.0 should be chosen as closing_release."""
        issues = [_issue(5)]
        # PR closes issue #5 and is referenced by both releases
        pr = _pr(10, body="closes #5")
        # v1.10.0 published earlier than v1.9.0
        rel_early = dict(_release("v1.10.0", body_summary="#10"))
        rel_early['published_at'] = "2026-06-01T00:00:00Z"
        rel_late = dict(_release("v1.9.0", body_summary="#10"))
        rel_late['published_at'] = "2026-07-01T00:00:00Z"

        corr_issues, _, _, _ = correlate(issues, [pr], [rel_early, rel_late])

        # Chronologically earliest is v1.10.0 (June), NOT v1.9.0 (July)
        self.assertEqual(corr_issues[0]['closing_release'], "v1.10.0")

    def test_unlinked_issue_closing_release_stays_none(self):
        issues = [_issue(5)]
        corr_issues, _, _, _ = correlate(issues, [], [])
        self.assertIsNone(corr_issues[0]['closing_release'])


class TestCorrelateUnlinkedRetained(unittest.TestCase):
    """Unlinked artifacts must be preserved in the output."""

    def test_unlinked_issue_retained(self):
        issues = [_issue(1), _issue(2)]
        corr_issues, _, _, _ = correlate(issues, [], [])
        self.assertEqual(len(corr_issues), 2)

    def test_unlinked_pr_retained(self):
        prs = [_pr(10), _pr(11)]
        _, corr_prs, _, _ = correlate([], prs, [])
        self.assertEqual(len(corr_prs), 2)

    def test_unlinked_release_retained(self):
        releases = [_release("v1.0"), _release("v2.0")]
        _, _, corr_releases, _ = correlate([], [], releases)
        self.assertEqual(len(corr_releases), 2)


if __name__ == "__main__":
    unittest.main()
