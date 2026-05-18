#!/usr/bin/env python3
"""Tests for stacky.utils.shell module."""

import shlex
import subprocess
import unittest
from unittest.mock import patch, MagicMock

from stacky.utils.shell import (
    _check_returncode, run, run_multiline, run_always_return, remove_prefix
)


class TestCheckReturnCode(unittest.TestCase):
    """Tests for _check_returncode function."""

    @patch("stacky.utils.shell.die")
    def test_check_returncode_zero(self, mock_die):
        """Test that zero return code does not call die."""
        sp = subprocess.CompletedProcess(args=["ls"], returncode=0)
        _check_returncode(sp, ["ls"])
        mock_die.assert_not_called()

    @patch("stacky.utils.shell.die")
    def test_check_returncode_negative(self, mock_die):
        """Test that negative return code (signal) calls die with signal info."""
        sp = subprocess.CompletedProcess(args=["ls"], returncode=-1, stderr=b"error")
        _check_returncode(sp, ["ls"])
        mock_die.assert_called_once_with(
            "Killed by signal {}: {}. Stderr was:\n{}",
            1, shlex.join(["ls"]), "error"
        )

    @patch("stacky.utils.shell.die")
    def test_check_returncode_positive(self, mock_die):
        """Test that positive return code calls die with exit status."""
        sp = subprocess.CompletedProcess(args=["ls"], returncode=1, stderr=b"error")
        _check_returncode(sp, ["ls"])
        mock_die.assert_called_once_with(
            "Exited with status {}: {}. Stderr was:\n{}",
            1, shlex.join(["ls"]), "error"
        )


class TestRun(unittest.TestCase):
    """Tests for run functions."""

    @patch("subprocess.run")
    @patch("stacky.utils.shell.debug")
    def test_run_success(self, mock_debug, mock_subprocess_run):
        """Test run returns stripped output on success."""
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["echo", "hello"],
            returncode=0,
            stdout=b"  hello world  \n",
            stderr=b""
        )
        result = run(["echo", "hello"])
        self.assertEqual(result, "hello world")

    @patch("subprocess.run")
    @patch("stacky.utils.shell.debug")
    def test_run_failure_check_false(self, mock_debug, mock_subprocess_run):
        """Test run returns None on failure when check=False."""
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["false"],
            returncode=1,
            stdout=b"",
            stderr=b"error"
        )
        result = run(["false"], check=False)
        self.assertIsNone(result)

    @patch("subprocess.run")
    @patch("stacky.utils.shell.debug")
    def test_run_multiline_preserves_newlines(self, mock_debug, mock_subprocess_run):
        """Test run_multiline preserves newlines in output."""
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["echo", "-e", "line1\\nline2"],
            returncode=0,
            stdout=b"line1\nline2\n",
            stderr=b""
        )
        result = run_multiline(["echo", "-e", "line1\\nline2"])
        self.assertEqual(result, "line1\nline2\n")

    @patch("subprocess.run")
    @patch("stacky.utils.shell.debug")
    def test_run_always_return_asserts_not_none(self, mock_debug, mock_subprocess_run):
        """Test run_always_return returns output (asserts not None)."""
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["echo", "test"],
            returncode=0,
            stdout=b"test",
            stderr=b""
        )
        result = run_always_return(["echo", "test"])
        self.assertEqual(result, "test")


class TestRemovePrefix(unittest.TestCase):
    """Tests for remove_prefix function."""

    def test_remove_prefix_success(self):
        """Test remove_prefix removes prefix correctly."""
        result = remove_prefix("refs/heads/main", "refs/heads/")
        self.assertEqual(result, "main")

    def test_remove_prefix_full_match(self):
        """Test remove_prefix with exact match returns empty string."""
        result = remove_prefix("prefix", "prefix")
        self.assertEqual(result, "")

    @patch("stacky.utils.shell.die")
    def test_remove_prefix_no_match(self, mock_die):
        """Test remove_prefix dies when prefix not found."""
        remove_prefix("other/path", "refs/heads/")
        mock_die.assert_called_once()


if __name__ == "__main__":
    unittest.main()
