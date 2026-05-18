"""Stack operations for stacky - loading, syncing, pushing."""

import json
import os
from typing import List, Optional, Tuple, TYPE_CHECKING

from stacky.git.branch import (
    get_all_branches, get_current_branch_name, get_stack_parent_branch, set_current_branch
)
from stacky.git.refs import (
    get_all_stack_bottoms, get_commit, get_commits_between,
    get_stack_parent_commit, set_parent_commit
)
from stacky.git.remote import start_muxed_ssh, stop_muxed_ssh, validate_local_remote
from stacky.git.snapshot import GitSnapshot, load_snapshot
from stacky.stack.models import BranchNCommit, StackBranch, StackBranchSet
from stacky.stack.tree import (
    forest_depth_first, get_complete_stack_forest_for_branch,
    load_pr_info_for_forest, print_forest
)
from stacky.utils.config import get_config
from stacky.utils.logging import cout, die, info, warning
from stacky.utils.shell import run, run_always_return
from stacky.utils.types import (
    BranchesTreeForest, BranchName, CmdArgs, Commit,
    STACK_BOTTOMS, STATE_FILE, TMP_STATE_FILE
)

if TYPE_CHECKING:
    pass


def load_all_stack_bottoms(snapshot: Optional[GitSnapshot] = None):
    """Load all custom stack bottoms into STACK_BOTTOMS."""
    if snapshot is not None:
        STACK_BOTTOMS.update(snapshot.bottoms)
    else:
        STACK_BOTTOMS.update(get_all_stack_bottoms())


def _parent_from_snapshot(snapshot: GitSnapshot, branch: BranchName) -> Optional[BranchName]:
    """Mirror of get_stack_parent_branch using the snapshot's branch_merge dict."""
    p = snapshot.branch_merge.get(branch)
    if p is None or p == branch:
        return None
    return p


def load_stack_for_given_branch(
    stack: StackBranchSet, branch: BranchName, *,
    check: bool = True, snapshot: Optional[GitSnapshot] = None
) -> Tuple[Optional[StackBranch], List[BranchName]]:
    """Load stack for a branch, returns (top_branch, list_of_branches)."""
    branches: List[BranchNCommit] = []
    while branch not in STACK_BOTTOMS:
        if snapshot is not None:
            parent = _parent_from_snapshot(snapshot, branch)
            parent_commit = snapshot.stack_parent_commit.get(branch)
        else:
            parent = get_stack_parent_branch(branch)
            parent_commit = get_stack_parent_commit(branch)
        branches.append(BranchNCommit(branch, parent_commit))
        if not parent or not parent_commit:
            if check:
                die("Branch is not in a stack: {}", branch)
            return None, [b.branch for b in branches]
        branch = parent

    branches.append(BranchNCommit(branch, None))
    top = None
    for b in reversed(branches):
        commit = None
        remote_info = None
        if snapshot is not None:
            commit = snapshot.head_commit.get(b.branch)
            if commit is not None:
                validate_local_remote(b.branch, snapshot.branch_remote.get(b.branch))
                remote_info = (
                    snapshot.remote_name,
                    b.branch,
                    snapshot.remote_commit.get(b.branch),
                )
        n = stack.add(
            b.branch,
            parent=top,
            parent_commit=b.parent_commit,
            commit=commit,
            remote_info=remote_info,
        )
        if top:
            stack.add_child(top, n)
        top = n

    return top, [b.branch for b in branches]


def load_all_stacks(
    stack: StackBranchSet, snapshot: Optional[GitSnapshot] = None
) -> Optional[StackBranch]:
    """Load all stacks, return top of current branch's stack."""
    if snapshot is None:
        snapshot = load_snapshot()
    load_all_stack_bottoms(snapshot)
    all_branches = set(snapshot.head_commit.keys())
    current_branch = get_current_branch_name()
    current_branch_top = None
    while all_branches:
        b = all_branches.pop()
        top, branches = load_stack_for_given_branch(stack, b, check=False, snapshot=snapshot)
        all_branches -= set(branches)
        if top is None:
            if len(branches) > 1:
                warning("Broken stack: {}", " -> ".join(branches))
            continue
        if b == current_branch:
            current_branch_top = top
    return current_branch_top


def inner_do_sync(syncs: List[StackBranch], sync_names: List[BranchName]):
    """Execute sync operations on branches."""
    print()
    current_branch = get_current_branch_name()
    sync_type = "merge" if get_config().use_merge else "rebase"
    while syncs:
        with open(TMP_STATE_FILE, "w") as f:
            json.dump({"branch": current_branch, "sync": sync_names}, f)
        os.replace(TMP_STATE_FILE, STATE_FILE)

        b = syncs.pop()
        sync_names.pop()
        if b.is_synced_with_parent():
            cout("{} is already synced on top of {}\n", b.name, b.parent.name)
            continue
        if b.parent.commit in get_commits_between(b.parent_commit, b.commit):
            cout(
                "Recording complete {} of {} on top of {}\n",
                sync_type, b.name, b.parent.name, fg="green",
            )
        else:
            r = None
            if get_config().use_merge:
                cout("Merging {} into {}\n", b.parent.name, b.name, fg="green")
                run(CmdArgs(["git", "checkout", str(b.name)]))
                r = run(CmdArgs(["git", "merge", b.parent.name]), out=True, check=False)
            else:
                cout("Rebasing {} on top of {}\n", b.name, b.parent.name, fg="green")
                r = run(
                    CmdArgs(["git", "rebase", "--onto", b.parent.name, b.parent_commit, b.name]),
                    out=True, check=False,
                )

            if r is None:
                print()
                die(
                    "Automatic {0} failed. Please complete the {0} (fix conflicts; "
                    "`git {0} --continue`), then run `stacky continue`".format(sync_type)
                )
            b.commit = get_commit(b.name)
        set_parent_commit(b.name, b.parent.commit, b.parent_commit)
        b.parent_commit = b.parent.commit
    run(CmdArgs(["git", "checkout", str(current_branch)]))


def do_sync(forest: BranchesTreeForest):
    """Sync a forest of branches."""
    print_forest(forest)

    syncs: List[StackBranch] = []
    sync_names: List[BranchName] = []
    syncs_set: set[StackBranch] = set()
    for b in forest_depth_first(forest):
        if not b.parent:
            cout("✓ Not syncing base branch {}\n", b.name, fg="green")
            continue
        if b.is_synced_with_parent() and b.parent not in syncs_set:
            cout(
                "✓ Not syncing branch {}, already synced with parent {}\n",
                b.name, b.parent.name, fg="green",
            )
            continue
        syncs.append(b)
        syncs_set.add(b)
        sync_names.append(b.name)
        cout("- Will sync branch {} on top of {}\n", b.name, b.parent.name)

    if not syncs:
        return

    syncs.reverse()
    sync_names.reverse()
    inner_do_sync(syncs, sync_names)


def do_push(
    forest: BranchesTreeForest,
    *,
    force: bool = False,
    pr: bool = False,
    remote_name: str = "origin",
):
    """Push branches in a forest."""
    from stacky.pr.github import add_or_update_stack_comment, create_gh_pr
    from stacky.utils.ui import confirm

    if pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)
    for b in forest_depth_first(forest):
        if not b.is_synced_with_parent():
            die(
                "Branch {} is not synced with parent {}, sync first",
                b.name, b.parent.name,
            )

    PR_NONE = 0
    PR_FIX_BASE = 1
    PR_CREATE = 2
    actions = []
    for b in forest_depth_first(forest):
        if not b.parent:
            cout("✓ Not pushing base branch {}\n", b.name, fg="green")
            continue

        push = False
        if b.is_synced_with_remote():
            cout(
                "✓ Not pushing branch {}, synced with remote {}/{}\n",
                b.name, b.remote, b.remote_branch, fg="green",
            )
        else:
            cout("- Will push branch {} to {}/{}\n", b.name, b.remote, b.remote_branch)
            push = True

        pr_action = PR_NONE
        if pr:
            if b.open_pr_info:
                expected_base = b.parent.name
                if b.open_pr_info["baseRefName"] != expected_base:
                    cout(
                        "- Branch {} already has open PR #{}; will change PR base from {} to {}\n",
                        b.name, b.open_pr_info["number"],
                        b.open_pr_info["baseRefName"], expected_base,
                    )
                    pr_action = PR_FIX_BASE
                else:
                    cout(
                        "✓ Branch {} already has open PR #{}\n",
                        b.name, b.open_pr_info["number"], fg="green",
                    )
            else:
                cout("- Will create PR for branch {}\n", b.name)
                pr_action = PR_CREATE

        if not push and pr_action == PR_NONE:
            continue
        actions.append((b, push, pr_action))

    if actions and not force:
        confirm()

    # Figure out prefix for branch (e.g. user:branch for forks)
    val = run(CmdArgs(["git", "config", f"remote.{remote_name}.gh-resolved"]), check=False)
    if val is not None and "/" in val:
        val = run_always_return(CmdArgs(["git", "config", f"remote.{remote_name}.url"]))
        prefix = f'{val.split(":")[1].split("/")[0]}:'
    else:
        prefix = ""

    muxed = False
    for b, push, pr_action in actions:
        if push:
            if not muxed:
                start_muxed_ssh(remote_name)
                muxed = True
            cout("Pushing {}\n", b.name, fg="green")
            cmd_args = ["git", "push"]
            if get_config().use_force_push:
                cmd_args.append("--force-with-lease")
            cmd_args.extend([b.remote, "{}:{}".format(b.name, b.remote_branch)])
            run(CmdArgs(cmd_args), out=True)
        if pr_action == PR_FIX_BASE:
            cout("Fixing PR base for {}\n", b.name, fg="green")
            assert b.open_pr_info is not None
            run(
                CmdArgs([
                    "gh", "pr", "edit", str(b.open_pr_info["number"]),
                    "--base", b.parent.name,
                ]),
                out=True,
            )
        elif pr_action == PR_CREATE:
            create_gh_pr(b, prefix)

    # Handle stack comments for PRs
    if pr and get_config().enable_stack_comment:
        load_pr_info_for_forest(forest)
        complete_forests_by_root = {}
        branches_with_prs = [b for b in forest_depth_first(forest) if b.open_pr_info]

        for b in branches_with_prs:
            root = b
            while root.parent and root.parent.name not in STACK_BOTTOMS:
                root = root.parent
            root_name = root.name
            if root_name not in complete_forests_by_root:
                complete_forest = get_complete_stack_forest_for_branch(b)
                load_pr_info_for_forest(complete_forest)
                complete_forests_by_root[root_name] = complete_forest

        for b in branches_with_prs:
            root = b
            while root.parent and root.parent.name not in STACK_BOTTOMS:
                root = root.parent
            complete_forest = complete_forests_by_root[root.name]
            add_or_update_stack_comment(b, complete_forest)

    stop_muxed_ssh(remote_name)


def get_branches_to_delete(forest: BranchesTreeForest) -> List[StackBranch]:
    """Get branches that can be deleted (PRs merged)."""
    deletes = []
    for b in forest_depth_first(forest):
        if not b.parent or b.open_pr_info:
            continue
        for pr_info in b.pr_info.values():
            if pr_info["state"] != "MERGED":
                continue
            cout(
                "- Will delete branch {}, PR #{} merged into {}\n",
                b.name, pr_info["number"], b.parent.name,
            )
            deletes.append(b)
            for c in b.children:
                cout("- Will reparent branch {} onto {}\n", c.name, b.parent.name)
            break
    return deletes


def delete_branches(stack: StackBranchSet, deletes: List[StackBranch]):
    """Delete merged branches and reparent their children."""
    from stacky.git.refs import set_parent

    current_branch = get_current_branch_name()
    for b in deletes:
        for c in b.children:
            info("Reparenting {} onto {}", c.name, b.parent.name)
            c.parent = b.parent
            set_parent(c.name, b.parent.name)
        info("Deleting {}", b.name)
        if b.name == current_branch:
            new_branch = next(iter(stack.bottoms))
            info("About to delete current branch, switching to {}", new_branch.name)
            run(CmdArgs(["git", "checkout", new_branch.name]))
            set_current_branch(new_branch.name)
        run(CmdArgs(["git", "branch", "-D", b.name]))


def cleanup_unused_refs(stack: StackBranchSet):
    """Clean up refs for non-existent branches."""
    from stacky.git.refs import get_all_stack_parent_refs

    info("Cleaning up unused refs")
    existing_branches = set(get_all_branches())

    stack_bottoms = get_all_stack_bottoms()
    for bottom in stack_bottoms:
        if bottom not in stack.stack or bottom not in existing_branches:
            ref = "refs/stacky-bottom-branch/{}".format(bottom)
            info("Deleting ref {} (branch {} no longer exists)".format(ref, bottom))
            run(CmdArgs(["git", "update-ref", "-d", ref]))

    stack_parent_refs = get_all_stack_parent_refs()
    for br in stack_parent_refs:
        if br not in stack.stack or br not in existing_branches:
            ref = "refs/stack-parent/{}".format(br)
            old_value = run(CmdArgs(["git", "show-ref", ref]), check=False)
            if old_value:
                info("Deleting ref {} (branch {} no longer exists)".format(old_value, br))
            else:
                info("Deleting ref refs/stack-parent/{} (branch {} no longer exists)".format(br, br))
            run(CmdArgs(["git", "update-ref", "-d", ref]))
