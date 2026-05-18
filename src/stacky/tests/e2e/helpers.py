"""Helpers for stacky end-to-end tests.

The ToyRepo handle wraps a throwaway git repo and runs real stacky commands
against it as subprocesses. State inspection goes through plain git commands,
which mirror stacky's own internal reads (see src/stacky/git/refs.py and
src/stacky/git/branch.py).
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


@dataclasses.dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


@dataclasses.dataclass
class ToyRepo:
    path: Path
    gh_dir: Optional[Path]  # None = strip any real `gh` from PATH for negative tests.
    use_merge: bool = False  # Reflects the .stackyconfig written by the fixture.

    def _env(self) -> dict:
        env = dict(os.environ)
        # Isolate HOME so ~/.stacky.state and ~/.stackyconfig don't leak real state.
        env["HOME"] = str(self.path.parent)
        if self.gh_dir is not None:
            env["PATH"] = f"{self.gh_dir}{os.pathsep}{env.get('PATH', '')}"
        else:
            # Drop any directory containing a `gh` executable so init_git()'s
            # `gh auth status` check reliably fails even if the host has gh installed.
            env["PATH"] = _path_without_gh(env.get("PATH", ""))
        # Turn off any git pager / prompts for determinism.
        env["GIT_PAGER"] = "cat"
        env["GIT_TERMINAL_PROMPT"] = "0"
        # Avoid editor pops during conflict recovery (`rebase --continue`, etc).
        env["GIT_EDITOR"] = "true"
        env["EDITOR"] = "true"
        # Stacky uses this for color decisions; force off so stdout is plain text.
        env["NO_COLOR"] = "1"
        return env

    def run_stacky(self, *args: str, check: bool = False) -> RunResult:
        """Invoke `python -m stacky <args>` in the toy repo."""
        sp = subprocess.run(
            [sys.executable, "-m", "stacky", *args],
            cwd=self.path,
            env=self._env(),
            capture_output=True,
            text=True,
        )
        result = RunResult(sp.returncode, sp.stdout, sp.stderr)
        if check and sp.returncode != 0:
            raise AssertionError(
                f"stacky {' '.join(args)} failed ({sp.returncode}).\n"
                f"stdout:\n{sp.stdout}\nstderr:\n{sp.stderr}"
            )
        return result

    def git(self, *args: str, check: bool = True) -> str:
        """Run a git command in the toy repo, returning stripped stdout."""
        sp = subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if check and sp.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed ({sp.returncode}).\n"
                f"stdout:\n{sp.stdout}\nstderr:\n{sp.stderr}"
            )
        return sp.stdout.strip()

    def write_file(self, name: str, contents: str = "") -> None:
        (self.path / name).write_text(contents)

    def add_file(self, name: str, contents: str = "") -> None:
        """Write a file and `git add` it — needed before `stacky commit`,
        since stacky's `-a` flag (just `git commit -a`) doesn't pick up
        untracked files.
        """
        self.write_file(name, contents)
        self.git("add", name)

    def commit_all(self, message: str) -> None:
        """Plain `git add -A && git commit -m ...` — bypasses stacky."""
        self.git("add", "-A")
        self.git("commit", "-m", message)

    def build_stack(self, names) -> None:
        """Build a linear stack master -> names[0] -> names[1] -> ... with a
        distinct file committed on each branch via stacky. Leaves the
        working tree on the topmost branch.
        """
        for name in names:
            self.run_stacky("branch", "new", name, check=True)
            self.add_file(f"{name}_file", f"{name}\n")
            self.run_stacky("commit", "-m", f"{name} commit", check=True)


def _path_without_gh(path: str) -> str:
    """Return PATH with any directory that contains a `gh` executable removed."""
    kept = []
    for entry in path.split(os.pathsep):
        if not entry:
            continue
        gh = os.path.join(entry, "gh")
        if os.path.isfile(gh) and os.access(gh, os.X_OK):
            continue
        kept.append(entry)
    return os.pathsep.join(kept)


def stack_parent_ref(repo: ToyRepo, branch: str) -> Optional[str]:
    """Read refs/stack-parent/<branch>, returning None if missing.

    Mirrors stacky.git.refs.get_stack_parent_commit (src/stacky/git/refs.py:10).
    """
    sp = subprocess.run(
        ["git", "rev-parse", f"refs/stack-parent/{branch}"],
        cwd=repo.path,
        env=repo._env(),
        capture_output=True,
        text=True,
    )
    if sp.returncode != 0:
        return None
    return sp.stdout.strip()


def merge_config(repo: ToyRepo, branch: str) -> Optional[str]:
    """Read branch.<branch>.merge, returning None if unset.

    Mirrors stacky.git.branch.get_stack_parent_branch (src/stacky/git/branch.py:61).
    """
    sp = subprocess.run(
        ["git", "config", f"branch.{branch}.merge"],
        cwd=repo.path,
        env=repo._env(),
        capture_output=True,
        text=True,
    )
    if sp.returncode != 0:
        return None
    return sp.stdout.strip()


def head(repo: ToyRepo, branch: str) -> str:
    """Resolve refs/heads/<branch> to its commit sha."""
    return repo.git("rev-parse", f"refs/heads/{branch}")


def list_branches(repo: ToyRepo) -> List[str]:
    """List local branches (short names)."""
    out = repo.git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [line for line in out.split("\n") if line]


def current_branch(repo: ToyRepo) -> str:
    return repo.git("symbolic-ref", "--short", "HEAD")


def run_stacky_expect_fail(repo: ToyRepo, *args: str) -> RunResult:
    """Run stacky and assert it exits non-zero. Returns the result so the
    caller can match against stdout/stderr for specific error strings.
    """
    result = repo.run_stacky(*args)
    if result.returncode == 0:
        raise AssertionError(
            f"stacky {' '.join(args)} unexpectedly succeeded.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def state_file_path(repo: ToyRepo) -> Path:
    """Location of stacky's ~/.stacky.state under our HOME override.

    Matches STATE_FILE in src/stacky/utils/types.py:24.
    """
    return repo.path.parent / ".stacky.state"


def make_conflict(repo: ToyRepo, file: str, branch_a: str, branch_b: str) -> None:
    """Write conflicting content to `file` on `branch_a` and `branch_b`,
    committing on each via plain git. Leaves the working tree on branch_b.

    The two branches share a common ancestor (stack parent) but touch the
    same line of the same file with different contents, so any attempt to
    rebase or cherry-pick b onto a (or vice versa) conflicts.
    """
    repo.git("checkout", branch_a)
    repo.write_file(file, "version-A\n")
    repo.git("add", file)
    repo.git("commit", "-m", f"{branch_a}: {file}")

    repo.git("checkout", branch_b)
    repo.write_file(file, "version-B\n")
    repo.git("add", file)
    repo.git("commit", "-m", f"{branch_b}: {file}")
