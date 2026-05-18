#!/usr/bin/env python3
"""Tests for stacky.stack.tree module."""

import unittest
from unittest.mock import patch, MagicMock

from stacky.stack.tree import (
    get_pr_status_emoji, make_tree_node, make_subtree, make_tree,
    format_name, depth_first, forest_depth_first
)
from stacky.utils.types import BranchName, BranchesTree, BranchesTreeForest


class TestGetPrStatusEmoji(unittest.TestCase):
    """Tests for get_pr_status_emoji function."""

    def test_no_pr_info(self):
        """Test emoji for no PR info."""
        result = get_pr_status_emoji(None)
        self.assertEqual(result, "")

    def test_draft_pr(self):
        """Test emoji for draft PR."""
        pr_info = {"isDraft": True}
        result = get_pr_status_emoji(pr_info)
        self.assertEqual(result, " 🚧")

    def test_approved_pr(self):
        """Test emoji for approved PR."""
        pr_info = {"isDraft": False, "reviewDecision": "APPROVED", "reviewRequests": []}
        result = get_pr_status_emoji(pr_info)
        self.assertEqual(result, " ✅")

    def test_pending_review_pr(self):
        """Test emoji for PR waiting on review."""
        pr_info = {"isDraft": False, "reviewDecision": None, "reviewRequests": [{"login": "reviewer"}]}
        result = get_pr_status_emoji(pr_info)
        self.assertEqual(result, " 🔄")

    def test_needs_changes_pr(self):
        """Test emoji for PR needing changes."""
        pr_info = {"isDraft": False, "reviewDecision": "CHANGES_REQUESTED", "reviewRequests": []}
        result = get_pr_status_emoji(pr_info)
        self.assertEqual(result, " ❌")


class TestMakeTree(unittest.TestCase):
    """Tests for tree building functions."""

    def test_make_subtree_no_children(self):
        """Test make_subtree with no children."""
        branch = MagicMock()
        branch.children = set()
        result = make_subtree(branch)
        self.assertEqual(result, {})

    def test_make_tree(self):
        """Test make_tree creates correct structure."""
        branch = MagicMock()
        branch.name = BranchName("feature")
        branch.children = set()
        result = make_tree(branch)
        self.assertIn("feature", result)


class TestFormatName(unittest.TestCase):
    """Tests for format_name function."""

    @patch("stacky.stack.tree.get_current_branch_name")
    @patch("stacky.stack.tree.get_config")
    def test_format_name_current_branch(self, mock_config, mock_current):
        """Test format_name marks current branch."""
        mock_current.return_value = BranchName("feature")
        mock_config.return_value = MagicMock(compact_pr_display=False)

        branch = MagicMock()
        branch.name = BranchName("feature")
        branch.is_synced_with_parent.return_value = True
        branch.is_synced_with_remote.return_value = True
        branch.open_pr_info = None

        result = format_name(branch, colorize=False)
        self.assertIn("*", result)
        self.assertIn("feature", result)

    @patch("stacky.stack.tree.get_current_branch_name")
    @patch("stacky.stack.tree.get_config")
    def test_format_name_not_synced_parent(self, mock_config, mock_current):
        """Test format_name shows ! when not synced with parent."""
        mock_current.return_value = BranchName("other")
        mock_config.return_value = MagicMock(compact_pr_display=False)

        branch = MagicMock()
        branch.name = BranchName("feature")
        branch.is_synced_with_parent.return_value = False
        branch.is_synced_with_remote.return_value = True
        branch.open_pr_info = None

        result = format_name(branch, colorize=False)
        self.assertIn("!", result)


class TestDepthFirst(unittest.TestCase):
    """Tests for depth-first traversal functions."""

    def test_depth_first_empty(self):
        """Test depth_first with empty tree."""
        tree = BranchesTree({})
        result = list(depth_first(tree))
        self.assertEqual(result, [])

    def test_depth_first_single_branch(self):
        """Test depth_first with single branch."""
        branch = MagicMock()
        branch.name = BranchName("feature")
        tree = BranchesTree({"feature": (branch, BranchesTree({}))})
        result = list(depth_first(tree))
        self.assertEqual(result, [branch])

    def test_forest_depth_first_empty(self):
        """Test forest_depth_first with empty forest."""
        forest = BranchesTreeForest([])
        result = list(forest_depth_first(forest))
        self.assertEqual(result, [])

    def test_forest_depth_first_single_tree(self):
        """Test forest_depth_first with single tree."""
        branch = MagicMock()
        branch.name = BranchName("feature")
        tree = BranchesTree({"feature": (branch, BranchesTree({}))})
        forest = BranchesTreeForest([tree])
        result = list(forest_depth_first(forest))
        self.assertEqual(result, [branch])


if __name__ == "__main__":
    unittest.main()
