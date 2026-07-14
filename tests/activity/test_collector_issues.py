"""Unit tests for collector_issues.py (issue #61)."""
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from lasso.issues.activity.collector_issues import _build_repo_qualifier
from lasso.issues.activity.collector_issues import _repo_name_from_url
from lasso.issues.activity.collector_issues import discover_repos
from lasso.issues.activity.schema import normalize_issue


class TestRepoNameFromUrl(unittest.TestCase):
    """Tests for _repo_name_from_url helper."""

    def test_standard_issue_url(self):
        url = "https://github.com/NASA-PDS/lasso-issues/issues/42"
        self.assertEqual(_repo_name_from_url(url), "lasso-issues")

    def test_standard_pr_url(self):
        url = "https://github.com/NASA-PDS/validate/pull/7"
        self.assertEqual(_repo_name_from_url(url), "validate")

    def test_invalid_url_returns_empty(self):
        self.assertEqual(_repo_name_from_url("not-a-url"), "")

    def test_empty_string_returns_empty(self):
        self.assertEqual(_repo_name_from_url(""), "")


class TestBuildRepoQualifier(unittest.TestCase):
    """Tests for _build_repo_qualifier."""

    def test_no_repos_returns_empty(self):
        self.assertEqual(_build_repo_qualifier("NASA-PDS", None), "")

    def test_empty_list_returns_empty(self):
        self.assertEqual(_build_repo_qualifier("NASA-PDS", []), "")

    def test_single_repo(self):
        result = _build_repo_qualifier("NASA-PDS", ["validate"])
        self.assertEqual(result, " repo:NASA-PDS/validate")

    def test_multiple_repos(self):
        result = _build_repo_qualifier("NASA-PDS", ["validate", "registry"])
        self.assertIn("repo:NASA-PDS/validate", result)
        self.assertIn("repo:NASA-PDS/registry", result)


class TestNormalizeIssue(unittest.TestCase):
    """Tests for schema.normalize_issue."""

    def _make_mock_issue(self, number=42, title="Test issue", state="closed",
                         labels=None, created_at=None, closed_at=None):
        issue = MagicMock()
        issue.id = 1000 + number
        issue.number = number
        issue.title = title
        issue.state = state
        issue.html_url = f"https://github.com/NASA-PDS/testrepo/issues/{number}"
        issue.created_at = created_at
        issue.closed_at = closed_at

        if labels is None:
            labels = []
        mock_labels = []
        for name in labels:
            lbl = MagicMock()
            lbl.name = name
            mock_labels.append(lbl)
        issue.labels = mock_labels

        return issue

    def test_basic_normalization(self):
        mock_issue = self._make_mock_issue(number=7, title="A bug", state="closed", labels=["bug"])
        result = normalize_issue(mock_issue, "testrepo")

        self.assertEqual(result['id'], 1007)
        self.assertEqual(result['number'], 7)
        self.assertEqual(result['repo'], "testrepo")
        self.assertEqual(result['title'], "A bug")
        self.assertEqual(result['state'], "closed")
        self.assertIn("bug", result['labels'])

    def test_empty_linked_fields_initialized(self):
        mock_issue = self._make_mock_issue()
        result = normalize_issue(mock_issue, "testrepo")

        self.assertEqual(result['linked_prs'], [])
        self.assertEqual(result['linked_releases'], [])
        self.assertIsNone(result['closing_release'])

    def test_no_parent_returns_null(self):
        mock_issue = self._make_mock_issue()
        result = normalize_issue(mock_issue, "testrepo")
        self.assertIsNone(result['parent_issue'])

    def test_closed_parent_issue_attached(self):
        mock_issue = self._make_mock_issue(number=5)
        parent = {'number': 1, 'title': 'Sprint Theme', 'state': 'closed',
                  'html_url': 'https://github.com/NASA-PDS/testrepo/issues/1'}
        result = normalize_issue(mock_issue, "testrepo", parent=parent)

        self.assertIsNotNone(result['parent_issue'])
        self.assertEqual(result['parent_issue']['number'], 1)
        self.assertEqual(result['parent_issue']['title'], 'Sprint Theme')
        self.assertEqual(result['parent_issue']['state'], 'closed')

    def test_open_parent_issue_state_preserved(self):
        """An open parent means partial progress toward a deliverable."""
        mock_issue = self._make_mock_issue(number=5)
        parent = {'number': 2, 'title': 'Ongoing Epic', 'state': 'open',
                  'html_url': 'https://github.com/NASA-PDS/testrepo/issues/2'}
        result = normalize_issue(mock_issue, "testrepo", parent=parent)

        self.assertEqual(result['parent_issue']['state'], 'open')

    def test_none_closed_at(self):
        mock_issue = self._make_mock_issue(state="open", closed_at=None)
        result = normalize_issue(mock_issue, "testrepo")
        self.assertIsNone(result['closed_at'])

    def test_dict_style_labels(self):
        issue = MagicMock()
        issue.id = 999
        issue.number = 1
        issue.title = "x"
        issue.state = "open"
        issue.html_url = "https://github.com/NASA-PDS/r/issues/1"
        issue.created_at = None
        issue.closed_at = None
        issue.labels = [{'name': 'enhancement'}, {'name': 'p.must-have'}]
        result = normalize_issue(issue, "r")
        self.assertIn('enhancement', result['labels'])
        self.assertIn('p.must-have', result['labels'])


class TestDiscoverRepos(unittest.TestCase):
    """Tests for discover_repos."""

    def _make_gh(self, repo_names):
        gh = MagicMock()
        org = MagicMock()
        repos = []
        for name in repo_names:
            r = MagicMock()
            r.name = name
            repos.append(r)
        org.repositories.return_value = iter(repos)
        gh.organization.return_value = org
        return gh

    def test_explicit_repos_returned_sorted(self):
        gh = MagicMock()
        result = discover_repos(gh, "NASA-PDS", repos_filter=["validate", "registry"])
        self.assertEqual(result, ["registry", "validate"])

    def test_all_org_repos_discovered(self):
        gh = self._make_gh(["b-repo", "a-repo", "c-repo"])
        result = discover_repos(gh, "NASA-PDS")
        self.assertEqual(result, ["a-repo", "b-repo", "c-repo"])

    def test_exclude_config_filters_explicit_repos(self):
        gh = MagicMock()
        config = {
            "products": {
                "ignored-product": {
                    "ignore": True,
                    "repositories": ["bad-repo"],
                }
            }
        }
        with patch("lasso.issues.activity.collector_issues.load_products_config", return_value=config):
            result = discover_repos(
                gh, "NASA-PDS",
                repos_filter=["good-repo", "bad-repo"],
                exclude_config_path="/fake/path.yaml",
            )
        self.assertEqual(result, ["good-repo"])

    def test_exclude_config_filters_org_repos(self):
        gh = self._make_gh(["good-repo", "bad-repo"])
        config = {
            "products": {
                "ignored": {"ignore": True, "repositories": ["bad-repo"]}
            }
        }
        with patch("lasso.issues.activity.collector_issues.load_products_config", return_value=config):
            result = discover_repos(gh, "NASA-PDS", exclude_config_path="/fake/path.yaml")
        self.assertNotIn("bad-repo", result)
        self.assertIn("good-repo", result)


if __name__ == "__main__":
    unittest.main()
