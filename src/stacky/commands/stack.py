"""Stack commands - stack info, push, sync, checkout."""

from stacky.git.branch import checkout
from stacky.stack.models import StackBranchSet
from stacky.stack.operations import do_push, do_sync
from stacky.stack.tree import (
    get_current_stack_as_forest, load_pr_info_for_forest, print_forest
)
from stacky.utils.ui import menu_choose_branch


def cmd_stack_info(stack: StackBranchSet, args):
    """Show info for current stack."""
    forest = get_current_stack_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_stack_push(stack: StackBranchSet, args):
    """Push current stack."""
    do_push(
        get_current_stack_as_forest(stack),
        force=args.force,
        pr=args.pr,
        remote_name=args.remote_name,
    )


def cmd_stack_sync(stack: StackBranchSet, args):
    """Sync current stack."""
    do_sync(get_current_stack_as_forest(stack))


def cmd_stack_checkout(stack: StackBranchSet, args):
    """Checkout a branch in current stack."""
    forest = get_current_stack_as_forest(stack)
    branch_name = menu_choose_branch(forest).name
    checkout(branch_name)
