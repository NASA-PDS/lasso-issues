"""GitHub stuff."""
import logging
import os
import sys

from github3 import login

_logger = logging.getLogger(__name__)


class GithubConnection:
    """A connection to GitHub."""

    gh = None

    @classmethod
    def getconnection(cls, token=None):
        """Get the connection."""
        if not cls.gh:
            token = token or os.environ.get("GITHUB_TOKEN")
            if not token:
                _logger.error("Github token must be provided or set as environment variable (GITHUB_TOKEN).")
                sys.exit(1)
            cls.gh = login(token=token)
        return cls.gh
