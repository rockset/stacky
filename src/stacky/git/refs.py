"""Git ref operations for stacky."""

from typing import List, Optional

from stacky.utils.logging import die
from stacky.utils.shell import run, run_multiline
from stacky.utils.types import BranchName, CmdArgs, Commit


def get_stack_parent_commit(branch: BranchName) -> Optional[Commit]:
    """Get the parent commit of a stack branch."""
    c = run(
        CmdArgs(["git", "rev-parse", "refs/stack-parent/{}".format(branch)]),
        check=False,
    )
    if c is not None:
        return Commit(c)
    return None


def get_commit(branch: BranchName) -> Commit:
    """Get the current commit of a branch."""
    c = run(CmdArgs(["git", "rev-parse", "refs/heads/{}".format(branch)]), check=False)
    assert c is not None
    return Commit(c)


def set_parent_commit(branch: BranchName, new_commit: Commit, prev_commit: Optional[str] = None):
    """Set the parent commit ref for a branch."""
    cmd = [
        "git",
        "update-ref",
        "refs/stack-parent/{}".format(branch),
        new_commit,
    ]
    if prev_commit is not None:
        cmd.append(prev_commit)
    run(CmdArgs(cmd))


def set_parent(branch: BranchName, target: Optional[BranchName], *, set_origin: bool = False):
    """Set the parent branch for a stack branch."""
    if set_origin:
        run(CmdArgs(["git", "config", "branch.{}.remote".format(branch), "."]))

    # If target is none this becomes a new stack bottom
    run(
        CmdArgs(
            [
                "git",
                "config",
                "branch.{}.merge".format(branch),
                "refs/heads/{}".format(target if target is not None else branch),
            ]
        )
    )

    if target is None:
        run(
            CmdArgs(
                [
                    "git",
                    "update-ref",
                    "-d",
                    "refs/stack-parent/{}".format(branch),
                ]
            )
        )


def get_branch_name_from_short_ref(ref: str) -> BranchName:
    """Extract branch name from a short ref like 'stack-parent/branch'."""
    parts = ref.split("/", 1)
    if len(parts) != 2:
        die("invalid ref: {}".format(ref))
    return BranchName(parts[1])


def get_all_stack_bottoms() -> List[BranchName]:
    """Get all custom stack bottom branches."""
    branches = run_multiline(
        CmdArgs(["git", "for-each-ref", "--format", "%(refname:short)", "refs/stacky-bottom-branch"])
    )
    if branches:
        return [get_branch_name_from_short_ref(b) for b in branches.split("\n") if b]
    return []


def get_all_stack_parent_refs() -> List[BranchName]:
    """Get all branches that have stack-parent refs."""
    branches = run_multiline(CmdArgs(["git", "for-each-ref", "--format", "%(refname:short)", "refs/stack-parent"]))
    if branches:
        return [get_branch_name_from_short_ref(b) for b in branches.split("\n") if b]
    return []


def get_commits_between(a: Commit, b: Commit) -> List[str]:
    """Get list of commits between two refs."""
    lines = run_multiline(CmdArgs(["git", "rev-list", "{}..{}".format(a, b)]))
    assert lines is not None
    # Have to strip the last element because it's empty, rev list includes a new line at the end
    return [x.strip() for x in lines.split("\n")][:-1]


def get_merge_base(b1: BranchName, b2: BranchName) -> Optional[str]:
    """Get the merge base of two branches."""
    return run(CmdArgs(["git", "merge-base", str(b1), str(b2)]))
