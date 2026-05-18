#!/usr/bin/env python3
"""Tests for stacky.stack.models module."""

import unittest
from unittest.mock import patch, MagicMock

from stacky.stack.models import PRInfo, PRInfos, StackBranch, StackBranchSet
from stacky.utils.types import BranchName, Commit


class TestPRInfos(unittest.TestCase):
    """Tests for PRInfos dataclass."""

    def test_prinfos_creation(self):
        """Test PRInfos creation."""
        all_prs = {"pr1": {"id": "pr1", "state": "OPEN"}}
        open_pr = {"id": "pr1", "state": "OPEN"}
        pr_infos = PRInfos(all=all_prs, open=open_pr)
        self.assertEqual(pr_infos.all, all_prs)
        self.assertEqual(pr_infos.open, open_pr)

    def test_prinfos_no_open_pr(self):
        """Test PRInfos with no open PR."""
        pr_infos = PRInfos(all={}, open=None)
        self.assertIsNone(pr_infos.open)


class TestStackBranch(unittest.TestCase):
    """Tests for StackBranch class."""

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_stack_branch_creation(self, mock_get_commit, mock_get_remote):
        """Test StackBranch creation."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("abc123"))

        parent = MagicMock()
        parent.commit = Commit("parent123")

        branch = StackBranch(
            name=BranchName("feature"),
            parent=parent,
            parent_commit=Commit("parent123")
        )

        self.assertEqual(branch.name, "feature")
        self.assertEqual(branch.parent, parent)
        self.assertEqual(branch.parent_commit, Commit("parent123"))
        self.assertEqual(branch.commit, Commit("abc123"))

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_is_synced_with_parent(self, mock_get_commit, mock_get_remote):
        """Test is_synced_with_parent method."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("abc123"))

        parent = MagicMock()
        parent.commit = Commit("parent123")

        branch = StackBranch(
            name=BranchName("feature"),
            parent=parent,
            parent_commit=Commit("parent123")
        )

        self.assertTrue(branch.is_synced_with_parent())

        # Unsynced case
        parent.commit = Commit("different")
        self.assertFalse(branch.is_synced_with_parent())

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_is_synced_with_remote(self, mock_get_commit, mock_get_remote):
        """Test is_synced_with_remote method."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("abc123"))

        branch = StackBranch(
            name=BranchName("feature"),
            parent=None,
            parent_commit=None
        )

        self.assertTrue(branch.is_synced_with_remote())

        # Unsynced case
        branch.remote_commit = Commit("different")
        self.assertFalse(branch.is_synced_with_remote())


class TestStackBranchSet(unittest.TestCase):
    """Tests for StackBranchSet class."""

    def test_stack_branch_set_creation(self):
        """Test StackBranchSet creation."""
        stack_set = StackBranchSet()
        self.assertEqual(stack_set.stack, {})
        self.assertEqual(stack_set.tops, set())
        self.assertEqual(stack_set.bottoms, set())

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_add_branch(self, mock_get_commit, mock_get_remote):
        """Test adding a branch to the set."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        stack_set = StackBranchSet()
        branch = stack_set.add(
            BranchName("main"),
            parent=None,
            parent_commit=None
        )

        self.assertIn(BranchName("main"), stack_set.stack)
        self.assertIn(branch, stack_set.bottoms)
        self.assertIn(branch, stack_set.tops)

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_remove_branch(self, mock_get_commit, mock_get_remote):
        """Test removing a branch from the set."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        stack_set = StackBranchSet()
        branch = stack_set.add(
            BranchName("main"),
            parent=None,
            parent_commit=None
        )

        removed = stack_set.remove(BranchName("main"))
        self.assertEqual(removed, branch)
        self.assertNotIn(BranchName("main"), stack_set.stack)

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_add_child(self, mock_get_commit, mock_get_remote):
        """Test adding child relationship."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        stack_set = StackBranchSet()
        parent = stack_set.add(
            BranchName("main"),
            parent=None,
            parent_commit=None
        )

        child = stack_set.add(
            BranchName("feature"),
            parent=parent,
            parent_commit=Commit("abc123")
        )

        stack_set.add_child(parent, child)
        self.assertIn(child, parent.children)
        self.assertNotIn(parent, stack_set.tops)


if __name__ == "__main__":
    unittest.main()
