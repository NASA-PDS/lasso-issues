"""Unit tests for collector_prs.py (issue #62)."""
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from lasso.issues.activity.schema import normalize_pr


class TestNormalizePr(unittest.TestCase):
    """Tests for schema.normalize_pr."""

    def _make_pr_data(self, number=10, title="Fix bug", state="closed",
                      merged_at="2026-06-01T10:00:00Z", draft=False, body="closes #5"):
        return {
            "id": 5000 + number,
            "number": number,
            "title": title,
            "state": state,
            "merged_at": merged_at,
            "draft": draft,
            "body": body,
            "html_url": f"https://github.com/NASA-PDS/testrepo/pull/{number}",
            "user": {"login": "octocat"},
        }

    def test_basic_normalization(self):
        data = self._make_pr_data(number=3, title="Merge me")
        result = normalize_pr(data, "testrepo")

        self.assertEqual(result['id'], 5003)
        self.assertEqual(result['number'], 3)
        self.assertEqual(result['repo'], "testrepo")
        self.assertEqual(result['title'], "Merge me")
        self.assertEqual(result['author'], "octocat")
        self.assertEqual(result['merged_at'], "2026-06-01T10:00:00Z")

    def test_empty_linked_fields_initialized(self):
        data = self._make_pr_data()
        result = normalize_pr(data, "testrepo")

        self.assertEqual(result['linked_issues'], [])
        self.assertEqual(result['linked_releases'], [])

    def test_no_user_returns_none_author(self):
        data = self._make_pr_data()
        data['user'] = None
        result = normalize_pr(data, "testrepo")
        self.assertIsNone(result['author'])

    def test_none_body_normalized_to_empty_string(self):
        data = self._make_pr_data()
        data['body'] = None
        result = normalize_pr(data, "testrepo")
        self.assertEqual(result['body'], "")


class TestCollectPrsDraftExclusion(unittest.TestCase):
    """Test that collect_prs excludes draft PRs."""

    def test_draft_prs_are_excluded(self):
        from lasso.issues.activity.collector_prs import collect_prs

        draft_pr_data = {
            "id": 9001, "number": 1, "title": "Draft", "state": "open",
            "merged_at": "2026-06-15T00:00:00Z", "draft": True,
            "body": "", "html_url": "https://github.com/NASA-PDS/testrepo/pull/1",
            "user": {"login": "dev"},
        }

        search_result = MagicMock()
        search_result.id = 9001
        search_result.number = 1
        search_result.html_url = "https://github.com/NASA-PDS/testrepo/pull/1"

        gh = MagicMock()
        gh.search_issues.return_value = iter([search_result])

        with patch("lasso.issues.activity.collector_prs._fetch_pr_data", return_value=draft_pr_data):
            result = collect_prs(gh, "NASA-PDS", ["testrepo"], "2026-06-01", "2026-06-30")

        self.assertEqual(result, [])

    def test_non_draft_prs_are_included(self):
        from lasso.issues.activity.collector_prs import collect_prs

        pr_data = {
            "id": 9002, "number": 2, "title": "Real PR", "state": "closed",
            "merged_at": "2026-06-15T00:00:00Z", "draft": False,
            "body": "", "html_url": "https://github.com/NASA-PDS/testrepo/pull/2",
            "user": {"login": "dev"},
        }

        search_result = MagicMock()
        search_result.id = 9002
        search_result.number = 2
        search_result.html_url = "https://github.com/NASA-PDS/testrepo/pull/2"

        gh = MagicMock()
        gh.search_issues.return_value = iter([search_result])

        with patch("lasso.issues.activity.collector_prs._fetch_pr_data", return_value=pr_data):
            result = collect_prs(gh, "NASA-PDS", ["testrepo"], "2026-06-01", "2026-06-30")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['number'], 2)


if __name__ == "__main__":
    unittest.main()
