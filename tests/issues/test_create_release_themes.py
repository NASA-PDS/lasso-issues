"""Tests for create_release_themes module."""
import json
import unittest
from unittest.mock import Mock
from unittest.mock import patch

import pandas as pd
from lasso.issues.issues.create_release_themes import check_issue_exists
from lasso.issues.issues.create_release_themes import create_issue_body
from lasso.issues.issues.create_release_themes import create_release_theme
from lasso.issues.issues.create_release_themes import ensure_label_exists
from lasso.issues.issues.create_release_themes import find_project_id
from lasso.issues.issues.create_release_themes import parse_date
from lasso.issues.issues.create_release_themes import run_gh_command


class TestParseDate(unittest.TestCase):
    """Test date parsing functionality."""

    def test_parse_date_valid(self):
        """Test parsing valid YYYY-MM-DD dates."""
        self.assertEqual(parse_date("2025-09-05"), "2025-09-05")
        self.assertEqual(parse_date("2025-10-16"), "2025-10-16")
        self.assertEqual(parse_date("2026-03-12"), "2026-03-12")
        self.assertEqual(parse_date("2030-12-31"), "2030-12-31")

    def test_parse_date_single_digit(self):
        """Test parsing dates with single digit month/day."""
        self.assertEqual(parse_date("2025-01-01"), "2025-01-01")
        self.assertEqual(parse_date("2025-01-15"), "2025-01-15")
        self.assertEqual(parse_date("2025-09-05"), "2025-09-05")

    def test_parse_date_invalid_format(self):
        """Test parsing invalid date formats raises ValueError."""
        with self.assertRaises(ValueError):
            parse_date("9/5/25")  # Old MM/DD/YY format
        with self.assertRaises(ValueError):
            parse_date("invalid")
        with self.assertRaises(ValueError):
            parse_date("2025-13-32")  # Invalid date


class TestCreateIssueBody(unittest.TestCase):
    """Test issue body creation."""

    def test_create_body_no_checklist(self):
        """Test creating issue body without checklist."""
        description = "This is a test description"
        body = create_issue_body(description)

        self.assertIn("## Are you sure this is not a new requirement or bug?", body)
        self.assertIn("Yes", body)
        self.assertIn("## 💡 Description", body)
        self.assertIn(description, body)
        self.assertNotIn("## ✅ Checklist", body)

    def test_create_body_with_checklist(self):
        """Test creating issue body with checklist."""
        description = "Test description"
        checklist = "Item 1;Item 2;Item 3"
        body = create_issue_body(description, checklist)

        self.assertIn("## ✅ Checklist", body)
        self.assertIn("- [ ] Item 1", body)
        self.assertIn("- [ ] Item 2", body)
        self.assertIn("- [ ] Item 3", body)

    def test_create_body_empty_checklist(self):
        """Test creating issue body with empty checklist."""
        description = "Test description"
        body = create_issue_body(description, "")

        self.assertNotIn("## ✅ Checklist", body)

    def test_create_body_whitespace_checklist(self):
        """Test creating issue body with whitespace-only checklist."""
        description = "Test description"
        body = create_issue_body(description, "   ")

        self.assertNotIn("## ✅ Checklist", body)

    def test_create_body_checklist_with_empty_items(self):
        """Test checklist with empty items (extra semicolons)."""
        description = "Test description"
        checklist = "Item 1;;Item 2;  ;Item 3"
        body = create_issue_body(description, checklist)

        # Should only include non-empty items
        self.assertEqual(body.count("- [ ]"), 3)
        self.assertIn("- [ ] Item 1", body)
        self.assertIn("- [ ] Item 2", body)
        self.assertIn("- [ ] Item 3", body)


class TestRunGhCommand(unittest.TestCase):
    """Test GitHub CLI command execution."""

    @patch("subprocess.run")
    def test_run_gh_command_success(self, mock_run):
        """Test successful command execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = run_gh_command(["issue", "list"])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "success")
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        self.assertEqual(call_args[0][0], ["gh", "issue", "list"])

    @patch("subprocess.run")
    def test_run_gh_command_failure(self, mock_run):
        """Test failed command execution."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result

        result = run_gh_command(["issue", "list"], check=False)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "error message")

    @patch("subprocess.run")
    def test_run_gh_command_with_input(self, mock_run):
        """Test command with stdin input."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        run_gh_command(["issue", "create"], input_data="test input")

        call_args = mock_run.call_args
        self.assertEqual(call_args[1]["input"], "test input")


class TestEnsureLabelExists(unittest.TestCase):
    """Test label existence checking and creation."""

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_label_exists(self, mock_run_gh):
        """Test when label already exists."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "B17\nB16\ntheme\nEpic"
        mock_run_gh.return_value = mock_result

        result = ensure_label_exists("NASA-PDS/test-repo", "B17")

        self.assertTrue(result)
        mock_run_gh.assert_called_once()
        # Should only check for label, not create
        call_args = mock_run_gh.call_args[0][0]
        self.assertIn("label", call_args)
        self.assertIn("list", call_args)

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_label_does_not_exist_create(self, mock_run_gh):
        """Test creating label when it doesn't exist."""
        # First call: label list (doesn't exist)
        # Second call: label create (success)
        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = "B16\ntheme\nEpic"

        mock_create_result = Mock()
        mock_create_result.returncode = 0

        mock_run_gh.side_effect = [mock_list_result, mock_create_result]

        result = ensure_label_exists("NASA-PDS/test-repo", "B17", dry_run=False)

        self.assertTrue(result)
        self.assertEqual(mock_run_gh.call_count, 2)
        # Check second call was create
        create_call = mock_run_gh.call_args_list[1][0][0]
        self.assertIn("create", create_call)
        self.assertIn("B17", create_call)

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_label_dry_run(self, mock_run_gh):
        """Test dry-run mode doesn't create label."""
        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = "B16\ntheme"
        mock_run_gh.return_value = mock_list_result

        result = ensure_label_exists("NASA-PDS/test-repo", "B17", dry_run=True)

        self.assertTrue(result)
        # Should only call list, not create
        self.assertEqual(mock_run_gh.call_count, 1)


class TestCheckIssueExists(unittest.TestCase):
    """Test issue existence checking."""

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_issue_exists(self, mock_run_gh):
        """Test when issue with exact title exists."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {"title": "B17 Release Planning"},
            {"title": "B17 Other Task"}
        ])
        mock_run_gh.return_value = mock_result

        result = check_issue_exists("NASA-PDS/test-repo", "B17 Release Planning")

        self.assertTrue(result)

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_issue_does_not_exist(self, mock_run_gh):
        """Test when issue doesn't exist."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([
            {"title": "B16 Release Planning"},
            {"title": "B17 Other Task"}
        ])
        mock_run_gh.return_value = mock_result

        result = check_issue_exists("NASA-PDS/test-repo", "B17 Release Planning")

        self.assertFalse(result)

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_issue_check_command_failure(self, mock_run_gh):
        """Test when gh command fails."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        mock_run_gh.return_value = mock_result

        result = check_issue_exists("NASA-PDS/test-repo", "B17 Release Planning")

        self.assertFalse(result)

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_issue_check_invalid_json(self, mock_run_gh):
        """Test when response is invalid JSON."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json"
        mock_run_gh.return_value = mock_result

        result = check_issue_exists("NASA-PDS/test-repo", "B17 Release Planning")

        self.assertFalse(result)


class TestFindProjectId(unittest.TestCase):
    """Test project ID lookup."""

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_find_project_success(self, mock_run_gh):
        """Test finding project successfully."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "projects": [
                {"title": "B16", "number": 10, "id": "PVT_id_16"},
                {"title": "B17", "number": 11, "id": "PVT_id_17"},
                {"title": "B18", "number": 12, "id": "PVT_id_18"}
            ]
        })
        mock_run_gh.return_value = mock_result

        project_number, project_node_id = find_project_id("B17")

        self.assertEqual(project_number, "11")
        self.assertEqual(project_node_id, "PVT_id_17")

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_find_project_not_found(self, mock_run_gh):
        """Test when project doesn't exist."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "projects": [
                {"title": "B16", "number": 10, "id": "PVT_id_16"},
                {"title": "B18", "number": 12, "id": "PVT_id_18"}
            ]
        })
        mock_run_gh.return_value = mock_result

        project_number, project_node_id = find_project_id("B17")

        self.assertIsNone(project_number)
        self.assertIsNone(project_node_id)

    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_find_project_command_failure(self, mock_run_gh):
        """Test when gh command fails."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        mock_run_gh.return_value = mock_result

        project_number, project_node_id = find_project_id("B17")

        self.assertIsNone(project_number)
        self.assertIsNone(project_node_id)


class TestCreateReleaseTheme(unittest.TestCase):
    """Test release theme creation."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_row = pd.Series({
            "Title": "Release Planning",
            "Repo": "NASA-PDS/test-repo",
            "Start Date": "2025-09-05",
            "End Date": "2025-10-16",
            "Description": "Test description",
            "Checklist": "Task 1;Task 2",
            "GitHub Project Product": "System Engineering"
        })

    @patch("lasso.issues.issues.create_release_themes.check_issue_exists")
    @patch("lasso.issues.issues.create_release_themes.ensure_label_exists")
    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_create_theme_dry_run(self, _mock_run_gh, mock_ensure_label, mock_check_exists):
        """Test creating theme in dry-run mode."""
        mock_ensure_label.return_value = True

        result = create_release_theme(self.test_row, 17, dry_run=True)

        # Should return dry-run URL
        self.assertEqual(result, "https://github.com/NASA-PDS/test-repo/issues/DRY-RUN")
        # Should not check for existing issues in dry-run
        mock_check_exists.assert_not_called()
        # Should still ensure label exists
        mock_ensure_label.assert_called_once()

    @patch("lasso.issues.issues.create_release_themes.check_issue_exists")
    def test_create_theme_already_exists(self, mock_check_exists):
        """Test skipping when issue already exists."""
        mock_check_exists.return_value = True

        result = create_release_theme(self.test_row, 17, dry_run=False)

        self.assertEqual(result, "SKIPPED")
        mock_check_exists.assert_called_once_with("NASA-PDS/test-repo", "B17 Release Planning")

    @patch("lasso.issues.issues.create_release_themes.get_project_item_id")
    @patch("lasso.issues.issues.create_release_themes.set_project_field")
    @patch("lasso.issues.issues.create_release_themes.find_project_id")
    @patch("lasso.issues.issues.create_release_themes.check_issue_exists")
    @patch("lasso.issues.issues.create_release_themes.ensure_label_exists")
    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_create_theme_success(self, mock_run_gh, mock_ensure_label, mock_check_exists, mock_find_project, mock_set_field, mock_get_item_id):
        """Test successfully creating an issue."""
        mock_check_exists.return_value = False
        mock_ensure_label.return_value = True
        mock_find_project.return_value = ("11", "PVT_id_17")
        mock_get_item_id.return_value = "PVTI_item_id"
        mock_set_field.return_value = True

        # First call: create issue
        mock_create_result = Mock()
        mock_create_result.returncode = 0
        mock_create_result.stdout = "https://github.com/NASA-PDS/test-repo/issues/123"

        # Second call: add to project
        mock_project_result = Mock()
        mock_project_result.returncode = 0

        mock_run_gh.side_effect = [mock_create_result, mock_project_result]

        result = create_release_theme(self.test_row, 17, dry_run=False)

        self.assertEqual(result, "https://github.com/NASA-PDS/test-repo/issues/123")

        # Verify issue creation call
        create_call = mock_run_gh.call_args_list[0][0][0]
        self.assertIn("issue", create_call)
        self.assertIn("create", create_call)
        self.assertIn("--title", create_call)
        title_index = create_call.index("--title") + 1
        self.assertEqual(create_call[title_index], "B17 Release Planning")

    @patch("lasso.issues.issues.create_release_themes.check_issue_exists")
    def test_create_theme_invalid_dates(self, mock_check_exists):
        """Test handling invalid dates."""
        mock_check_exists.return_value = False
        invalid_row = self.test_row.copy()
        invalid_row["Start Date"] = "invalid"

        result = create_release_theme(invalid_row, 17, dry_run=False)

        self.assertIsNone(result)

    @patch("lasso.issues.issues.create_release_themes.find_project_id")
    @patch("lasso.issues.issues.create_release_themes.check_issue_exists")
    @patch("lasso.issues.issues.create_release_themes.ensure_label_exists")
    @patch("lasso.issues.issues.create_release_themes.run_gh_command")
    def test_create_theme_issue_creation_fails(self, mock_run_gh, mock_ensure_label, mock_check_exists, _mock_find_project):
        """Test when issue creation fails."""
        mock_check_exists.return_value = False
        mock_ensure_label.return_value = True

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        mock_run_gh.return_value = mock_result

        result = create_release_theme(self.test_row, 17, dry_run=False)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
