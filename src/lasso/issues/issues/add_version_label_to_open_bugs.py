"""Lasso Issues: add version label to open bugs issues"""
import argparse

# have ever seen the same module name embedded so many time
from lasso.issues.issues.issues import DEFAULT_GITHUB_ORG
from lasso.issues.github import GithubConnection


def add_label_to_open_bugs(repo, label_name: str):
    """
    Add a label (str) to the open bugs of a repository.

    The label need to be created first.

    @param repo: repository from the github3 api
    @param label_name: the name of the label to be added
    """

    for issue in repo.issues(state="open", labels=["bug"]):
        issue.add_labels(label_name)


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
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
    label = f"open.{args.version}"
    repo.create_label(label, "#062C9B")
    add_label_to_open_bugs(repo, label)


if __name__ == "__main__":
    main()
