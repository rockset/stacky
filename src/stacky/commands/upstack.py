"""Upstack commands - info, push, sync, onto, as."""

from stacky.git.branch import get_current_branch_name
from stacky.git.refs import set_parent
from stacky.stack.models import StackBranchSet
from stacky.stack.operations import do_push, do_sync
from stacky.stack.tree import (
    forest_depth_first, get_current_upstack_as_forest,
    load_pr_info_for_forest, print_forest
)
from stacky.utils.logging import die, info
from stacky.utils.shell import run
from stacky.utils.types import CmdArgs


def cmd_upstack_info(stack: StackBranchSet, args):
    """Show info for current upstack."""
    forest = get_current_upstack_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_upstack_push(stack: StackBranchSet, args):
    """Push current upstack."""
    do_push(
        get_current_upstack_as_forest(stack),
        force=args.force,
        pr=args.pr,
        remote_name=args.remote_name,
    )


def cmd_upstack_sync(stack: StackBranchSet, args):
    """Sync current upstack."""
    do_sync(get_current_upstack_as_forest(stack))


def cmd_upstack_onto(stack: StackBranchSet, args):
    """Move current upstack onto a different parent."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    if not b.parent:
        die("may not upstack a stack bottom, use stacky adopt")
    target = stack.stack[args.target]
    upstack = get_current_upstack_as_forest(stack)
    for ub in forest_depth_first(upstack):
        if ub == target:
            die("Target branch {} is upstack of {}", target.name, b.name)
    b.parent = target
    set_parent(b.name, target.name)
    do_sync(upstack)


def cmd_upstack_as_base(stack: StackBranchSet):
    """Set current branch as a new stack bottom."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    if not b.parent:
        die("Branch {} is already a stack bottom", b.name)

    b.parent = None  # type: ignore
    stack.remove(b.name)
    stack.addStackBranch(b)
    set_parent(b.name, None)

    run(CmdArgs(["git", "update-ref", "refs/stacky-bottom-branch/{}".format(b.name), b.commit, ""]))
    info("Set {} as new bottom branch".format(b.name))


def cmd_upstack_as(stack: StackBranchSet, args):
    """Upstack branch as something (e.g., bottom)."""
    if args.target == "bottom":
        cmd_upstack_as_base(stack)
    else:
        die("Invalid target {}, acceptable targets are [base]", args.target)
