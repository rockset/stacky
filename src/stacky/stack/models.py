"""Stack data models for stacky."""

import dataclasses
from typing import Dict, List, Optional, Tuple, TypedDict

from stacky.git.refs import get_commit
from stacky.git.remote import get_remote_info
from stacky.utils.logging import die
from stacky.utils.types import BranchName, Commit

RemoteInfo = Tuple[str, BranchName, Optional[Commit]]


class PRInfo(TypedDict):
    """Type definition for PR information from GitHub."""
    id: str
    number: int
    state: str
    mergeable: str
    url: str
    title: str
    baseRefName: str
    headRefName: str
    commits: List[Dict[str, str]]


@dataclasses.dataclass
class PRInfos:
    """Container for all PRs and the open PR for a branch."""
    all: Dict[str, PRInfo]
    open: Optional[PRInfo]


@dataclasses.dataclass
class BranchNCommit:
    """Branch name with its parent commit."""
    branch: BranchName
    parent_commit: Optional[str]


class StackBranch:
    """Represents a branch in a stack."""

    def __init__(
        self,
        name: BranchName,
        parent: "StackBranch",
        parent_commit: Commit,
        *,
        commit: Optional[Commit] = None,
        remote_info: Optional[RemoteInfo] = None,
    ):
        self.name = name
        self.parent = parent
        self.parent_commit = parent_commit
        self.children: set["StackBranch"] = set()
        self.commit = commit if commit is not None else get_commit(name)
        if remote_info is None:
            remote_info = get_remote_info(name)
        self.remote, self.remote_branch, self.remote_commit = remote_info
        self.pr_info: Dict[str, PRInfo] = {}
        self.open_pr_info: Optional[PRInfo] = None
        self._pr_info_loaded = False

    def is_synced_with_parent(self):
        """Check if branch is synced with its parent."""
        return self.parent is None or self.parent_commit == self.parent.commit

    def is_synced_with_remote(self):
        """Check if branch is synced with remote."""
        return self.commit == self.remote_commit

    def __repr__(self):
        return f"StackBranch: {self.name} {len(self.children)} {self.commit}"

    def load_pr_info(self):
        """Load PR info from GitHub (lazy loading)."""
        if not self._pr_info_loaded:
            self._pr_info_loaded = True
            from stacky.pr.github import get_pr_info
            pr_infos = get_pr_info(self.name)
            self.pr_info, self.open_pr_info = (
                pr_infos.all,
                pr_infos.open,
            )


class StackBranchSet:
    """Collection of stack branches."""

    def __init__(self: "StackBranchSet"):
        self.stack: Dict[BranchName, StackBranch] = {}
        self.tops: set[StackBranch] = set()
        self.bottoms: set[StackBranch] = set()

    def add(
        self,
        name: BranchName,
        parent: Optional[StackBranch],
        parent_commit: Optional[Commit],
        *,
        commit: Optional[Commit] = None,
        remote_info: Optional[RemoteInfo] = None,
    ) -> StackBranch:
        """Add a branch to the stack, or return the existing entry if present."""
        if name in self.stack:
            s = self.stack[name]
            assert s.name == name
            for field, new_value in (("parent", parent), ("parent_commit", parent_commit)):
                if getattr(s, field) != new_value:
                    die(
                        "Mismatched stack: {}: {}={}, expected {}",
                        name, field, getattr(s, field), new_value,
                    )
            return s
        s = StackBranch(
            name, parent, parent_commit,
            commit=commit, remote_info=remote_info,
        )
        self.stack[name] = s
        if s.parent is None:
            self.bottoms.add(s)
        self.tops.add(s)
        return s

    def addStackBranch(self, s: StackBranch):
        """Add an existing StackBranch object to the set."""
        if s.name not in self.stack:
            self.stack[s.name] = s
            if s.parent is None:
                self.bottoms.add(s)
            if len(s.children) == 0:
                self.tops.add(s)
        return s

    def remove(self, name: BranchName) -> Optional[StackBranch]:
        """Remove a branch from the stack."""
        if name in self.stack:
            s = self.stack[name]
            assert s.name == name
            del self.stack[name]
            if s in self.tops:
                self.tops.remove(s)
            if s in self.bottoms:
                self.bottoms.remove(s)
            return s
        return None

    def __repr__(self) -> str:
        return f"StackBranchSet: {self.stack}"

    def add_child(self, s: StackBranch, child: StackBranch):
        """Add a child branch to a parent."""
        s.children.add(child)
        self.tops.discard(s)
