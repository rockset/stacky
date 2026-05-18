#!/usr/bin/env python3
"""Tests for stacky.pr.github module."""

import unittest
from unittest.mock import patch, MagicMock

from stacky.pr.github import (
    find_issue_marker, find_reviewers, extract_stack_comment,
    generate_stack_string
)
from stacky.utils.types import BranchName, BranchesTreeForest, BranchesTree


class TestFindIssueMarker(unittest.TestCase):
    """Tests for find_issue_marker function."""

    def test_simple_issue_marker(self):
        """Test finding simple issue marker."""
        result = find_issue_marker("SRE-12")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_with_suffix(self):
        """Test finding issue marker with suffix."""
        result = find_issue_marker("SRE-12-find-things")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_underscore(self):
        """Test finding issue marker with underscore."""
        result = find_issue_marker("SRE_12")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_underscore_with_suffix(self):
        """Test finding issue marker with underscore and suffix."""
        result = find_issue_marker("SRE_12-find-things")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_with_prefix(self):
        """Test finding issue marker with prefix."""
        result = find_issue_marker("john_SRE_12")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_with_prefix_and_suffix(self):
        """Test finding issue marker with prefix and suffix."""
        result = find_issue_marker("john_SRE_12-find-things")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_no_separator(self):
        """Test finding issue marker without separator."""
        result = find_issue_marker("john_SRE12-find-things")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_date_prefix(self):
        """Test finding issue marker with date prefix."""
        result = find_issue_marker("anna_01_01_SRE-12")
        self.assertEqual(result, "SRE-12")

    def test_issue_marker_date_prefix_no_separator(self):
        """Test finding issue marker with date prefix no separator."""
        result = find_issue_marker("anna_01_01_SRE12")
        self.assertEqual(result, "SRE-12")

    def test_no_issue_marker(self):
        """Test no issue marker found."""
        result = find_issue_marker("john_test_12")
        self.assertIsNone(result)

    def test_no_issue_marker_no_separator(self):
        """Test no issue marker found without separator."""
        result = find_issue_marker("john_test12")
        self.assertIsNone(result)


class TestFindReviewers(unittest.TestCase):
    """Tests for find_reviewers function."""

    @patch("stacky.pr.github.run_multiline")
    def test_find_reviewers_single(self, mock_run):
        """Test finding single reviewer."""
        mock_run.return_value = "Some commit message\n\nReviewer: alice\n"
        branch = MagicMock()
        branch.name = BranchName("feature")
        result = find_reviewers(branch)
        self.assertEqual(result, ["alice"])

    @patch("stacky.pr.github.run_multiline")
    def test_find_reviewers_multiple(self, mock_run):
        """Test finding multiple reviewers."""
        mock_run.return_value = "Some commit message\n\nReviewers: alice, bob\n"
        branch = MagicMock()
        branch.name = BranchName("feature")
        result = find_reviewers(branch)
        self.assertEqual(result, ["alice", " bob"])

    @patch("stacky.pr.github.run_multiline")
    def test_find_reviewers_none(self, mock_run):
        """Test no reviewers found."""
        mock_run.return_value = "Some commit message\n"
        branch = MagicMock()
        branch.name = BranchName("feature")
        result = find_reviewers(branch)
        self.assertIsNone(result)


class TestExtractStackComment(unittest.TestCase):
    """Tests for extract_stack_comment function."""

    def test_extract_existing_comment(self):
        """Test extracting existing stack comment."""
        body = """Some PR description

<!-- Stacky Stack Info -->
**Stack:**
- branch1 (#1)
- branch2 (#2)
<!-- End Stacky Stack Info -->

More description"""
        result = extract_stack_comment(body)
        self.assertIn("Stacky Stack Info", result)
        self.assertIn("branch1", result)

    def test_extract_no_comment(self):
        """Test extracting when no comment exists."""
        body = "Just a regular PR description"
        result = extract_stack_comment(body)
        self.assertEqual(result, "")

    def test_extract_empty_body(self):
        """Test extracting from empty body."""
        result = extract_stack_comment("")
        self.assertEqual(result, "")

    def test_extract_none_body(self):
        """Test extracting from None body."""
        result = extract_stack_comment(None)
        self.assertEqual(result, "")


class TestGenerateStackString(unittest.TestCase):
    """Tests for generate_stack_string function."""

    def test_generate_empty_forest(self):
        """Test generating stack string for empty forest."""
        forest = BranchesTreeForest([])
        branch = MagicMock()
        branch.name = BranchName("feature")
        result = generate_stack_string(forest, branch)
        self.assertEqual(result, "")

    def test_generate_with_branches(self):
        """Test generating stack string with branches."""
        branch1 = MagicMock()
        branch1.name = BranchName("feature-1")
        branch1.open_pr_info = {"number": 1}

        branch2 = MagicMock()
        branch2.name = BranchName("feature-2")
        branch2.open_pr_info = {"number": 2}

        tree = BranchesTree({
            "feature-1": (branch1, BranchesTree({
                "feature-2": (branch2, BranchesTree({}))
            }))
        })
        forest = BranchesTreeForest([tree])

        result = generate_stack_string(forest, branch2)
        self.assertIn("Stacky Stack Info", result)
        self.assertIn("feature-1", result)
        self.assertIn("feature-2", result)
        self.assertIn("CURRENT PR", result)


if __name__ == "__main__":
    unittest.main()
