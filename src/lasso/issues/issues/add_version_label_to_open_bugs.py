"""Lasso Issues: add version label to open bugs issues."""
import argparse
import logging

from github3.exceptions import NotFoundError
from lasso.issues.argparse import add_standard_arguments
from lasso.issues.github import GithubConnection
from lasso.issues.issues.issues import DEFAULT_GITHUB_ORG


COLOR_OF_VERSION_LABELS = "#062C9B"

_logger = logging.getLogger(__name__)


def add_label_to_open_bugs(repo, label_name: str, dry_run: bool = True):
    """Add a label (str) to the open bugs of a repository.

    The label need to be created first.

    @param repo: repository from the github3 api
    @param label_name: the name of the label to be added
    @param dry_run: does not update the issue with new label

    @return: True if at least on bug has been found and labelled
    """
    one_found = False
    for issue in repo.issues(state="open", labels=["bug"]):
        one_found = True
        if not dry_run:
            issue.add_labels(label_name)

    return one_found


def create_label_if_not_exists(repo, label: str, color: str):
    """Create the label in the repo if it does not exist yet.

    @param repo: github3 object
    @param label: string
    @param color: string for example #123456
    @return:
    """
    try:
        repo.label(label)
        _logger.info("label %s already exist, skip creation.", label)
        return
    except NotFoundError:
        repo.create_label(label, color)
        _logger.info("label %s has been created.", label)
        return


def main():
    """Main function to add labels to open bugs in a release."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    add_standard_arguments(parser)
    parser.add_argument("--labelled-version", help="stable version containing the open bugs")
    parser.add_argument("--github-org", help="github org", default=DEFAULT_GITHUB_ORG)
    parser.add_argument(
        "--github-repo",
        help="github repo name",
    )
    parser.add_argument("--token", help="github token.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the release note without creating the label and updating the issues in github.",
    )

    args = parser.parse_args()

    gh = GithubConnection.get_connection(token=args.token)
    repo = gh.repository(args.github_org, args.github_repo)
    label = f"open.{args.labelled_version}"
    create_label_if_not_exists(repo, label, COLOR_OF_VERSION_LABELS)
    print("Add the following line to your release notes on github:")
    section_title = "**Known bugs** and possible work arounds"
    if add_label_to_open_bugs(repo, label, dry_run=args.dry_run):
        msg = (
            f"{section_title}: [known bugs in {args.labelled_version}]"
            f"(https://github.com/{args.github_org}/{args.github_repo}/"
            f"issues?q=is%3Aissue+label%3Aopen.{args.labelled_version})"
        )
        print(msg)
    else:
        print(f"{section_title}: no known bugs")


if __name__ == "__main__":
    main()
