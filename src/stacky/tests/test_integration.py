#!/usr/bin/env python3
"""Integration tests for stacky workflow."""

import unittest
from unittest.mock import patch, MagicMock

from stacky.stack.models import StackBranch, StackBranchSet
from stacky.utils.types import BranchName, Commit


class TestStackWorkflow(unittest.TestCase):
    """Integration tests for stack workflow."""

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_build_simple_stack(self, mock_get_commit, mock_get_remote):
        """Test building a simple two-branch stack."""
        # Mock git operations
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        # Create stack
        stack = StackBranchSet()

        # Add main branch (bottom)
        main = stack.add(
            BranchName("main"),
            parent=None,
            parent_commit=None
        )

        # Add feature branch
        mock_get_commit.return_value = Commit("def456")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("def456"))
        feature = stack.add(
            BranchName("feature"),
            parent=main,
            parent_commit=Commit("abc123")
        )
        stack.add_child(main, feature)

        # Verify stack structure
        self.assertEqual(len(stack.stack), 2)
        self.assertIn(main, stack.bottoms)
        self.assertIn(feature, stack.tops)
        self.assertIn(feature, main.children)
        self.assertEqual(feature.parent, main)

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_build_branching_stack(self, mock_get_commit, mock_get_remote):
        """Test building a stack with multiple branches from one parent."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        stack = StackBranchSet()

        # Add main
        main = stack.add(BranchName("main"), parent=None, parent_commit=None)

        # Add feature-1
        mock_get_commit.return_value = Commit("def456")
        mock_get_remote.return_value = ("origin", BranchName("feature-1"), Commit("def456"))
        feature1 = stack.add(BranchName("feature-1"), parent=main, parent_commit=Commit("abc123"))
        stack.add_child(main, feature1)

        # Add feature-2 (also from main)
        mock_get_commit.return_value = Commit("ghi789")
        mock_get_remote.return_value = ("origin", BranchName("feature-2"), Commit("ghi789"))
        feature2 = stack.add(BranchName("feature-2"), parent=main, parent_commit=Commit("abc123"))
        stack.add_child(main, feature2)

        # Verify structure
        self.assertEqual(len(main.children), 2)
        self.assertIn(feature1, main.children)
        self.assertIn(feature2, main.children)
        self.assertEqual(len(stack.tops), 2)

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_sync_status_detection(self, mock_get_commit, mock_get_remote):
        """Test that sync status is correctly detected."""
        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        stack = StackBranchSet()
        main = stack.add(BranchName("main"), parent=None, parent_commit=None)

        # Add feature synced with parent
        mock_get_commit.return_value = Commit("def456")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("def456"))
        feature = stack.add(BranchName("feature"), parent=main, parent_commit=Commit("abc123"))

        # Initially synced
        self.assertTrue(feature.is_synced_with_parent())
        self.assertTrue(feature.is_synced_with_remote())

        # Simulate parent moving ahead
        main.commit = Commit("new123")
        self.assertFalse(feature.is_synced_with_parent())

        # Simulate remote moving ahead
        feature.remote_commit = Commit("remote456")
        self.assertFalse(feature.is_synced_with_remote())


class TestTreeTraversal(unittest.TestCase):
    """Integration tests for tree traversal."""

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    def test_forest_traversal_order(self, mock_get_commit, mock_get_remote):
        """Test that forest traversal visits branches in correct order."""
        from stacky.stack.tree import depth_first, forest_depth_first, make_tree
        from stacky.utils.types import BranchesTreeForest

        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("main"), Commit("abc123"))

        stack = StackBranchSet()
        main = stack.add(BranchName("main"), parent=None, parent_commit=None)

        mock_get_commit.return_value = Commit("def456")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("def456"))
        feature = stack.add(BranchName("feature"), parent=main, parent_commit=Commit("abc123"))
        stack.add_child(main, feature)

        tree = make_tree(main)
        branches = list(depth_first(tree))

        self.assertEqual(len(branches), 2)
        self.assertEqual(branches[0].name, "main")
        self.assertEqual(branches[1].name, "feature")


class TestPRInfoLoading(unittest.TestCase):
    """Integration tests for PR info loading."""

    @patch("stacky.stack.models.get_remote_info")
    @patch("stacky.stack.models.get_commit")
    @patch("stacky.pr.github.get_pr_info")
    def test_lazy_pr_loading(self, mock_get_pr_info, mock_get_commit, mock_get_remote):
        """Test that PR info is loaded lazily."""
        from stacky.stack.models import PRInfos

        mock_get_commit.return_value = Commit("abc123")
        mock_get_remote.return_value = ("origin", BranchName("feature"), Commit("abc123"))
        mock_get_pr_info.return_value = PRInfos(
            all={"pr1": {"id": "pr1", "state": "OPEN", "number": 1}},
            open={"id": "pr1", "state": "OPEN", "number": 1}
        )

        stack = StackBranchSet()
        feature = stack.add(BranchName("feature"), parent=None, parent_commit=None)

        # PR info not loaded yet
        self.assertFalse(feature._pr_info_loaded)
        self.assertEqual(feature.pr_info, {})

        # Load PR info
        feature.load_pr_info()

        # Now loaded
        self.assertTrue(feature._pr_info_loaded)
        mock_get_pr_info.assert_called_once_with(BranchName("feature"))


if __name__ == "__main__":
    unittest.main()
