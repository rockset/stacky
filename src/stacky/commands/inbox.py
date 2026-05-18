"""Inbox commands - inbox, prs."""

import json

from simple_term_menu import TerminalMenu  # type: ignore

from stacky.pr.github import edit_pr_description
from stacky.stack.models import StackBranchSet
from stacky.utils.logging import IS_TERMINAL, cout, die
from stacky.utils.shell import run_always_return
from stacky.utils.types import CmdArgs


def cmd_inbox(stack: StackBranchSet, args):
    """List all active GitHub pull requests for the current user."""
    fields = [
        "number", "title", "headRefName", "baseRefName", "state", "url",
        "createdAt", "updatedAt", "author", "reviewDecision", "reviewRequests",
        "mergeable", "mergeStateStatus", "statusCheckRollup", "isDraft", "body"
    ]

    my_prs_data = json.loads(
        run_always_return(CmdArgs([
            "gh", "pr", "list", "--json", ",".join(fields),
            "--state", "open", "--author", "@me"
        ]))
    )

    review_prs_data = json.loads(
        run_always_return(CmdArgs([
            "gh", "pr", "list", "--json", ",".join(fields),
            "--state", "open", "--search", "review-requested:@me"
        ]))
    )

    # Categorize PRs
    waiting_on_me = []
    waiting_on_review = []
    approved = []

    for pr in my_prs_data:
        if pr.get("isDraft", False):
            waiting_on_me.append(pr)
        elif pr["reviewDecision"] == "APPROVED":
            approved.append(pr)
        elif pr["reviewRequests"] and len(pr["reviewRequests"]) > 0:
            waiting_on_review.append(pr)
        else:
            waiting_on_me.append(pr)

    # Sort by updatedAt
    for lst in [waiting_on_me, waiting_on_review, approved, review_prs_data]:
        lst.sort(key=lambda pr: pr["updatedAt"], reverse=True)

    def get_check_status(pr):
        if not pr.get("statusCheckRollup") or len(pr.get("statusCheckRollup")) == 0:
            return "", "gray"
        rollup = pr["statusCheckRollup"]
        states = [check["state"] for check in rollup if isinstance(check, dict) and "state" in check]
        if not states:
            return "", "gray"
        if "FAILURE" in states or "ERROR" in states:
            return "✗ Checks failed", "red"
        elif "PENDING" in states or "QUEUED" in states:
            return "⏳ Checks running", "yellow"
        elif all(state == "SUCCESS" for state in states):
            return "✓ Checks passed", "green"
        return "Checks mixed", "yellow"

    def display_pr_compact(pr, show_author=False):
        check_text, check_color = get_check_status(pr)
        pr_number_text = f"#{pr['number']}"
        clickable_number = f"\033]8;;{pr['url']}\033\\\033[96m{pr_number_text}\033[0m\033]8;;\033\\"
        cout("{} ", clickable_number)
        cout("{} ", pr["title"], fg="white")
        cout("({}) ", pr["headRefName"], fg="gray")
        if show_author:
            cout("by {} ", pr["author"]["login"], fg="gray")
        if pr.get("isDraft", False):
            cout("[DRAFT] ", fg="orange")
        if check_text:
            cout("{} ", check_text, fg=check_color)
        cout("Updated: {}\n", pr["updatedAt"][:10], fg="gray")

    def display_pr_full(pr, show_author=False):
        check_text, check_color = get_check_status(pr)
        pr_number_text = f"#{pr['number']}"
        clickable_number = f"\033]8;;{pr['url']}\033\\\033[96m{pr_number_text}\033[0m\033]8;;\033\\"
        cout("{} ", clickable_number)
        cout("{}\n", pr["title"], fg="white")
        cout("  {} -> {}\n", pr["headRefName"], pr["baseRefName"], fg="gray")
        if show_author:
            cout("  Author: {}\n", pr["author"]["login"], fg="gray")
        if pr.get("isDraft", False):
            cout("  [DRAFT]\n", fg="orange")
        if check_text:
            cout("  {}\n", check_text, fg=check_color)
        cout("  {}\n", pr["url"], fg="blue")
        cout("  Updated: {}, Created: {}\n\n", pr["updatedAt"][:10], pr["createdAt"][:10], fg="gray")

    def display_pr_list(prs, show_author=False):
        for pr in prs:
            if args.compact:
                display_pr_compact(pr, show_author)
            else:
                display_pr_full(pr, show_author)

    if waiting_on_me:
        cout("Your PRs - Waiting on You:\n", fg="red")
        display_pr_list(waiting_on_me)
        cout("\n")
    if waiting_on_review:
        cout("Your PRs - Waiting on Review:\n", fg="yellow")
        display_pr_list(waiting_on_review)
        cout("\n")
    if approved:
        cout("Your PRs - Approved:\n", fg="green")
        display_pr_list(approved)
        cout("\n")
    if not my_prs_data:
        cout("No active pull requests authored by you.\n", fg="green")
    if review_prs_data:
        cout("Pull Requests Awaiting Your Review:\n", fg="yellow")
        display_pr_list(review_prs_data, show_author=True)
    else:
        cout("No pull requests awaiting your review.\n", fg="yellow")


def cmd_prs(stack: StackBranchSet, args):
    """Interactive PR management - select and edit PR descriptions."""
    fields = [
        "number", "title", "headRefName", "baseRefName", "state", "url",
        "createdAt", "updatedAt", "author", "reviewDecision", "reviewRequests",
        "mergeable", "mergeStateStatus", "statusCheckRollup", "isDraft", "body"
    ]

    my_prs_data = json.loads(
        run_always_return(CmdArgs([
            "gh", "pr", "list", "--json", ",".join(fields),
            "--state", "open", "--author", "@me"
        ]))
    )

    review_prs_data = json.loads(
        run_always_return(CmdArgs([
            "gh", "pr", "list", "--json", ",".join(fields),
            "--state", "open", "--search", "review-requested:@me"
        ]))
    )

    all_prs = my_prs_data + review_prs_data
    if not all_prs:
        cout("No active pull requests found.\n", fg="green")
        return

    if not IS_TERMINAL:
        die("Interactive PR management requires a terminal")

    menu_options = [f"#{pr['number']} {pr['title']}" for pr in all_prs]
    menu_options.append("Exit")

    while True:
        cout("\nSelect a PR to edit its description:\n", fg="cyan")
        menu = TerminalMenu(menu_options, cursor_index=0)
        idx = menu.show()

        if idx is None or idx == len(menu_options) - 1:
            break

        selected_pr = all_prs[idx]
        edit_pr_description(selected_pr)
