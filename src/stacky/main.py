"""Main entry point for stacky."""

import json
import logging
import os
import sys
from argparse import ArgumentParser

import argcomplete  # type: ignore

from stacky.git.branch import (
    branch_name_completer, check_gh_auth, get_current_branch_name,
    get_real_stack_bottom, init_git, set_current_branch
)
from stacky.stack.models import StackBranchSet
from stacky.stack.operations import inner_do_sync, load_all_stacks, load_stack_for_given_branch
from stacky.stack.tree import get_current_stack_as_forest
from stacky.utils.config import get_config
from stacky.utils.logging import (
    ExitException, _LOGGING_FORMAT, error, set_color_mode
)
from stacky.utils.shell import run
from stacky.utils.types import BranchName, LOGLEVELS, STATE_FILE

# Import all command handlers
from stacky.commands.navigation import cmd_info, cmd_log, cmd_branch_up, cmd_branch_down
from stacky.commands.branch import cmd_branch_new, cmd_branch_commit, cmd_branch_checkout
from stacky.commands.commit import cmd_commit, cmd_amend
from stacky.commands.stack import cmd_stack_info, cmd_stack_push, cmd_stack_sync, cmd_stack_checkout
from stacky.commands.upstack import (
    cmd_upstack_info, cmd_upstack_push, cmd_upstack_sync, cmd_upstack_onto, cmd_upstack_as
)
from stacky.commands.downstack import cmd_downstack_info, cmd_downstack_push, cmd_downstack_sync
from stacky.commands.update import cmd_update, cmd_import, cmd_adopt
from stacky.commands.land import cmd_land
from stacky.commands.inbox import cmd_inbox, cmd_prs
from stacky.commands.fold import (
    cmd_fold, inner_do_fold, finish_merge_fold_operation
)
from stacky.commands.recreate import cmd_recreate


def main():
    """Main entry point for stacky."""
    logging.basicConfig(format=_LOGGING_FORMAT, level=logging.INFO)
    try:
        parser = ArgumentParser(description="Handle git stacks")
        parser.add_argument(
            "--log-level", default="info", choices=LOGLEVELS.keys(),
            help="Set the log level",
        )
        parser.add_argument(
            "--color", default="auto", choices=["always", "auto", "never"],
            help="Colorize output and error",
        )
        parser.add_argument(
            "--remote-name", "-r", default="origin",
            help="name of the git remote where branches will be pushed",
        )

        subparsers = parser.add_subparsers(required=True, dest="command")

        # continue
        continue_parser = subparsers.add_parser("continue", help="Continue previously interrupted command")
        continue_parser.set_defaults(func=None)

        # down / up
        down_parser = subparsers.add_parser("down", help="Go down in the current stack (towards master/main)")
        down_parser.set_defaults(func=cmd_branch_down)
        up_parser = subparsers.add_parser("up", help="Go up in the current stack (away master/main)")
        up_parser.set_defaults(func=cmd_branch_up)

        # info
        info_parser = subparsers.add_parser("info", help="Stack info")
        info_parser.add_argument("--pr", action="store_true", help="Get PR info (slow)")
        info_parser.set_defaults(func=cmd_info)

        # log
        log_parser = subparsers.add_parser("log", help="Show git log with conditional merge handling")
        log_parser.set_defaults(func=cmd_log)

        # commit
        commit_parser = subparsers.add_parser("commit", help="Commit")
        commit_parser.add_argument("-m", help="Commit message", dest="message")
        commit_parser.add_argument("--amend", action="store_true", help="Amend last commit")
        commit_parser.add_argument("--allow-empty", action="store_true", help="Allow empty commit")
        commit_parser.add_argument("--no-edit", action="store_true", help="Skip editor")
        commit_parser.add_argument("-a", action="store_true", help="Add all files to commit", dest="add_all")
        commit_parser.add_argument("--no-verify", action="store_true", help="Bypass pre-commit and commit-msg hooks")
        commit_parser.set_defaults(func=cmd_commit)

        # amend
        amend_parser = subparsers.add_parser("amend", help="Shortcut for amending last commit")
        amend_parser.add_argument("--no-verify", action="store_true", help="Bypass pre-commit and commit-msg hooks")
        amend_parser.set_defaults(func=cmd_amend)

        _setup_branch_subcommands(subparsers)
        _setup_stack_subcommands(subparsers)
        _setup_upstack_subcommands(subparsers)
        _setup_downstack_subcommands(subparsers)
        _setup_other_commands(subparsers)

        argcomplete.autocomplete(parser)
        args = parser.parse_args()
        logging.basicConfig(format=_LOGGING_FORMAT, level=LOGLEVELS[args.log_level], force=True)
        set_color_mode(args.color)

        from stacky.git.snapshot import load_snapshot
        snapshot = load_snapshot()
        init_git(snapshot)
        if _needs_gh(args):
            check_gh_auth()
        stack = StackBranchSet()
        load_all_stacks(stack, snapshot)

        current_branch = get_current_branch_name()
        if args.command == "continue":
            _handle_continue(stack, current_branch)
        elif args.command == "recreate":
            args.func(stack, args)
        else:
            if current_branch not in stack.stack:
                main_branch = get_real_stack_bottom()
                if get_config().change_to_main and main_branch is not None:
                    run(["git", "checkout", main_branch])
                    set_current_branch(main_branch)
                else:
                    from stacky.utils.logging import die
                    die("Current branch {} is not in a stack", current_branch)

            get_current_stack_as_forest(stack)
            args.func(stack, args)

        # Success, delete the state file
        try:
            os.remove(STATE_FILE)
        except FileNotFoundError:
            pass
    except ExitException as e:
        error("{}", e.args[0])
        sys.exit(1)


def _needs_gh(args) -> bool:
    """Whether this invocation will shell out to `gh`.

    Commands that always use `gh` set `needs_gh=True` via set_defaults on
    their subparser. Commands where `gh` is toggled by `--pr` / `--no-pr`
    are handled by checking `args.pr` here — no subparser flag needed.
    """
    return getattr(args, "needs_gh", False) or getattr(args, "pr", False)


def _handle_continue(stack: StackBranchSet, current_branch: BranchName):
    """Handle the 'continue' command for interrupted operations."""
    from stacky.utils.logging import die

    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except FileNotFoundError:
        die("No previous command in progress")

    branch = state["branch"]
    run(["git", "checkout", branch])
    set_current_branch(branch)

    if branch not in stack.stack:
        die("Current branch {} is not in a stack", branch)

    if "sync" in state:
        sync_names = state["sync"]
        syncs = [stack.stack[n] for n in sync_names]
        inner_do_sync(syncs, sync_names)
    elif "fold" in state:
        fold_state = state["fold"]
        inner_do_fold(
            stack,
            fold_state["fold_branch"],
            fold_state["parent_branch"],
            fold_state["commits"],
            fold_state["children"],
            fold_state["allow_empty"]
        )
    elif "merge_fold" in state:
        merge_fold_state = state["merge_fold"]
        finish_merge_fold_operation(
            stack,
            merge_fold_state["fold_branch"],
            merge_fold_state["parent_branch"],
            merge_fold_state["children"]
        )
    else:
        die("Unknown operation in progress")


def _setup_branch_subcommands(subparsers):
    """Setup branch subcommands."""
    branch_parser = subparsers.add_parser("branch", aliases=["b"], help="Operations on branches")
    branch_subparsers = branch_parser.add_subparsers(required=True, dest="branch_command")

    branch_up_parser = branch_subparsers.add_parser("up", aliases=["u"], help="Move upstack")
    branch_up_parser.set_defaults(func=cmd_branch_up)

    branch_down_parser = branch_subparsers.add_parser("down", aliases=["d"], help="Move downstack")
    branch_down_parser.set_defaults(func=cmd_branch_down)

    branch_new_parser = branch_subparsers.add_parser("new", aliases=["create"], help="Create a new branch")
    branch_new_parser.add_argument("name", help="Branch name")
    branch_new_parser.set_defaults(func=cmd_branch_new)

    branch_commit_parser = branch_subparsers.add_parser("commit", help="Create a new branch and commit all changes")
    branch_commit_parser.add_argument("name", help="Branch name")
    branch_commit_parser.add_argument("-m", help="Commit message", dest="message")
    branch_commit_parser.add_argument("-a", action="store_true", help="Add all files to commit", dest="add_all")
    branch_commit_parser.add_argument("--no-verify", action="store_true", help="Bypass pre-commit and commit-msg hooks")
    branch_commit_parser.set_defaults(func=cmd_branch_commit)

    branch_checkout_parser = branch_subparsers.add_parser("checkout", aliases=["co"], help="Checkout a branch")
    branch_checkout_parser.add_argument("name", help="Branch name", nargs="?").completer = branch_name_completer
    branch_checkout_parser.set_defaults(func=cmd_branch_checkout)


def _setup_stack_subcommands(subparsers):
    """Setup stack subcommands."""
    stack_parser = subparsers.add_parser("stack", aliases=["s"], help="Operations on the full current stack")
    stack_subparsers = stack_parser.add_subparsers(required=True, dest="stack_command")

    stack_info_parser = stack_subparsers.add_parser("info", aliases=["i"], help="Info for current stack")
    stack_info_parser.add_argument("--pr", action="store_true", help="Get PR info (slow)")
    stack_info_parser.set_defaults(func=cmd_stack_info)

    stack_push_parser = stack_subparsers.add_parser("push", help="Push")
    stack_push_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    stack_push_parser.add_argument("--no-pr", dest="pr", action="store_false", help="Skip Create PRs")
    stack_push_parser.set_defaults(func=cmd_stack_push)

    stack_sync_parser = stack_subparsers.add_parser("sync", help="Sync")
    stack_sync_parser.set_defaults(func=cmd_stack_sync)

    stack_checkout_parser = stack_subparsers.add_parser("checkout", aliases=["co"], help="Checkout a branch in this stack")
    stack_checkout_parser.set_defaults(func=cmd_stack_checkout)


def _setup_upstack_subcommands(subparsers):
    """Setup upstack subcommands."""
    upstack_parser = subparsers.add_parser("upstack", aliases=["us"], help="Operations on the current upstack")
    upstack_subparsers = upstack_parser.add_subparsers(required=True, dest="upstack_command")

    upstack_info_parser = upstack_subparsers.add_parser("info", aliases=["i"], help="Info for current upstack")
    upstack_info_parser.add_argument("--pr", action="store_true", help="Get PR info (slow)")
    upstack_info_parser.set_defaults(func=cmd_upstack_info)

    upstack_push_parser = upstack_subparsers.add_parser("push", help="Push")
    upstack_push_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    upstack_push_parser.add_argument("--no-pr", dest="pr", action="store_false", help="Skip Create PRs")
    upstack_push_parser.set_defaults(func=cmd_upstack_push)

    upstack_sync_parser = upstack_subparsers.add_parser("sync", help="Sync")
    upstack_sync_parser.set_defaults(func=cmd_upstack_sync)

    upstack_onto_parser = upstack_subparsers.add_parser("onto", aliases=["restack"], help="Restack")
    upstack_onto_parser.add_argument("target", help="New parent")
    upstack_onto_parser.set_defaults(func=cmd_upstack_onto)

    upstack_as_parser = upstack_subparsers.add_parser("as", help="Upstack branch this as a new stack bottom")
    upstack_as_parser.add_argument("target", help="bottom, restack this branch as a new stack bottom").completer = branch_name_completer
    upstack_as_parser.set_defaults(func=cmd_upstack_as)


def _setup_downstack_subcommands(subparsers):
    """Setup downstack subcommands."""
    downstack_parser = subparsers.add_parser("downstack", aliases=["ds"], help="Operations on the current downstack")
    downstack_subparsers = downstack_parser.add_subparsers(required=True, dest="downstack_command")

    downstack_info_parser = downstack_subparsers.add_parser("info", aliases=["i"], help="Info for current downstack")
    downstack_info_parser.add_argument("--pr", action="store_true", help="Get PR info (slow)")
    downstack_info_parser.set_defaults(func=cmd_downstack_info)

    downstack_push_parser = downstack_subparsers.add_parser("push", help="Push")
    downstack_push_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    downstack_push_parser.add_argument("--no-pr", dest="pr", action="store_false", help="Skip Create PRs")
    downstack_push_parser.set_defaults(func=cmd_downstack_push)

    downstack_sync_parser = downstack_subparsers.add_parser("sync", help="Sync")
    downstack_sync_parser.set_defaults(func=cmd_downstack_sync)


def _setup_other_commands(subparsers):
    """Setup other commands (update, import, adopt, land, shortcuts, etc.)."""
    # update
    update_parser = subparsers.add_parser("update", help="Update repo, all bottom branches must exist in remote")
    update_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    update_parser.set_defaults(func=cmd_update, needs_gh=True)

    # import
    import_parser = subparsers.add_parser("import", help="Import Graphite stack")
    import_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    import_parser.add_argument("name", help="Foreign stack top").completer = branch_name_completer
    import_parser.set_defaults(func=cmd_import, needs_gh=True)

    # adopt
    adopt_parser = subparsers.add_parser("adopt", help="Adopt one branch")
    adopt_parser.add_argument("name", help="Branch name").completer = branch_name_completer
    adopt_parser.set_defaults(func=cmd_adopt)

    # land
    land_parser = subparsers.add_parser("land", help="Land bottom-most PR on current stack")
    land_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    land_parser.add_argument("--auto", "-a", action="store_true", help="Automatically merge after all checks pass")
    land_parser.set_defaults(func=cmd_land, needs_gh=True)

    # shortcuts
    push_parser = subparsers.add_parser("push", help="Alias for downstack push")
    push_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    push_parser.add_argument("--no-pr", dest="pr", action="store_false", help="Skip Create PRs")
    push_parser.set_defaults(func=cmd_downstack_push)

    sync_parser = subparsers.add_parser("sync", help="Alias for stack sync")
    sync_parser.set_defaults(func=cmd_stack_sync)

    checkout_parser = subparsers.add_parser("checkout", aliases=["co"], help="Checkout a branch")
    checkout_parser.add_argument("name", help="Branch name", nargs="?").completer = branch_name_completer
    checkout_parser.set_defaults(func=cmd_branch_checkout)

    sco_parser = subparsers.add_parser("sco", help="Checkout a branch in this stack")
    sco_parser.set_defaults(func=cmd_stack_checkout)

    # inbox
    inbox_parser = subparsers.add_parser("inbox", help="List all active GitHub pull requests for the current user")
    inbox_parser.add_argument("--compact", "-c", action="store_true", help="Show compact view")
    inbox_parser.set_defaults(func=cmd_inbox, needs_gh=True)

    # prs
    prs_parser = subparsers.add_parser("prs", help="Interactive PR management - select and edit PR descriptions")
    prs_parser.set_defaults(func=cmd_prs, needs_gh=True)

    # fold
    fold_parser = subparsers.add_parser("fold", help="Fold current branch into parent branch and delete current branch")
    fold_parser.add_argument("--allow-empty", action="store_true", help="Allow empty commits during cherry-pick")
    fold_parser.set_defaults(func=cmd_fold)

    # recreate
    recreate_parser = subparsers.add_parser(
        "recreate",
        help="Rebuild a stack from `stacky info` output (read from stdin or --file)",
    )
    recreate_parser.add_argument("--file", help="Read stack info from a file instead of stdin")
    recreate_parser.add_argument("--force", "-f", action="store_true", help="Bypass confirmation")
    recreate_parser.set_defaults(func=cmd_recreate)
