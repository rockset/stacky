"""Downstack commands - info, push, sync."""

from stacky.stack.models import StackBranchSet
from stacky.stack.operations import do_push, do_sync
from stacky.stack.tree import (
    get_current_downstack_as_forest, load_pr_info_for_forest, print_forest
)


def cmd_downstack_info(stack: StackBranchSet, args):
    """Show info for current downstack."""
    forest = get_current_downstack_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_downstack_push(stack: StackBranchSet, args):
    """Push current downstack."""
    do_push(
        get_current_downstack_as_forest(stack),
        force=args.force,
        pr=args.pr,
        remote_name=args.remote_name,
    )


def cmd_downstack_sync(stack: StackBranchSet, args):
    """Sync current downstack."""
    do_sync(get_current_downstack_as_forest(stack))
