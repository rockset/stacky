"""Recreate command - rebuild a stack from `stacky info` output."""

import re
import sys
from typing import Iterable, List, Optional, Tuple

from stacky.git.branch import get_all_branches
from stacky.git.refs import get_merge_base, set_parent, set_parent_commit
from stacky.stack.models import StackBranchSet
from stacky.utils.logging import cout, die, info
from stacky.utils.types import BranchName, Commit, STACK_BOTTOMS
from stacky.utils.ui import confirm


_TREE_CHARS = "│┌├└─"  # │ ┌ ├ └ ─
_LINE_RE = re.compile(
    r"^(?P<indent>[\s│┌├└─]*)"
    r"(?:[!~*]+\s*)*"
    r"(?P<name>[A-Za-z0-9_][\w./-]*)"
    r"(?:\s+\(.*\))?\s*$"
)


def _indent_of(line: str) -> int:
    """Visual indent of the branch on a line, measured by the leftmost tree
    character. Lines without any tree character (e.g. `* main`) are roots and
    get -1 so they sort below everything else.
    """
    for i, ch in enumerate(line):
        if ch in "┌├└":  # ┌ ├ └
            return i
    return -1


def parse_stack_info(text: str) -> List[Tuple[BranchName, Optional[BranchName]]]:
    """Parse `stacky info` output into a list of (child, parent) edges.

    The bottom-most branch (e.g. `main`) is returned with parent=None.
    Lines are processed top-to-bottom; each branch's parent is the next line
    *below* it with a strictly smaller indent (since stacky prints the tree
    upside-down, so visually-lower = closer to the root).
    """
    parsed: List[Tuple[int, BranchName]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        name = BranchName(m.group("name"))
        parsed.append((_indent_of(raw), name))

    edges: List[Tuple[BranchName, Optional[BranchName]]] = []
    for i, (indent, name) in enumerate(parsed):
        parent: Optional[BranchName] = None
        for j in range(i + 1, len(parsed)):
            j_indent, j_name = parsed[j]
            if j_indent < indent:
                parent = j_name
                break
        edges.append((name, parent))
    return edges


def _validate_branches_exist(edges: Iterable[Tuple[BranchName, Optional[BranchName]]]):
    existing = set(get_all_branches())
    missing: List[BranchName] = []
    for child, parent in edges:
        if child not in existing:
            missing.append(child)
        if parent is not None and parent not in existing:
            missing.append(parent)
    if missing:
        die("Branches not found in repo: {}", ", ".join(sorted(set(missing))))


def cmd_recreate(stack: StackBranchSet, args):
    """Rebuild a stack from `stacky info` output piped on stdin or via --file."""
    if args.file:
        with open(args.file) as f:
            text = f.read()
    else:
        if sys.stdin.isatty():
            die("No input provided. Pipe `stacky info` output or pass --file.")
        text = sys.stdin.read()

    edges = parse_stack_info(text)
    if not edges:
        die("No branches parsed from input")

    _validate_branches_exist(edges)

    to_apply = [(c, p) for c, p in edges if p is not None]
    roots = [c for c, p in edges if p is None]

    cout("Will recreate stack with {} edges:\n", len(to_apply), fg="green")
    for child, parent in to_apply:
        cout("  {} -> {}\n", child, parent)
    if roots:
        cout("Stack bottoms (unchanged): {}\n", ", ".join(roots), fg="cyan")

    for root in roots:
        if root not in STACK_BOTTOMS:
            info(
                "Note: {} is treated as a root but is not a known stack bottom",
                root,
            )

    if not args.force:
        confirm()

    for child, parent in to_apply:
        base = get_merge_base(child, parent)  # type: ignore[arg-type]
        if base is None:
            die("Could not find merge-base between {} and {}", child, parent)
        set_parent(child, parent, set_origin=True)
        set_parent_commit(child, Commit(base))
        info("Set {} -> {} (parent commit {})", child, parent, base[:8])

    cout("Done. Run `stacky info` to verify.\n", fg="green")
