"""Integration tests for --group-by-component flag in pds-issues CLI.

These tests require a valid GITHUB_TOKEN environment variable and make real
GitHub API calls. Run via: tox -e integration
"""
import os
import subprocess
import tempfile

import pytest


@pytest.mark.integration
class TestGroupByComponentRst:
    """Integration tests for --group-by-component with --format rst."""

    def _run_pds_issues(self, args, cwd):
        """Run pds-issues CLI and return CompletedProcess."""
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            pytest.skip("GITHUB_TOKEN environment variable not set")
        return subprocess.run(
            ["pds-issues", "--token", token] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

    def test_group_by_component_produces_component_sections(self):
        """Verify --group-by-component creates Component: headings in RST output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_pds_issues(
                [
                    "--format", "rst",
                    "--issue_state", "closed",
                    "--build", "B15.1",
                    "--github-repos", "validate", "registry",
                    "--group-by-component",
                ],
                cwd=tmpdir,
            )

            assert result.returncode == 0, (
                f"pds-issues exited with code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

            output_file = os.path.join(tmpdir, "pdsen_issues.rst")
            assert os.path.exists(output_file), (
                f"Expected output file not found: {output_file}\n"
                f"stderr: {result.stderr}"
            )

            with open(output_file) as f:
                content = f.read()

            assert "Component:" in content, (
                "--group-by-component did not produce any 'Component:' sections.\n"
                "This likely means conf/pds-products.yaml was not loaded.\n"
                f"RST output:\n{content[:2000]}"
            )

    def test_group_by_component_maps_repos_to_correct_products(self):
        """Verify repos appear under their correct product component sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_pds_issues(
                [
                    "--format", "rst",
                    "--issue_state", "closed",
                    "--build", "B15.1",
                    "--github-repos", "validate", "registry",
                    "--group-by-component",
                ],
                cwd=tmpdir,
            )

            assert result.returncode == 0, f"pds-issues failed: {result.stderr}"

            with open(os.path.join(tmpdir, "pdsen_issues.rst")) as f:
                content = f.read()

            # 'validate' repo → 'validate' product → 'Component: Validate'
            # 'registry' repo → 'registry-tools' product → 'Component: Registry Tools'
            # At least one of these should appear, depending on whether there are
            # closed issues for that repo in B15.1.
            component_headers = [line for line in content.splitlines() if line.startswith("Component:")]
            assert len(component_headers) > 0, (
                "No Component: headers found in RST output. "
                f"--group-by-component is not working. Content:\n{content[:3000]}"
            )

    def test_no_group_by_component_has_no_component_sections(self):
        """Verify that without --group-by-component, there are no Component: sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_pds_issues(
                [
                    "--format", "rst",
                    "--issue_state", "closed",
                    "--build", "B15.1",
                    "--github-repos", "validate", "registry",
                ],
                cwd=tmpdir,
            )

            assert result.returncode == 0, f"pds-issues failed: {result.stderr}"

            with open(os.path.join(tmpdir, "pdsen_issues.rst")) as f:
                content = f.read()

            assert "Component:" not in content, (
                "Found unexpected 'Component:' sections when --group-by-component was not specified."
            )

    def test_bundled_config_loaded_from_tmpdir(self):
        """Verify pds-products.yaml is loaded from the installed package, not CWD.

        Runs from a fresh tmpdir that has no conf/pds-products.yaml, ensuring
        the bundled package config is the fallback that enables component grouping.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Confirm no config file in tmpdir
            assert not os.path.exists(os.path.join(tmpdir, "conf", "pds-products.yaml"))

            result = self._run_pds_issues(
                [
                    "--format", "rst",
                    "--issue_state", "closed",
                    "--build", "B15.1",
                    "--github-repos", "validate",
                    "--group-by-component",
                ],
                cwd=tmpdir,
            )

            assert result.returncode == 0, f"pds-issues failed: {result.stderr}"

            with open(os.path.join(tmpdir, "pdsen_issues.rst")) as f:
                content = f.read()

            # If bundled config was NOT loaded, "Component:" won't appear.
            assert "Component:" in content, (
                "Component sections missing — bundled pds-products.yaml not loaded from package. "
                "Check that src/lasso/issues/conf/pds-products.yaml is installed as package data."
            )
