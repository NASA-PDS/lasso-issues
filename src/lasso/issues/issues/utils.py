"""Utilities."""
ISSUE_TYPES = ["bug", "enhancement", "requirement", "theme"]
TOP_PRIORITIES = ["p.must-have", "s.high", "s.critical"]
IGNORE_LABELS = ["wontfix", "duplicate", "invalid"]


def get_issue_type(issue):
    """Get issue type."""
    for label in issue.labels():
        if label.name in ISSUE_TYPES:
            return label.name


def get_issue_priority(short_issue):
    """Get issue priority."""
    for label in short_issue.labels():
        if "p." in label.name or "s." in label.name:
            return label.name

    return "unknown"


def ignore_issue(labels, ignore_labels=IGNORE_LABELS):
    """Ignore issue."""
    for label in labels:
        if label.name in ignore_labels:
            return True

    return False


def get_issues_groupby_type(repo, state="all", start_time=None, ignore_types=None):
    """Get issues grouped by type."""
    issues = {}
    for t in ISSUE_TYPES:
        print(f"++++++++{t}")
        if ignore_types and t in ignore_types:
            continue

        issues[t] = []
        for issue in repo.issues(state=state, labels=t, direction="asc", since=start_time):
            if not ignore_issue(issue.labels()):
                issues[t].append(issue)

    return issues


def get_labels(gh_issue):
    """Get Label Names.

    Return list of label names for easier access.
    """
    labels = []
    for label in gh_issue.labels():
        labels.append(label.name)

    return labels


def has_label(gh_issue, label_name):
    """Has label."""
    for _label in gh_issue.labels():
        if _label.name == label_name:
            return True
    return False


def is_theme(labels, zen_issue):
    """Check If Issue Is a Release Theme.

    Use the input Github Issue object and Zenhub Issue object to check:
    * if issue is an Epic (Zenhub)
    * if issue contains a `theme` label
    """
    if zen_issue["is_epic"]:
        if "theme" in labels:
            return True
