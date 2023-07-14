#!/usr/bin/env python
"""Tool for closing milestones and producing Github issue reports."""
import argparse
import datetime
import logging
import os
import sys

from github3 import exceptions
from github3 import login
from lasso.issues.argparse import add_standard_arguments


DEFAULT_GITHUB_ORG = "NASA-PDS"

_logger = logging.getLogger(__name__)


DELAYED_LABELS_RUNNING_LATE = "d.running-late"
DELAYED_LABELS_RUNNING_LATER = "d.getting-later"
DELAYED_LABELS_DONT_FORGET_ME = "d.dont-forget-me"
SPRINT_BACKLOG_LABEL = "sprint-backlog"


def get_next_milestone(repo, milestone):
    """Get the next mielstone."""
    for m in repo.milestones():
        if m.number == milestone.number + 1:
            return m
    return None


def get_milestone(repo, sprint_title):
    """Get a milestone."""
    for m in repo.milestones():
        if m.title.lower() == sprint_title.lower():
            return m
    return None


def move_open_issues(repo, milestone, next_milestone):
    """Move issues still open ``repo`` in the ``milestone`` to the ``next_milestone``."""
    for issue in repo.issues(milestone=milestone.number, state="open"):
        labels = []
        already_late = False
        for label in issue.labels():
            if label.name == DELAYED_LABELS_RUNNING_LATE:
                labels.append(DELAYED_LABELS_RUNNING_LATER)
                already_late = True
            elif label.name == DELAYED_LABELS_RUNNING_LATER:
                labels.append(DELAYED_LABELS_DONT_FORGET_ME)
                already_late = True
            else:
                labels.append(label.name)

        if not already_late:
            labels.append(DELAYED_LABELS_RUNNING_LATE)

        issue.edit(milestone=next_milestone.number, labels=labels)


def remove_closed_issues_from_sprint_backlog(repo, milestone):
    """Remove issues that got closed in ``repo`` for the given ``mitlestone`` from the sprint backlog."""
    for issue in repo.issues(milestone=milestone.number, state="closed"):
        labels = []
        for label in issue.labels():
            if SPRINT_BACKLOG_LABEL != label.name:
                labels.append(label.name)
        issue.edit(labels=labels)


def defer_open_issues(repo, milestone):
    """Defer open issues in ``repo`` in the given ``milestone``."""
    next_milestone = get_next_milestone(repo, milestone)
    if next_milestone:
        _logger.info("defer open issues from milestone %s to milestone %s", milestone.title, next_milestone.title)
        move_open_issues(repo, milestone, next_milestone)
    else:
        _logger.info("no next milestone available, skipping repo")


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    add_standard_arguments(parser)
    parser.add_argument("--github-org", help="github org", default=DEFAULT_GITHUB_ORG)
    parser.add_argument(
        "--github-repos",
        nargs="*",
        help="github repo names. if not specified, tool will include all repos in org by default.",
    )
    parser.add_argument("--length", default=21, help="milestone length in number of days.")
    parser.add_argument("--token", help="github token.")
    parser.add_argument("--create", action="store_true", help="create milestone.")
    parser.add_argument("--delete", action="store_true", help="delete milestone.")
    parser.add_argument("--close", action="store_true", help="close milestone.")
    parser.add_argument("--due-date", help="Due date of first sprint. Format: YYYY-MM-DD")
    parser.add_argument(
        "--sprint-name-file",
        help=(
            "yaml file containing list of sprint names. tool will create " "as many milestones as specified in file."
        ),
    )
    parser.add_argument("--sprint-names", nargs="*", help="create one sprint with this name")
    parser.add_argument(
        "--prepend-number", type=int, help="specify number to prepend sprint names or to start with. e.g. 01.foo"
    )

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format="%(levelname)s %(message)s")

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        _logger.error("Github token must be provided or set as environment variable (GITHUB_TOKEN).")
        sys.exit(1)

    _sprint_names = args.sprint_names

    if args.sprint_name_file:
        with open(args.sprint_name_file) as f:
            _sprint_names = f.read().splitlines()

    if not _sprint_names:
        _logger.error("One of --sprint-names or --sprint-name_file must be specified.")
        sys.exit(1)

    _due_date = None
    if args.create:
        if not args.due_date:
            _logger.error("--due-date must be specified.")
            sys.exit(1)
        else:
            _due_date = datetime.datetime.strptime(args.due_date, "%Y-%m-%d") + datetime.timedelta(hours=8)

    _sprint_number = args.prepend_number
    for n in _sprint_names:
        _sprint_name = n.replace(" ", ".")

        if not _sprint_name:
            continue

        if _sprint_number is not None:
            _sprint_name = f"{str(_sprint_number).zfill(2)}.{_sprint_name}"
            _sprint_number += 1

        # connect to github
        gh = login(token=token)
        for _repo in gh.repositories_by(args.github_org):
            if args.github_repos and _repo.name not in args.github_repos:
                continue

            if args.create:
                _logger.info(f"+++ milestone: {_sprint_name}, due: {_due_date}")
                try:
                    _logger.info(f"CREATE repo: {_repo.name}")
                    _repo.create_milestone(_sprint_name, due_on=_due_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
                except exceptions.UnprocessableEntity:
                    # milestone already exists with this name
                    _logger.info(f"CREATE repo: {_repo.name}, already exists. skipping...")
            elif args.close:
                _logger.info(f"+++ milestone: {_sprint_name}")
                _milestone = get_milestone(_repo, _sprint_name)
                if _milestone:
                    _logger.info(f"CLOSE repo: {_repo.name}")
                    remove_closed_issues_from_sprint_backlog(_repo, _milestone)
                    defer_open_issues(_repo, _milestone)
                    _milestone.update(state="closed")
                else:
                    _logger.info(f"CLOSE repo: {_repo.name}, skipping...")
            elif args.delete:
                _logger.info(f"+++ milestone: {_sprint_name}")
                _milestone = get_milestone(_repo, _sprint_name)
                if _milestone:
                    _logger.info(f"DELETE repo: {_repo.name}")
                    _milestone.delete()
                else:
                    _logger.info(f"DELETE repo: {_repo.name}, skipping...")
            else:
                _logger.warning("NONE: no action specified")

        if _due_date:
            # Increment due date for next milestone
            _due_date = _due_date + datetime.timedelta(days=args.length)


if __name__ == "__main__":
    main()
