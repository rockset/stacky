"""Branch operations for stacky."""

from typing import List, Optional

from stacky.utils.logging import info
from stacky.utils.shell import remove_prefix, run, run_always_return, run_multiline
from stacky.utils.types import BranchName, CmdArgs, PathName, STACK_BOTTOMS

# Global current branch - set by init_git()
CURRENT_BRANCH: BranchName = BranchName("")


def get_current_branch_name() -> BranchName:
    """Get the current branch name (from global state)."""
    return CURRENT_BRANCH


def set_current_branch(branch: BranchName):
    """Set the current branch (global state)."""
    global CURRENT_BRANCH
    CURRENT_BRANCH = branch


def get_current_branch() -> Optional[BranchName]:
    """Get the current branch from git."""
    s = run(CmdArgs(["git", "symbolic-ref", "-q", "HEAD"]))
    if s is not None:
        return BranchName(remove_prefix(s, "refs/heads/"))
    return None


def get_all_branches() -> List[BranchName]:
    """Get all local branches."""
    branches = run_multiline(CmdArgs(["git", "for-each-ref", "--format", "%(refname:short)", "refs/heads"]))
    assert branches is not None
    return [BranchName(b) for b in branches.split("\n") if b]


def branch_name_completer(prefix, parsed_args, **kwargs):
    """Argcomplete completer function for branch names."""
    try:
        branches = get_all_branches()
        return [branch for branch in branches if branch.startswith(prefix)]
    except Exception:
        return []


def get_real_stack_bottom() -> Optional[BranchName]:
    """Return the actual stack bottom for this current repo."""
    branches = get_all_branches()
    candidates = set()
    for b in branches:
        if b in STACK_BOTTOMS:
            candidates.add(b)

    if len(candidates) == 1:
        return candidates.pop()
    return None


def get_stack_parent_branch(branch: BranchName) -> Optional[BranchName]:
    """Get the parent branch of a stack branch."""
    if branch in STACK_BOTTOMS:
        return None
    p = run(CmdArgs(["git", "config", "branch.{}.merge".format(branch)]), check=False)
    if p is not None:
        p = remove_prefix(p, "refs/heads/")
        if BranchName(p) == branch:
            return None
        return BranchName(p)
    return None


def get_top_level_dir() -> PathName:
    """Get the top-level directory of the git repository."""
    p = run_always_return(CmdArgs(["git", "rev-parse", "--show-toplevel"]))
    return PathName(p)


def checkout(branch: BranchName):
    """Checkout a branch."""
    info("Checking out branch {}", branch)
    run(["git", "checkout", branch], out=True)


def create_branch(branch: BranchName):
    """Create a new branch tracking current branch."""
    run(["git", "checkout", "-b", branch, "--track"], out=True)


def init_git(snapshot=None):
    """Initialize git state for stacky from a GitSnapshot.

    Takes no subprocesses of its own — the snapshot already ran them in
    parallel. The `snapshot=None` fallback loads one lazily for callers
    (tests, scripts) that don't want to thread one through.

    Intentionally does NOT run `gh auth status` — that call makes a GitHub
    network round-trip and dominated startup time for commands that never
    touch `gh`. See `check_gh_auth()`; callers only run it when they need
    `gh`.
    """
    from stacky.utils.logging import die
    if snapshot is None:
        from stacky.git.snapshot import load_snapshot
        snapshot = load_snapshot()

    if snapshot.push_default is not None:
        die("`git config remote.pushDefault` may not be set")
    if snapshot.current_branch is not None:
        global CURRENT_BRANCH
        CURRENT_BRANCH = snapshot.current_branch
    return snapshot


def check_gh_auth():
    """Verify `gh` is installed and authenticated.

    Only commands that invoke `gh` (push with PRs, land, inbox, prs, update,
    import, info --pr) need to call this.
    """
    from stacky.utils.logging import die

    auth_status = run(["gh", "auth", "status"], check=False)
    if auth_status is None:
        die("`gh` authentication failed")
