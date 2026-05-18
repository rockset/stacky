"""Tier 3 — sync / fold conflict recovery.

When a rebase or cherry-pick conflicts during `stacky sync` or `stacky fold`,
stacky writes `~/.stacky.state` (a JSON file describing where it was), dies,
and expects the user to resolve manually and run `stacky continue`. These
tests exercise that state-file + continue machinery end-to-end.
"""
from __future__ import annotations

import json

from stacky.tests.e2e.helpers import (
    head,
    list_branches,
    run_stacky_expect_fail,
    stack_parent_ref,
    state_file_path,
)


def _build_sync_conflict(toy_repo):
    """Build master -> A -> B where a subsequent commit on A will conflict
    with B's own change to the same file. Leaves the tree on A with a
    staged conflicting commit ready to land.

    Returns the new head of A after the drift commit.
    """
    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("shared.txt", "A-initial\n")
    toy_repo.run_stacky("commit", "-m", "A: create shared", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    # B replaces the content — this patch will NOT apply cleanly once A moves.
    toy_repo.write_file("shared.txt", "B-version\n")
    toy_repo.git("add", "shared.txt")
    toy_repo.git("commit", "-m", "B: rewrite shared")

    # Drift A via plain git so B's stack-parent ref goes stale.
    toy_repo.git("checkout", "A")
    toy_repo.write_file("shared.txt", "A-drifted\n")
    toy_repo.git("add", "shared.txt")
    toy_repo.git("commit", "-m", "A: drift")
    return head(toy_repo, "A")


def test_sync_conflict_writes_state_file_and_dies(toy_repo):
    """A sync that hits a conflict leaves ~/.stacky.state describing it."""
    _build_sync_conflict(toy_repo)

    # Trigger the sync of B on top of A. Should fail with a conflict.
    result = run_stacky_expect_fail(toy_repo, "sync")
    combined = (result.stdout + result.stderr).lower()
    # stacky's die message tells the user what to do next.
    assert "stacky continue" in combined

    # State file written with the 'sync' key and the right branch.
    state_path = state_file_path(toy_repo)
    assert state_path.exists(), "expected ~/.stacky.state after conflict"
    state = json.loads(state_path.read_text())
    assert "sync" in state
    assert "B" in state["sync"]


def test_stacky_continue_completes_sync_after_manual_resolution(toy_repo):
    """After a user resolves the conflict by hand, `stacky continue` finishes
    the sync and clears the state file.
    """
    _build_sync_conflict(toy_repo)
    run_stacky_expect_fail(toy_repo, "sync")

    # Resolve by keeping B's version. Rebase vs merge take slightly different
    # continuation paths — handle both.
    toy_repo.write_file("shared.txt", "B-version\n")
    toy_repo.git("add", "shared.txt")
    if toy_repo.use_merge:
        # mid-merge: record the merge commit
        toy_repo.git("commit", "--no-edit")
    else:
        # mid-rebase: continue (GIT_EDITOR=true keeps it non-interactive)
        toy_repo.git("rebase", "--continue")

    result = toy_repo.run_stacky("continue", check=True)
    assert result.returncode == 0

    # State file cleared and B is now synced with A.
    assert not state_file_path(toy_repo).exists(), "state file should be removed"
    assert stack_parent_ref(toy_repo, "B") == head(toy_repo, "A")


def test_fold_conflict_and_continue(toy_repo):
    """A fold conflict writes its state key and `stacky continue` resumes.

    Rebase path  — cherry-pick conflict → state key `"fold"`, resolve with
                  `git cherry-pick --continue`.
    Merge path   — 3-way merge conflict → state key `"merge_fold"`, resolve
                  by completing the merge commit with `git commit --no-edit`.

    Setup needs a mid-stack layout (`master → M → A → B`) so A is not a
    stack bottom — fold refuses to fold into a bottom. We then drift A via
    plain git and spoof B's stack-parent ref so fold's is_synced_with_parent
    guard passes. The divergent content on `shared.txt` forces a conflict
    in both modes (cherry-pick for rebase, 3-way merge for merge).
    """
    # master -> M -> A -> B (so A is not a stack bottom)
    toy_repo.run_stacky("branch", "new", "M", check=True)
    toy_repo.add_file("m_file", "m\n")
    toy_repo.run_stacky("commit", "-m", "M", check=True)

    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("shared.txt", "A-initial\n")
    toy_repo.run_stacky("commit", "-m", "A", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    toy_repo.write_file("shared.txt", "B-version\n")
    toy_repo.git("add", "shared.txt")
    toy_repo.git("commit", "-m", "B rewrites shared")

    # Drift A and spoof B's stack-parent so fold's sync-guard passes.
    toy_repo.git("checkout", "A")
    toy_repo.write_file("shared.txt", "A-drifted\n")
    toy_repo.git("add", "shared.txt")
    toy_repo.git("commit", "-m", "A drift")
    new_a = head(toy_repo, "A")
    toy_repo.git("update-ref", "refs/stack-parent/B", new_a)

    # Fold B into A. In rebase mode this cherry-picks B's commit onto the
    # drifted A and conflicts; in merge mode it does a 3-way merge that
    # conflicts on `shared.txt`.
    toy_repo.git("checkout", "B")
    result = run_stacky_expect_fail(toy_repo, "fold")
    assert "stacky continue" in (result.stdout + result.stderr).lower()

    state_key = "merge_fold" if toy_repo.use_merge else "fold"
    state = json.loads(state_file_path(toy_repo).read_text())
    assert state_key in state, f"expected state key {state_key!r}, got {state}"
    assert state[state_key]["fold_branch"] == "B"
    assert state[state_key]["parent_branch"] == "A"

    # Resolve: keep B's version.
    toy_repo.write_file("shared.txt", "B-version\n")
    toy_repo.git("add", "shared.txt")
    if toy_repo.use_merge:
        toy_repo.git("commit", "--no-edit")
    else:
        toy_repo.git("cherry-pick", "--continue")

    result = toy_repo.run_stacky("continue", check=True)
    assert result.returncode == 0
    assert not state_file_path(toy_repo).exists()
    assert "B" not in list_branches(toy_repo)