"""Integration tests for pds-evidence CLI (issue #65).

Requires a valid GITHUB_TOKEN environment variable.
Run via: pytest tests/evidence/test_cli.py -m integration
"""
import json
import os
import subprocess
import tempfile

import pytest


@pytest.mark.integration
class TestPdsEvidenceCli:
    """Integration tests for the pds-evidence CLI."""

    def _run(self, args, cwd=None):
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            pytest.skip("GITHUB_TOKEN environment variable not set")
        return subprocess.run(
            ["pds-evidence", "--token", token] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    def test_produces_evidence_json_with_required_keys(self):
        """Verify evidence.json is written with all top-level schema keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run(
                [
                    "--org", "NASA-PDS",
                    "--repos", "lasso-issues",
                    "--start-date", "2026-01-01",
                    "--end-date", "2026-07-11",
                    "--output", os.path.join(tmpdir, "evidence.json"),
                ],
                cwd=tmpdir,
            )

            assert result.returncode == 0, (
                f"pds-evidence exited with code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

            evidence_path = os.path.join(tmpdir, "evidence.json")
            assert os.path.exists(evidence_path), f"evidence.json not written\nstderr: {result.stderr}"

            with open(evidence_path) as fh:
                doc = json.load(fh)

            for key in ("metadata", "issues", "pull_requests", "releases", "correlation_log"):
                assert key in doc, f"Missing top-level key '{key}' in evidence.json"

    def test_metadata_fields_populated(self):
        """Verify metadata block has all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "evidence.json")
            result = self._run(
                ["--repos", "lasso-issues", "--start-date", "2026-06-01", "--end-date", "2026-07-11", "--output", out]
            )
            assert result.returncode == 0, result.stderr

            with open(out) as fh:
                doc = json.load(fh)

            meta = doc["metadata"]
            for field in ("org", "start_date", "end_date", "generated_at", "tool_version", "repo_count"):
                assert field in meta, f"Missing metadata field '{field}'"

            assert meta["org"] == "NASA-PDS"
            assert meta["start_date"] == "2026-06-01"
            assert meta["end_date"] == "2026-07-11"
            assert meta["repo_count"] >= 1

    def test_validation_log_written(self):
        """Verify evidence-validation.log is written alongside evidence.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "evidence.json")
            result = self._run(
                ["--repos", "lasso-issues", "--start-date", "2026-06-01", "--end-date", "2026-07-11", "--output", out]
            )
            assert result.returncode == 0, result.stderr

            log_path = os.path.join(tmpdir, "evidence-validation.log")
            assert os.path.exists(log_path), "evidence-validation.log not found"

            with open(log_path) as fh:
                content = fh.read()
            assert "issues:" in content
            assert "pull_requests:" in content
            assert "releases:" in content

    def test_invalid_date_range_exits_nonzero(self):
        """Verify that start-date after end-date causes a non-zero exit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "evidence.json")
            result = self._run(
                ["--repos", "lasso-issues", "--start-date", "2026-12-31", "--end-date", "2026-01-01", "--output", out]
            )
            assert result.returncode != 0, "Expected non-zero exit for invalid date range"
