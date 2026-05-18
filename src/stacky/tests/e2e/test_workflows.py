"""End-to-end tests for stacky workflows.

Each test uses a fresh toy_repo fixture (real git, no remote, fake `gh` on
PATH) and drives stacky via a real subprocess. Assertions read stacky's
on-disk state directly (git refs, branch config) so failures are easy to
trace back to the production code being verified.
"""
from __future__ import annotations

import pytest

from stacky.tests.e2e.helpers import (
    current_branch,
    head,
    list_branches,
    merge_config,
    stack_parent_ref,
)


def test_branch_new_records_parent(toy_repo):
    """`stacky branch new` creates a branch and records its parent commit ref."""
    master_head = head(toy_repo, "master")

    result = toy_repo.run_stacky("branch", "new", "feature1", check=True)
    assert result.returncode == 0, result.stderr

    assert "feature1" in list_branches(toy_repo)
    assert current_branch(toy_repo) == "feature1"
    # branch.<name>.merge points at parent — mirror of get_stack_parent_branch.
    assert merge_config(toy_repo, "feature1") == "refs/heads/master"
    # refs/stack-parent/<name> captures the parent commit at creation time.
    assert stack_parent_ref(toy_repo, "feature1") == master_head


def test_commit_advances_branch_head(toy_repo):
    """`stacky commit` advances the feature branch but leaves master alone."""
    toy_repo.run_stacky("branch", "new", "feature1", check=True)
    master_head = head(toy_repo, "master")
    feature_head_before = head(toy_repo, "feature1")

    toy_repo.add_file("new_file", "content\n")
    toy_repo.run_stacky("commit", "-m", "add new_file", check=True)

    assert head(toy_repo, "master") == master_head
    assert head(toy_repo, "feature1") != feature_head_before


def test_two_level_stack_info_shows_both_branches(toy_repo):
    """Build master -> f1 -> f2, then `stacky info` mentions both branches."""
    toy_repo.run_stacky("branch", "new", "f1", check=True)
    toy_repo.add_file("a", "a\n")
    toy_repo.run_stacky("commit", "-m", "f1 commit", check=True)

    toy_repo.run_stacky("branch", "new", "f2", check=True)
    toy_repo.add_file("b", "b\n")
    toy_repo.run_stacky("commit", "-m", "f2 commit", check=True)

    result = toy_repo.run_stacky("info", check=True)
    assert "f1" in result.stdout
    assert "f2" in result.stdout
    assert "master" in result.stdout

    # Parent wiring for the upper branch.
    assert merge_config(toy_repo, "f2") == "refs/heads/f1"


def test_sync_rebases_upstack_on_parent_change(toy_repo):
    """Committing on A auto-syncs (rebases) B on top of A's new head.

    Exercises do_sync in src/stacky/stack/operations.py:131.
    """
    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("a", "a\n")
    toy_repo.run_stacky("commit", "-m", "A1", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    toy_repo.add_file("b", "b\n")
    toy_repo.run_stacky("commit", "-m", "B1", check=True)

    # Go back to A, add another commit. This should trigger B's rebase.
    toy_repo.git("checkout", "A")
    toy_repo.add_file("a2", "a2\n")
    toy_repo.run_stacky("commit", "-m", "A2", check=True)

    new_a_head = head(toy_repo, "A")
    # After the auto-sync, B's recorded parent commit should equal A's new head.
    assert stack_parent_ref(toy_repo, "B") == new_a_head
    # And B should still contain its own change on top.
    log = toy_repo.git("log", "--format=%s", f"{new_a_head}..B")
    assert "B1" in log


def test_fold_collapses_branch_into_parent(toy_repo):
    """`stacky fold` on B (master -> A -> B) removes B and moves its commits onto A."""
    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("a", "a\n")
    toy_repo.run_stacky("commit", "-m", "A commit", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    toy_repo.add_file("b", "b\n")
    toy_repo.run_stacky("commit", "-m", "B commit", check=True)

    result = toy_repo.run_stacky("fold", check=True)
    assert result.returncode == 0, result.stderr

    # B is gone; A has B's file.
    assert "B" not in list_branches(toy_repo)
    assert "A" in list_branches(toy_repo)
    # A's tree now contains the "b" file.
    a_files = toy_repo.git("ls-tree", "--name-only", "A").split("\n")
    assert "a" in a_files
    assert "b" in a_files
    # stack-parent ref for B is cleaned up.
    assert stack_parent_ref(toy_repo, "B") is None


def test_adopt_untracked_branch(toy_repo):
    """`stacky adopt` wires a plain git branch into the current stack."""
    # Make a sidebar branch the "dumb" way and go back to master.
    toy_repo.git("checkout", "-b", "sidebar")
    toy_repo.write_file("side", "side\n")
    toy_repo.commit_all("side commit")
    toy_repo.git("checkout", "master")

    master_head = head(toy_repo, "master")
    result = toy_repo.run_stacky("adopt", "sidebar", check=True)
    assert result.returncode == 0, result.stderr

    # adopt records parent=master (merge config) and parent_commit=merge-base.
    assert merge_config(toy_repo, "sidebar") == "refs/heads/master"
    # sidebar was branched from master's initial commit, so merge-base == master_head.
    assert stack_parent_ref(toy_repo, "sidebar") == master_head


def test_info_succeeds_without_gh(toy_repo_no_gh):
    """`stacky info` does NOT need `gh` — only commands that actually touch
    GitHub (push, land, inbox, prs, update, import, info --pr) do.

    Verifies the gh-auth gating in main._needs_gh (src/stacky/main.py).
    """
    result = toy_repo_no_gh.run_stacky("info")
    assert result.returncode == 0, (
        f"stacky info should succeed without gh; got stderr:\n{result.stderr}"
    )


def test_inbox_fails_without_gh(toy_repo_no_gh):
    """Negative: a command that needs `gh` dies when `gh` is missing.

    Verifies check_gh_auth is still wired up for gh-using commands
    (src/stacky/git/branch.py check_gh_auth).
    """
    result = toy_repo_no_gh.run_stacky("inbox")
    assert result.returncode != 0
    assert "gh" in (result.stdout + result.stderr).lower()


def _build_stack(toy_repo, names):
    """Build a linear stack master -> names[0] -> names[1] -> ... with a
    distinct file committed on each branch. Leaves the working tree on the
    topmost branch.
    """
    for name in names:
        toy_repo.run_stacky("branch", "new", name, check=True)
        toy_repo.add_file(f"{name}_file", f"{name}\n")
        toy_repo.run_stacky("commit", "-m", f"{name} commit", check=True)


def test_upstack_onto_reparents_branch(toy_repo):
    """`stacky upstack onto master` moves a mid-stack branch (and its upstack)
    to sit on master directly. Exercises cmd_upstack_onto in
    src/stacky/commands/upstack.py:39.
    """
    _build_stack(toy_repo, ["A", "B", "C"])
    # master -> A -> B -> C, now on C.

    toy_repo.git("checkout", "B")
    result = toy_repo.run_stacky("upstack", "onto", "master", check=True)
    assert result.returncode == 0, result.stderr

    # B's parent is now master; C's parent is still B (it moved with B).
    assert merge_config(toy_repo, "B") == "refs/heads/master"
    assert merge_config(toy_repo, "C") == "refs/heads/B"
    # B's recorded parent-commit matches master's HEAD.
    assert stack_parent_ref(toy_repo, "B") == head(toy_repo, "master")
    # After the re-sync C's parent-commit matches B's new head.
    assert stack_parent_ref(toy_repo, "C") == head(toy_repo, "B")
    # A is untouched and still rooted on master.
    assert merge_config(toy_repo, "A") == "refs/heads/master"


def test_upstack_as_bottom_promotes_branch(toy_repo):
    """`stacky upstack as bottom` promotes the current branch to a new stack
    bottom. Exercises cmd_upstack_as_base in src/stacky/commands/upstack.py:55.
    """
    _build_stack(toy_repo, ["A", "B"])
    toy_repo.git("checkout", "B")

    result = toy_repo.run_stacky("upstack", "as", "bottom", check=True)
    assert result.returncode == 0, result.stderr

    # Sentinel ref marks B as a custom stack bottom.
    bottom_ref = toy_repo.git("rev-parse", "refs/stacky-bottom-branch/B")
    assert bottom_ref == head(toy_repo, "B")
    # set_parent(B, None) points merge at itself.
    assert merge_config(toy_repo, "B") == "refs/heads/B"
    # And the old stack-parent ref is gone.
    assert stack_parent_ref(toy_repo, "B") is None
    # A is unchanged.
    assert merge_config(toy_repo, "A") == "refs/heads/master"


def test_fold_then_upstack_onto(toy_repo):
    """Fold B into A, then re-parent C (formerly above B) with upstack onto.

    Verifies that the reparenting fold does inside finish_fold_operation
    cooperates correctly with a follow-up upstack onto.
    """
    _build_stack(toy_repo, ["A", "B", "C"])
    # master -> A -> B -> C, currently on C.

    # Fold B into A. C gets reparented onto A, B is deleted.
    toy_repo.git("checkout", "B")
    toy_repo.run_stacky("fold", check=True)

    assert "B" not in list_branches(toy_repo)
    assert merge_config(toy_repo, "C") == "refs/heads/A"
    # A now carries its own + B's files.
    a_tree = toy_repo.git("ls-tree", "--name-only", "A").split("\n")
    assert "A_file" in a_tree
    assert "B_file" in a_tree

    # Now lift C off A and put it directly on master.
    toy_repo.git("checkout", "C")
    toy_repo.run_stacky("upstack", "onto", "master", check=True)

    assert merge_config(toy_repo, "C") == "refs/heads/master"
    assert stack_parent_ref(toy_repo, "C") == head(toy_repo, "master")
    # A still exists with the folded contents.
    assert "A" in list_branches(toy_repo)


def test_amend_updates_last_commit(toy_repo):
    """`stacky amend` folds staged changes into the previous commit.

    Rebase-only: stacky refuses to amend under use_merge
    (src/stacky/commands/commit.py:27).
    """
    if toy_repo.use_merge:
        pytest.skip("stacky amend is not supported with use_merge=True")

    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("a", "a\n")
    toy_repo.run_stacky("commit", "-m", "A commit", check=True)
    first_head = head(toy_repo, "A")

    # Stage a new change and amend it into the previous commit.
    toy_repo.add_file("a_extra", "extra\n")
    result = toy_repo.run_stacky("amend", check=True)
    assert result.returncode == 0, result.stderr

    new_head = head(toy_repo, "A")
    assert new_head != first_head, "amend should rewrite the commit"
    # Both files are present in the single commit above master.
    tree = toy_repo.git("ls-tree", "--name-only", "A").split("\n")
    assert "a" in tree
    assert "a_extra" in tree
    # Exactly one commit above master — confirms amend didn't just add a new one.
    log = [
        l for l in toy_repo.git("log", "--format=%H", "master..A").split("\n") if l
    ]
    assert len(log) == 1, f"expected 1 commit above master, got {log}"
