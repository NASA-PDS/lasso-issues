"""pds-evidence CLI: orchestrate the PDS EN Evidence Collector (issue #65).

Collects GitHub issues, PRs, and releases for a date range across NASA-PDS
repositories and writes a canonical evidence.json file.
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

from lasso.issues.argparse import add_standard_arguments
from lasso.issues.evidence.collector_issues import collect_issues
from lasso.issues.evidence.collector_issues import discover_repos
from lasso.issues.evidence.collector_prs import collect_prs
from lasso.issues.evidence.collector_releases import collect_releases
from lasso.issues.evidence.correlator import correlate
from lasso.issues.evidence.schema import EvidenceDocument
from lasso.issues.evidence.schema import EvidenceMetadata
from lasso.issues.github import GithubConnection

try:
    from lasso.issues import VERSION
except ImportError:
    VERSION = "unknown"

_logger = logging.getLogger(__name__)

DEFAULT_ORG = "NASA-PDS"
DEFAULT_OUTPUT = "evidence.json"


def build_evidence_document(
    org: str,
    start_date: str,
    end_date: str,
    issues: list,
    prs: list,
    releases: list,
    correlation_log: list,
    repo_count: int,
) -> dict:
    """Assemble the canonical EvidenceDocument dict.

    All artifact lists are sorted deterministically by (repo, id) so that
    the same inputs always produce the same output.

    Args:
        org: GitHub organization name
        start_date: ISO 8601 date (YYYY-MM-DD)
        end_date: ISO 8601 date (YYYY-MM-DD)
        issues: Correlated EvidenceIssue list
        prs: Correlated EvidencePR list
        releases: Correlated EvidenceRelease list
        correlation_log: List of log strings from the correlator
        repo_count: Number of repositories searched

    Returns:
        dict matching the EvidenceDocument schema
    """
    generated_at = datetime.now(tz=timezone.utc).isoformat()

    metadata = EvidenceMetadata(
        org=org,
        start_date=start_date,
        end_date=end_date,
        generated_at=generated_at,
        tool_version=VERSION,
        repo_count=repo_count,
    )

    sorted_issues = sorted(issues, key=lambda i: (i['repo'], i['id']))
    sorted_prs = sorted(prs, key=lambda p: (p['repo'], p['id']))
    sorted_releases = sorted(releases, key=lambda r: (r['repo'], r['published_at'] or ''))

    return EvidenceDocument(
        metadata=metadata,
        issues=sorted_issues,
        pull_requests=sorted_prs,
        releases=sorted_releases,
        correlation_log=sorted(correlation_log),
    )


def write_evidence(document: dict, output_path: str) -> None:
    """Write the evidence document to JSON.

    Args:
        document: EvidenceDocument dict
        output_path: File path to write (created or overwritten)
    """
    path = Path(output_path)
    with path.open('w', encoding='utf-8') as fh:
        json.dump(document, fh, indent=2, sort_keys=True, default=str)
    _logger.info("Evidence written to %s", path)


def write_validation_log(document: dict, output_path: str) -> None:
    """Write a validation summary log alongside the evidence JSON.

    Args:
        document: EvidenceDocument dict
        output_path: Path of the evidence.json file (log is written next to it)
    """
    log_path = Path(output_path).with_name(Path(output_path).stem + '-validation.log')
    issues = document['issues']
    prs = document['pull_requests']
    releases = document['releases']
    correlation_log = document['correlation_log']
    metadata = document['metadata']

    linked_issues = sum(1 for i in issues if i['linked_prs'])
    linked_prs = sum(1 for p in prs if p['linked_issues'])
    linked_releases = sum(1 for r in releases if r['linked_prs'])

    warnings = []
    if not issues:
        warnings.append("WARNING: No issues collected — check date range and org/repo scope")
    if not prs:
        warnings.append("WARNING: No pull requests collected")

    lines = [
        f"Evidence Validation Log",
        f"Generated: {metadata['generated_at']}",
        f"Org: {metadata['org']}  Date range: {metadata['start_date']} to {metadata['end_date']}",
        f"Repos searched: {metadata['repo_count']}",
        f"",
        f"Counts:",
        f"  issues:        {len(issues)} ({linked_issues} linked to PRs)",
        f"  pull_requests: {len(prs)} ({linked_prs} linked to issues)",
        f"  releases:      {len(releases)} ({linked_releases} linked to PRs)",
        f"  correlation log entries: {len(correlation_log)}",
        f"",
    ]
    if warnings:
        lines += warnings + ['']

    with log_path.open('w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))

    _logger.info("Validation log written to %s", log_path)


def main():
    """Main entrypoint for pds-evidence CLI."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Collect GitHub issues, PRs, and releases for PDS EN status reporting.",
    )
    add_standard_arguments(parser)

    parser.add_argument("--org", default=DEFAULT_ORG, help="GitHub organization (default: NASA-PDS)")
    parser.add_argument(
        "--repos",
        nargs="*",
        metavar="REPO",
        help="Repository names to include. If omitted, all org repos are collected.",
    )
    parser.add_argument(
        "--exclude-config",
        metavar="PATH",
        help="Path to a pds-products.yaml-style YAML. Repos under products with ignore:true are excluded.",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date for collection (YYYY-MM-DD, inclusive).",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date for collection (YYYY-MM-DD, inclusive).",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--token", help="GitHub API token (or set GITHUB_TOKEN env var).")

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel, format="%(levelname)s %(message)s")

    try:
        _validate_dates(args.start_date, args.end_date)
    except ValueError as exc:
        _logger.error("Invalid date argument: %s", exc)
        sys.exit(1)

    gh = GithubConnection.get_connection(token=args.token)

    _logger.info("Discovering repositories in %s", args.org)
    try:
        repos = discover_repos(gh, args.org, repos_filter=args.repos, exclude_config_path=args.exclude_config)
    except Exception as exc:
        _logger.exception("Failed to discover repositories: %s", exc)
        sys.exit(1)

    if not repos:
        _logger.error("No repositories found to collect from. Check --repos or --org.")
        sys.exit(1)

    _logger.info("Collecting issues from %s to %s across %d repos", args.start_date, args.end_date, len(repos))
    try:
        issues = collect_issues(gh, args.org, repos, args.start_date, args.end_date)
        prs = collect_prs(gh, args.org, repos, args.start_date, args.end_date)
        releases = collect_releases(gh, args.org, repos, args.start_date, args.end_date)
    except Exception as exc:
        _logger.exception("Collection failed: %s", exc)
        sys.exit(1)

    _logger.info("Running correlation engine")
    corr_issues, corr_prs, corr_releases, corr_log = correlate(issues, prs, releases)

    document = build_evidence_document(
        org=args.org,
        start_date=args.start_date,
        end_date=args.end_date,
        issues=corr_issues,
        prs=corr_prs,
        releases=corr_releases,
        correlation_log=corr_log,
        repo_count=len(repos),
    )

    write_evidence(document, args.output)
    write_validation_log(document, args.output)

    _logger.info(
        "Done. %d issues, %d PRs, %d releases collected.",
        len(corr_issues), len(corr_prs), len(corr_releases),
    )


def _validate_dates(start_date: str, end_date: str) -> None:
    """Validate date strings and their ordering.

    Args:
        start_date: YYYY-MM-DD string
        end_date: YYYY-MM-DD string

    Raises:
        ValueError: if either date is malformed or start > end
    """
    fmt = "%Y-%m-%d"
    start_dt = datetime.strptime(start_date, fmt)
    end_dt = datetime.strptime(end_date, fmt)
    if start_dt > end_dt:
        raise ValueError(f"--start-date {start_date} is after --end-date {end_date}")


if __name__ == "__main__":
    main()
