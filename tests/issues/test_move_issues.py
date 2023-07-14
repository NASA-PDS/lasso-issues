"""Issue moving tests."""
import unittest

# from lasso.issues.issues.move_issues import get_gh_connection
# from lasso.issues.issues.move_issues import move_issues


class MyTestCase(unittest.TestCase):
    """My test case."""

    # Disabled as it requires GITHUB_TOKEN

    # def test_move_issue(self):
    #     """See if we can move issues but dryly."""
    #     gh_connection = get_gh_connection()
    #     move_issues("NASA-PDS/registry-api", "NASA-PDS/registry", gh_connection, label="model", dry_run=True)


if __name__ == "__main__":
    unittest.main()
