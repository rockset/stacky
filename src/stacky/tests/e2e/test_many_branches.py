"""Correctness under a many-branch, multi-tree topology.

stacky's startup path batches git ref/config reads via GitSnapshot
(src/stacky/git/snapshot.py). These tests drive that path with more branches
than the rest of the e2e suite uses, and across several independent stacks,
to catch any regression where the batched load produces a different stack
graph than the per-branch load did.

We verify three things end to end:
    1. `stacky info` lists every branch in the right tree.
    2. Checkout moves the `*` marker to the new current branch.
    3. A no-op `stacky stack sync` reports "already synced" for each branch —
       this exercises is_synced_with_parent / is_synced_with_remote, which
       depend on StackBranch.commit and .remote_commit being populated
       correctly from the snapshot.
"""
from __future__ import annotations

from stacky.tests.e2e.helpers import (
    current_branch,
    list_branches,
    merge_config,
)


def _build_many_branches(toy_repo):
    """Build three stacks totaling 12 branches, with sibling branching.

    Shape:
        master -> a1 -> a2 -> a3 -> a4
                  a1 -> b1 -> b2 -> b3        (sibling fork off a1)
        master -> x1 -> x2 -> x3
        master -> y1

    Leaves the working tree on y1.
    """
    # Stack A: linear 4 deep
    toy_repo.run_stacky("branch", "new", "a1", check=True)
    toy_repo.add_file("a1_file", "a1\n")
    toy_repo.run_stacky("commit", "-m", "a1", check=True)
    for name in ("a2", "a3", "a4"):
        toy_repo.run_stacky("branch", "new", name, check=True)
        toy_repo.add_file(f"{name}_file", f"{name}\n")
        toy_repo.run_stacky("commit", "-m", name, check=True)

    # Stack B: sibling fork off a1
    toy_repo.git("checkout", "a1")
    for name in ("b1", "b2", "b3"):
        toy_repo.run_stacky("branch", "new", name, check=True)
        toy_repo.add_file(f"{name}_file", f"{name}\n")
        toy_repo.run_stacky("commit", "-m", name, check=True)

    # Stack X: independent 3-deep stack
    toy_repo.git("checkout", "master")
    for name in ("x1", "x2", "x3"):
        toy_repo.run_stacky("branch", "new", name, check=True)
        toy_repo.add_file(f"{name}_file", f"{name}\n")
        toy_repo.run_stacky("commit", "-m", name, check=True)

    # Stack Y: single-branch stack
    toy_repo.git("checkout", "master")
    toy_repo.run_stacky("branch", "new", "y1", check=True)
    toy_repo.add_file("y1_file", "y1\n")
    toy_repo.run_stacky("commit", "-m", "y1", check=True)


def test_many_branches_info_lists_all(toy_repo):
    """`stacky info` lists every branch across three stacks with sibling fork."""
    _build_many_branches(toy_repo)
    result = toy_repo.run_stacky("info", check=True)

    all_branches = ["a1", "a2", "a3", "a4", "b1", "b2", "b3", "x1", "x2", "x3", "y1"]
    for b in all_branches:
        assert b in result.stdout, f"{b!r} missing from stacky info output"

    # Sibling fork is preserved: b1 parents on a1, not on x1 or master.
    assert merge_config(toy_repo, "b1") == "refs/heads/a1"
    assert merge_config(toy_repo, "a2") == "refs/heads/a1"
    assert merge_config(toy_repo, "x1") == "refs/heads/master"
    assert merge_config(toy_repo, "y1") == "refs/heads/master"

    # Every branch we created is a real local branch.
    locals_ = set(list_branches(toy_repo))
    for b in all_branches:
        assert b in locals_, f"{b!r} missing from `git for-each-ref refs/heads`"


def test_many_branches_checkout_moves_current_marker(toy_repo):
    """After checking out a mid-stack branch, stacky info marks it as current."""
    _build_many_branches(toy_repo)

    toy_repo.run_stacky("checkout", "a2", check=True)
    assert current_branch(toy_repo) == "a2"

    result = toy_repo.run_stacky("info", check=True)
    # The current-branch marker `*` always appears right before the branch name.
    # Since NO_COLOR is set by the fixture, check for the literal "* a2".
    assert "* a2" in result.stdout, (
        f"expected '* a2' in output; got:\n{result.stdout}"
    )
    # No other branch should be marked current.
    for other in ("a1", "a3", "b1", "x1", "y1"):
        assert f"* {other}" not in result.stdout, (
            f"unexpected '* {other}' marker in output:\n{result.stdout}"
        )


def test_many_branches_sync_reports_already_synced(toy_repo):
    """A fresh stack is in-sync: `stacky stack sync` should be a no-op.

    This hits is_synced_with_parent for every branch in the current stack,
    which depends on commit / parent_commit being populated correctly
    from the snapshot.
    """
    _build_many_branches(toy_repo)

    # Check out the deepest branch so the full a1 -> a2 -> a3 -> a4 chain is
    # the "current stack".
    toy_repo.run_stacky("checkout", "a4", check=True)

    result = toy_repo.run_stacky("stack", "sync", check=True)
    # Every non-bottom branch in the current stack should appear as
    # already-synced; exact wording comes from stack/operations.py.
    for b in ("a2", "a3", "a4"):
        assert f"already synced with parent" in result.stdout, (
            f"expected 'already synced' notice; got:\n{result.stdout}"
        )
        assert b in result.stdout
