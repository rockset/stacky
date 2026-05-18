"""Tier 1 — error/guard path tests.

Every `die(...)` in stacky is a behavior contract. These tests verify that
stacky refuses invalid operations with the specific error message it
documents, rather than silently doing the wrong thing.
"""
from __future__ import annotations

from stacky.tests.e2e.helpers import (
    head,
    run_stacky_expect_fail,
)


def _err(result) -> str:
    """Combined stdout+stderr, lowercased — what we match die messages against."""
    return (result.stdout + result.stderr).lower()


# ---------- commit guards (commit.py:19, 21, 27, 30) ----------


def test_commit_on_master_dies(toy_repo):
    """Do-not-commit-on-master guard (src/stacky/commands/commit.py:19)."""
    toy_repo.add_file("anything", "x\n")
    result = run_stacky_expect_fail(toy_repo, "commit", "-m", "nope")
    assert "do not commit directly on" in _err(result)
    assert "master" in _err(result)


def test_commit_out_of_sync_with_parent_dies(toy_repo):
    """Refuse to commit when branch's stack-parent ref is stale.

    src/stacky/commands/commit.py:21
    """
    toy_repo.build_stack(["A", "B"])
    # Advance A outside stacky — this makes B's parent_commit ref stale.
    toy_repo.git("checkout", "A")
    toy_repo.add_file("a_drift", "drift\n")
    toy_repo.git("commit", "-m", "drift on A")
    toy_repo.git("checkout", "B")

    toy_repo.add_file("b_new", "b\n")
    result = run_stacky_expect_fail(toy_repo, "commit", "-m", "B change")
    assert "not synced with parent" in _err(result)


def test_amend_blocked_when_use_force_push_false(toy_repo_with_config):
    """Amend refuses when use_force_push is False.

    src/stacky/commands/commit.py:27 — rebase-only (use_merge=False) so we
    isolate the use_force_push branch of the guard.
    """
    repo = toy_repo_with_config(git={"use_force_push": False})
    repo.run_stacky("branch", "new", "A", check=True)
    repo.add_file("a", "a\n")
    repo.run_stacky("commit", "-m", "A", check=True)

    result = run_stacky_expect_fail(repo, "amend")
    assert "amending is not allowed" in _err(result)


def test_amend_on_branch_with_no_commits_dies(toy_repo):
    """Amend needs at least one commit above the parent (commit.py:30)."""
    if toy_repo.use_merge:
        # Earlier guard (use_merge) fires first — a different test covers that.
        import pytest
        pytest.skip("covered by amend's use_merge guard")
    toy_repo.run_stacky("branch", "new", "A", check=True)
    # No commits on A yet — its head equals master's head.
    result = run_stacky_expect_fail(toy_repo, "amend")
    assert "no commits, may not amend" in _err(result)


# ---------- fold guards (fold.py:25, 28, 31) ----------


def test_fold_stack_bottom_dies(toy_repo):
    """Refuse to fold master/main (fold.py:25)."""
    result = run_stacky_expect_fail(toy_repo, "fold")
    assert "cannot fold stack bottom" in _err(result)


def test_fold_into_stack_bottom_dies(toy_repo):
    """Refuse to fold a branch whose parent IS the stack bottom (fold.py:28).

    Folding into master would pollute master's history; stacky guards against it.
    """
    toy_repo.build_stack(["A"])  # master -> A, currently on A
    result = run_stacky_expect_fail(toy_repo, "fold")
    assert "cannot fold into stack bottom" in _err(result)


def test_fold_out_of_sync_branch_dies(toy_repo):
    """Refuse to fold an out-of-sync branch (fold.py:31)."""
    toy_repo.build_stack(["A", "B"])
    toy_repo.git("checkout", "A")
    toy_repo.add_file("a_drift", "drift\n")
    toy_repo.git("commit", "-m", "drift on A")
    toy_repo.git("checkout", "B")

    result = run_stacky_expect_fail(toy_repo, "fold")
    assert "not synced with parent" in _err(result)


# ---------- upstack guards (upstack.py:43, 48, 59) ----------


def test_upstack_onto_cycle_dies(toy_repo):
    """Refuse a target that is upstack of the current branch (upstack.py:48)."""
    toy_repo.build_stack(["A", "B", "C"])
    toy_repo.git("checkout", "A")
    # B is upstack of A — would create a cycle.
    result = run_stacky_expect_fail(toy_repo, "upstack", "onto", "B")
    assert "is upstack of" in _err(result)


def test_upstack_onto_stack_bottom_dies(toy_repo):
    """Refuse to upstack-onto on master — stack bottoms can't be moved.

    src/stacky/commands/upstack.py:43
    """
    # Needs a target branch to exist; build a sibling.
    toy_repo.build_stack(["A"])
    toy_repo.git("checkout", "master")
    result = run_stacky_expect_fail(toy_repo, "upstack", "onto", "A")
    assert "may not upstack a stack bottom" in _err(result)


def test_upstack_as_bottom_on_bottom_dies(toy_repo):
    """`upstack as bottom` on master dies (upstack.py:59)."""
    result = run_stacky_expect_fail(toy_repo, "upstack", "as", "bottom")
    assert "already a stack bottom" in _err(result)


# ---------- adopt guards (update.py:105, 115, 122) ----------


def test_adopt_self_dies(toy_repo):
    """Cannot adopt the branch you're currently on (update.py:105)."""
    result = run_stacky_expect_fail(toy_repo, "adopt", "master")
    assert "cannot adopt itself" in _err(result)


def test_adopt_from_non_bottom_dies(toy_repo):
    """Adopt requires current branch to be a stack bottom (update.py:115)."""
    toy_repo.build_stack(["A"])  # now on A (non-bottom)
    # Make a sidebar via plain git so stacky has something to try adopting.
    sidebar_head = head(toy_repo, "master")
    toy_repo.git("branch", "sidebar", sidebar_head)

    result = run_stacky_expect_fail(toy_repo, "adopt", "sidebar")
    assert "must be a valid stack bottom" in _err(result)


def test_adopt_frozen_bottom_dies(toy_repo):
    """Cannot adopt master/main (update.py:122).

    Create a `main` branch alongside master and try to adopt it while on master.
    """
    master_head = head(toy_repo, "master")
    toy_repo.git("branch", "main", master_head)
    # We're on master; 'main' is a frozen bottom so adopt should refuse.
    result = run_stacky_expect_fail(toy_repo, "adopt", "main")
    assert "cannot adopt frozen stack bottoms" in _err(result)


# ---------- non-stack branch (main.py:122) ----------


def test_non_stack_branch_without_change_to_main_dies(toy_repo):
    """Stacky refuses to operate on a branch that's not in any stack.

    src/stacky/main.py:122 — unless `change_to_main = True`, which is
    covered by test_config.py.
    """
    toy_repo.git("checkout", "-b", "orphan")
    result = run_stacky_expect_fail(toy_repo, "info")
    assert "not in a stack" in _err(result)
