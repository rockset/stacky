"""Tree formatting and traversal for stacky stacks."""

from typing import Generator, List, TYPE_CHECKING

from stacky.git.branch import get_current_branch_name
from stacky.utils.config import get_config
from stacky.utils.logging import COLOR_STDOUT, fmt
from stacky.utils.types import BranchesTree, BranchesTreeForest, BranchName, TreeNode

if TYPE_CHECKING:
    from stacky.stack.models import StackBranch, StackBranchSet


def get_pr_status_emoji(pr_info) -> str:
    """Get the status emoji for a PR based on review state."""
    if not pr_info:
        return ""

    review_decision = pr_info.get('reviewDecision')
    review_requests = pr_info.get('reviewRequests', [])
    is_draft = pr_info.get('isDraft', False)

    if is_draft:
        # Draft PRs are waiting on author
        return " 🚧"
    elif review_decision == "APPROVED":
        return " ✅"
    elif review_requests and len(review_requests) > 0:
        # Has pending review requests - waiting on review
        return " 🔄"
    else:
        # No pending review requests, likely needs changes or author action
        return " ❌"


def make_tree_node(b: "StackBranch") -> TreeNode:
    """Create a tree node for a branch."""
    return (b.name, (b, make_subtree(b)))


def make_subtree(b: "StackBranch") -> BranchesTree:
    """Create a subtree for a branch's children."""
    return BranchesTree(dict(make_tree_node(c) for c in sorted(b.children, key=lambda x: x.name)))


def make_tree(b: "StackBranch") -> BranchesTree:
    """Create a tree rooted at a branch."""
    return BranchesTree(dict([make_tree_node(b)]))


def format_name(b: "StackBranch", *, colorize: bool) -> str:
    """Format a branch name with status indicators."""
    current_branch = get_current_branch_name()
    prefix = ""
    severity = 0
    # TODO: Align things so that we have the same prefix length?
    if not b.is_synced_with_parent():
        prefix += fmt("!", color=colorize, fg="yellow")
        severity = max(severity, 2)
    if not b.is_synced_with_remote():
        prefix += fmt("~", color=colorize, fg="yellow")
    if b.name == current_branch:
        prefix += fmt("*", color=colorize, fg="cyan")
    else:
        severity = max(severity, 1)
    if prefix:
        prefix += " "
    fg = ["cyan", "green", "yellow", "red"][severity]
    suffix = ""
    if b.open_pr_info:
        suffix += " "
        # Make the PR info a clickable link
        pr_url = b.open_pr_info["url"]
        pr_number = b.open_pr_info["number"]
        status_emoji = get_pr_status_emoji(b.open_pr_info)

        if get_config().compact_pr_display:
            # Compact: just number and emoji
            suffix += fmt("(\033]8;;{}\033\\#{}{}\033]8;;\033\\)", pr_url, pr_number, status_emoji, color=colorize, fg="blue")
        else:
            # Full: number, emoji, and title
            pr_title = b.open_pr_info["title"]
            suffix += fmt("(\033]8;;{}\033\\#{}{} {}\033]8;;\033\\)", pr_url, pr_number, status_emoji, pr_title, color=colorize, fg="blue")
    return prefix + fmt("{}", b.name, color=colorize, fg=fg) + suffix


def format_tree(tree: BranchesTree, *, colorize: bool = False):
    """Format a tree for display."""
    return {
        format_name(branch, colorize=colorize): format_tree(children, colorize=colorize)
        for branch, children in tree.values()
    }


def print_tree(tree: BranchesTree):
    """Print a tree (upside down to match upstack/downstack nomenclature)."""
    from stacky.utils.ui import ASCII_TREE
    s = ASCII_TREE(format_tree(tree, colorize=COLOR_STDOUT))
    lines = s.split("\n")
    print("\n".join(reversed(lines)))


def print_forest(trees: List[BranchesTree]):
    """Print multiple trees."""
    for i, t in enumerate(trees):
        if i != 0:
            print()
        print_tree(t)


def forest_depth_first(forest: BranchesTreeForest) -> Generator["StackBranch", None, None]:
    """Iterate over a forest in depth-first order."""
    for tree in forest:
        for b in depth_first(tree):
            yield b


def depth_first(tree: BranchesTree) -> Generator["StackBranch", None, None]:
    """Iterate over a tree in depth-first order."""
    for _, (branch, children) in tree.items():
        yield branch
        for b in depth_first(children):
            yield b


def get_all_stacks_as_forest(stack: "StackBranchSet") -> BranchesTreeForest:
    """Get all stacks as a forest."""
    return BranchesTreeForest([make_tree(b) for b in stack.bottoms])


def get_current_stack_as_forest(stack: "StackBranchSet") -> BranchesTreeForest:
    """Get the current stack as a forest."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    d: BranchesTree = make_tree(b)
    b = b.parent
    while b:
        d = BranchesTree({b.name: (b, d)})
        b = b.parent
    return [d]


def get_current_upstack_as_forest(stack: "StackBranchSet") -> BranchesTreeForest:
    """Get the current upstack (current branch and above) as a forest."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    return BranchesTreeForest([make_tree(b)])


def get_current_downstack_as_forest(stack: "StackBranchSet") -> BranchesTreeForest:
    """Get the current downstack (current branch and below) as a forest."""
    current_branch = get_current_branch_name()
    b = stack.stack[current_branch]
    d: BranchesTree = BranchesTree({})
    while b:
        d = BranchesTree({b.name: (b, d)})
        b = b.parent
    return BranchesTreeForest([d])


def get_bottom_level_branches_as_forest(stack: "StackBranchSet") -> BranchesTreeForest:
    """Get bottom level branches (stack bottoms and their direct children) as a forest."""
    return BranchesTreeForest(
        [
            BranchesTree(
                {
                    bottom.name: (
                        bottom,
                        BranchesTree({b.name: (b, BranchesTree({})) for b in bottom.children}),
                    )
                }
            )
            for bottom in stack.bottoms
        ]
    )


def load_pr_info_for_forest(forest: BranchesTreeForest):
    """Load PR info for all branches in a forest."""
    for b in forest_depth_first(forest):
        b.load_pr_info()


def get_complete_stack_forest_for_branch(branch: "StackBranch") -> BranchesTreeForest:
    """Get the complete stack forest containing the given branch."""
    from stacky.utils.types import STACK_BOTTOMS
    # Find the root of the stack
    root = branch
    while root.parent and root.parent.name not in STACK_BOTTOMS:
        root = root.parent

    # Create a forest with just this root's complete tree
    return BranchesTreeForest([make_tree(root)])
