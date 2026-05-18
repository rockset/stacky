"""Configuration management for stacky."""

import configparser
import dataclasses
import os
from typing import Optional

from stacky.utils.logging import debug


@dataclasses.dataclass
class StackyConfig:
    """Configuration options for stacky."""
    skip_confirm: bool = False
    change_to_main: bool = False
    change_to_adopted: bool = False
    share_ssh_session: bool = False
    use_merge: bool = False
    use_force_push: bool = True
    compact_pr_display: bool = False
    enable_stack_comment: bool = True

    def read_one_config(self, config_path: str):
        """Read configuration from a single file."""
        rawconfig = configparser.ConfigParser()
        rawconfig.read(config_path)
        if rawconfig.has_section("UI"):
            self.skip_confirm = rawconfig.getboolean("UI", "skip_confirm", fallback=self.skip_confirm)
            self.change_to_main = rawconfig.getboolean("UI", "change_to_main", fallback=self.change_to_main)
            self.change_to_adopted = rawconfig.getboolean("UI", "change_to_adopted", fallback=self.change_to_adopted)
            self.share_ssh_session = rawconfig.getboolean("UI", "share_ssh_session", fallback=self.share_ssh_session)
            self.compact_pr_display = rawconfig.getboolean("UI", "compact_pr_display", fallback=self.compact_pr_display)
            self.enable_stack_comment = rawconfig.getboolean("UI", "enable_stack_comment", fallback=self.enable_stack_comment)

        if rawconfig.has_section("GIT"):
            self.use_merge = rawconfig.getboolean("GIT", "use_merge", fallback=self.use_merge)
            self.use_force_push = rawconfig.getboolean("GIT", "use_force_push", fallback=self.use_force_push)


# Global config singleton
CONFIG: Optional[StackyConfig] = None


def get_config() -> StackyConfig:
    """Get the global configuration, loading it if necessary."""
    global CONFIG
    if CONFIG is None:
        CONFIG = read_config()
    return CONFIG


def read_config() -> StackyConfig:
    """Read configuration from config files."""
    config = StackyConfig()
    config_paths = [os.path.expanduser("~/.stackyconfig")]

    try:
        from stacky.git.branch import get_top_level_dir
        root_dir = get_top_level_dir()
        config_paths.append(f"{root_dir}/.stackyconfig")
    except Exception:
        # Not in a git repository, skip the repo-level config
        debug("Not in a git repository, skipping repo-level config")
        pass

    for p in config_paths:
        # Root dir config overwrites home directory config
        if os.path.exists(p):
            config.read_one_config(p)

    return config
