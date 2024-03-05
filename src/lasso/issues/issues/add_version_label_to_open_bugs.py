"""Lasso Issues: add version label to open bugs issues."""
import argparse

from lasso.issues.argparse import add_standard_arguments
from lasso.issues.github import GithubConnection
from lasso.issues.issues.issues import DEFAULT_GITHUB_ORG

# have ever seen the same module name embedded so many time

COLOR_OF_VERSION_LABELS = "#062C9B"


def add_label_to_open_bugs(repo, label_name: str):
    """Add a label (str) to the open bugs of a repository.

    The label need to be created first.

    @param repo: repository from the github3 api
    @param label_name: the name of the label to be added

    @return: True if at least on bug has been found and labelled
    """
    one_found = False
    for issue in repo.issues(state="open", labels=["bug"]):
        issue.add_labels(label_name)
        one_found = True

    return one_found


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

    args = parser.parse_args()

    gh = GithubConnection.get_connection(token=args.token)
    repo = gh.repository(args.github_org, args.github_repo)
    label = f"open.{args.labelled_version}"
    repo.create_label(label, COLOR_OF_VERSION_LABELS)
    print("Add the following line to your release notes on github:")
    section_title = "**Known bugs** and possible work arounds"
    if add_label_to_open_bugs(repo, label):
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
