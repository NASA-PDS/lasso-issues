#!/usr/bin/env python
"""Labels and organizational defaults."""
import argparse
import logging
import os
import sys
import time
import traceback

import yaml
from github3 import login
from github3.exceptions import ConnectionError
from github3.exceptions import ForbiddenError
from github3.exceptions import NotFoundError
from github3.exceptions import UnprocessableEntity
from lasso.issues.argparse import add_standard_arguments


DEFAULT_GITHUB_ORG = "NASA-PDS"

_logger = logging.getLogger(__name__)


class Labels:
    """Labels."""

    def __init__(self, org, repos, token, dev=False):
        """Initializer."""
        self._org = org
        self._repos = []
        self._gh = login(token=token)

        if repos:
            for repo in repos:
                self._repos.append(self._gh.repository(self._org, repo))
        else:
            self._repos = self._gh.repositories_by(self._org)

    def create_labels_for_org(self, label_name, label_color):
        """Create labels for an organization."""
        _logger.info(f'Creating label "{label_name}" (color: "{label_color}")')
        for repo in self._repos:
            if not repo.archived:
                self.create_label(repo, label_name, label_color)

    def delete_labels_for_org(self, labels):
        """Delete labels from an organization."""
        for repo in self._repos:
            if not repo.archived:
                for label in repo.labels():
                    if label.name in labels.keys():
                        label.delete()
                        _logger.info("%s: Delete SUCCESS" % repo)

    def create_label(self, repo, label_name, label_color):
        """Create a label in ``repo`` named ``label_name`` and colored ``label_color``."""
        try:
            try:
                label = repo.label(label_name)
                label.update(label_name, label_color)
                _logger.info("%s: Update SUCCESS" % repo)
            except NotFoundError:
                repo.create_label(label_name, label_color)
                _logger.info("%s: Creation SUCCESS" % repo)
        except ForbiddenError:
            # Most likely due to archived repo, just keep going
            return
        except (UnprocessableEntity, ConnectionError):
            _logger.warning("Odd connection error or out of API calls. Wait 1 hour...")
            time.sleep(3600)
            self.create_label(repo, label_name, label_color)
        except Exception:
            _logger.error("ERROR: Create/update failed.")
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    add_standard_arguments(parser)
    parser.add_argument("--github_org", help="github org", default=DEFAULT_GITHUB_ORG)
    parser.add_argument(
        "--github_repos",
        nargs="*",
        help="github repo names. if not specified, tool will include all repos in org, by default.",
    )
    parser.add_argument("--token", help="github token.")
    parser.add_argument("--label-name", help="Add new label with this name.")
    parser.add_argument("--label-color", help="Color in hex")
    parser.add_argument("--create", action="store_true", help="create labels")
    parser.add_argument("--delete", action="store_true", help="remove labels")
    parser.add_argument("--config_file", help="YAML config file containing many label-name + label-color combinations.")

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format="%(levelname)s %(message)s")

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        _logger.error("Github token must be provided or set as environment variable (GITHUB_TOKEN).")
        sys.exit(1)

    if (args.label_name and not args.label_color) or (not args.label_name and args.label_color):
        raise Exception("Must specify label name and label color")

    labels_obj = Labels(args.github_org, args.github_repos, token)

    if args.label_name and args.label_color:
        if args.create:
            labels_obj.create_labels_for_org(args.label_name, args.label_color)
        elif args.delete:
            labels_obj.delete_labels_for_org({args.label_name: ""})
    elif args.config_file:
        with open(args.config_file) as _file:
            _yml = yaml.load(_file, Loader=yaml.FullLoader)
            if args.delete:
                labels_obj.delete_labels_for_org(_yml["labels"])
            elif args.create:
                for name, color in _yml["labels"].items():
                    labels_obj.create_labels_for_org(name, color)
