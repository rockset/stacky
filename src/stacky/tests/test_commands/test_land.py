#!/usr/bin/env python3
"""Tests for stacky.commands.land module."""

import unittest
from unittest.mock import patch, MagicMock

from stacky.commands.land import cmd_land


class TestCmdLand(unittest.TestCase):
    """Tests for cmd_land function."""

    @patch("stacky.commands.land.COLOR_STDOUT", True)
    @patch("sys.stdout.write")
    @patch("stacky.commands.land.get_current_branch_name")
    @patch("stacky.commands.land.get_current_downstack_as_forest")
    @patch("stacky.commands.land.die")
    @patch("stacky.commands.land.cout")
    @patch("stacky.commands.land.confirm")
    @patch("stacky.commands.land.run")
    def test_cmd_land_success(
        self,
        mock_run,
        mock_confirm,
        mock_cout,
        mock_die,
        mock_forest,
        mock_current_branch,
        mock_write,
    ):
        """Test successful land command."""
        args = MagicMock()
        args.force = False
        args.auto = False

        bottom_branch = MagicMock()
        bottom_branch.name = "main"

        stack = MagicMock()
        stack.bottoms = {bottom_branch}

        branch = MagicMock()
        branch.name = "feature"
        branch.is_synced_with_parent.return_value = True
        branch.is_synced_with_remote.return_value = True
        branch.load_pr_info.return_value = None
        branch.open_pr_info = {
            "mergeable": "MERGEABLE",
            "number": 1,
            "url": "http://example.com"
        }
        branch.parent = MagicMock()
        branch.parent.name = "main"

        mock_current_branch.return_value = "feature"
        mock_forest.return_value = [
            {"main": (bottom_branch, {"feature": (branch, None)})}
        ]
        mock_run.return_value = "abc123"

        cmd_land(stack, args)

        mock_forest.assert_called_once_with(stack)
        branch.is_synced_with_parent.assert_called_once()
        branch.is_synced_with_remote.assert_called_once()
        branch.load_pr_info.assert_called_once()
        mock_confirm.assert_called_once()

    @patch("stacky.commands.land.get_current_branch_name")
    @patch("stacky.commands.land.get_current_downstack_as_forest")
    @patch("stacky.commands.land.die")
    def test_cmd_land_not_synced_parent(
        self,
        mock_die,
        mock_forest,
        mock_current_branch,
    ):
        """Test land fails when not synced with parent."""
        from stacky.utils.logging import ExitException
        mock_die.side_effect = ExitException("Not synced with parent")

        args = MagicMock()
        args.force = False

        bottom_branch = MagicMock()
        bottom_branch.name = "main"

        stack = MagicMock()
        stack.bottoms = {bottom_branch}

        branch = MagicMock()
        branch.name = "feature"
        branch.is_synced_with_parent.return_value = False
        branch.parent = MagicMock()
        branch.parent.name = "main"

        mock_current_branch.return_value = "feature"
        mock_forest.return_value = [
            {"main": (bottom_branch, {"feature": (branch, None)})}
        ]

        with self.assertRaises(ExitException):
            cmd_land(stack, args)
        mock_die.assert_called()

    @patch("stacky.commands.land.get_current_branch_name")
    @patch("stacky.commands.land.get_current_downstack_as_forest")
    @patch("stacky.commands.land.die")
    def test_cmd_land_not_synced_remote(
        self,
        mock_die,
        mock_forest,
        mock_current_branch,
    ):
        """Test land fails when not synced with remote."""
        from stacky.utils.logging import ExitException
        mock_die.side_effect = ExitException("Not synced with remote")

        args = MagicMock()
        args.force = False

        bottom_branch = MagicMock()
        bottom_branch.name = "main"

        stack = MagicMock()
        stack.bottoms = {bottom_branch}

        branch = MagicMock()
        branch.name = "feature"
        branch.is_synced_with_parent.return_value = True
        branch.is_synced_with_remote.return_value = False
        branch.parent = MagicMock()
        branch.parent.name = "main"

        mock_current_branch.return_value = "feature"
        mock_forest.return_value = [
            {"main": (bottom_branch, {"feature": (branch, None)})}
        ]

        with self.assertRaises(ExitException):
            cmd_land(stack, args)
        mock_die.assert_called()

    @patch("stacky.commands.land.get_current_branch_name")
    @patch("stacky.commands.land.get_current_downstack_as_forest")
    @patch("stacky.commands.land.die")
    def test_cmd_land_no_open_pr(
        self,
        mock_die,
        mock_forest,
        mock_current_branch,
    ):
        """Test land fails when no open PR."""
        from stacky.utils.logging import ExitException
        mock_die.side_effect = ExitException("No open PR")

        args = MagicMock()
        args.force = False

        bottom_branch = MagicMock()
        bottom_branch.name = "main"

        stack = MagicMock()
        stack.bottoms = {bottom_branch}

        branch = MagicMock()
        branch.name = "feature"
        branch.is_synced_with_parent.return_value = True
        branch.is_synced_with_remote.return_value = True
        branch.load_pr_info.return_value = None
        branch.open_pr_info = None
        branch.parent = MagicMock()
        branch.parent.name = "main"

        mock_current_branch.return_value = "feature"
        mock_forest.return_value = [
            {"main": (bottom_branch, {"feature": (branch, None)})}
        ]

        with self.assertRaises(ExitException):
            cmd_land(stack, args)
        mock_die.assert_called()


if __name__ == "__main__":
    unittest.main()
