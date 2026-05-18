#!/usr/bin/env python3
"""Tests for stacky.git.refs module."""

import unittest
from unittest.mock import patch

from stacky.git.refs import (
    get_stack_parent_commit, get_commit, set_parent_commit,
    get_branch_name_from_short_ref, get_all_stack_bottoms,
    get_commits_between, get_merge_base
)
from stacky.utils.types import BranchName, Commit


class TestGetStackParentCommit(unittest.TestCase):
    """Tests for get_stack_parent_commit function."""

    @patch("stacky.git.refs.run")
    def test_get_stack_parent_commit_success(self, mock_run):
        """Test getting parent commit."""
        mock_run.return_value = "abc123"
        result = get_stack_parent_commit(BranchName("feature"))
        self.assertEqual(result, Commit("abc123"))

    @patch("stacky.git.refs.run")
    def test_get_stack_parent_commit_none(self, mock_run):
        """Test getting parent commit when not set."""
        mock_run.return_value = None
        result = get_stack_parent_commit(BranchName("feature"))
        self.assertIsNone(result)


class TestGetCommit(unittest.TestCase):
    """Tests for get_commit function."""

    @patch("stacky.git.refs.run")
    def test_get_commit(self, mock_run):
        """Test getting branch commit."""
        mock_run.return_value = "def456"
        result = get_commit(BranchName("main"))
        self.assertEqual(result, Commit("def456"))


class TestSetParentCommit(unittest.TestCase):
    """Tests for set_parent_commit function."""

    @patch("stacky.git.refs.run")
    def test_set_parent_commit(self, mock_run):
        """Test setting parent commit."""
        set_parent_commit(BranchName("feature"), Commit("abc123"))
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("update-ref", call_args)
        self.assertIn("refs/stack-parent/feature", call_args)
        self.assertIn("abc123", call_args)

    @patch("stacky.git.refs.run")
    def test_set_parent_commit_with_prev(self, mock_run):
        """Test setting parent commit with previous value."""
        set_parent_commit(BranchName("feature"), Commit("abc123"), "old123")
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn("old123", call_args)


class TestGetBranchNameFromShortRef(unittest.TestCase):
    """Tests for get_branch_name_from_short_ref function."""

    def test_get_branch_name_from_short_ref(self):
        """Test extracting branch name from short ref."""
        result = get_branch_name_from_short_ref("stack-parent/feature")
        self.assertEqual(result, BranchName("feature"))

    def test_get_branch_name_from_short_ref_invalid(self):
        """Test invalid ref format raises error."""
        from stacky.utils.logging import ExitException
        # The function will raise ExitException via die() for invalid refs
        with self.assertRaises(ExitException):
            get_branch_name_from_short_ref("invalid")


class TestGetAllStackBottoms(unittest.TestCase):
    """Tests for get_all_stack_bottoms function."""

    @patch("stacky.git.refs.run_multiline")
    def test_get_all_stack_bottoms(self, mock_run):
        """Test getting all stack bottom branches."""
        mock_run.return_value = "stacky-bottom-branch/feature-1\nstacky-bottom-branch/feature-2\n"
        result = get_all_stack_bottoms()
        self.assertEqual(result, [BranchName("feature-1"), BranchName("feature-2")])

    @patch("stacky.git.refs.run_multiline")
    def test_get_all_stack_bottoms_empty(self, mock_run):
        """Test no stack bottoms."""
        mock_run.return_value = ""
        result = get_all_stack_bottoms()
        self.assertEqual(result, [])


class TestGetCommitsBetween(unittest.TestCase):
    """Tests for get_commits_between function."""

    @patch("stacky.git.refs.run_multiline")
    def test_get_commits_between(self, mock_run):
        """Test getting commits between two refs."""
        mock_run.return_value = "abc123\ndef456\n"
        result = get_commits_between(Commit("start"), Commit("end"))
        self.assertEqual(result, ["abc123", "def456"])

    @patch("stacky.git.refs.run_multiline")
    def test_get_commits_between_empty(self, mock_run):
        """Test no commits between refs."""
        mock_run.return_value = ""
        result = get_commits_between(Commit("same"), Commit("same"))
        self.assertEqual(result, [])


class TestGetMergeBase(unittest.TestCase):
    """Tests for get_merge_base function."""

    @patch("stacky.git.refs.run")
    def test_get_merge_base(self, mock_run):
        """Test getting merge base."""
        mock_run.return_value = "abc123"
        result = get_merge_base(BranchName("main"), BranchName("feature"))
        self.assertEqual(result, "abc123")


if __name__ == "__main__":
    unittest.main()
