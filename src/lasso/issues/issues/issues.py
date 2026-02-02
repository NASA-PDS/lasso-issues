"""Lasso Issues: issue handling."""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from lasso.issues.argparse import add_standard_arguments
from lasso.issues.github import get_parent_issue
from lasso.issues.github import get_sub_issues
from lasso.issues.github import GithubConnection
from lasso.issues.issues import CsvTestCaseReport
from lasso.issues.issues import MetricsRddReport
from lasso.issues.issues import RstRddReport
from lasso.issues.issues.utils import get_issue_priority
from lasso.issues.issues.utils import get_org_issues_groupby_type_and_repo
from lasso.issues.issues.utils import TOP_PRIORITIES
from mdutils.mdutils import MdUtils


DEFAULT_GITHUB_ORG = "NASA-PDS"

_logger = logging.getLogger(__name__)


def load_products_config():
    """Load the PDS products configuration from YAML file.

    Returns:
        dict: Products configuration, or None if file not found
    """
    # Try to find conf/pds-products.yaml relative to this file
    current_dir = Path(__file__).parent
    config_paths = [
        current_dir.parent.parent.parent.parent / "conf" / "pds-products.yaml",  # From src/lasso/issues/issues
        Path.cwd() / "conf" / "pds-products.yaml",  # From current working directory
    ]

    for config_path in config_paths:
        if config_path.exists():
            _logger.debug(f"Loading products config from {config_path}")
            with open(config_path) as f:
                return yaml.safe_load(f)

    _logger.warning("Could not find conf/pds-products.yaml - grouping by component will not be available")
    return None


def build_repo_to_product_map(products_config):
    """Build a mapping from repository name to product name.

    Args:
        products_config: Products configuration dict

    Returns:
        dict: Mapping from repo name to (product_name, product_info) tuple
    """
    repo_map = {}
    if not products_config or "products" not in products_config:
        return repo_map

    for product_name, product_info in products_config["products"].items():
        if product_info.get("ignore", False):
            continue
        for repo in product_info.get("repositories", []):
            repo_map[repo] = (product_name, product_info)

    return repo_map


def build_parent_child_map(gh, org, repo_name, issues_list, fetch_parents=False):
    """Build a map of parent issues to their children using GitHub's native sub-issues API.

    Args:
        gh: GitHub connection
        org: Organization/owner name
        repo_name: Repository name
        issues_list: List of issues
        fetch_parents: If True, fetch parent issues that aren't in issues_list

    Returns:
        tuple: (parent_to_children dict, set of child issue numbers, dict of fetched parent issues)
    """
    parent_to_children = {}
    child_issues = set()
    fetched_parents = {}  # issue_number -> issue data (for parents not in issues_list)

    # Create a map of issue numbers to issues
    issue_map = {issue.number: issue for issue in issues_list}

    # First pass: check each issue for sub-issues using GitHub's native API
    for issue in issues_list:
        sub_issues = get_sub_issues(gh, org, repo_name, issue.number)
        if sub_issues:
            children = []
            for sub_issue in sub_issues:
                child_num = sub_issue.get("number")
                if child_num and child_num in issue_map:
                    children.append(child_num)
                    child_issues.add(child_num)

            if children:
                parent_to_children[issue.number] = children

    # Second pass: if fetch_parents is True, check for parent issues not in our list
    if fetch_parents:
        for issue in issues_list:
            # Skip if we already know this is a parent
            if issue.number in parent_to_children:
                continue

            # Check if this issue has a parent
            parent_data = get_parent_issue(gh, org, repo_name, issue.number)
            if parent_data:
                parent_num = parent_data.get("number")
                if parent_num and parent_num not in issue_map:
                    # Parent is not in our issues list - store the data
                    fetched_parents[parent_num] = parent_data
                    child_issues.add(issue.number)

                    # Add to parent_to_children map
                    if parent_num not in parent_to_children:
                        parent_to_children[parent_num] = []
                    parent_to_children[parent_num].append(issue.number)

    return parent_to_children, child_issues, fetched_parents


def convert_issues_to_known_bugs_report(
    md_file, repo_name, issues_map, gh=None, show_parent_child=False, header_offset=0, org=None
):
    """Convert the issue map into a known bug report, e.g. for a release.

    Args:
        md_file: Markdown file object
        repo_name: Repository name
        issues_map: Dictionary of issues grouped by type
        gh: GitHub connection (optional, for parent-child grouping)
        show_parent_child: If True, group sub-issues under their parents
        header_offset: Offset to add to header levels (default 0)
        org: GitHub organization name (for fetching parent issues)
    """
    # Skip if no bugs
    if len(issues_map.get("bug", [])) == 0:
        return

    md_file.new_header(level=2 + header_offset, title=repo_name)

    md_file.new_line(
        "Here is the list of the known bug for the current release, "
        "click on them for more information and possible work around."
    )

    bugs_list = issues_map["bug"]

    # Build parent-child map if requested
    parent_to_children = {}
    child_issue_nums = set()
    if show_parent_child and gh and org:
        parent_to_children, child_issue_nums, _ = build_parent_child_map(gh, org, repo_name, bugs_list)

    table = ["Issue", "Severity", "Status"]
    count = 1

    # Process parent bugs first
    for short_issue in bugs_list:
        # Skip if this is a child issue (will be shown under parent)
        if short_issue.number in child_issue_nums:
            continue

        issue = f"[{repo_name}#{short_issue.number}]({short_issue.html_url}) - {short_issue.title}"
        priority = get_issue_priority(short_issue)
        status = short_issue.state

        table.extend([issue, priority, status])
        count += 1

        # Add child bugs if this is a parent
        if short_issue.number in parent_to_children:
            for child_num in parent_to_children[short_issue.number]:
                # Find the child issue object
                child_issue = next((i for i in bugs_list if i.number == child_num), None)
                if child_issue:
                    child_link = f"  ↳ [{repo_name}#{child_issue.number}]({child_issue.html_url}) - {child_issue.title}"
                    child_priority = get_issue_priority(child_issue)
                    child_status = child_issue.state

                    table.extend([child_link, child_priority, child_status])
                    count += 1

    md_file.new_line()
    md_file.new_table(columns=3, rows=int(len(table) / 3), text=table, text_align="left")


def convert_issues_to_planning_report(
    md_file, repo_name, issues_map, gh=None, show_parent_child=False, header_offset=0, org=None
):
    """Conver the issues into a planning report.

    Args:
        md_file: Markdown file object
        repo_name: Repository name
        issues_map: Dictionary of issues grouped by type
        gh: GitHub connection (optional, for parent-child grouping)
        show_parent_child: If True, group sub-issues under their parents
        header_offset: Offset to add to header levels (default 0)
        org: GitHub organization name (for fetching parent issues)
    """
    from lasso.issues.issues.utils import get_issue_type

    # Check if there are any issues to report
    total_issues = sum(len(issues) for issues in issues_map.values())
    if total_issues == 0:
        return  # Skip empty repositories

    md_file.new_header(level=2 + header_offset, title=repo_name)

    # Combine all issues from all types into a single list
    all_issues = []
    for _, issues in issues_map.items():
        all_issues.extend(issues)

    if len(all_issues) == 0:
        return

    # Build parent-child map if requested
    parent_to_children = {}
    child_issue_nums = set()
    parent_issues_to_add = {}  # parent_number -> parent_issue (for open parents of closed children)

    if show_parent_child and gh and org:
        parent_to_children, child_issue_nums, _ = build_parent_child_map(gh, org, repo_name, all_issues)

        # Check if any closed children have open parent issues
        for parent_num, children in parent_to_children.items():
            parent_issue = next((i for i in all_issues if i.number == parent_num), None)
            if parent_issue:
                # Check if any children are closed while parent is open
                has_closed_children = any(
                    next((i for i in all_issues if i.number == child_num), None)
                    and next((i for i in all_issues if i.number == child_num), None).state == "closed"
                    for child_num in children
                )
                if has_closed_children and parent_issue.state == "open":
                    # Parent should be marked as "in progress"
                    parent_issues_to_add[parent_num] = parent_issue

    # Separate issues into parent issues and standalone issues
    parent_issues = []
    standalone_issues = []

    for issue in all_issues:
        if issue.number in parent_to_children:
            # This issue has children
            parent_issues.append(issue)
        elif issue.number not in child_issue_nums:
            # This issue has no parent (not a child)
            standalone_issues.append(issue)

    # Section 1: Parent Issues with their children
    if parent_issues or parent_issues_to_add:
        md_file.new_header(level=3 + header_offset, title="Parent Issues")
        table = ["Issue", "Type", "Priority / Bug Severity", "Status", "On Deck"]
        count = 1

        # First, add any open parent issues that have closed children
        for parent_num, parent_issue in parent_issues_to_add.items():
            if parent_num in child_issue_nums:
                # This parent is also a child, will be shown under its parent
                continue

            issue = f"[{repo_name}#{parent_issue.number}]({parent_issue.html_url}) - {parent_issue.title}"
            issue_type = get_issue_type(parent_issue) or "unknown"
            priority = get_issue_priority(parent_issue)
            status = "in progress"  # Special status for parents with completed children

            ondeck = ""
            if priority in TOP_PRIORITIES:
                ondeck = "X"

            table.extend([issue, issue_type, priority, status, ondeck])
            count += 1

            # Show the closed children under this parent
            if parent_num in parent_to_children:
                for child_num in parent_to_children[parent_num]:
                    child_issue = next((i for i in all_issues if i.number == child_num), None)
                    if child_issue and child_issue.state == "closed":
                        child_link = f"  ↳ [{repo_name}#{child_issue.number}]({child_issue.html_url}) - {child_issue.title}"
                        child_type = get_issue_type(child_issue) or "unknown"
                        child_priority = get_issue_priority(child_issue)
                        child_status = child_issue.state

                        child_ondeck = ""
                        if child_priority in TOP_PRIORITIES:
                            child_ondeck = "X"

                        table.extend([child_link, child_type, child_priority, child_status, child_ondeck])
                        count += 1

        # Process remaining parent issues
        for short_issue in parent_issues:
            # Skip if already shown as open parent with closed children
            if short_issue.number in parent_issues_to_add:
                continue

            issue = f"[{repo_name}#{short_issue.number}]({short_issue.html_url}) - {short_issue.title}"
            issue_type = get_issue_type(short_issue) or "unknown"
            priority = get_issue_priority(short_issue)
            status = short_issue.state

            ondeck = ""
            if priority in TOP_PRIORITIES:
                ondeck = "X"

            table.extend([issue, issue_type, priority, status, ondeck])
            count += 1

            # Add child issues under this parent
            if short_issue.number in parent_to_children:
                for child_num in parent_to_children[short_issue.number]:
                    # Find the child issue object
                    child_issue = next((i for i in all_issues if i.number == child_num), None)
                    if child_issue:
                        child_link = f"  ↳ [{repo_name}#{child_issue.number}]({child_issue.html_url}) - {child_issue.title}"
                        child_type = get_issue_type(child_issue) or "unknown"
                        child_priority = get_issue_priority(child_issue)
                        child_status = child_issue.state

                        child_ondeck = ""
                        if child_priority in TOP_PRIORITIES:
                            child_ondeck = "X"

                        table.extend([child_link, child_type, child_priority, child_status, child_ondeck])
                        count += 1

        md_file.new_line()
        md_file.new_table(columns=5, rows=int(len(table) / 5), text=table, text_align="left")

    # Section 2: Other Issues (standalone issues without parents)
    if standalone_issues:
        md_file.new_header(level=3 + header_offset, title="Other Issues")
        table = ["Issue", "Type", "Priority / Bug Severity", "Status", "On Deck"]
        count = 1

        for short_issue in standalone_issues:
            issue = f"[{repo_name}#{short_issue.number}]({short_issue.html_url}) - {short_issue.title}"
            issue_type = get_issue_type(short_issue) or "unknown"
            priority = get_issue_priority(short_issue)
            status = short_issue.state

            ondeck = ""
            if priority in TOP_PRIORITIES:
                ondeck = "X"

            table.extend([issue, issue_type, priority, status, ondeck])
            count += 1

        md_file.new_line()
        md_file.new_table(columns=5, rows=int(len(table) / 5), text=table, text_align="left")


def create_md_issue_report(
    org,
    repos,
    issue_state="all",
    start_time=None,
    end_time=None,
    token=None,
    output_report="planning",
    group_by_component=False,
    show_parent_child=False,
):
    """Create the issue report, in Markdown format.

    Args:
        org: GitHub organization name
        repos: List of specific repositories to include (None = all)
        issue_state: State filter ("open", "closed", "all")
        start_time: Start datetime for filtering (ISO 8601)
        end_time: End datetime for filtering (ISO 8601)
        token: GitHub API token
        output_report: Report type ("planning" or "known_bugs")
        group_by_component: If True, group repositories by product/component
        show_parent_child: If True, group sub-issues under their parent issues
    """
    gh = GithubConnection.get_connection(token=token)

    out_report_function_name = f"convert_issues_to_{output_report}_report"
    thismodule = sys.modules[__name__]
    out_report_function = getattr(thismodule, out_report_function_name)

    current_date = datetime.now().strftime("%Y-%m-%d")
    title = "PDS EN Issues" if output_report == "planning" else f"Known Bugs on {current_date}"
    _md_file = MdUtils(file_name="pdsen_issues", title=title)

    # Load products config if grouping by component
    repo_to_product = {}
    if group_by_component:
        products_config = load_products_config()
        if products_config:
            repo_to_product = build_repo_to_product_map(products_config)

    # Get all issues at organization level (much more efficient!)
    _logger.info(f"Searching for issues in organization {org}")
    all_repos_issues = get_org_issues_groupby_type_and_repo(
        gh, org, repos_filter=repos, state=issue_state, start_time=start_time, end_time=end_time
    )

    # Track metrics for summary table
    metrics_by_component = {}  # component_name -> {opened: count, closed: count}
    metrics_by_repo = {}  # repo_name -> {opened: count, closed: count}

    # Calculate metrics from all issues
    for repo_name, issues_map in all_repos_issues.items():
        total_count = 0
        by_type = {}

        for issue_type, issues in issues_map.items():
            count = len(issues)
            by_type[issue_type] = count
            total_count += count

        metrics_by_repo[repo_name] = {"total": total_count, "by_type": by_type}

        # Roll up by component
        if group_by_component and repo_to_product and repo_name in repo_to_product:
            component_name, _ = repo_to_product[repo_name]
        else:
            component_name = "Other"

        if component_name not in metrics_by_component:
            metrics_by_component[component_name] = {"total": 0, "by_type": {}}

        metrics_by_component[component_name]["total"] += total_count

        for issue_type, count in by_type.items():
            if issue_type not in metrics_by_component[component_name]["by_type"]:
                metrics_by_component[component_name]["by_type"][issue_type] = 0
            metrics_by_component[component_name]["by_type"][issue_type] += count

    # Generate report
    if group_by_component and repo_to_product:
        # Group by product
        product_repos = {}  # product_name -> list of (repo_name, issues_map)

        for repo_name, issues_map in all_repos_issues.items():
            # Skip if no issues
            if sum(len(issues) for issues in issues_map.values()) == 0:
                continue

            # Determine product
            if repo_name in repo_to_product:
                product_name, product_info = repo_to_product[repo_name]
            else:
                product_name = "other"

            if product_name not in product_repos:
                product_repos[product_name] = []
            product_repos[product_name].append((repo_name, issues_map))

        # Generate report grouped by product
        for product_name in sorted(product_repos.keys()):
            if product_name != "other":
                _md_file.new_header(level=1, title=f"Component: {product_name}")

            for repo_name, issues_map in sorted(product_repos[product_name]):
                out_report_function(
                    _md_file,
                    repo_name,
                    issues_map,
                    gh=gh,
                    show_parent_child=show_parent_child,
                    header_offset=0,
                    org=org,
                )

    else:
        # Generate report without component grouping
        for repo_name in sorted(all_repos_issues.keys()):
            issues_map = all_repos_issues[repo_name]

            # Skip if no issues
            if sum(len(issues) for issues in issues_map.values()) == 0:
                continue

            out_report_function(
                _md_file,
                repo_name,
                issues_map,
                gh=gh,
                show_parent_child=show_parent_child,
                header_offset=0,
                org=org,
            )

    # Add metrics summary table at the end
    _md_file.new_header(level=1, title="Summary Metrics")

    # Determine what we're counting based on filter
    if issue_state == "closed":
        start_date = start_time.split('T')[0] if start_time else 'start'
        end_date = end_time.split('T')[0] if end_time else 'end'
        metric_description = f"Issues closed between {start_date} and {end_date}"
    elif issue_state == "open":
        metric_description = "Open issues updated in the specified period"
    else:
        metric_description = "All issues in the specified period"

    _md_file.new_line(metric_description)
    _md_file.new_line()

    if group_by_component and metrics_by_component:
        # Component-level metrics
        _md_file.new_header(level=2, title="By Component")
        table = ["Component", "Bug", "Enhancement", "Requirement", "Task", "Theme", "Total"]

        grand_total = 0

        for component_name in sorted(metrics_by_component.keys()):
            metrics = metrics_by_component[component_name]
            bug_count = metrics["by_type"].get("bug", 0)
            enhancement_count = metrics["by_type"].get("enhancement", 0)
            requirement_count = metrics["by_type"].get("requirement", 0)
            task_count = metrics["by_type"].get("task", 0)
            theme_count = metrics["by_type"].get("theme", 0)
            total = metrics["total"]

            grand_total += total

            table.extend([
                component_name,
                str(bug_count),
                str(enhancement_count),
                str(requirement_count),
                str(task_count),
                str(theme_count),
                str(total)
            ])

        # Add total row
        total_bugs = sum(m["by_type"].get("bug", 0) for m in metrics_by_component.values())
        total_enhancements = sum(m["by_type"].get("enhancement", 0) for m in metrics_by_component.values())
        total_requirements = sum(m["by_type"].get("requirement", 0) for m in metrics_by_component.values())
        total_tasks = sum(m["by_type"].get("task", 0) for m in metrics_by_component.values())
        total_themes = sum(m["by_type"].get("theme", 0) for m in metrics_by_component.values())

        table.extend([
            "**TOTAL**",
            f"**{total_bugs}**",
            f"**{total_enhancements}**",
            f"**{total_requirements}**",
            f"**{total_tasks}**",
            f"**{total_themes}**",
            f"**{grand_total}**"
        ])

        _md_file.new_line()
        _md_file.new_table(columns=7, rows=int(len(table) / 7), text=table, text_align="left")
    else:
        # Repository-level metrics only
        table = ["Repository", "Bug", "Enhancement", "Requirement", "Task", "Theme", "Total"]

        grand_total = 0

        for repo_name in sorted(metrics_by_repo.keys()):
            metrics = metrics_by_repo[repo_name]
            bug_count = metrics["by_type"].get("bug", 0)
            enhancement_count = metrics["by_type"].get("enhancement", 0)
            requirement_count = metrics["by_type"].get("requirement", 0)
            task_count = metrics["by_type"].get("task", 0)
            theme_count = metrics["by_type"].get("theme", 0)
            total = metrics["total"]

            grand_total += total

            table.extend([
                repo_name,
                str(bug_count),
                str(enhancement_count),
                str(requirement_count),
                str(task_count),
                str(theme_count),
                str(total)
            ])

        # Add total row
        total_bugs = sum(m["by_type"].get("bug", 0) for m in metrics_by_repo.values())
        total_enhancements = sum(m["by_type"].get("enhancement", 0) for m in metrics_by_repo.values())
        total_requirements = sum(m["by_type"].get("requirement", 0) for m in metrics_by_repo.values())
        total_tasks = sum(m["by_type"].get("task", 0) for m in metrics_by_repo.values())
        total_themes = sum(m["by_type"].get("theme", 0) for m in metrics_by_repo.values())

        table.extend([
            "**TOTAL**",
            f"**{total_bugs}**",
            f"**{total_enhancements}**",
            f"**{total_requirements}**",
            f"**{total_tasks}**",
            f"**{total_themes}**",
            f"**{grand_total}**"
        ])

        _md_file.new_line()
        _md_file.new_table(columns=7, rows=int(len(table) / 7), text=table, text_align="left")

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

    parser.add_argument("--report", default="planning", help="planning or known_bugs, only applies when --format=md")

    parser.add_argument(
        "--group-by-component",
        action="store_true",
        help="Group repositories by product/component from conf/pds-products.yaml (only applies when --format=md)"
    )

    parser.add_argument(
        "--show-parent-child",
        action="store_true",
        help="Group sub-issues under their parent issues (only applies when --format=md)"
    )

    parser.add_argument("--testrail-url", help="URL of testrail")
    parser.add_argument("--testrail-user-email", help="email used to authenticate the user of testrail API")
    parser.add_argument("--testrail-user-token", help="token used to authenticate the user to the testrail API")

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
            end_time=args.end_time,
            token=args.token,
            output_report=args.report,
            group_by_component=args.group_by_component,
            show_parent_child=args.show_parent_child,
        )

    elif args.format == "rst":
        rst_rdd_report = RstRddReport(
            args.github_org, start_time=args.start_time, end_time=args.end_time, build=args.build, token=args.token
        )

        rst_rdd_report.create(args.github_repos)

    elif args.format == "metrics":
        rdd_metrics = MetricsRddReport(
            args.github_org, start_time=args.start_time, end_time=args.end_time, build=args.build, token=args.token
        )

        rdd_metrics.create(args.github_repos)

    elif args.format == "csv":
        csv_report = CsvTestCaseReport(
            args.github_org,
            start_time=args.start_time,
            end_time=args.end_time,
            build=args.build,
            token=args.token,
            testrail_base_url=args.testrail_url,
            testrail_user_email=args.testrail_user_email,
            testrail_user_token=args.testrail_user_token,
        )
        csv_report.create(args.github_repos)

    else:
        _logger.error("unsupported format %s, must be rst or md or metrics", args.format)


if __name__ == "__main__":
    main()
