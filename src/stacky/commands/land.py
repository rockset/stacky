"""Land command - land a PR."""

import sys

from stacky.git.branch import get_current_branch_name
from stacky.stack.models import StackBranchSet
from stacky.stack.tree import get_current_downstack_as_forest
from stacky.utils.logging import COLOR_STDOUT, cout, die, fmt
from stacky.utils.shell import run
from stacky.utils.types import CmdArgs, Commit
from stacky.utils.ui import confirm


def cmd_land(stack: StackBranchSet, args):
    """Land bottom-most PR on current stack."""
    current_branch = get_current_branch_name()
    forest = get_current_downstack_as_forest(stack)
    assert len(forest) == 1
    branches = []
    p = forest[0]
    while p:
        assert len(p) == 1
        _, (b, p) = next(iter(p.items()))
        branches.append(b)
    assert branches
    assert branches[0] in stack.bottoms
    if len(branches) == 1:
        die("May not land {}", branches[0].name)

    b = branches[1]
    if not b.is_synced_with_parent():
        die(
            "Branch {} is not synced with parent {}, sync before landing",
            b.name, b.parent.name,
        )
    if not b.is_synced_with_remote():
        die(
            "Branch {} is not synced with remote branch, push local changes before landing",
            b.name,
        )

    b.load_pr_info()
    pr = b.open_pr_info
    if not pr:
        die("Branch {} does not have an open PR", b.name)
        assert pr is not None

    if pr["mergeable"] != "MERGEABLE":
        die(
            "PR #{} for branch {} is not mergeable: {}",
            pr["number"], b.name, pr["mergeable"],
        )

    if len(branches) > 2:
        cout(
            "The `land` command only lands the bottom-most branch {}; "
            "the current stack has {} branches, ending with {}\n",
            b.name, len(branches) - 1, current_branch, fg="yellow",
        )

    msg = fmt("- Will land PR #{} (", pr["number"], color=COLOR_STDOUT)
    msg += fmt("{}", pr["url"], color=COLOR_STDOUT, fg="blue")
    msg += fmt(") for branch {}", b.name, color=COLOR_STDOUT)
    msg += fmt(" into branch {}\n", b.parent.name, color=COLOR_STDOUT)
    sys.stdout.write(msg)

    if not args.force:
        confirm()

    v = run(CmdArgs(["git", "rev-parse", b.name]))
    assert v is not None
    head_commit = Commit(v)
    cmd = CmdArgs(["gh", "pr", "merge", b.name, "--squash", "--match-head-commit", head_commit])
    if args.auto:
        cmd.append("--auto")
    run(cmd, out=True)
    cout("\n✓ Success! Run `stacky update` to update local state.\n", fg="green")
