"""Lasso Issues: issue handling."""
import argparse
import logging

from lasso.issues.argparse import add_standard_arguments
from lasso.issues.github import GithubConnection
from mdutils.mdutils import MdUtils

from . import MetricsRddReport
from . import RstRddReport
from .utils import get_issue_priority
from .utils import get_issues_groupby_type
from .utils import TOP_PRIORITIES


DEFAULT_GITHUB_ORG = "NASA-PDS"

_logger = logging.getLogger(__name__)


def convert_issues_to_planning_report(md_file, repo_name, issues_map):
    """Conver the issues into a planning report."""
    md_file.new_header(level=1, title=repo_name)

    for issue_type in issues_map:
        md_file.new_header(level=2, title=issue_type)

        table = ["Issue", "Priority / Bug Severity", "On Deck"]
        count = 1
        for short_issue in issues_map[issue_type]:
            issue = f"[{repo_name}#{short_issue.number}]({short_issue.html_url}) - {short_issue.title}"
            priority = get_issue_priority(short_issue)

            ondeck = ""
            if priority in TOP_PRIORITIES:
                ondeck = "X"

            table.extend([issue, priority, ondeck])
            count += 1

        md_file.new_line()
        md_file.new_table(columns=3, rows=int(len(table) / 3), text=table, text_align="left")


def create_md_issue_report(org, repos, issue_state="all", start_time=None, token=None):
    """Create the issue report, in Markdown format."""
    gh = GithubConnection.getConnection(token=token)

    _md_file = MdUtils(file_name="pdsen_issues", title="PDS EN Issues")
    for _repo in gh.repositories_by(org):
        if repos and _repo.name not in repos:
            continue
        issues_map = get_issues_groupby_type(_repo, state=issue_state, start_time=start_time)
        convert_issues_to_planning_report(_md_file, _repo.name, issues_map)

    _md_file.create_md_file()


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
    parser.add_argument("--token", help="github token.")
    parser.add_argument(
        "--issue_state", choices=["open", "closed", "all"], default="all", help="Return open, closed, or all issues"
    )
    parser.add_argument(
        "--start-time",
        help="Start datetime for tickets to find. This is a timestamp in ISO 8601-like format: YYYY-MM-DDTHH:MM:SS+00:00.",
    )
    parser.add_argument(
        "--end-time",
        help="End datetime for tickets to find. This is a timestamp in ISO 8601-like format: YYYY-MM-DDTHH:MM:SS+00:00.",
    )
    parser.add_argument("--format", default="md", help="rst or md or metrics")

    parser.add_argument("--build", default=None, help="build label, for example B11.1 or B12.0")

    parser.add_argument(
        "--loglevel",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the root logger level to the specified level.",
    )

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format="%(levelname)s %(message)s")

    _logger.info("Working on build %s", args.build)

    if args.format == "md":
        create_md_issue_report(
            args.github_org,
            args.github_repos,
            issue_state=args.issue_state,
            start_time=args.start_time,
            token=args.token,
        )

    elif args.format == "rst":
        rst_rdd_report = RstRddReport(
            args.github_org, start_time=args.start_time, end_time=args.end_time, build=args.build, token=args.token
        )

        rst_rdd_report.create(args.github_repos, "pdsen_issues.rst")

    elif args.format == "metrics":
        rdd_metrics = MetricsRddReport(
            args.github_org, start_time=args.start_time, end_time=args.end_time, build=args.build, token=args.token
        )

        rdd_metrics.create(args.github_repos)

    else:
        _logger.error("unsupported format %s, must be rst or md or metrics", args.format)
