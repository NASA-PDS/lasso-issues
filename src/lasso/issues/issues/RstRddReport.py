"""A Rdd report for reStructuredText.

Now if only someone could define "Rdd"! 😆
"""
import logging
import os
import sys
from datetime import datetime
from enum import Enum

import rstcloth
from github3.issues.issue import Issue
from github3.issues.issue import ShortIssue
from lasso.issues.github import GithubConnection
from zenhub import Zenhub

from .utils import get_issue_priority
from .utils import has_label
from .utils import ignore_issue

_logger = logging.getLogger(__name__)


def _indent_ok_for_table(content, indent):
    """Indent—ok?—but for a table.

    :param content:
    :param indent:
    :return:
    """
    if indent == 0:
        return content
    else:
        indent = " " * indent
        if isinstance(content, list):
            return ["".join([indent, line]) for line in content]
        elif "\n" in content:
            content_lines = content.split("\n")
            return f"\n{indent}".join(content_lines)
        else:
            return "".join([indent, content])


# Monkey-patching the function used in the rstpackage; should do a pull request eventually
rstcloth.rstcloth._indent = _indent_ok_for_table
_indent = _indent_ok_for_table


class RstClothReferenceable(rstcloth.RstCloth):
    """Apparently this is cloth described in reStructuredText that is also referenceable."""

    def __init__(self, line_width=160):
        """Initializer."""
        super().__init__(line_width=line_width)
        self._deferred_directives = []

    def hyperlink(self, ref, url):
        """Hyperlink the given ``ref`` to ``url``."""
        self._deferred_directives.append(f".. _{ref}: {url}")

    def deferred_directive(self, name, arg=None, fields=None, content=None, indent=0, wrap=True, reference=None):
        """Adds a deferred directive.

        :param name: the directive itself to use
        :param arg: the argument to pass into the directive
        :param fields: fields to append as children underneath the directive
        :param content: the text to write into this element
        :param indent: (optional default=0) number of characters to indent this element
        :param wrap: (optional, default=True) Whether or not to wrap lines to the line_width
        :param reference: (optional, default=None) Reference to call the directive elswhere
        :return:
        """
        _logger.debug("Ignoring wrap parameter, presumably for api consistency. wrap=%s", wrap)
        o = list()
        if reference:
            o.append(".. |{0}| {1}::".format(reference, name))
        else:
            o.append(".. {0}::".format(name))

        if arg is not None:
            o[0] += " " + arg

        if fields is not None:
            for k, v in fields:
                o.append(_indent(":" + k + ": " + str(v), 3))

        if content is not None:
            o.append("")

            if isinstance(content, list):
                o.extend(_indent(content, 3))
            else:
                o.append(_indent(content, 3))

        self._deferred_directives.extend(_indent(o, indent))

    def write(self, filename):
        """Write myself to the given ``filename``.

        :param filename:
        :return:
        """
        dirpath = os.path.dirname(filename)
        if os.path.isdir(dirpath) is False:
            try:
                os.makedirs(dirpath)
            except OSError:
                _logger.info("{0} exists. ignoring.".format(dirpath))

        with open(filename, "w") as f:
            f.write("\n".join(self._data))
            f.write("\n")
            f.write("\n".join(self._deferred_directives))
            f.write("\n")


class PDSIssue(ShortIssue):
    """A PDS-specific issue."""

    def get_rationale(self):
        """Get the rational for this issue."""
        splitted_body = self.body.split("Rationale:")
        if len(splitted_body) == 2:
            return splitted_body[1].replace("\n", " ").replace("\r", " ").replace("*", "").strip()
        else:
            return None


class StatusEmoji(Enum):
    """Enumerate the emojis."""

    SKIP = "|:blue_circle:|"
    TESTING_NEEDED = "|:yellow_circle:|"
    TESTING_COMPLETE = "|:green_circle:|"


class RddReport:
    """The Rdd report."""

    ISSUE_TYPES = ["bug", "requirement", "theme", "enhancement"]  # non hierarchical tickets
    THEME = "theme"
    IGNORED_LABELS = {"wontfix", "duplicate", "invalid", "I&T", "untestable", "task"}
    SKIP_TESTING = "i&t.skip"
    TESTING_COMPLETE = "i&t.done"
    IGNORED_REPOS = {
        "PDS-Software-Issues-Repo",
        "pds-template-repo-python",
        "pdsen-corral",
        "github-actions-base",
        ".github",
        "nasa-pds.github.io",
        "pds-github-util",
        "pds-template-repo-java",
        "kdp",
        "naif-pds4-bundler",
    }
    REPO_INFO = (
        "*{}*\n\n"
        ".. list-table:: \n"
        "   :widths: 15 15 15 15 15 15\n\n"
        "   * - `User Guide <{}>`_\n"
        "     - `Github Repo <{}>`_\n"
        "     - `Issue Tracking <{}/issues>`_ \n"
        "     - `Requirements <{}/tree/main/docs/requirements>`_ \n"
        "     - `Stable Release <{}/releases/latest>`_ \n"
        "     - `Dev Release <{}/releases>`_ \n\n"
    )
    SWG_REPO_NAME = "pds-swg"

    def __init__(self, org, title=None, start_time=None, end_time=None, build=None, token=None):
        """Initializer."""
        # Quiet github3 logging — 😬 This should be user-controllable (command-line, config file) and not
        # forced by the code.
        self._logger = logging.getLogger("github3")
        self._logger.setLevel(level=logging.WARNING)

        # Why bother saving the github3 logger in ``_logger`` if we're just overwriting it with the ``_name`` logger? 🤔
        self._logger = logging.getLogger(__name__)

        self._org = org
        self._gh = GithubConnection.getconnection(token=token)
        self._start_time = start_time
        self._end_time = end_time
        self._build = build
        self._target_build = build.replace("-SNAPSHOT", "")
        self._rst_doc = RstClothReferenceable()

        self._rst_doc.title(title)

    def available_repos(self):
        """Yield available repositories."""
        for _repo in self._gh.repositories_by(self._org):
            if _repo.name not in RstRddReport.IGNORED_REPOS:
                yield _repo

    def add_repo(self, repo):
        """Add a repository."""
        issues_map = self._get_issues_groupby_type(repo, state="closed")
        issue_count = sum([len(issues) for _, issues in issues_map.items()])
        if issue_count > 0:
            self._write_repo_change_section(repo)

    def _get_issues_groupby_type(self, repo, state="closed"):
        """Get the issues grouped by type."""
        issues = {}
        for t in RstRddReport.ISSUE_TYPES:
            issues[t] = []

            labels = [t]
            if self._build:
                labels.append(self._build)

            self._logger.info("get %s issues for build %s", t, self._build)
            type_issues = repo.issues(state=state, labels=",".join(labels), direction="asc")

            for issue in type_issues:
                compare_date = issue.created_at
                if state == "closed":
                    compare_date = issue.closed_at

                if (
                    not ignore_issue(issue.labels(), ignore_labels=RstRddReport.IGNORED_LABELS)
                    and (self._end_time is None or compare_date < datetime.fromisoformat(self._end_time))
                    and (self._start_time is None or compare_date > datetime.fromisoformat(self._start_time))
                ):
                    issues[t].append(issue)

        return issues


class MetricsRddReport(RddReport):
    """A metrics report, which is a kind of Rdd report."""

    def __init__(self, org, start_time=None, end_time=None, build=None, token=None):
        """Initialzer."""
        title = f"Release Metrics for build {build}" if build else ""

        super().__init__(org, title=title, start_time=start_time, end_time=end_time, build=build, token=token)
        self.issues_type_counts = {}
        for t in self.ISSUE_TYPES:
            self.issues_type_counts[t] = 0

        self.issues_type_five_biggest = {}
        for t in self.ISSUE_TYPES:
            self.issues_type_five_biggest[t] = []

        self.bugs_open_closed = {}
        self.bugs_severity = {}

        self.open_bugs = {}

        self.epic_closed_for_the_build = {}

    def create(self, repos):
        """Create."""
        for _repo in self.available_repos():
            if not repos or _repo.name in repos:
                self.add_repo(_repo)

        print("Issues Types")
        print(self.issues_type_counts)

        print("Bug States")
        print(self.bugs_open_closed)

        print("Bug Severity")
        print(self.bugs_severity)

        print("Open High/Critical Bugs")
        for s, bugs in self.open_bugs.items():
            print(s)
            print(bugs)

        print("Closed Epics")
        print(self.epic_closed_for_the_build)

    def _non_bug_metrics(self, type, repo):
        """Non-bug metrics."""
        for issue in repo.issues(
            state="closed", labels=f"{self._target_build},{type}", direction="asc", since=self._start_time
        ):
            if not ignore_issue(issue.labels(), ignore_labels=RstRddReport.IGNORED_LABELS) and (
                not self._end_time or issue.created_at < datetime.fromisoformat(self._end_time)
            ):
                self.issues_type_counts[type] += 1

    def _bug_metrics(self, repo):
        """Bug metrics."""
        for issue in repo.issues(
            state="all", labels=f"{self._target_build},bug", direction="asc", since=self._start_time
        ):
            if not ignore_issue(issue.labels(), ignore_labels=RstRddReport.IGNORED_LABELS) and (
                not self._end_time or issue.created_at < datetime.fromisoformat(self._end_time)
            ):
                # get severity
                severity = "s.unknown"
                for label in issue.labels():
                    if label.name.startswith("s."):
                        severity = label.name
                        break
                if severity in self.bugs_severity.keys():
                    self.bugs_severity[severity] += 1
                else:
                    self.bugs_severity[severity] = 1

                # get state
                if issue.state in self.bugs_open_closed.keys():
                    self.bugs_open_closed[issue.state] += 1
                else:
                    self.bugs_open_closed[issue.state] = 1

                if issue.state == "open" and severity in {"s.critical", "s.high", "s.medium", "s.low"}:
                    self._logger.info("%s#%i %s %s %s", repo, issue.number, issue.title, severity, issue.state)
                    if severity not in self.open_bugs:
                        self.open_bugs[severity] = ""
                    self.open_bugs[severity] += "%s#%i %s\n" % (repo, issue.number, issue.title)

                # get count
                if issue.state == "closed":
                    self.issues_type_counts["bug"] += 1
                else:
                    self._logger.info("this issues is still open %s#%i: %s", repo, issue.number, issue.title)

    def _get_epics_count(self, repo):
        """Get the epics count."""
        epics = repo.issues(state="closed", labels=f"{self._target_build},Epic")
        n = 0

        for _ in epics:
            n += 1

        return n

    def _get_issue_type_count(self, repo):
        """Get issue type count."""
        # count epics
        n_epics = self._get_epics_count(repo)
        if n_epics > 0:
            self.epic_closed_for_the_build[repo.name] = n_epics

        for t in RstRddReport.ISSUE_TYPES:
            if t == "bug":
                self._bug_metrics(repo)
            else:
                self._non_bug_metrics(t, repo)

    def add_repo(self, repo):
        """Add the ``repo``."""
        self._logger.debug("add repo %s", repo)
        self._get_issue_type_count(repo)


class EpicFactory:
    """A factory of epics."""

    def __init__(self, zenhub, logger):
        """Initializer."""
        self._zenhub = zenhub
        self._logger = logger

    def create_enhancement(self, repo, gh_issue, build):
        """Create enhancement."""
        self._logger.debug("Create enhancement for repo %s for issue %i", repo.name, gh_issue.number)

        enhancement = Enhancement(gh_issue, log=self._logger)
        self._logger.debug(enhancement.type.value)
        if (
            enhancement.type.value == EnhancementTypes.THEME.value
            or enhancement.type.value == EnhancementTypes.EPIC.value
        ):  # not leaf in the tree
            self._logger.debug("search for epic children")
            epic_child_issues = self._zenhub.get_epic_data(repo.id, gh_issue.number)
            self._logger.debug(epic_child_issues)
            for issue in epic_child_issues["issues"]:
                if issue["repo_id"] == repo.id:
                    self._logger.debug("github api request, get issue %i", issue["issue_number"])
                    gh_child_issue = repo.issue(issue["issue_number"])
                    if has_label(gh_child_issue, build) and gh_child_issue.state == "closed":
                        enhancement_child = self.create_enhancement(repo, gh_child_issue, build)
                        enhancement.add_child(enhancement_child)

        return enhancement


class EnhancementTypes(Enum):
    """Enumeration of types of enhancements."""

    THEME = "theme"
    EPIC = "epic"
    ENHANCEMENT = "enhancement"
    REQUIREMENT = "requirement"
    BUG = "bug"
    TASK = "task"


class Enhancement(Issue):
    """An ehancement, a kind of issue."""

    def __init__(self, issue, log=None):
        """Initializer."""
        if log:
            self._logger = log
            log.debug("Create enhancement for issue %i", issue.number)

        self.issue = issue
        self.children = []
        self.type = Enhancement._get_enhancement_type(issue)

    def crawl(self):
        """Crawl."""
        self._logger.debug("yield issue %i", self.issue.number)
        yield self
        for child in self.children:
            self._logger.debug("crawl issue %i", child.issue.number)
            yield from child.crawl()

    @staticmethod
    def _get_enhancement_type(issue):
        """Get enhancement type."""
        enhancement_type = EnhancementTypes.TASK
        for label in issue.labels():
            if label.name in {item.value for item in EnhancementTypes}:
                enhancement_type = EnhancementTypes(label.name)
                break

        return enhancement_type

    def add_child(self, issue):
        """Add a child."""
        self.children.append(issue)


class RstRddReport(RddReport):
    """The reStructuredText format Rdd report."""

    ZENHUB_TOKEN = "ZENHUB_TOKEN"

    def __init__(self, org, title=None, start_time=None, end_time=None, build=None, token=None):
        """Initializer."""
        if not title:
            build_text = f"(Build {build})" if build else ""
            title = "Release Description Document " + build_text
        super().__init__(org, title=title, start_time=start_time, end_time=end_time, build=build, token=token)

        self._rst_doc = RstClothReferenceable(line_width=120)
        self._rst_doc.title(title)

        if RstRddReport.ZENHUB_TOKEN not in os.environ.keys():
            self._logger.error("missing %s environment variable", RstRddReport.ZENHUB_TOKEN)
            sys.exit(1)

        zenhub_token = os.environ.get("ZENHUB_TOKEN")
        self._zenhub = Zenhub(zenhub_token)

    def _get_change_requests(self):
        """Get change requests."""
        self._logger.info(
            "Getting change requests from %s/%s for build %s", self._org, RstRddReport.SWG_REPO_NAME, self._target_build
        )
        swg_repo = self._gh.repository(self._org, RstRddReport.SWG_REPO_NAME)

        labels = ["change-request"]
        if self._build:
            labels.append(self._build)

        change_requests = swg_repo.issues(state="closed", labels=",".join(labels))

        columns = ["Issue", "Title", "Rationale"]
        data = []
        for cr in change_requests:
            self._rst_doc.hyperlink(f"{RstRddReport.SWG_REPO_NAME}_{cr.number}", cr.html_url)
            cr.__class__ = PDSIssue  # python cast
            data.append(
                [f"{RstRddReport.SWG_REPO_NAME}_{cr.number}_ {cr.title}".replace("|", ""), cr.title, cr.get_rationale()]
            )

        self._rst_doc.table(columns, data=data)

    def _add_repo_description(self, repo):
        """Add repo description."""
        repo_info = RstRddReport.REPO_INFO.format(
            repo.description,
            repo.homepage or repo.html_url + "#readme",
            repo.html_url,
            repo.html_url,
            repo.html_url,
            repo.html_url,
            repo.html_url,
        )
        self._rst_doc._add(repo_info)

    def _get_theme_trees(self, repo):
        """Get theme trees."""
        labels = [self.THEME, self._target_build]
        # Only want to see closed themes in the RDD, anything not closed should be in the deferrals
        theme_issues = repo.issues(state="closed", labels=",".join(labels), direction="asc")
        theme_trees = []
        for theme_issue in theme_issues:
            theme = EpicFactory(self._zenhub, self._logger).create_enhancement(repo, theme_issue, self._target_build)
            theme_trees.append(theme)
        return theme_trees

    def _write_repo_change_section(self, repo):
        """Wrirte repo change section."""
        issue_map = self._get_issues_groupby_type(repo, state="closed")

        issue_count = sum([len(issues) for issues in issue_map.values()])

        if issue_count:
            self._rst_doc.content("--------")
            self._rst_doc.newline()
            self._rst_doc.h2(repo.name.capitalize())
            self._add_repo_description(repo)
            planned_tickets = self._add_planned_updates(repo)
            self._add_other_updates(repo, issue_map, ignore_tickets=planned_tickets)

    def _add_other_updates(self, repo, issues_map, ignore_tickets=None):
        """Add other updates."""
        for type, issues in issues_map.items():
            issues_map[type] = list(set(issues) - ignore_tickets)

        issue_count = sum([len(issues) for issues in issues_map.values()])

        if issue_count > 0:
            self._rst_doc.h3("Other Updates")
            for issue_type, issues in issues_map.items():
                if issues and issue_type != RddReport.THEME:
                    self._add_rst_repo_change_sub_section(repo, issue_type, issues, ignore_tickets=ignore_tickets)

    def _flush_theme_updates(self, theme_line, ticket_lines):
        """Flush theme updates."""
        theme_line = theme_line
        self._rst_doc.h4(theme_line)

        if ticket_lines:
            columns = ["Issue", "I&T Status", "Level", "Priority / Bug Severity"]
            self._rst_doc.table(columns, data=ticket_lines)
        else:
            self._rst_doc.content(
                "No requirements, significant enhancements, or bug fixes identified for this Build."
                + " See theme for more details."
            )

        self._rst_doc.newline()

    @staticmethod
    def _testing_status(issue):
        """Testing status."""
        for label in issue.labels():
            if label.name == RstRddReport.SKIP_TESTING:
                return StatusEmoji.SKIP.value
            elif label.name == RstRddReport.TESTING_COMPLETE:
                return StatusEmoji.TESTING_COMPLETE.value

        return StatusEmoji.TESTING_NEEDED.value

    @staticmethod
    def _get_theme_head(repo, issue):
        """Get theme head."""
        return f"`{repo.name}#{issue.number}`_ {issue.title}"

    def _add_planned_updates(self, repo):
        """Add planned updates."""
        themes = self._get_theme_trees(repo)
        self._rst_doc.h3("Planned Updates")
        planned_tickets = set()
        done = False
        for theme in themes:
            theme_crawler = theme.crawl()
            theme = next(theme_crawler)
            planned_tickets.add(theme.issue)
            self._rst_doc.hyperlink(f"{repo.name}#{theme.issue.number}", theme.issue.html_url)
            theme_head = RstRddReport._get_theme_head(repo, theme.issue)
            data = []
            for enhancement in theme_crawler:
                issue = enhancement.issue
                if not ignore_issue(issue.labels(), ignore_labels=RstRddReport.IGNORED_LABELS):
                    self._logger.debug("crawl theme tree %i", issue.number)
                    self._rst_doc.hyperlink(f"{repo.name}#{issue.number}", issue.html_url)

                    i_and_t = RstRddReport._testing_status(issue)
                    priority = get_issue_priority(issue)
                    data.append(
                        [
                            f"`{repo.name}#{issue.number}`_ {issue.title}".replace("|", ""),
                            i_and_t,
                            enhancement.type.value,
                            priority,
                        ]
                    )
                    if enhancement.type.value == "requirement" and priority == "unknown":
                        self._log_missing_priority(repo.name, issue.number)

                    planned_tickets.add(issue)

            self._flush_theme_updates(theme_head, data)
            done = True

        if not done:
            self._rst_doc.content("No planned updates realized for this build in this repository.")
            self._rst_doc.newline()

        return planned_tickets

    def _add_rst_repo_change_sub_section(self, repo, type, issues, ignore_tickets=None):
        """Add reStructuredText repo change sub section."""
        data = []
        for issue in issues:
            if issue.number not in ignore_tickets:
                i_and_t = RstRddReport._testing_status(issue)
                self._rst_doc.hyperlink(f"{repo.name}#{issue.number}", issue.html_url)
                priority = get_issue_priority(issue)
                data.append([f"`{repo.name}#{issue.number}`_ {issue.title}".replace("|", ""), i_and_t, priority])
                if type in {"bug", "requirement"} and priority == "unknown":
                    self._log_missing_priority(repo.name, issue.number)
        if data:
            self._rst_doc.h4(type.capitalize() + "s")
            columns = ["Issue", "I&T Status", "Priority / Bug Severity"]
            self._rst_doc.table(columns, data=data)

    def _log_missing_priority(self, repo_name, issue_number):
        """Log missing priority."""
        self._logger.warning("%s#%d misses priority", repo_name, issue_number)
        self._logger.info("update at https://github.com/NASA-PDS/%s/issues/%d", repo_name, issue_number)

    def _add_software_changes(self, repos):
        """Add software changes."""
        self._logger.info("Add software changes")
        self._rst_doc.h1("Software Changes")
        self._rst_doc.content(
            "The changes types are 'Bug', 'Enhancement' or 'Requirement'. "
            "For each software repository, the changes are listed in 2 categories: "
        )
        self._rst_doc.newline()
        self._rst_doc.li("Planned Updates")
        self._rst_doc.li("Other Updates")
        self._rst_doc.newline()

        self._rst_doc.content(
            "The 'Planned Updates' are organized by 'Themes' (or 'Release Themes'), which are defined in advance "
            f"and approved by the PDS Software Working Group (see `Plan {self._build}`_)"
        )
        self._rst_doc.content(
            "The 'Other Updates' occurs during the build cycle witout being planned or attached to a theme. "
            "They are organized by types (bug, enhancements, requirements, tasks). Any updates that require "
            "a de-scope of planned tasks are reviewed by the PDS Software Working Group."
        )
        self._rst_doc.newline()
        self._rst_doc.content(
            "The deliveries are validated by the development team and go through an additional Integration & "
            "Test process, as applicable, as indicated by the ```Testing Status``` column in the tables below. "
            "There are 3 possible statuses for testing:"
        )
        self._rst_doc.newline()
        self._rst_doc.li(
            f"{StatusEmoji.SKIP.value} Skip Testing - Testing is not needed for this ticket. These are determined at "
            "the discretion of the team based upon the technical or operational nature of the closed task.",
            wrap=False,
        )
        self._rst_doc.li(f"{StatusEmoji.TESTING_NEEDED.value} Testing Needed")
        self._rst_doc.li(
            f"{StatusEmoji.TESTING_COMPLETE.value} Testing Complete - Initial testing complete, and test "
            "cases/results documented.",
            wrap=False,
        )
        self._rst_doc.newline()

        for _repo in self.available_repos():
            if not repos or _repo.name in repos:
                self._write_repo_change_section(_repo)

    def _add_liens(self):
        """Add liens."""
        self._logger.info("Add liens")
        self._rst_doc.h1("Liens")
        self._get_change_requests()

    def _add_software_catalogue(self):
        """Add sofware catalog."""
        self._logger.info("Add software catalog")
        self._rst_doc.h1("Engineering Node Software Catalog")
        self._rst_doc.content(
            f"The Engineering Node Software resources are listed in the `Software Release Summary ({self._build})`_"
        )
        self._rst_doc.newline()
        self._rst_doc.hyperlink(
            f"Software Release Summary ({self._build})",
            f"https://nasa-pds.github.io/releases/{self._build[1:]}/index.html",
        )

    def _add_install_and_operation(self):
        """Add and install operation."""
        self._logger.info("Add installation and operations")
        self._rst_doc.h1("Installation and Operation")
        self._rst_doc.content(
            "PDS Engineering Node Software have 3 different venues/purposes for execution: Standalone, "
            "Discipline Node Deployment or Engineering Node-only Deployment"
        )

        self._rst_doc.content(
            "For the Installation and Operation manual see the `user"
            "s manuals` in the software summary sections below:"
        )

        self._add_li("`PDS Standalone`_")
        self._add_li("`PDS Discipline Nodes`_")
        self._add_li("`PDS Engineering Node Only`_")

        self._rst_doc.hyperlink(
            "PDS Standalone", "https://nasa-pds.github.io/releases/11.1/index.html#standalone-tools-and-libraries"
        )

        self._rst_doc.hyperlink(
            "PDS Discipline Nodes", "https://nasa-pds.github.io/releases/11.1/index.html#discipline-node-services"
        )

        self._rst_doc.hyperlink(
            "PDS Engineering Node Only", "https://nasa-pds.github.io/releases/11.1/index.html#enineering-node-services"
        )

        self._rst_doc.newline()

    def _add_li(self, s):
        self._rst_doc.newline()
        self._rst_doc.li(s, wrap=False)

    def _add_reference_docs(self):
        self._logger.info("Add reference docs")
        self._rst_doc.h1("Reference documents")
        self._rst_doc.content(
            "This section details the controlling and applicable documents referenced for this release. "
            "The controlling documents are as follows:"
        )

        self._add_li("PDS Level 1, 2 and 3 Requirements, April 20, 2017.")
        self._add_li("PDS4 Project Plan, July 17, 2013.")
        self._add_li("PDS4 System Architecture Specification, Version 1.3, September 1, 2013.")
        self._add_li("PDS4 Operations Concept, Version 1.0, September 1, 2013.")
        self._add_li(
            "PDS Harvest Tool Software Requirements and Design Document (SRD/SDD), Version 1.2, September 1, 2013."
        )
        self._add_li(
            "PDS Preparation Tools Software Requirements and Design Document (SRD/SDD), Version 0.3, "
            "September 1, 2013."
        )
        self._add_li(
            "PDS Registry Service Software Requirements and Design Document (SRD/SDD), Version 1.1, "
            "September 1, 2013."
        )
        self._add_li(
            "PDS Report Service Software Requirements and Design Document (SRD/SDD), Version 1.1, " "September 1, 2013."
        )
        self._add_li(
            "PDS Search Service Software Requirements and Design Document (SRD/SDD), Version 1.0, " "September 1, 2013."
        )
        self._add_li("PDS Search Scenarios, Version 1.0, September 1, 2013.")
        self._add_li("PDS Search Protocol, Version 1.2, March 21, 2014.")
        self._add_li("PDAP Search Protocol, Version 1.0, March 21, 2014.")
        self._add_li(
            "PDS Security Service Software Requirements and Design Document (SRD/SDD), Version 1.1, "
            "September 1, 2013."
        )
        self._add_li("`PDS Deep Archive Software Requirements and Design Document (SRD/SDD)`_")
        self._add_li("`PDS DOI Service Requirements and Design Document (SRD/SDD)`_")

        self._rst_doc.newline()

        self._rst_doc.hyperlink(
            "PDS Deep Archive Software Requirements and Design Document (SRD/SDD)",
            "https://github.com/NASA-PDS/pds-deep-archive/blob/master/docs/"
            "pds4_nssdca_delivery_design_20191219.docx",
        )
        self._rst_doc.hyperlink(
            "PDS DOI Service Requirements and Design Document (SRD/SDD)",
            "https://github.com/NASA-PDS/pds-doi-service/blob/master/docs/design/pds-doi-service-srd.md",
        )

    def _add_introduction(self):
        """Add intro."""
        self._logger.info("Add introduction")
        self._rst_doc.content(
            "This release of the PDS4 System is intended as an operational release of the system components to date."
        )

        if self._build:
            self._rst_doc.content(f"The original plan for this release can be found here: `plan {self._build}`_")
            self._rst_doc.newline()
            self._rst_doc.content("The following sections can be found in this document:")
            self._rst_doc.hyperlink(
                f"plan {self._target_build}", f"https://nasa-pds.github.io/releases/{self._build[1:]}/plan.html"
            )  # remove B prefix from the build code

        self._rst_doc.newline()
        self._rst_doc.directive("toctree", fields=[("glob", ""), ("maxdepth", 3)], content="rdd.rst")
        self._rst_doc.newline()

    def _add_standard_and_information_model_changes(self):
        self._logger.info("Add standard updates")
        im_repo = "pds4-information-model"

        self._rst_doc.h1("PDS4 Standards and Information Model Changes")
        self._rst_doc.content(
            "This section details the changes to the PDS4 Standards and Information Model approved by the PDS4 "
            "Change Control Board and implemented by the PDS within the latest build period."
        )

        columns = ["Ref", "Title"]

        data = []

        repository = self._gh.repository(self._org, im_repo)

        labels = ["pending-scr"]
        if self._target_build:
            labels.append(self._target_build)

        for issue in repository.issues(
            state="closed", labels=",".join(labels), direction="asc", since=self._start_time
        ):
            self._rst_doc.hyperlink(f"{im_repo}#{issue.number}", issue.html_url)
            data.append([f"`{im_repo}#{issue.number}`_".replace("|", ""), issue.title])

        if data:
            self._rst_doc.table(columns, data=data)
        else:
            self._rst_doc.newline()
            self._rst_doc.content("No PDS4 Standards Updates")
            self._rst_doc.newline()

    def create(self, repos, filename):
        """Create."""
        self._logger.info("Create RDD rst")
        self._add_introduction()
        self._add_standard_and_information_model_changes()
        self._add_software_changes(repos)
        self._add_liens()
        self._add_software_catalogue()
        self._add_install_and_operation()
        self._add_reference_docs()
        self.write(filename)

    def add_repo(self, repo):
        """Add ``repo``."""
        issues_map = self._get_issues_groupby_type(repo, state="closed")
        issue_count = sum([len(issues) for _, issues in issues_map.items()])

        if issue_count > 0:
            self._write_repo_change_section(repo)

    def write(self, filename):
        """Write to the file named ``filename``."""
        self._logger.info("Create file %s", filename)
        self._rst_doc.write(filename)
