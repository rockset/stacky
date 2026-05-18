"""Branch commands - new, commit, checkout."""

from stacky.commands.commit import do_commit
from stacky.git.branch import checkout, create_branch, get_current_branch_name, set_current_branch
from stacky.git.refs import get_commit
from stacky.stack.models import StackBranchSet
from stacky.stack.operations import load_stack_for_given_branch
from stacky.stack.tree import get_all_stacks_as_forest
from stacky.utils.shell import run
from stacky.utils.types import BranchName, CmdArgs
from stacky.utils.ui import menu_choose_branch


def cmd_branch_new(stack: StackBranchSet, args):
    """Create a new branch on top of the current branch."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    assert b.commit
    name = args.name
    create_branch(name)
    run(CmdArgs(["git", "update-ref", "refs/stack-parent/{}".format(name), b.commit, ""]))


def cmd_branch_commit(stack: StackBranchSet, args):
    """Create a new branch and commit all changes with the provided message."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    assert b.commit
    name = args.name
    create_branch(name)
    run(CmdArgs(["git", "update-ref", "refs/stack-parent/{}".format(name), b.commit, ""]))

    # Update global CURRENT_BRANCH since we just checked out the new branch
    set_current_branch(BranchName(name))

    # Reload the stack to include the new branch
    load_stack_for_given_branch(stack, BranchName(name))

    # Now commit all changes with the provided message
    do_commit(
        stack,
        message=args.message,
        amend=False,
        allow_empty=False,
        edit=True,
        add_all=args.add_all,
        no_verify=args.no_verify,
    )


def cmd_branch_checkout(stack: StackBranchSet, args):
    """Checkout a branch (with menu if no name provided)."""
    branch_name = args.name
    if branch_name is None:
        forest = get_all_stacks_as_forest(stack)
        branch_name = menu_choose_branch(forest).name
    checkout(branch_name)
