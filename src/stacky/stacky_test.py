#!/usr/bin/env python3
import os
import shlex
import subprocess
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

from stacky import (
    PRInfos,
    _check_returncode,
    cmd_land,
    find_issue_marker,
    get_top_level_dir,
    read_config,
    stop_muxed_ssh,
)


class TestCheckReturnCode(unittest.TestCase):
    @patch("stacky.die")
    def test_check_returncode_zero(self, mock_die):
        sp = subprocess.CompletedProcess(args=["ls"], returncode=0)
        _check_returncode(sp, ["ls"])
        mock_die.assert_not_called()

    @patch("stacky.die")
    def test_check_returncode_negative(self, mock_die):
        sp = subprocess.CompletedProcess(args=["ls"], returncode=-1, stderr=b"error")
        _check_returncode(sp, ["ls"])
        mock_die.assert_called_once_with("Killed by signal {}: {}. Stderr was:\n{}", 1, shlex.join(["ls"]), "error")

    @patch("stacky.die")
    def test_check_returncode_positive(self, mock_die):
        sp = subprocess.CompletedProcess(args=["ls"], returncode=1, stderr=b"error")
        _check_returncode(sp, ["ls"])
        mock_die.assert_called_once_with("Exited with status {}: {}. Stderr was:\n{}", 1, shlex.join(["ls"]), "error")


class TestStringMethods(unittest.TestCase):
    def test_find_issue_marker(self):
        out = find_issue_marker("SRE-12")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("SRE-12-find-things")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("SRE_12")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("SRE_12-find-things")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("john_SRE_12")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("john_SRE_12-find-things")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("john_SRE12-find-things")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("anna_01_01_SRE-12")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("anna_01_01_SRE12")
        self.assertTrue(out is not None)
        self.assertEqual("SRE-12", out)

        out = find_issue_marker("john_test_12")
        self.assertTrue(out is None)

        out = find_issue_marker("john_test12")
        self.assertTrue(out is None)


class TestCmdLand(unittest.TestCase):
    @patch("stacky.COLOR_STDOUT", True)
    @patch("sys.stdout.write")
    @patch("stacky.get_current_downstack_as_forest")
    @patch("stacky.die")
    @patch("stacky.cout")
    @patch("stacky.confirm")
    @patch("stacky.run")
    @patch("stacky.CmdArgs")
    @patch("stacky.Commit")
    def test_cmd_land(
        self,
        mock_Commit,
        mock_CmdArgs,
        mock_run,
        mock_confirm,
        mock_cout,
        mock_die,
        mock_get_current_downstack_as_forest,
        mock_write,
    ):
        # Mock the args
        args = MagicMock()
        args.force = False
        args.auto = False

        bottom_branch = MagicMock()
        bottom_branch.name = "bottom_branch"

        # Mock the stack
        stack = MagicMock()
        stack.bottoms = [bottom_branch]

        # Mock the branch
        branch = MagicMock()
        branch.is_synced_with_parent.return_value = True
        branch.is_synced_with_remote.return_value = True
        branch.load_pr_info.return_value = None
        branch.open_pr_info = {"mergeable": "MERGEABLE", "number": 1, "url": "http://example.com"}
        branch.name = "branch_name"
        branch.parent.name = "parent_name"

        # Mock the forest and branches
        mock_get_current_downstack_as_forest.return_value = [
            {"bottom_branch": (bottom_branch, {"branch": (branch, None)})}
        ]

        # Mock the CmdArgs
        mock_CmdArgs.return_value = ["cmd_args"]

        # Mock the Commit
        mock_Commit.return_value = "commit"

        # Call the function
        cmd_land(stack, args)

        # Assert the mocks were called correctly
        mock_get_current_downstack_as_forest.assert_called_once_with(stack)
        branch.is_synced_with_parent.assert_called_once()
        branch.is_synced_with_remote.assert_called_once()
        branch.load_pr_info.assert_called_once()
        mock_write.assert_called_with(
            "- Will land PR #1 (\x1b[34mhttp://example.com\x1b[0m) for branch branch_name into branch parent_name\n"
        )
        mock_run.assert_called_with(["cmd_args"], out=True)
        mock_cout.assert_called_with("\n✓ Success! Run `stacky update` to update local state.\n", fg="green")


class TestStopMuxedSsh(unittest.TestCase):
    @patch("stacky.get_config", return_value=MagicMock(share_ssh_session=True))
    @patch("stacky.get_remote_type", return_value="host")
    @patch("stacky.gen_ssh_mux_cmd", return_value=["ssh", "-S"])
    @patch("subprocess.Popen")
    def test_stop_muxed_ssh(self, mock_popen, mock_gen_ssh_mux_cmd, mock_get_remote_type, mock_get_config):
        stop_muxed_ssh()
        mock_popen.assert_called_once_with(["ssh", "-S", "-O", "exit", "host"], stderr=subprocess.DEVNULL)

    @patch("stacky.get_config", return_value=MagicMock(share_ssh_session=False))
    @patch("stacky.get_remote_type", return_value="host")
    @patch("stacky.gen_ssh_mux_cmd", return_value=["ssh", "-S"])
    @patch("subprocess.Popen")
    def test_stop_muxed_ssh_no_share(self, mock_popen, mock_gen_ssh_mux_cmd, mock_get_remote_type, mock_get_config):
        stop_muxed_ssh()
        mock_popen.assert_not_called()

    @patch("stacky.get_config", return_value=MagicMock(share_ssh_session=True))
    @patch("stacky.get_remote_type", return_value=None)
    @patch("stacky.gen_ssh_mux_cmd", return_value=["ssh", "-S"])
    @patch("subprocess.Popen")
    def test_stop_muxed_ssh_no_host(self, mock_popen, mock_gen_ssh_mux_cmd, mock_get_remote_type, mock_get_config):
        stop_muxed_ssh()
        mock_popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
