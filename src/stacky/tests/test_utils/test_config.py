#!/usr/bin/env python3
"""Tests for stacky.utils.config module."""

import os
import tempfile
import unittest
from unittest.mock import patch

from stacky.utils.config import StackyConfig, read_config, get_config


class TestStackyConfig(unittest.TestCase):
    """Tests for StackyConfig dataclass."""

    def test_default_values(self):
        """Test StackyConfig has correct default values."""
        config = StackyConfig()
        self.assertFalse(config.skip_confirm)
        self.assertFalse(config.change_to_main)
        self.assertFalse(config.change_to_adopted)
        self.assertFalse(config.share_ssh_session)
        self.assertFalse(config.use_merge)
        self.assertTrue(config.use_force_push)
        self.assertFalse(config.compact_pr_display)
        self.assertTrue(config.enable_stack_comment)

    def test_read_one_config_ui_section(self):
        """Test reading UI section from config file."""
        config = StackyConfig()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write("[UI]\n")
            f.write("skip_confirm = true\n")
            f.write("change_to_main = true\n")
            f.write("compact_pr_display = true\n")
            f.name
        try:
            config.read_one_config(f.name)
            self.assertTrue(config.skip_confirm)
            self.assertTrue(config.change_to_main)
            self.assertTrue(config.compact_pr_display)
        finally:
            os.unlink(f.name)

    def test_read_one_config_git_section(self):
        """Test reading GIT section from config file."""
        config = StackyConfig()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write("[GIT]\n")
            f.write("use_merge = true\n")
            f.write("use_force_push = false\n")
            f.name
        try:
            config.read_one_config(f.name)
            self.assertTrue(config.use_merge)
            self.assertFalse(config.use_force_push)
        finally:
            os.unlink(f.name)


class TestReadConfig(unittest.TestCase):
    """Tests for read_config function."""

    @patch("os.path.exists", return_value=False)
    @patch("stacky.utils.config.debug")
    def test_read_config_no_files(self, mock_debug, mock_exists):
        """Test read_config returns defaults when no config files exist."""
        config = read_config()
        self.assertIsInstance(config, StackyConfig)
        self.assertFalse(config.skip_confirm)

    @patch("os.path.exists", return_value=False)
    def test_read_config_with_no_files(self, mock_exists):
        """Test read_config returns defaults when no config files exist."""
        # Mock the get_top_level_dir to raise an exception (not in git repo)
        with patch("stacky.git.branch.get_top_level_dir", side_effect=Exception("Not in git repo")):
            config = read_config()
            self.assertIsInstance(config, StackyConfig)
            # Should have default values
            self.assertFalse(config.skip_confirm)


class TestGetConfig(unittest.TestCase):
    """Tests for get_config singleton function."""

    def setUp(self):
        """Reset global CONFIG before each test."""
        import stacky.utils.config as config_module
        config_module.CONFIG = None

    @patch("stacky.utils.config.read_config")
    def test_get_config_caches_result(self, mock_read_config):
        """Test get_config caches the config and only reads once."""
        mock_config = StackyConfig(skip_confirm=True)
        mock_read_config.return_value = mock_config

        result1 = get_config()
        result2 = get_config()

        self.assertEqual(result1, result2)
        mock_read_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
