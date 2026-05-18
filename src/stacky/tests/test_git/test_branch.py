#!/usr/bin/env python3
"""Tests for stacky.git.branch module."""

import unittest
from unittest.mock import patch, MagicMock

from stacky.git.branch import (
    get_current_branch, get_all_branches, get_stack_parent_branch,
    get_real_stack_bottom, checkout, create_branch
)
from stacky.utils.types import BranchName


class TestGetCurrentBranch(unittest.TestCase):
    """Tests for get_current_branch function."""

    @patch("stacky.git.branch.run")
    def test_get_current_branch_success(self, mock_run):
        """Test get_current_branch returns branch name."""
        mock_run.return_value = "refs/heads/feature-branch"
        result = get_current_branch()
        self.assertEqual(result, "feature-branch")

    @patch("stacky.git.branch.run")
    def test_get_current_branch_detached_head(self, mock_run):
        """Test get_current_branch returns None on detached HEAD."""
        mock_run.return_value = None
        result = get_current_branch()
        self.assertIsNone(result)


class TestGetAllBranches(unittest.TestCase):
    """Tests for get_all_branches function."""

    @patch("stacky.git.branch.run_multiline")
    def test_get_all_branches(self, mock_run_multiline):
        """Test get_all_branches returns list of branch names."""
        mock_run_multiline.return_value = "main\nfeature-1\nfeature-2\n"
        result = get_all_branches()
        self.assertEqual(result, [BranchName("main"), BranchName("feature-1"), BranchName("feature-2")])

    @patch("stacky.git.branch.run_multiline")
    def test_get_all_branches_empty(self, mock_run_multiline):
        """Test get_all_branches with no branches."""
        mock_run_multiline.return_value = ""
        result = get_all_branches()
        self.assertEqual(result, [])


class TestGetStackParentBranch(unittest.TestCase):
    """Tests for get_stack_parent_branch function."""

    @patch("stacky.git.branch.run")
    def test_get_stack_parent_branch_success(self, mock_run):
        """Test getting parent branch."""
        mock_run.return_value = "refs/heads/parent-branch"
        result = get_stack_parent_branch(BranchName("child-branch"))
        self.assertEqual(result, "parent-branch")

    @patch("stacky.git.branch.run")
    def test_get_stack_parent_branch_no_parent(self, mock_run):
        """Test getting parent when no parent configured."""
        mock_run.return_value = None
        result = get_stack_parent_branch(BranchName("orphan-branch"))
        self.assertIsNone(result)

    def test_get_stack_parent_branch_is_bottom(self):
        """Test getting parent of stack bottom returns None."""
        result = get_stack_parent_branch(BranchName("master"))
        self.assertIsNone(result)


class TestGetRealStackBottom(unittest.TestCase):
    """Tests for get_real_stack_bottom function."""

    @patch("stacky.git.branch.get_all_branches")
    def test_get_real_stack_bottom_master(self, mock_get_all):
        """Test finding master as stack bottom."""
        mock_get_all.return_value = [BranchName("master"), BranchName("feature")]
        result = get_real_stack_bottom()
        self.assertEqual(result, "master")

    @patch("stacky.git.branch.get_all_branches")
    def test_get_real_stack_bottom_main(self, mock_get_all):
        """Test finding main as stack bottom."""
        mock_get_all.return_value = [BranchName("main"), BranchName("feature")]
        result = get_real_stack_bottom()
        self.assertEqual(result, "main")

    @patch("stacky.git.branch.get_all_branches")
    def test_get_real_stack_bottom_none(self, mock_get_all):
        """Test no stack bottom found."""
        mock_get_all.return_value = [BranchName("feature")]
        result = get_real_stack_bottom()
        self.assertIsNone(result)


class TestCheckout(unittest.TestCase):
    """Tests for checkout function."""

    @patch("stacky.git.branch.run")
    @patch("stacky.git.branch.info")
    def test_checkout(self, mock_info, mock_run):
        """Test checkout calls git checkout."""
        checkout(BranchName("feature"))
        mock_run.assert_called_once_with(["git", "checkout", "feature"], out=True)


class TestCreateBranch(unittest.TestCase):
    """Tests for create_branch function."""

    @patch("stacky.git.branch.run")
    def test_create_branch(self, mock_run):
        """Test create_branch calls git checkout -b with track."""
        create_branch(BranchName("new-feature"))
        mock_run.assert_called_once_with(
            ["git", "checkout", "-b", "new-feature", "--track"], out=True
        )


if __name__ == "__main__":
    unittest.main()
