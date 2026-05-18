"""Batched git reads for stacky startup.

`stacky`'s stack-loading path used to shell out five times per local branch
(one `git config` + four `git rev-parse`/`git config` calls inside
`StackBranch.__init__`). On a checkout with many branches that startup cost
dominated wall time. `GitSnapshot` collects all of the same data in three
parallel subprocess calls: `git for-each-ref` for the ref table,
`git config --null --get-regexp` for the per-branch merge/remote config
(plus `remote.pushDefault`), and `git symbolic-ref` for HEAD.

Callers that already have a snapshot should pass it down so the fine-grained
helpers in `stacky.git.refs` / `stacky.git.branch` / `stacky.git.remote` don't
run again. Those helpers still exist and remain the right tool for mutation
paths (`cmd_adopt`, `cmd_import`, `inner_do_sync`, ...) where state has just
changed and stale snapshot data would be wrong.
"""

import dataclasses
import subprocess
from typing import Dict, Optional, Set, Tuple

from stacky.utils.types import BranchName, Commit


@dataclasses.dataclass
class GitSnapshot:
    """Batched view of the git refs and branch config stacky needs at load time."""
    head_commit: Dict[BranchName, Commit]
    remote_commit: Dict[BranchName, Commit]
    stack_parent_commit: Dict[BranchName, Commit]
    bottoms: Set[BranchName]
    branch_merge: Dict[BranchName, BranchName]
    branch_remote: Dict[BranchName, str]
    remote_name: str
    push_default: Optional[str]
    current_branch: Optional[BranchName]


ParsedRefs = Tuple[
    Dict[BranchName, Commit],
    Dict[BranchName, Commit],
    Dict[BranchName, Commit],
    Set[BranchName],
]
ParsedConfig = Tuple[Dict[BranchName, BranchName], Dict[BranchName, str], Optional[str]]


def _parse_refs(out: Optional[str], remote_name: str) -> ParsedRefs:
    head_commit: Dict[BranchName, Commit] = {}
    remote_commit: Dict[BranchName, Commit] = {}
    stack_parent_commit: Dict[BranchName, Commit] = {}
    bottoms: Set[BranchName] = set()
    if not out:
        return head_commit, remote_commit, stack_parent_commit, bottoms

    remote_prefix = f"refs/remotes/{remote_name}/"
    for line in out.split("\n"):
        if not line:
            continue
        refname, _, sha = line.partition(" ")
        if not sha:
            continue
        if refname.startswith("refs/heads/"):
            head_commit[BranchName(refname[len("refs/heads/"):])] = Commit(sha)
        elif refname.startswith(remote_prefix):
            remote_commit[BranchName(refname[len(remote_prefix):])] = Commit(sha)
        elif refname.startswith("refs/stack-parent/"):
            stack_parent_commit[BranchName(refname[len("refs/stack-parent/"):])] = Commit(sha)
        elif refname.startswith("refs/stacky-bottom-branch/"):
            bottoms.add(BranchName(refname[len("refs/stacky-bottom-branch/"):]))
    return head_commit, remote_commit, stack_parent_commit, bottoms


def _parse_null_config(out: Optional[str]) -> ParsedConfig:
    """Parse `git config --null --get-regexp` output.

    With --null, each record is "key\\nvalue\\0". Using NUL as the record
    separator avoids ambiguity when config values contain spaces or newlines.
    """
    branch_merge: Dict[BranchName, BranchName] = {}
    branch_remote: Dict[BranchName, str] = {}
    push_default: Optional[str] = None
    if not out:
        return branch_merge, branch_remote, push_default

    for record in out.split("\0"):
        if not record:
            continue
        key, _, value = record.partition("\n")
        # git config normalizes section/name keys to lowercase on output.
        if key == "remote.pushdefault":
            push_default = value
            continue
        if not key.startswith("branch."):
            continue
        rest = key[len("branch."):]
        name, _, field = rest.rpartition(".")
        if not name:
            continue
        if field == "merge":
            if value.startswith("refs/heads/"):
                value = value[len("refs/heads/"):]
            branch_merge[BranchName(name)] = BranchName(value)
        elif field == "remote":
            branch_remote[BranchName(name)] = value
    return branch_merge, branch_remote, push_default


def load_snapshot(remote_name: str = "origin") -> GitSnapshot:
    """Collect every ref + branch-config stacky needs, in three parallel subprocesses."""
    p_refs = subprocess.Popen(
        [
            "git", "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads",
            f"refs/remotes/{remote_name}",
            "refs/stack-parent",
            "refs/stacky-bottom-branch",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    p_config = subprocess.Popen(
        [
            "git", "config", "--null", "--get-regexp",
            r"^(branch\..*\.(merge|remote)|remote\.pushDefault)$",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    p_head = subprocess.Popen(
        ["git", "symbolic-ref", "-q", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    refs_bytes, _ = p_refs.communicate()
    config_bytes, _ = p_config.communicate()
    head_bytes, _ = p_head.communicate()

    refs_out = refs_bytes.decode("UTF-8")
    # `git config --get-regexp` returns rc=1 when no keys match; that's "no
    # branch config / no pushDefault", not an error.
    config_out = config_bytes.decode("UTF-8") if p_config.returncode in (0, 1) else ""
    # `git symbolic-ref -q` returns rc=1 on detached HEAD; treat as "no branch".
    head_out = head_bytes.decode("UTF-8").strip() if p_head.returncode == 0 else ""

    head_commit, remote_commit, stack_parent_commit, bottoms = _parse_refs(refs_out, remote_name)
    branch_merge, branch_remote, push_default = _parse_null_config(config_out)

    current_branch: Optional[BranchName] = None
    if head_out.startswith("refs/heads/"):
        current_branch = BranchName(head_out[len("refs/heads/"):])

    return GitSnapshot(
        head_commit=head_commit,
        remote_commit=remote_commit,
        stack_parent_commit=stack_parent_commit,
        bottoms=bottoms,
        branch_merge=branch_merge,
        branch_remote=branch_remote,
        remote_name=remote_name,
        push_default=push_default,
        current_branch=current_branch,
    )
