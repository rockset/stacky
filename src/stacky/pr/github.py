"""GitHub PR operations for stacky."""

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional, TYPE_CHECKING

from stacky.stack.models import PRInfo, PRInfos
from stacky.stack.tree import get_pr_status_emoji
from stacky.utils.config import get_config
from stacky.utils.logging import COLOR_STDOUT, cout, fmt
from stacky.utils.shell import run, run_always_return, run_multiline
from stacky.utils.types import BranchesTreeForest, BranchName, CmdArgs, STACK_BOTTOMS

if TYPE_CHECKING:
    from stacky.stack.models import StackBranch


def get_pr_info(branch: BranchName, *, full: bool = False) -> PRInfos:
    """Get PR information for a branch."""
    from stacky.utils.logging import die

    fields = [
        "id", "number", "state", "mergeable", "url", "title",
        "baseRefName", "headRefName", "reviewDecision", "reviewRequests", "isDraft",
    ]
    if full:
        fields += ["commits"]
    data = json.loads(
        run_always_return(
            CmdArgs([
                "gh", "pr", "list", "--json", ",".join(fields),
                "--state", "all", "--head", branch,
            ])
        )
    )
    raw_infos: List[PRInfo] = data

    infos: Dict[str, PRInfo] = {info["id"]: info for info in raw_infos}
    open_prs: List[PRInfo] = [info for info in infos.values() if info["state"] == "OPEN"]
    if len(open_prs) > 1:
        die(
            "Branch {} has more than one open PR: {}",
            branch, ", ".join([str(pr) for pr in open_prs]),
        )
    return PRInfos(infos, open_prs[0] if open_prs else None)


def find_reviewers(b: "StackBranch") -> Optional[List[str]]:
    """Find reviewers from commit message."""
    out = run_multiline(
        CmdArgs(["git", "log", "--pretty=format:%b", "-1", f"{b.name}"]),
    )
    assert out is not None
    for l in out.split("\n"):
        reviewer_match = re.match(r"^reviewers?\s*:\s*(.*)", l, re.I)
        if reviewer_match:
            reviewers = reviewer_match.group(1).split(",")
            logging.debug(f"Found the following reviewers: {', '.join(reviewers)}")
            return reviewers
    return None


def find_issue_marker(name: str) -> Optional[str]:
    """Find issue marker (e.g. SRE-123) in branch name."""
    match = re.search(r"(?:^|[_-])([A-Z]{3,}[_-]?\d{2,})($|[_-].*)", name)
    if match:
        res = match.group(1)
        if "_" in res:
            return res.replace("_", "-")
        if "-" not in res:
            newmatch = re.match(r"(...)(\d+)", res)
            assert newmatch is not None
            return f"{newmatch.group(1)}-{newmatch.group(2)}"
        return res
    return None


def create_gh_pr(b: "StackBranch", prefix: str):
    """Create a GitHub PR for a branch."""
    from stacky.utils.ui import prompt

    cout("Creating PR for {}\n", b.name, fg="green")
    parent_prefix = ""
    if b.parent.name not in STACK_BOTTOMS:
        prefix = ""
    cmd = [
        "gh", "pr", "create",
        "--head", f"{prefix}{b.name}",
        "--base", f"{parent_prefix}{b.parent.name}",
    ]
    reviewers = find_reviewers(b)
    issue_id = find_issue_marker(b.name)
    if issue_id:
        out = run_multiline(
            CmdArgs(["git", "log", "--pretty=oneline", f"{b.parent.name}..{b.name}"]),
        )
        title = f"[{issue_id}] "
        if out is not None and len(out.split("\n")) == 2:
            out = run(
                CmdArgs(["git", "log", "--pretty=format:%s", "-1", f"{b.name}"]),
                out=False,
            )
            if out is None:
                out = ""
            if b.name not in out:
                title += out
            else:
                title = out

        title = prompt(
            (fmt("? ", color=COLOR_STDOUT, fg="green") +
             fmt("Title ", color=COLOR_STDOUT, style="bold", fg="white")),
            title,
        )
        cmd.extend(["--title", title.strip()])
    if reviewers:
        logging.debug(f"Adding {len(reviewers)} reviewer(s) to the review")
        for r in reviewers:
            r = r.strip()
            r = r.replace("#", "rockset/")
            if len(r) > 0:
                cmd.extend(["--reviewer", r])

    run(CmdArgs(cmd), out=True)


def generate_stack_string(forest: BranchesTreeForest, current_branch: "StackBranch") -> str:
    """Generate a string representation of the PR stack."""
    from stacky.stack.tree import BranchesTree

    stack_lines = []

    def add_branch_to_stack(b: "StackBranch", depth: int):
        if b.name in STACK_BOTTOMS:
            return
        indent = "  " * depth
        pr_info = ""
        if b.open_pr_info:
            pr_number = b.open_pr_info['number']
            status_emoji = get_pr_status_emoji(b.open_pr_info)
            pr_info = f" (#{pr_number}{status_emoji})"
        current_indicator = " ← (CURRENT PR)" if b.name == current_branch.name else ""
        stack_lines.append(f"{indent}- {b.name}{pr_info}{current_indicator}")

    def traverse_tree(tree: BranchesTree, depth: int):
        for _, (branch, children) in tree.items():
            add_branch_to_stack(branch, depth)
            traverse_tree(children, depth + 1)

    for tree in forest:
        traverse_tree(tree, 0)

    if not stack_lines:
        return ""

    return "\n".join([
        "<!-- Stacky Stack Info -->",
        "**Stack:**",
        *stack_lines,
        "<!-- End Stacky Stack Info -->"
    ])


def extract_stack_comment(body: str) -> str:
    """Extract existing stack comment from PR body."""
    if not body:
        return ""
    pattern = r'<!-- Stacky Stack Info -->.*?<!-- End Stacky Stack Info -->'
    match = re.search(pattern, body, re.DOTALL)
    if match:
        return match.group(0).strip()
    return ""


def add_or_update_stack_comment(branch: "StackBranch", complete_forest: BranchesTreeForest):
    """Add or update stack comment in PR body."""
    if not branch.open_pr_info:
        return

    pr_number = branch.open_pr_info["number"]
    pr_data = json.loads(
        run_always_return(CmdArgs(["gh", "pr", "view", str(pr_number), "--json", "body"]))
    )

    current_body = pr_data.get("body", "")
    stack_string = generate_stack_string(complete_forest, branch)

    if not stack_string:
        return

    existing_stack = extract_stack_comment(current_body)

    if not existing_stack:
        if current_body:
            new_body = f"{current_body}\n\n{stack_string}"
        else:
            new_body = stack_string
        cout("Adding stack comment to PR #{}\n", pr_number, fg="green")
        run(CmdArgs(["gh", "pr", "edit", str(pr_number), "--body", new_body]), out=True)
    else:
        if existing_stack != stack_string:
            updated_body = current_body.replace(existing_stack, stack_string)
            cout("Updating stack comment in PR #{}\n", pr_number, fg="yellow")
            run(CmdArgs(["gh", "pr", "edit", str(pr_number), "--body", updated_body]), out=True)
        else:
            cout("✓ Stack comment in PR #{} is already correct\n", pr_number, fg="green")


def edit_pr_description(pr):
    """Edit a PR's description using the user's default editor."""
    cout("Editing PR #{} - {}\n", pr["number"], pr["title"], fg="green")
    cout("Current description:\n", fg="yellow")
    current_body = pr.get("body", "")
    if current_body:
        cout("{}\n\n", current_body, fg="gray")
    else:
        cout("(No description)\n\n", fg="gray")

    with tempfile.NamedTemporaryFile(mode='w+', suffix='.md', delete=False) as temp_file:
        temp_file.write(current_body or "")
        temp_file_path = temp_file.name

    try:
        editor = os.environ.get('EDITOR', 'vim')
        result = subprocess.run([editor, temp_file_path])
        if result.returncode != 0:
            cout("Editor exited with error, not updating PR description.\n", fg="red")
            return

        with open(temp_file_path, 'r') as temp_file:
            new_body = temp_file.read().strip()

        original_content = (current_body or "").strip()
        new_content = new_body.strip()

        if new_content == original_content:
            cout("No changes made to PR description.\n", fg="yellow")
            return

        cout("Updating PR description...\n", fg="green")
        run(CmdArgs(["gh", "pr", "edit", str(pr["number"]), "--body", new_body]), out=True)
        cout("✓ Successfully updated PR #{} description\n", pr["number"], fg="green")
        pr["body"] = new_body

    except Exception as e:
        cout("Error editing PR description: {}\n", str(e), fg="red")
    finally:
        try:
            os.unlink(temp_file_path)
        except OSError:
            pass
