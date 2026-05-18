"""Commit commands - commit, amend."""

from stacky.git.branch import get_current_branch_name
from stacky.git.refs import get_commit
from stacky.stack.models import StackBranchSet
from stacky.stack.operations import do_sync
from stacky.stack.tree import get_current_upstack_as_forest
from stacky.utils.config import get_config
from stacky.utils.logging import die
from stacky.utils.shell import run
from stacky.utils.types import CmdArgs


def do_commit(stack: StackBranchSet, *, message=None, amend=False, allow_empty=False,
              edit=True, add_all=False, no_verify=False):
    """Perform a commit operation."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    if not b.parent:
        die("Do not commit directly on {}", b.name)
    if not b.is_synced_with_parent():
        die(
            "Branch {} is not synced with parent {}, sync before committing",
            b.name, b.parent.name,
        )

    if amend and (get_config().use_merge or not get_config().use_force_push):
        die("Amending is not allowed if using git merge or if force pushing is disallowed")

    if amend and b.commit == b.parent.commit:
        die("Branch {} has no commits, may not amend", b.name)

    cmd = ["git", "commit"]
    if add_all:
        cmd += ["-a"]
    if allow_empty:
        cmd += ["--allow-empty"]
    if no_verify:
        cmd += ["--no-verify"]
    if amend:
        cmd += ["--amend"]
        if not edit:
            cmd += ["--no-edit"]
    elif not edit:
        die("--no-edit is only supported with --amend")
    if message:
        cmd += ["-m", message]
    run(CmdArgs(cmd), out=True)

    # Sync everything upstack
    b.commit = get_commit(b.name)
    do_sync(get_current_upstack_as_forest(stack))


def cmd_commit(stack: StackBranchSet, args):
    """Commit command handler."""
    do_commit(
        stack,
        message=args.message,
        amend=args.amend,
        allow_empty=args.allow_empty,
        edit=not args.no_edit,
        add_all=args.add_all,
        no_verify=args.no_verify,
    )


def cmd_amend(stack: StackBranchSet, args):
    """Amend last commit (shortcut)."""
    do_commit(stack, amend=True, edit=False, no_verify=args.no_verify)
