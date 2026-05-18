#!/usr/bin/env python3
"""Tests for stacky.git.remote module."""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from stacky.git.remote import (
    get_remote_type, gen_ssh_mux_cmd, stop_muxed_ssh, start_muxed_ssh
)


class TestGetRemoteType(unittest.TestCase):
    """Tests for get_remote_type function."""

    @patch("stacky.git.remote.run_always_return")
    def test_get_remote_type_ssh(self, mock_run):
        """Test getting SSH remote type."""
        mock_run.return_value = "origin\tgit@github.com:user/repo.git (push)"
        result = get_remote_type("origin")
        self.assertEqual(result, "git@github.com")

    @patch("stacky.git.remote.run_always_return")
    def test_get_remote_type_https(self, mock_run):
        """Test getting HTTPS remote type returns None."""
        mock_run.return_value = "origin\thttps://github.com/user/repo.git (push)"
        result = get_remote_type("origin")
        self.assertIsNone(result)


class TestGenSshMuxCmd(unittest.TestCase):
    """Tests for gen_ssh_mux_cmd function."""

    def test_gen_ssh_mux_cmd(self):
        """Test SSH mux command generation."""
        cmd = gen_ssh_mux_cmd()
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("-o", cmd)
        self.assertIn("ControlMaster=auto", cmd)
        self.assertIn("ControlPath=~/.ssh/stacky-%C", cmd)


class TestStopMuxedSsh(unittest.TestCase):
    """Tests for stop_muxed_ssh function."""

    @patch("stacky.git.remote.get_config")
    @patch("stacky.git.remote.get_remote_type")
    @patch("stacky.git.remote.gen_ssh_mux_cmd")
    @patch("subprocess.Popen")
    def test_stop_muxed_ssh(self, mock_popen, mock_gen_cmd, mock_get_remote, mock_get_config):
        """Test stopping muxed SSH connection."""
        mock_get_config.return_value = MagicMock(share_ssh_session=True)
        mock_get_remote.return_value = "git@github.com"
        mock_gen_cmd.return_value = ["ssh", "-S"]

        stop_muxed_ssh()

        mock_popen.assert_called_once_with(
            ["ssh", "-S", "-O", "exit", "git@github.com"],
            stderr=subprocess.DEVNULL
        )

    @patch("stacky.git.remote.get_config")
    @patch("subprocess.Popen")
    def test_stop_muxed_ssh_disabled(self, mock_popen, mock_get_config):
        """Test stop_muxed_ssh does nothing when disabled."""
        mock_get_config.return_value = MagicMock(share_ssh_session=False)
        stop_muxed_ssh()
        mock_popen.assert_not_called()

    @patch("stacky.git.remote.get_config")
    @patch("stacky.git.remote.get_remote_type")
    @patch("subprocess.Popen")
    def test_stop_muxed_ssh_no_host(self, mock_popen, mock_get_remote, mock_get_config):
        """Test stop_muxed_ssh does nothing when no SSH host."""
        mock_get_config.return_value = MagicMock(share_ssh_session=True)
        mock_get_remote.return_value = None
        stop_muxed_ssh()
        mock_popen.assert_not_called()


class TestStartMuxedSsh(unittest.TestCase):
    """Tests for start_muxed_ssh function."""

    @patch("stacky.git.remote.get_config")
    def test_start_muxed_ssh_disabled(self, mock_get_config):
        """Test start_muxed_ssh does nothing when disabled."""
        mock_get_config.return_value = MagicMock(share_ssh_session=False)
        # Should not raise any errors
        start_muxed_ssh()


if __name__ == "__main__":
    unittest.main()
