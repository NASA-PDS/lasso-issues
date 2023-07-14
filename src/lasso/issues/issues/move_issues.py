"""Issue moving."""
import argparse
import logging
import os
import sys
from datetime import datetime

import github3

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_parser():
    """Create an argument parser and return it."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    parser.add_argument("--source-repo", type=str, required=True, help="source repository <org>/<repo>")
    parser.add_argument("--target-repo", type=str, help="target repository <org>/<repo>")
    parser.add_argument(
        "--label",
        type=str,
        required=False,
        default=None,
        help="label added to the issues in their target repository, "
        "usually the name of the module the issue is related to",
    )
    parser.add_argument("--token", type=str, required=False, help="github token.")
    parser.add_argument("--dry-run", default=False, required=False, action="store_true")
    return parser


def get_gh_connection(token=None):
    """Get the GitHub connection using the given ``token``."""
    github_token = token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        logger.error("github API token must be provided or set as environment" " variable (GITHUB_TOKEN).")
        sys.exit(1)
    else:
        return github3.login(token=github_token)


def move_issue(issue, target_repository, label=None, dry_run=False):
    """Move the given ``issue`` to the ``target_repository``.

    You can optionally assign a new ``label`` to it. And if ``dry_run`` is True, we just hand-wave it.
    """
    labels = [label.name for label in issue.labels()]
    if label:
        labels.append(label)

    comment = {
        "created_at": datetime.now().astimezone().isoformat(),
        "body": f"imported, see original ticket {issue.html_url}",
    }

    optional_args = {"closed": issue.state == "closed", "labels": labels, "comments": [comment]}
    if issue.assignee:
        optional_args["assignee"] = issue.assignee.login
    if issue.milestone:
        optional_args["milestone"] = issue.milestone.id

    if not dry_run:
        target_repository.import_issue(issue.title, issue.body, issue.created_at.isoformat(), **optional_args)

        if issue.state != "closed":
            issue.close()
    else:
        # Dry run so don't take action but show what would happen
        logger.info("Moving issue «%s» to %s/%s", issue.title, target_repository.owner, target_repository.name)


def move_issues(source_repo, target_repo, gh_connection, label=None, dry_run=True):
    """Move issues."""
    owner, repo_name = source_repo.split("/")
    source_repository = gh_connection.repository(owner, repo_name)

    owner, repo_name = target_repo.split("/")
    target_repository = gh_connection.repository(owner, repo_name)

    pull_request_numbers = []
    for pull_request in source_repository.pull_requests(state="all"):
        pull_request_numbers.append(pull_request.number)

    for short_issue in source_repository.issues(state="all"):
        if short_issue.number not in pull_request_numbers:
            logger.info("move issue %d", short_issue.number)
            issue = source_repository.issue(short_issue.number)
            move_issue(issue, target_repository, label=label, dry_run=dry_run)


def main():
    """Main entrypoint."""
    parser = create_parser()
    args = parser.parse_args()

    gh_connection = get_gh_connection(token=args.token)

    move_issues(args.source_repo, args.target_repo, gh_connection, label=args.label, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
