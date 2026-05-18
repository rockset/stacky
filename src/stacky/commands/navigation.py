"""Navigation commands - info, log, up, down."""

from stacky.git.branch import checkout, get_current_branch_name
from stacky.stack.models import StackBranchSet
from stacky.stack.tree import (
    get_all_stacks_as_forest, load_pr_info_for_forest, print_forest
)
from stacky.utils.config import get_config
from stacky.utils.logging import IS_TERMINAL, cout, die, info
from stacky.utils.shell import run
from stacky.utils.types import BranchesTreeForest, BranchName, BranchesTree
from stacky.utils.ui import menu_choose_branch


def cmd_info(stack: StackBranchSet, args):
    """Show info for all stacks."""
    forest = get_all_stacks_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_log(stack: StackBranchSet, args):
    """Show git log with conditional merge handling."""
    config = get_config()
    if config.use_merge:
        run(["git", "log", "--no-merges", "--first-parent"], out=True)
    else:
        run(["git", "log"], out=True)


def cmd_branch_up(stack: StackBranchSet, args):
    """Move up in the stack (away from master/main)."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    if not b.children:
        info("Branch {} is already at the top of the stack", current_branch)
        return
    if len(b.children) > 1:
        if not IS_TERMINAL:
            die(
                "Branch {} has multiple children: {}",
                current_branch, ", ".join(c.name for c in b.children),
            )
        cout(
            "Branch {} has {} children, choose one\n",
            current_branch, len(b.children), fg="green",
        )
        forest = BranchesTreeForest([
            BranchesTree({BranchName(c.name): (c, BranchesTree({}))})
            for c in b.children
        ])
        child = menu_choose_branch(forest).name
    else:
        child = next(iter(b.children)).name
    checkout(child)


def cmd_branch_down(stack: StackBranchSet, args):
    """Move down in the stack (towards master/main)."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    if not b.parent:
        info("Branch {} is already at the bottom of the stack", current_branch)
        return
    checkout(b.parent.name)
