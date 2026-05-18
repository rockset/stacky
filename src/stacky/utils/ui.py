"""User interface utilities for stacky."""

import os
import sys
from typing import TYPE_CHECKING

import asciitree  # type: ignore
from simple_term_menu import TerminalMenu  # type: ignore

from stacky.utils.config import get_config
from stacky.utils.logging import IS_TERMINAL, cout, die

if TYPE_CHECKING:
    from stacky.stack.models import StackBranch
    from stacky.utils.types import BranchesTreeForest


def prompt(message: str, default_value: str | None) -> str:
    """Prompt the user for input."""
    cout(message)
    if default_value is not None:
        cout("({})", default_value, fg="gray")
        cout(" ")
    while True:
        sys.stderr.flush()
        r = input().strip()

        if len(r) > 0:
            return r
        if default_value:
            return default_value


def confirm(msg: str = "Proceed?"):
    """Ask for confirmation. Skips if skip_confirm is set."""
    if get_config().skip_confirm:
        return
    if not os.isatty(0):
        die("Standard input is not a terminal, use --force option to force action")
    print()
    while True:
        cout("{} [yes/no] ", msg, fg="yellow")
        sys.stderr.flush()
        r = input().strip().lower()
        if r == "yes" or r == "y":
            break
        if r == "no":
            die("Not confirmed")
        cout("Please answer yes or no\n", fg="red")


# Print upside down, to match our "upstack" / "downstack" nomenclature
_ASCII_TREE_BOX = {
    "UP_AND_RIGHT": "\u250c",
    "HORIZONTAL": "\u2500",
    "VERTICAL": "\u2502",
    "VERTICAL_AND_RIGHT": "\u251c",
}
_ASCII_TREE_STYLE = asciitree.drawing.BoxStyle(gfx=_ASCII_TREE_BOX)
ASCII_TREE = asciitree.LeftAligned(draw=_ASCII_TREE_STYLE)


def menu_choose_branch(forest: "BranchesTreeForest") -> "StackBranch":
    """Display a menu for choosing a branch from the forest."""
    # Import here to avoid circular dependency
    from stacky.stack.tree import forest_depth_first, format_tree

    if not IS_TERMINAL:
        die("May only choose from menu when using a terminal")

    s = ""
    lines = []
    for tree in forest:
        s = ASCII_TREE(format_tree(tree))
        lines += [l.rstrip() for l in s.split("\n")]
    lines.reverse()

    # Find current branch marker
    from stacky.git.branch import get_current_branch_name
    current = get_current_branch_name()
    initial_index = 0
    for i, l in enumerate(lines):
        if "*" in l:  # lol
            initial_index = i
            break

    menu = TerminalMenu(lines, cursor_index=initial_index)
    idx = menu.show()
    if idx is None:
        die("Aborted")

    branches = list(forest_depth_first(forest))
    branches.reverse()
    return branches[idx]
