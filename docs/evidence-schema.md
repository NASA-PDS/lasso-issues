# evidence.json Schema

This document describes the canonical output format produced by `pds-evidence`.

## Top-level structure

```json
{
  "metadata":        { ... },
  "issues":          [ ... ],
  "pull_requests":   [ ... ],
  "releases":        [ ... ],
  "correlation_log": [ ... ]
}
```

---

## `metadata`

| Field | Type | Description |
|---|---|---|
| `org` | string | GitHub organization name (e.g. `NASA-PDS`) |
| `start_date` | string (YYYY-MM-DD) | Inclusive collection start date |
| `end_date` | string (YYYY-MM-DD) | Inclusive collection end date |
| `generated_at` | string (ISO 8601) | UTC timestamp when the file was generated |
| `tool_version` | string | Version of `lasso-issues` used |
| `repo_count` | integer | Number of repositories searched |

---

## `issues[]`

Each entry is a closed GitHub issue normalized to the following fields:

| Field | Type | Description |
|---|---|---|
| `id` | integer | GitHub internal issue ID |
| `repo` | string | Repository name (without org prefix) |
| `number` | integer | Issue number within the repo |
| `title` | string | Issue title |
| `state` | string | `open` or `closed` |
| `labels` | string[] | List of label names |
| `opened_at` | string (ISO 8601) or null | When the issue was created |
| `closed_at` | string (ISO 8601) or null | When the issue was closed |
| `html_url` | string | GitHub URL |
| `linked_prs` | integer[] | PR numbers (same repo) linked via body references |
| `linked_releases` | string[] | Release tags linked transitively via closing PRs |
| `closing_release` | string or null | Earliest release tag that includes this issue |

---

## `pull_requests[]`

Each entry is a merged pull request:

| Field | Type | Description |
|---|---|---|
| `id` | integer | GitHub internal PR ID |
| `repo` | string | Repository name |
| `number` | integer | PR number |
| `title` | string | PR title |
| `state` | string | Always `closed` for merged PRs |
| `merged_at` | string (ISO 8601) or null | Merge timestamp |
| `author` | string or null | GitHub login of the PR author |
| `html_url` | string | GitHub URL |
| `body` | string | PR description (raw, may be empty) |
| `linked_issues` | integer[] | Issue numbers (same repo) linked via `closes #N` etc. |
| `linked_releases` | string[] | Release tags that reference this PR in their body |

Draft PRs are excluded from collection.

---

## `releases[]`

Each entry is a GitHub Release or (as fallback) a version tag:

| Field | Type | Description |
|---|---|---|
| `id` | integer or null | GitHub release ID; `null` for tag-fallback records |
| `repo` | string | Repository name |
| `tag` | string | Git tag name (e.g. `v1.2.3`) |
| `name` | string | Release display name (falls back to tag if blank) |
| `published_at` | string (ISO 8601) or null | Publication timestamp |
| `body_summary` | string | First 500 chars of the release body |
| `linked_prs` | integer[] | PR numbers referenced in the release body |
| `is_prerelease` | boolean | True if marked as a pre-release on GitHub |
| `html_url` | string | GitHub URL |

---

## `correlation_log[]`

A sorted list of human-readable strings describing every linkage established
by the correlation engine. Example entries:

```
Issue testrepo#42 linked to PR #17 via PR body reference
Release testrepo@v1.0.0 linked to PR #17 via release body reference
Issue testrepo#42 transitively linked to release v1.0.0 via closing PR #17
```

---

## Validation log

Alongside `evidence.json`, a file named `evidence-validation.log` is written
with per-section counts and any collection warnings.

---

## Sorting

All artifact lists are sorted deterministically:
- `issues` and `pull_requests`: by `(repo, id)` ascending
- `releases`: by `(repo, published_at)` ascending
- `correlation_log`: alphabetically

This ensures that identical inputs always produce byte-for-byte identical output.
