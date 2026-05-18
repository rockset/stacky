"""Tier 4 — non-default `.stackyconfig` flag coverage.

The default `toy_repo` fixture only flips `use_merge`. A few other config
toggles change stacky's user-facing behavior significantly; each deserves
one dedicated test.
"""
from __future__ import annotations

from stacky.tests.e2e.helpers import current_branch, merge_config


def test_change_to_main_auto_switches_from_non_stack_branch(toy_repo_with_config):
    """With change_to_main=True, stacky auto-checks-out master instead of
    dying when invoked from a branch that isn't in any stack.

    Covers src/stacky/main.py:117 (the `change_to_main` branch of the
    non-stack-branch guard).
    """
    repo = toy_repo_with_config(ui={"change_to_main": True})
    # Create a branch with no stacky metadata.
    repo.git("checkout", "-b", "orphan")
    # `stacky info` would normally die with "not in a stack". With the flag
    # on, it should silently check out master first and then show info.
    result = repo.run_stacky("info", check=True)
    assert result.returncode == 0
    # After the command, HEAD is on master.
    assert current_branch(repo) == "master"


def test_change_to_adopted_switches_current_branch(toy_repo_with_config):
    """With change_to_adopted=True, `stacky adopt` leaves you ON the
    adopted branch. Default behavior leaves you where you started.

    Covers src/stacky/commands/update.py:128.
    """
    repo = toy_repo_with_config(ui={"change_to_adopted": True})
    # Create a sidebar via plain git off master.
    repo.git("checkout", "-b", "sidebar")
    repo.add_file("side", "side\n")
    repo.git("commit", "-m", "side commit")
    repo.git("checkout", "master")

    repo.run_stacky("adopt", "sidebar", check=True)

    # Current branch is now sidebar, not master.
    assert current_branch(repo) == "sidebar"
    # And the adopt still wrote the parent config correctly.
    assert merge_config(repo, "sidebar") == "refs/heads/master"
