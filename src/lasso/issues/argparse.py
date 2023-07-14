"""Argument parsing."""
import argparse
import logging

from . import VERSION


def add_standard_arguments(parser: argparse.ArgumentParser):
    """Add normally expected command-line arguments to the given ``parser``."""
    # The "version" option
    parser.add_argument("--version", action="version", version=VERSION)

    # Logging options
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-d",
        "--debug",
        action="store_const",
        const=logging.DEBUG,
        default=logging.INFO,
        dest="loglevel",
        help="Log copious debugging messages suitable for developers",
    )
    group.add_argument(
        "-q",
        "--quiet",
        action="store_const",
        const=logging.WARNING,
        dest="loglevel",
        help="Don't log anything except warnings and critically-important messages",
    )
