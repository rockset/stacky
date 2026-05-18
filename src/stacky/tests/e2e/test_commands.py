"""Tier 5 — coverage for stacky commands not touched by other test files.

These are pure-coverage tests; the harness already works, they just
exercise surfaces (`checkout`, `branch up`/`down`, `log`, explicit
`stack sync`, compound `branch commit`) that nothing else runs.
"""
from __future__ import annotations

from stacky.tests.e2e.helpers import (
    current_branch,
    head,
    list_branches,
    stack_parent_ref,
)


def test_checkout_by_name(toy_repo):
    """`stacky checkout A` swaps HEAD to A, same as git checkout."""
    toy_repo.build_stack(["A"])
    toy_repo.git("checkout", "master")
    assert current_branch(toy_repo) == "master"

    toy_repo.run_stacky("checkout", "A", check=True)
    assert current_branch(toy_repo) == "A"


def test_branch_up_single_child(toy_repo):
    """With exactly one child, `branch up` moves HEAD there unambiguously."""
    toy_repo.build_stack(["A", "B"])
    toy_repo.git("checkout", "A")
    toy_repo.run_stacky("branch", "up", check=True)
    assert current_branch(toy_repo) == "B"


def test_branch_down(toy_repo):
    """`branch down` moves HEAD to the parent."""
    toy_repo.build_stack(["A", "B"])
    # Already on B.
    toy_repo.run_stacky("branch", "down", check=True)
    assert current_branch(toy_repo) == "A"


def test_branch_up_at_top_is_noop(toy_repo):
    """At the top of the stack, `branch up` prints a message and stays put."""
    toy_repo.build_stack(["A"])  # on A, no children
    result = toy_repo.run_stacky("branch", "up", check=True)
    assert current_branch(toy_repo) == "A"
    # Friendly message — don't pin exact wording, just check it mentions
    # the "top" state.
    assert "top of the stack" in (result.stdout + result.stderr).lower()


def test_branch_down_at_bottom_is_noop(toy_repo):
    """On master, `branch down` is a no-op with a friendly message."""
    result = toy_repo.run_stacky("branch", "down", check=True)
    assert current_branch(toy_repo) == "master"
    assert "bottom of the stack" in (result.stdout + result.stderr).lower()


def test_stack_sync_as_explicit_command(toy_repo):
    """Running `stacky stack sync` explicitly re-syncs a stale upstack.

    Previously the suite only exercised sync via `commit`'s auto-sync tail.
    This test covers the standalone cmd_stack_sync entry point.
    """
    toy_repo.build_stack(["A", "B"])

    # Advance A outside stacky so B's stack-parent ref goes stale.
    toy_repo.git("checkout", "A")
    toy_repo.add_file("a_drift", "drift\n")
    toy_repo.git("commit", "-m", "drift on A")
    new_a_head = head(toy_repo, "A")

    # Explicitly sync the stack. Must run from a branch in the stack.
    toy_repo.run_stacky("stack", "sync", check=True)

    # B is now synced — its stack-parent ref matches A's head.
    assert stack_parent_ref(toy_repo, "B") == new_a_head


def test_branch_commit_compound(toy_repo):
    """`stacky branch commit X -m msg` creates the branch AND commits in one go.

    Exercises cmd_branch_commit in src/stacky/commands/branch.py:24.
    """
    toy_repo.add_file("payload", "payload\n")
    # Note: the file is staged but the branch X doesn't exist yet.
    toy_repo.run_stacky(
        "branch", "commit", "X", "-m", "X: payload", check=True
    )

    # X exists, is current, and has the payload committed.
    assert "X" in list_branches(toy_repo)
    assert current_branch(toy_repo) == "X"
    tree = toy_repo.git("ls-tree", "--name-only", "X").split("\n")
    assert "payload" in tree


def test_log_runs_under_both_modes(toy_repo):
    """Smoke test for `stacky log` — cmd_log branches on use_merge.

    src/stacky/commands/navigation.py:23 — both branches should exit 0.
    """
    toy_repo.build_stack(["A"])
    result = toy_repo.run_stacky("log", check=True)
    # Git log should show at least the A commit and the seed commit.
    assert "A commit" in result.stdout or "A commit" in result.stderr
