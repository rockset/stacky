"""Stacky - GitHub helper for stacked diffs."""

from .main import main

# Re-exports for backward compatibility with tests
from .utils.shell import _check_returncode, run, run_always_return, run_multiline
from .utils.logging import (
    die, cout, debug, info, warning, error, fmt,
    COLOR_STDOUT, COLOR_STDERR, ExitException
)
from .utils.types import BranchName, Commit, CmdArgs, STACK_BOTTOMS
from .utils.config import StackyConfig, get_config, read_config
from .utils.ui import confirm, prompt

from .git.branch import (
    get_current_branch, get_all_branches, get_top_level_dir,
    get_stack_parent_branch, checkout, create_branch
)
from .git.remote import (
    get_remote_info, get_remote_type, gen_ssh_mux_cmd,
    start_muxed_ssh, stop_muxed_ssh
)
from .git.refs import get_stack_parent_commit, set_parent_commit, get_commit

from .stack.models import PRInfo, PRInfos, StackBranch, StackBranchSet
from .stack.tree import (
    get_all_stacks_as_forest, get_current_stack_as_forest,
    get_current_downstack_as_forest, get_current_upstack_as_forest,
    print_tree, print_forest, format_tree
)

from .pr.github import find_issue_marker, get_pr_info, create_gh_pr

from .commands.land import cmd_land


def runner():
    main()
