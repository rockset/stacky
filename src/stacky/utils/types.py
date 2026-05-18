"""Type aliases and constants for stacky."""

import logging
import os
from typing import Dict, FrozenSet, List, NewType, Tuple, Union

# Type aliases
BranchName = NewType("BranchName", str)
PathName = NewType("PathName", str)
Commit = NewType("Commit", str)
CmdArgs = NewType("CmdArgs", List[str])

# Forward reference types (actual types defined in stack/models.py)
# These are used for type hints only
StackSubTree = Tuple["StackBranch", "BranchesTree"]  # type: ignore
TreeNode = Tuple[BranchName, StackSubTree]
BranchesTree = NewType("BranchesTree", Dict[BranchName, StackSubTree])
BranchesTreeForest = NewType("BranchesTreeForest", List[BranchesTree])

JSON = Union[Dict[str, "JSON"], List["JSON"], str, int, float, bool, None]

# Constants
MAX_SSH_MUX_LIFETIME = 120  # 2 minutes ought to be enough for anybody ;-)
STATE_FILE = os.path.expanduser("~/.stacky.state")
TMP_STATE_FILE = STATE_FILE + ".tmp"

# Stack bottoms - mutable set that can be extended
STACK_BOTTOMS: set[BranchName] = set([BranchName("master"), BranchName("main")])
FROZEN_STACK_BOTTOMS: FrozenSet[BranchName] = frozenset([BranchName("master"), BranchName("main")])

# Log levels
LOGLEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}
