"""Fold command - fold branch into parent."""

import json
import os
from typing import List

from stacky.git.branch import checkout, get_current_branch_name, set_current_branch
from stacky.git.refs import get_commit, get_commits_between, set_parent, set_parent_commit
from stacky.stack.models import StackBranch, StackBranchSet
from stacky.utils.config import get_config
from stacky.utils.logging import cout, die, info
from stacky.utils.shell import run
from stacky.utils.types import BranchName, CmdArgs, STACK_BOTTOMS, STATE_FILE, TMP_STATE_FILE


def cmd_fold(stack: StackBranchSet, args):
    """Fold current branch into parent branch and delete current branch."""
    current_branch = get_current_branch_name()

    if current_branch not in stack.stack:
        die("Current branch {} is not in a stack", current_branch)

    b = stack.stack[current_branch]

    if not b.parent:
        die("Cannot fold stack bottom branch {}", current_branch)

    if b.parent.name in STACK_BOTTOMS:
        die("Cannot fold into stack bottom branch {}", b.parent.name)

    if not b.is_synced_with_parent():
        die(
            "Branch {} is not synced with parent {}, sync before folding",
            b.name, b.parent.name,
        )

    commits_to_apply = get_commits_between(b.parent_commit, b.commit)
    if not commits_to_apply:
        info("No commits to fold from {} into {}", b.name, b.parent.name)
    else:
        cout("Folding {} commits from {} into {}\n", len(commits_to_apply), b.name, b.parent.name, fg="green")

    children = list(b.children)
    if children:
        cout("Reparenting {} children to {}\n", len(children), b.parent.name, fg="yellow")
        for child in children:
            cout("  {} -> {}\n", child.name, b.parent.name, fg="gray")

    checkout(b.parent.name)
    set_current_branch(b.parent.name)

    if get_config().use_merge:
        inner_do_merge_fold(stack, b.name, b.parent.name, [child.name for child in children])
    else:
        if commits_to_apply:
            commits_to_apply = list(reversed(commits_to_apply))
            inner_do_fold(stack, b.name, b.parent.name, commits_to_apply, [child.name for child in children], args.allow_empty)
        else:
            finish_fold_operation(stack, b.name, b.parent.name, [child.name for child in children])


def inner_do_merge_fold(stack: StackBranchSet, fold_branch_name: BranchName, parent_branch_name: BranchName,
                        children_names: List[BranchName]):
    """Perform merge-based fold operation."""
    print()
    current_branch = get_current_branch_name()

    with open(TMP_STATE_FILE, "w") as f:
        json.dump({
            "branch": current_branch,
            "merge_fold": {
                "fold_branch": fold_branch_name,
                "parent_branch": parent_branch_name,
                "children": children_names,
            }
        }, f)
    os.replace(TMP_STATE_FILE, STATE_FILE)

    cout("Merging {} into {}\n", fold_branch_name, parent_branch_name, fg="green")
    result = run(CmdArgs(["git", "merge", fold_branch_name]), check=False)
    if result is None:
        die("Merge failed for branch {}. Please resolve conflicts and run `stacky continue`", fold_branch_name)

    finish_merge_fold_operation(stack, fold_branch_name, parent_branch_name, children_names)


def finish_merge_fold_operation(stack: StackBranchSet, fold_branch_name: BranchName,
                                parent_branch_name: BranchName, children_names: List[BranchName]):
    """Complete merge-based fold operation."""
    fold_branch = stack.stack.get(fold_branch_name)
    parent_branch = stack.stack[parent_branch_name]

    if not fold_branch:
        cout("✓ Merge fold operation completed\n", fg="green")
        return

    parent_branch.commit = get_commit(parent_branch_name)

    for child_name in children_names:
        if child_name in stack.stack:
            child = stack.stack[child_name]
            info("Reparenting {} from {} to {}", child.name, fold_branch.name, parent_branch.name)
            child.parent = parent_branch
            parent_branch.children.add(child)
            fold_branch.children.discard(child)
            set_parent(child.name, parent_branch.name)
            set_parent_commit(child.name, parent_branch.commit, child.parent_commit)
            child.parent_commit = parent_branch.commit

    parent_branch.children.discard(fold_branch)

    info("Deleting branch {}", fold_branch.name)
    run(CmdArgs(["git", "branch", "-D", fold_branch.name]))
    run(CmdArgs(["git", "update-ref", "-d", "refs/stack-parent/{}".format(fold_branch.name)]))
    stack.remove(fold_branch.name)

    cout("✓ Successfully merged and folded {} into {}\n", fold_branch.name, parent_branch.name, fg="green")


def inner_do_fold(stack: StackBranchSet, fold_branch_name: BranchName, parent_branch_name: BranchName,
                  commits_to_apply: List[str], children_names: List[BranchName], allow_empty: bool):
    """Cherry-pick based fold operation."""
    print()
    current_branch = get_current_branch_name()

    if not commits_to_apply:
        finish_fold_operation(stack, fold_branch_name, parent_branch_name, children_names)
        return

    while commits_to_apply:
        with open(TMP_STATE_FILE, "w") as f:
            json.dump({
                "branch": current_branch,
                "fold": {
                    "fold_branch": fold_branch_name,
                    "parent_branch": parent_branch_name,
                    "commits": commits_to_apply,
                    "children": children_names,
                    "allow_empty": allow_empty
                }
            }, f)
        os.replace(TMP_STATE_FILE, STATE_FILE)

        commit = commits_to_apply.pop()

        # Check if commit would be empty
        dry_run_result = run(CmdArgs(["git", "cherry-pick", "--no-commit", commit]), check=False)
        if dry_run_result is not None:
            has_changes = run(CmdArgs(["git", "diff", "--cached", "--quiet"]), check=False) is None
            run(CmdArgs(["git", "reset", "--hard", "HEAD"]))
            if not has_changes:
                cout("Skipping empty commit {}\n", commit[:8], fg="yellow")
                continue
        else:
            run(CmdArgs(["git", "reset", "--hard", "HEAD"]), check=False)

        cout("Cherry-picking commit {}\n", commit[:8], fg="green")
        cherry_pick_cmd = ["git", "cherry-pick"]
        if allow_empty:
            cherry_pick_cmd.append("--allow-empty")
        cherry_pick_cmd.append(commit)
        result = run(CmdArgs(cherry_pick_cmd), check=False)
        if result is None:
            die("Cherry-pick failed for commit {}. Please resolve conflicts and run `stacky continue`", commit)

    finish_fold_operation(stack, fold_branch_name, parent_branch_name, children_names)


def finish_fold_operation(stack: StackBranchSet, fold_branch_name: BranchName,
                          parent_branch_name: BranchName, children_names: List[BranchName]):
    """Complete fold operation after commits applied."""
    fold_branch = stack.stack.get(fold_branch_name)
    parent_branch = stack.stack[parent_branch_name]

    if not fold_branch:
        cout("✓ Fold operation completed\n", fg="green")
        return

    parent_branch.commit = get_commit(parent_branch_name)

    for child_name in children_names:
        if child_name in stack.stack:
            child = stack.stack[child_name]
            info("Reparenting {} from {} to {}", child.name, fold_branch.name, parent_branch.name)
            child.parent = parent_branch
            parent_branch.children.add(child)
            fold_branch.children.discard(child)
            set_parent(child.name, parent_branch.name)
            set_parent_commit(child.name, parent_branch.commit, child.parent_commit)
            child.parent_commit = parent_branch.commit

    parent_branch.children.discard(fold_branch)

    info("Deleting branch {}", fold_branch.name)
    run(CmdArgs(["git", "branch", "-D", fold_branch.name]))
    run(CmdArgs(["git", "update-ref", "-d", "refs/stack-parent/{}".format(fold_branch.name)]))
    stack.remove(fold_branch.name)

    cout("✓ Successfully folded {} into {}\n", fold_branch.name, parent_branch.name, fg="green")
