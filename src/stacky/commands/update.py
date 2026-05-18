"""Update commands - update, import, adopt."""

from stacky.git.branch import get_current_branch_name, get_real_stack_bottom, set_current_branch
from stacky.git.refs import get_merge_base, set_parent, set_parent_commit
from stacky.git.remote import start_muxed_ssh, stop_muxed_ssh
from stacky.pr.github import get_pr_info
from stacky.stack.models import StackBranch, StackBranchSet
from stacky.stack.operations import cleanup_unused_refs, delete_branches, get_branches_to_delete
from stacky.stack.tree import get_bottom_level_branches_as_forest, load_pr_info_for_forest
from stacky.utils.config import get_config
from stacky.utils.logging import cout, die, info
from stacky.utils.shell import run, run_always_return
from stacky.utils.types import BranchName, CmdArgs, Commit, FROZEN_STACK_BOTTOMS, STACK_BOTTOMS
from stacky.utils.ui import confirm


def cmd_update(stack: StackBranchSet, args):
    """Update repo from remote."""
    remote = "origin"
    start_muxed_ssh(remote)
    info("Fetching from {}", remote)
    run(CmdArgs(["git", "fetch", remote]))

    current_branch = get_current_branch_name()
    for b in stack.bottoms:
        run(
            CmdArgs([
                "git", "update-ref",
                "refs/heads/{}".format(b.name),
                "refs/remotes/{}/{}".format(remote, b.remote_branch),
            ])
        )
        if b.name == current_branch:
            run(CmdArgs(["git", "reset", "--hard", "HEAD"]))

    info("Checking if any PRs have been merged and can be deleted")
    forest = get_bottom_level_branches_as_forest(stack)
    load_pr_info_for_forest(forest)

    deletes = get_branches_to_delete(forest)
    if deletes and not args.force:
        confirm()

    delete_branches(stack, deletes)
    stop_muxed_ssh(remote)

    info("Cleaning up refs for non-existent branches")
    cleanup_unused_refs(stack)


def cmd_import(stack: StackBranchSet, args):
    """Import Graphite stack."""
    branch = args.name
    branches = []
    bottoms = set(b.name for b in stack.bottoms)
    while branch not in bottoms:
        pr_info = get_pr_info(branch, full=True)
        open_pr = pr_info.open
        info("Getting PR information for {}", branch)
        if open_pr is None:
            die("Branch {} has no open PR", branch)
            assert open_pr is not None
        if open_pr["headRefName"] != branch:
            die(
                "Branch {} is misconfigured: PR #{} head is {}",
                branch, open_pr["number"], open_pr["headRefName"],
            )
        if not open_pr["commits"]:
            die("PR #{} has no commits", open_pr["number"])
        first_commit = open_pr["commits"][0]["oid"]
        parent_commit = Commit(run_always_return(CmdArgs(["git", "rev-parse", "{}^".format(first_commit)])))
        next_branch = open_pr["baseRefName"]
        info(
            "Branch {}: PR #{}, parent is {} at commit {}",
            branch, open_pr["number"], next_branch, parent_commit,
        )
        branches.append((branch, parent_commit))
        branch = next_branch

    if not branches:
        return

    base_branch = branch
    branches.reverse()

    for b, parent_commit in branches:
        cout("- Will set parent of {} to {} at commit {}\n", b, branch, parent_commit)
        branch = b

    if not args.force:
        confirm()

    branch = base_branch
    for b, parent_commit in branches:
        set_parent(b, branch, set_origin=True)
        set_parent_commit(b, parent_commit)
        branch = b


def cmd_adopt(stack: StackBranch, args):
    """Adopt a branch onto current stack bottom."""
    branch = args.name
    current_branch = get_current_branch_name()

    if branch == current_branch:
        die("A branch cannot adopt itself")

    if current_branch not in STACK_BOTTOMS:
        main_branch = get_real_stack_bottom()
        if get_config().change_to_main and main_branch is not None:
            run(CmdArgs(["git", "checkout", main_branch]))
            set_current_branch(main_branch)
            current_branch = main_branch
        else:
            die(
                "The current branch {} must be a valid stack bottom: {}",
                current_branch, ", ".join(sorted(STACK_BOTTOMS)),
            )

    if branch in STACK_BOTTOMS:
        if branch in FROZEN_STACK_BOTTOMS:
            die("Cannot adopt frozen stack bottoms {}".format(FROZEN_STACK_BOTTOMS))
        run(CmdArgs(["git", "update-ref", "-d", "refs/stacky-bottom-branch/{}".format(branch)]))

    parent_commit = get_merge_base(current_branch, branch)
    set_parent(branch, current_branch, set_origin=True)
    set_parent_commit(branch, parent_commit)
    if get_config().change_to_adopted:
        run(CmdArgs(["git", "checkout", branch]))
