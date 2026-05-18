"""Tier 2 — branching topology + multi-commit tests.

Everything in test_workflows.py uses linear stacks. These tests exercise
the forest/tree shapes stacky's data model is built for:
    - one parent with multiple children (siblings)
    - multi-commit branches (stress the cherry-pick loop in fold)
    - custom stack bottoms behaving like real bottoms
"""
from __future__ import annotations

from stacky.tests.e2e.helpers import (
    current_branch,
    head,
    list_branches,
    merge_config,
    stack_parent_ref,
)


def _branching(toy_repo):
    """Build master -> A, A -> B, A -> C (B and C are siblings).

    Leaves the working tree on C.
    """
    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("A_file", "A\n")
    toy_repo.run_stacky("commit", "-m", "A", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    toy_repo.add_file("B_file", "B\n")
    toy_repo.run_stacky("commit", "-m", "B", check=True)

    toy_repo.git("checkout", "A")
    toy_repo.run_stacky("branch", "new", "C", check=True)
    toy_repo.add_file("C_file", "C\n")
    toy_repo.run_stacky("commit", "-m", "C", check=True)


def test_branching_stack_info_shows_both_children(toy_repo):
    """`stacky info` lists sibling branches under their common parent."""
    _branching(toy_repo)
    result = toy_repo.run_stacky("info", check=True)
    assert "A" in result.stdout
    assert "B" in result.stdout
    assert "C" in result.stdout
    # Both siblings carry the correct merge config back to A.
    assert merge_config(toy_repo, "B") == "refs/heads/A"
    assert merge_config(toy_repo, "C") == "refs/heads/A"


def test_sibling_unaffected_by_commit(toy_repo):
    """A commit on B does not touch C's stack-parent ref."""
    _branching(toy_repo)
    c_parent_before = stack_parent_ref(toy_repo, "C")
    c_head_before = head(toy_repo, "C")

    toy_repo.git("checkout", "B")
    toy_repo.add_file("B_more", "B2\n")
    toy_repo.run_stacky("commit", "-m", "B2", check=True)

    # C's ref state is untouched — it's not in B's upstack.
    assert stack_parent_ref(toy_repo, "C") == c_parent_before
    assert head(toy_repo, "C") == c_head_before


def test_commit_fanout_syncs_all_children(toy_repo):
    """A commit on A auto-syncs *both* children (B and C).

    Exercises the multi-child loop inside do_sync / get_current_upstack_as_forest.
    """
    _branching(toy_repo)
    toy_repo.git("checkout", "A")
    toy_repo.add_file("A_more", "A2\n")
    toy_repo.run_stacky("commit", "-m", "A2", check=True)

    new_a_head = head(toy_repo, "A")
    # Both siblings should have been rebased/merged onto A's new head.
    assert stack_parent_ref(toy_repo, "B") == new_a_head, "B not synced"
    assert stack_parent_ref(toy_repo, "C") == new_a_head, "C not synced"


def test_fold_reparents_multiple_children(toy_repo):
    """Fold a mid branch with multiple children — both children get reparented.

    Shape:  master -> A -> B -> C
                           B -> D
    After fold B:  master -> A -> C
                            A -> D
    Exercises the child reparenting loop in finish_fold_operation
    (src/stacky/commands/fold.py:181-189).
    """
    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("A_file", "A\n")
    toy_repo.run_stacky("commit", "-m", "A", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    toy_repo.add_file("B_file", "B\n")
    toy_repo.run_stacky("commit", "-m", "B", check=True)

    toy_repo.run_stacky("branch", "new", "C", check=True)
    toy_repo.add_file("C_file", "C\n")
    toy_repo.run_stacky("commit", "-m", "C", check=True)

    # Make a sibling D off B.
    toy_repo.git("checkout", "B")
    toy_repo.run_stacky("branch", "new", "D", check=True)
    toy_repo.add_file("D_file", "D\n")
    toy_repo.run_stacky("commit", "-m", "D", check=True)

    # Fold B into A.
    toy_repo.git("checkout", "B")
    toy_repo.run_stacky("fold", check=True)

    assert "B" not in list_branches(toy_repo)
    # Both former-children of B now point at A.
    assert merge_config(toy_repo, "C") == "refs/heads/A"
    assert merge_config(toy_repo, "D") == "refs/heads/A"
    # Their recorded parent-commit is A's (new) head.
    new_a_head = head(toy_repo, "A")
    assert stack_parent_ref(toy_repo, "C") == new_a_head
    assert stack_parent_ref(toy_repo, "D") == new_a_head


def test_multi_commit_fold(toy_repo):
    """Fold a branch that has THREE commits.

    Stresses the cherry-pick loop in inner_do_fold (fold.py:120-166) so any
    stop-after-first or off-by-one bug surfaces immediately.
    """
    # Two-level stack so fold's "cannot fold into stack bottom" guard doesn't fire.
    toy_repo.run_stacky("branch", "new", "A", check=True)
    toy_repo.add_file("a0", "a0\n")
    toy_repo.run_stacky("commit", "-m", "A0", check=True)

    toy_repo.run_stacky("branch", "new", "B", check=True)
    for i in range(3):
        toy_repo.add_file(f"b{i}", f"b{i}\n")
        toy_repo.run_stacky("commit", "-m", f"B{i}", check=True)

    toy_repo.run_stacky("fold", check=True)

    # All three files landed in A.
    a_tree = toy_repo.git("ls-tree", "--name-only", "A").split("\n")
    for i in range(3):
        assert f"b{i}" in a_tree, f"b{i} missing after multi-commit fold"
    assert "a0" in a_tree  # original A commit preserved


def test_custom_bottom_usable_as_stack_root(toy_repo):
    """After `upstack as bottom`, can build new branches on top of the new bottom.

    Verifies the promoted branch behaves like a real stack root for
    subsequent branch creation + commits + info.
    """
    toy_repo.build_stack(["A", "B"])
    toy_repo.git("checkout", "B")
    toy_repo.run_stacky("upstack", "as", "bottom", check=True)

    # Now build a new branch on top of the promoted bottom B.
    toy_repo.run_stacky("branch", "new", "Y", check=True)
    toy_repo.add_file("y_file", "y\n")
    toy_repo.run_stacky("commit", "-m", "Y", check=True)

    assert current_branch(toy_repo) == "Y"
    assert merge_config(toy_repo, "Y") == "refs/heads/B"
    # `info` includes the new stack rooted at B.
    result = toy_repo.run_stacky("info", check=True)
    assert "Y" in result.stdout
    assert "B" in result.stdout
