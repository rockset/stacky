#!/usr/bin/env python3
# GitHub helper for stacked diffs.
#
# Git maintains all metadata locally. Does everything by forking "git" and "gh"
# commands.
#
# Theory of operation:
#
# Each entry in a stack is a branch, set to track its parent (that is, `git
# config branch.<name>.remote` is ".", and `git config branch.<name>.merge` is
# "refs/heads/<parent>")
#
# For each branch, we maintain a ref (call it PC, for "parent commit") pointing
# to the commit at the tip of the parent branch, as `git update-ref
# refs/stack-parent/<name>`.
#
# When rebasing or restacking, we proceed in depth-first order (from "master"
# onwards). After updating a parent branch P, given a child branch C,
# we rebase everything from C's PC until C's tip onto P.
#
# That's all there is to it.

import configparser
import dataclasses
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from argparse import ArgumentParser
from typing import List, Optional, Tuple

import asciitree
import colors
from simple_term_menu import TerminalMenu

_LOGGING_FORMAT = "%(asctime)s %(module)s %(levelname)s: %(message)s"

COLOR_STDOUT = os.isatty(1)
COLOR_STDERR = os.isatty(2)
IS_TERMINAL = os.isatty(1) and os.isatty(2)
CURRENT_BRANCH = None
STACK_BOTTOMS = frozenset(["master", "main"])
STATE_FILE = os.path.expanduser("~/.stacky.state")
TMP_STATE_FILE = STATE_FILE + ".tmp"

LOGLEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}


@dataclasses.dataclass
class StackyConfig:
    skip_confirm: bool = False
    change_to_main: bool = False
    change_to_adopted: bool = False

    def read_one_config(self, config_path: str):
        rawconfig = configparser.ConfigParser()
        rawconfig.read(config_path)
        if rawconfig.has_section("UI"):
            self.skip_confirm = rawconfig.get(
                "UI", "skip_confirm", fallback=self.skip_confirm
            )
            self.change_to_main = rawconfig.get(
                "UI", "change_to_main", fallback=self.change_to_main
            )
            self.change_to_adopted = rawconfig.get(
                "UI", "change_to_adopted", fallback=self.change_to_adopted
            )


def read_config() -> StackyConfig:
    root_dir = get_top_level_dir()
    config = StackyConfig()
    config_paths = [f"{root_dir}/.stackyconfig", os.path.expanduser("~/.stackyconfig")]

    for p in config_paths:
        if os.path.exists(p):
            config.read_one_config(p)

    return config


def fmt(s, *args, color=False, fg=None, bg=None, style=None, **kwargs):
    s = colors.color(s, fg=fg, bg=bg, style=style) if color else s
    return s.format(*args, **kwargs)


def cout(*args, **kwargs):
    return sys.stdout.write(fmt(*args, color=COLOR_STDOUT, **kwargs))


def _log(fn, *args, **kwargs):
    return fn("%s", fmt(*args, color=COLOR_STDERR, **kwargs))


def debug(*args, **kwargs):
    return _log(logging.debug, *args, fg="green", **kwargs)


def info(*args, **kwargs):
    return _log(logging.info, *args, fg="green", **kwargs)


def warning(*args, **kwargs):
    return _log(logging.warning, *args, fg="yellow", **kwargs)


def error(*args, **kwargs):
    return _log(logging.error, *args, fg="red", **kwargs)


class ExitException(BaseException):
    def __init__(self, fmt, *args, **kwargs):
        super().__init__(fmt.format(*args, **kwargs))


def die(*args, **kwargs):
    raise ExitException(*args, **kwargs)


def _check_returncode(sp, cmd):
    rc = sp.returncode
    if rc == 0:
        return
    stderr = sp.stderr.decode("UTF-8")
    if rc < 0:
        die("Killed by signal {}: {}. Stderr was:\n{}", -rc, shlex.join(cmd), stderr)
    else:
        die("Exited with status {}: {}. Stderr was:\n{}", rc, shlex.join(cmd), stderr)


def run_multiline(cmd, *, check=True, null=True, out=False):
    debug("Running: {}", shlex.join(cmd))
    sys.stdout.flush()
    sys.stderr.flush()
    sp = subprocess.run(
        cmd,
        stdout=1 if out else subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check:
        _check_returncode(sp, cmd)
    rc = sp.returncode
    if rc != 0:
        return None
    if sp.stdout is None:
        return ""
    return sp.stdout.decode("UTF-8")


def run(cmd, **kwargs):
    out = run_multiline(cmd, **kwargs)
    return None if out is None else out.strip()


def remove_prefix(s, prefix):
    if not s.startswith(prefix):
        die('Invalid string "{}": expected prefix "{}"', s, prefix)
    return s[len(prefix) :]  # noqa: E203


def get_current_branch():
    return remove_prefix(run(["git", "symbolic-ref", "-q", "HEAD"]), "refs/heads/")


def get_all_branches():
    branches = run_multiline(
        ["git", "for-each-ref", "--format", "%(refname:short)", "refs/heads"]
    )
    return [b for b in branches.split("\n") if b]


def get_real_stack_bottom() -> Optional[str]:
    """
    return the actual stack bottom for this current repo
    """
    branches = get_all_branches()
    candiates = set()
    for b in branches:
        if b in STACK_BOTTOMS:
            candiates.add(b)

    if len(candiates) == 1:
        return candiates.pop()


def get_stack_parent_branch(branch):
    if branch in STACK_BOTTOMS:
        return None
    p = run(["git", "config", "branch.{}.merge".format(branch)], check=False)
    if p is not None:
        p = remove_prefix(p, "refs/heads/")
    return p


def get_top_level_dir() -> str:
    return run(["git", "rev-parse", "--show-toplevel"])


def get_stack_parent_commit(branch):
    return run(["git", "rev-parse", "refs/stack-parent/{}".format(branch)], check=False)


def get_commit(branch):
    return run(["git", "rev-parse", "refs/heads/{}".format(branch)], check=False)


def get_pr_info(branch, *, full=False):
    fields = [
        "id",
        "number",
        "state",
        "mergeable",
        "url",
        "title",
        "baseRefName",
        "headRefName",
    ]
    if full:
        fields += ["commits"]
    fields = ",".join(fields)
    infos = json.loads(
        run(
            [
                "gh",
                "pr",
                "list",
                "--json",
                fields,
                "--state",
                "all",
                "--head",
                branch,
            ]
        )
    )
    infos = {info["id"]: info for info in infos}
    open_prs = [info for info in infos.values() if info["state"] == "OPEN"]
    if len(open_prs) > 1:
        die("Branch {} has more than one open PR: {}", branch, ", ".join(open_prs))
    return infos, open_prs[0] if open_prs else None


# (remote, remote_branch, remote_branch_commit)
def get_remote_info(branch):
    if branch not in STACK_BOTTOMS:
        remote = run(["git", "config", "branch.{}.remote".format(branch)], check=False)
        if remote != ".":
            die("Misconfigured branch {}: remote {}", branch, remote)

    # TODO(tudor): Maybe add a way to change these.
    remote = "origin"
    remote_branch = branch

    remote_commit = run(
        ["git", "rev-parse", "refs/remotes/{}/{}".format(remote, remote_branch)],
        check=False,
    )

    return (remote, remote_branch, remote_commit)


class StackBranch:
    def __init__(
        self,
        name,
        parent,
        parent_commit,
    ):
        self.name = name
        self.parent = parent
        self.parent_commit = parent_commit
        self.children = set()
        self.commit = get_commit(name)
        self.remote, self.remote_branch, self.remote_commit = get_remote_info(name)
        self.pr_info = []
        self.open_pr_info = None
        self._pr_info_loaded = False

    def is_synced_with_parent(self):
        return self.parent is None or self.parent_commit == self.parent.commit

    def is_synced_with_remote(self):
        return self.commit == self.remote_commit

    def __repr__(self):
        return f"StackBranch: {self.name} {len(self.children)}"

    def load_pr_info(self):
        if not self._pr_info_loaded:
            self._pr_info_loaded = True
            self.pr_info, self.open_pr_info = get_pr_info(self.name)


class StackBranchSet:
    def __init__(self):
        self.stack = {}
        self.tops = set()
        self.bottoms = set()

    def add(self, name, **kwargs) -> StackBranch:
        if name in self.stack:
            s = self.stack[name]
            assert s.name == name
            for k, v in kwargs.items():
                if getattr(s, k) != v:
                    die(
                        "Mismatched stack: {}: {}={}, expected {}",
                        name,
                        k,
                        getattr(s, k),
                        v,
                    )
        else:
            s = StackBranch(name, **kwargs)
            self.stack[name] = s
            if s.parent is None:
                self.bottoms.add(s)
            self.tops.add(s)
        return s

    def add_child(self, s, child):
        s.children.add(child)
        self.tops.discard(s)


def load_current_stack(stack, branch, *, check=True):
    branches = []
    while branch not in STACK_BOTTOMS:
        parent = get_stack_parent_branch(branch)
        parent_commit = get_stack_parent_commit(branch)
        branches.append((branch, parent_commit))
        if not parent or not parent_commit:
            if check:
                die("Branch is not in a stack: {}", branch)
            return None, [b for b, _ in branches]
        branch = parent

    branches.append((branch, None))
    top = None
    for name, parent_commit in reversed(branches):
        n = stack.add(
            name,
            parent=top,
            parent_commit=parent_commit,
        )
        if top:
            stack.add_child(top, n)
        top = n

    return top, [b for b, _ in branches]


def load_all_stacks(stack):
    all_branches = set(get_all_branches())
    current_branch_top = None
    while all_branches:
        b = all_branches.pop()
        top, branches = load_current_stack(stack, b, check=False)
        all_branches -= set(branches)
        if top is None:
            if len(branches) > 1:
                # Incomplete (broken) stack
                warning("Broken stack: {}", " -> ".join(branches))
            continue
        if b == CURRENT_BRANCH:
            current_branch_top = top
    return current_branch_top


def make_tree_node(b):
    return (b.name, (b, make_subtree(b)))


def make_subtree(b):
    return dict(make_tree_node(c) for c in sorted(b.children, key=lambda x: x.name))


def make_tree(b):
    return dict([make_tree_node(b)])


def format_name(b, *, color=None):
    prefix = ""
    severity = 0
    if not b.is_synced_with_parent():
        prefix += fmt("!", color=color, fg="yellow")
        severity = max(severity, 2)
    if not b.is_synced_with_remote():
        prefix += fmt("~", color=color, fg="yellow")
    if b.name == CURRENT_BRANCH:
        prefix += fmt("*", color=color, fg="cyan")
    else:
        severity = max(severity, 1)
    if prefix:
        prefix += " "
    fg = ["cyan", "green", "yellow", "red"][severity]
    suffix = ""
    if b.open_pr_info:
        suffix += " "
        suffix += fmt("(#{})", b.open_pr_info["number"], color=color, fg="blue")
        suffix += " "
        suffix += fmt("{}", b.open_pr_info["title"], color=color, fg="blue")
    return prefix + fmt("{}", b.name, color=color, fg=fg) + suffix


def format_tree(tree, *, color=None):
    return {
        format_name(branch, color=color): format_tree(children, color=color)
        for branch, children in tree.values()
    }


# Print upside down, to match our "upstack" / "downstack" nomenclature
_ASCII_TREE_BOX = {
    "UP_AND_RIGHT": "\u250c",
    "HORIZONTAL": "\u2500",
    "VERTICAL": "\u2502",
    "VERTICAL_AND_RIGHT": "\u251c",
}
_ASCII_TREE_STYLE = asciitree.drawing.BoxStyle(gfx=_ASCII_TREE_BOX)
ASCII_TREE = asciitree.LeftAligned(draw=_ASCII_TREE_STYLE)


def print_tree(tree):
    global ASCII_TREE
    s = ASCII_TREE(format_tree(tree, color=COLOR_STDOUT))
    lines = s.split("\n")
    print("\n".join(reversed(lines)))


def print_forest(trees):
    for i, t in enumerate(trees):
        if i != 0:
            print()
        print_tree(t)


def get_all_stacks_as_forest(stack):
    return [make_tree(b) for b in stack.bottoms]


def get_current_stack_as_forest(stack):
    b = stack.stack[CURRENT_BRANCH]
    d = make_tree(b)
    b = b.parent
    while b:
        d = {b.name: (b, d)}
        b = b.parent
    return [d]


def get_current_upstack_as_forest(stack):
    b = stack.stack[CURRENT_BRANCH]
    return [make_tree(b)]


def get_current_downstack_as_forest(stack):
    b = stack.stack[CURRENT_BRANCH]
    d = {}
    while b:
        d = {b.name: (b, d)}
        b = b.parent
    return [d]


def init_git():
    push_default = run(["git", "config", "remote.pushDefault"], check=False)
    if push_default is not None:
        die("`git config remote.pushDefault` may not be set")
    auth_status = run(["gh", "auth", "status"], check=False)
    if auth_status is None:
        die("`gh` authentication failed")
    global CURRENT_BRANCH
    CURRENT_BRANCH = get_current_branch()


def depth_first(forest):
    if type(forest) == list:
        for tree in forest:
            for b in depth_first(tree):
                yield b
    else:
        for _, (branch, children) in forest.items():
            yield branch
            for b in depth_first(children):
                yield b


def menu_choose_branch(forest):
    if not IS_TERMINAL:
        die("May only choose from menu when using a terminal")

    global ASCII_TREE
    s = ""
    lines = []
    for tree in forest:
        s = ASCII_TREE(format_tree(tree))
        lines += [l.rstrip() for l in s.split("\n")]
    lines.reverse()

    initial_index = 0
    for i, l in enumerate(lines):
        if "*" in l:  # lol
            initial_index = i
            break

    menu = TerminalMenu(lines, cursor_index=initial_index)
    idx = menu.show()
    if idx is None:
        die("Aborted")

    branches = list(depth_first(forest))
    branches.reverse()
    return branches[idx]


def load_pr_info_for_forest(forest):
    for b in depth_first(forest):
        b.load_pr_info()


def cmd_info(stack, args):
    forest = get_all_stacks_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def checkout(branch):
    info("Checking out branch {}", branch)
    run(["git", "checkout", branch], out=True)


def cmd_branch_up(stack, args):
    b = stack.stack[CURRENT_BRANCH]
    if not b.children:
        info("Branch {} is already at the top of the stack", CURRENT_BRANCH)
        return
    if len(b.children) > 1:
        if not IS_TERMINAL:
            die(
                "Branch {} has multiple children: {}",
                CURRENT_BRANCH,
                ", ".join(c.name for c in b.children),
            )
        cout(
            "Branch {} has {} children, choose one\n",
            CURRENT_BRANCH,
            len(b.children),
            fg="green",
        )
        forest = [{c.name: (c, {})} for c in b.children]
        child = menu_choose_branch(forest).name
    else:
        child = next(iter(b.children)).name
    checkout(child)


def cmd_branch_down(stack, args):
    b = stack.stack[CURRENT_BRANCH]
    if not b.parent:
        info("Branch {} is already at the bottom of the stack", CURRENT_BRANCH)
        return
    checkout(b.parent.name)


def create_branch(branch):
    run(["git", "checkout", "-b", branch, "--track"], out=True)


def cmd_branch_new(stack, args):
    b = stack.stack[CURRENT_BRANCH]
    assert b.commit
    name = args.name
    create_branch(name)
    run(["git", "update-ref", "refs/stack-parent/{}".format(name), b.commit, ""])


def cmd_branch_checkout(stack, args):
    branch_name = args.name
    if branch_name is None:
        forest = get_all_stacks_as_forest(stack)
        branch_name = menu_choose_branch(forest).name
    checkout(branch_name)


def cmd_stack_info(stack, args):
    forest = get_current_stack_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_stack_checkout(stack, args):
    forest = get_current_stack_as_forest(stack)
    branch_name = menu_choose_branch(forest).name
    checkout(branch_name)


def prompt(message: str, default_value: Optional[str]) -> str:
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


def confirm(msg="Proceed?"):
    if CONFIG.skip_confirm:
        return
    if not os.isatty(0):
        die("Standard input is not a terminal, use --force option to force action")
    print()
    while True:
        cout("{} [yes/no] ", msg, fg="yellow")
        sys.stderr.flush()
        r = input().strip().lower()
        if r == "yes":
            break
        if r == "no":
            die("Not confirmed")
        cout("Please answer yes or no\n", fg="red")


def find_reviewers(b) -> Optional[List[str]]:
    out = run_multiline(
        [
            "git",
            "log",
            "--pretty=format:%b",
            "-1",
            f"{b.name}",
        ],
    )
    for l in out.split("\n"):
        reviewer_match = re.match(r"^reviewers?\s*:\s*(.*)", l, re.I)
        if reviewer_match:
            reviewers = reviewer_match.group(1).split(",")
            logging.debug(f"Found the following reviewers: {', '.join(reviewers)}")
            return reviewers
    return


def create_gh_pr(b):
    cout("Creating PR for {}\n", b.name, fg="green")
    cmd = ["gh", "pr", "create", "--head", b.name, "--base", b.parent.name]
    match = re.match(r"([A-Z]{3,}-\d{1,})($|-.*)", b.name)
    reviewers = find_reviewers(b)
    if match:
        out = run_multiline(
            ["git", "log", "--pretty=oneline", f"{b.parent.name}..{b.name}"],
        )
        title = f"[{match.group(1)}] "
        # Just one line (hence 2 elements with the last one being an empty string when we
        # split on "\"n ?
        # Then use the title of the commit as the title of the PR

        if len(out.split("\n")) == 2:
            out = run(
                [
                    "git",
                    "log",
                    "--pretty=format:%s",
                    "-1",
                    f"{b.name}",
                ],
                out=False,
            )
            if b.name not in out:
                title += out
            else:
                title = out

        title = prompt(
            (
                fmt("? ", color=COLOR_STDOUT, fg="green")
                + fmt("Title ", color=COLOR_STDOUT, style="bold", fg="white")
            ),
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

    run(
        cmd,
        out=True,
    )


def do_push(forest, *, force=False, pr=False):
    if pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)
    for b in depth_first(forest):
        if not b.is_synced_with_parent():
            die(
                "Branch {} is not synced with parent {}, sync first",
                b.name,
                b.parent.name,
            )

    # (branch, push, pr_action)
    PR_NONE = 0
    PR_FIX_BASE = 1
    PR_CREATE = 2
    actions = []
    for b in depth_first(forest):
        if not b.parent:
            cout("✓ Not pushing base branch {}\n", b.name, fg="green")
            continue

        push = False
        if b.is_synced_with_remote():
            cout(
                "✓ Not pushing branch {}, synced with remote {}/{}\n",
                b.name,
                b.remote,
                b.remote_branch,
                fg="green",
            )
        else:
            cout("- Will push branch {} to {}/{}\n", b.name, b.remote, b.remote_branch)
            push = True

        pr_action = PR_NONE
        if pr:
            if b.open_pr_info:
                expected_base = b.parent.name
                if b.open_pr_info["baseRefName"] != expected_base:
                    cout(
                        "- Branch {} already has open PR #{}; will change PR base from {} to {}\n",
                        b.name,
                        b.open_pr_info["number"],
                        b.open_pr_info["baseRefName"],
                        expected_base,
                    )
                    pr_action = PR_FIX_BASE
                else:
                    cout(
                        "✓ Branch {} already has open PR #{}\n",
                        b.name,
                        b.open_pr_info["number"],
                        fg="green",
                    )
            else:
                cout("- Will create PR for branch {}\n", b.name)
                pr_action = PR_CREATE

        if not push and pr_action == PR_NONE:
            continue

        actions.append((b, push, pr_action))

    if actions and not force:
        confirm()

    for b, push, pr_action in actions:
        if push:
            cout("Pushing {}\n", b.name, fg="green")
            run(
                [
                    "git",
                    "push",
                    "-f",
                    b.remote,
                    "{}:{}".format(b.name, b.remote_branch),
                ],
                out=True,
            )
        if pr_action == PR_FIX_BASE:
            cout("Fixing PR base for {}\n", b.name, fg="green")
            run(
                [
                    "gh",
                    "pr",
                    "edit",
                    str(b.open_pr_info["number"]),
                    "--base",
                    b.parent.name,
                ],
                out=True,
            )
        elif pr_action == PR_CREATE:
            create_gh_pr(b)


def cmd_stack_push(stack, args):
    do_push(get_current_stack_as_forest(stack), force=args.force, pr=args.pr)


def do_sync(forest):
    print_forest(forest)

    syncs = []
    sync_names = []
    syncs_set = set()
    for b in depth_first(forest):
        if not b.parent:
            cout("✓ Not syncing base branch {}\n", b.name, fg="green")
            continue
        if b.is_synced_with_parent() and not b.parent in syncs_set:
            cout(
                "✓ Not syncing branch {}, already synced with parent {}\n",
                b.name,
                b.parent.name,
                fg="green",
            )
            continue
        syncs.append(b)
        syncs_set.add(b)
        sync_names.append(b.name)
        cout("- Will sync branch {} on top of {}\n", b.name, b.parent.name)

    if not syncs:
        return

    syncs.reverse()
    sync_names.reverse()
    inner_do_sync(syncs, sync_names)


def set_parent_commit(branch, new_commit, prev_commit=None):
    cmd = [
        "git",
        "update-ref",
        "refs/stack-parent/{}".format(branch),
        new_commit,
    ]
    if prev_commit is not None:
        cmd.append(prev_commit)
    run(cmd)


def get_commits_between(a, b):
    lines = run_multiline(["git", "rev-list", "{}..{}".format(a, b)])
    return [x.strip() for x in lines.split("\n")]


def inner_do_sync(syncs, sync_names):
    print()
    while syncs:
        with open(TMP_STATE_FILE, "w") as f:
            json.dump({"branch": CURRENT_BRANCH, "sync": sync_names}, f)
        os.replace(TMP_STATE_FILE, STATE_FILE)  # make the write atomic

        b = syncs.pop()
        sync_names.pop()
        if b.is_synced_with_parent():
            cout("{} is already synced on top of {}\n", b.name, b.parent.name)
            continue
        if b.parent.commit in get_commits_between(b.parent_commit, b.commit):
            cout(
                "Recording complete rebase of {} on top of {}\n",
                b.name,
                b.parent.name,
                fg="green",
            )
        else:
            cout("Rebasing {} on top of {}\n", b.name, b.parent.name, fg="green")
            r = run(
                ["git", "rebase", "--onto", b.parent.name, b.parent_commit, b.name],
                out=True,
                check=False,
            )
            if r is None:
                print()
                die(
                    "Automatic rebase failed. Please complete the rebase (fix conflicts; `git rebase --continue`), then run `stacky continue`"
                )
            b.commit = get_commit(b.name)
        set_parent_commit(b.name, b.parent.commit, b.parent_commit)
        b.parent_commit = b.parent.commit
    run(["git", "checkout", CURRENT_BRANCH])


def cmd_stack_sync(stack, args):
    do_sync(get_current_stack_as_forest(stack))


def do_commit(stack, *, message=None, amend=False, allow_empty=False, edit=True):
    b = stack.stack[CURRENT_BRANCH]
    if not b.parent:
        die("Do not commit directly on {}", b.name)
    if not b.is_synced_with_parent():
        die(
            "Branch {} is not synced with parent {}, sync before committing",
            b.name,
            b.parent.name,
        )
    if amend and b.commit == b.parent.commit:
        die("Branch {} has no commits, may not amend", b.name)

    cmd = ["git", "commit"]
    if allow_empty:
        cmd += ["--allow-empty"]
    if amend:
        cmd += ["--amend"]
        if not edit:
            cmd += ["--no-edit"]
    elif not edit:
        die("--no-edit is only supported with --amend")
    if message:
        cmd += ["-m", message]
    run(cmd, out=True)

    # Sync everything upstack
    b.commit = get_commit(b.name)
    do_sync(get_current_upstack_as_forest(stack))


def cmd_commit(stack, args):
    do_commit(
        stack,
        message=args.message,
        amend=args.amend,
        allow_empty=args.allow_empty,
        edit=not args.no_edit,
    )


def cmd_amend(stack, args):
    do_commit(stack, amend=True, edit=False)


def cmd_upstack_info(stack, args):
    forest = get_current_upstack_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_upstack_push(stack, args):
    do_push(get_current_upstack_as_forest(stack), force=args.force, pr=args.pr)


def cmd_upstack_sync(stack, args):
    do_sync(get_current_upstack_as_forest(stack))


def set_parent(branch, target, *, set_origin=False):
    if set_origin:
        run(["git", "config", "branch.{}.remote".format(branch), "."])

    run(
        [
            "git",
            "config",
            "branch.{}.merge".format(branch),
            "refs/heads/{}".format(target),
        ]
    )


def cmd_upstack_onto(stack, args):
    b = stack.stack[CURRENT_BRANCH]
    if not b.parent:
        die("May not restack {}", b.name)
    target = stack.stack[args.target]
    upstack = get_current_upstack_as_forest(stack)
    for ub in depth_first(upstack):
        if ub == target:
            die("Target branch {} is upstack of {}", target.name, b.name)
    b.parent = target
    set_parent(b.name, target.name)

    do_sync(upstack)


def cmd_downstack_info(stack, args):
    forest = get_current_downstack_as_forest(stack)
    if args.pr:
        load_pr_info_for_forest(forest)
    print_forest(forest)


def cmd_downstack_push(stack, args):
    do_push(get_current_downstack_as_forest(stack), force=args.force, pr=args.pr)


def cmd_downstack_sync(stack, args):
    do_sync(get_current_downstack_as_forest(stack))


def get_bottom_level_branches_as_forest(stack):
    return [
        {bottom.name: (bottom, {b.name: (b, {}) for b in bottom.children})}
        for bottom in stack.bottoms
    ]


def cmd_update(stack, args):
    remote = "origin"
    info("Fetching from {}", remote)
    run(["git", "fetch", remote])

    # TODO(tudor): We should rebase instead of silently dropping
    # everything you have on local master. Oh well.
    global CURRENT_BRANCH
    for b in stack.bottoms:
        run(
            [
                "git",
                "update-ref",
                "refs/heads/{}".format(b.name),
                "refs/remotes/{}/{}".format(remote, b.remote_branch),
            ]
        )
        if b.name == CURRENT_BRANCH:
            run(["git", "reset", "--hard", "HEAD"])

    # We treat origin as the source of truth for bottom branches (master), and
    # the local repo as the source of truth for everything else. So we can only
    # track PR closure for branches that are direct descendants of master.

    info("Checking if any PRs have been merged and can be deleted")
    forest = get_bottom_level_branches_as_forest(stack)
    load_pr_info_for_forest(forest)

    deletes = []
    for b in depth_first(forest):
        if not b.parent or b.open_pr_info:
            continue
        for pr_info in b.pr_info.values():
            if pr_info["state"] != "MERGED":
                continue
            cout(
                "- Will delete branch {}, PR #{} merged into {}\n",
                b.name,
                pr_info["number"],
                b.parent.name,
            )
            deletes.append(b)
            for c in b.children:
                cout(
                    "- Will reparent branch {} onto {}\n",
                    c.name,
                    b.parent.name,
                )
            break

    if deletes and not args.force:
        confirm()

    # Make sure we're not trying to delete the current branch
    for b in deletes:
        for c in b.children:
            info("Reparenting {} onto {}", c.name, b.parent.name)
            c.parent = b.parent
            set_parent(c.name, b.parent.name)
        info("Deleting {}", b.name)
        if b.name == CURRENT_BRANCH:
            new_branch = next(iter(stack.bottoms))
            info("About to delete current branch, switching to {}", new_branch.name)
            run(["git", "checkout", new_branch.name])
            CURRENT_BRANCH = new_branch
        run(["git", "branch", "-D", b.name])


def cmd_import(stack, args):
    # Importing has to happen based on PR info, rather than local branch
    # relationships, as that's the only place Graphite populates.
    branch = args.name
    branches = []
    bottoms = set(b.name for b in stack.bottoms)
    while branch not in bottoms:
        _, open_pr = get_pr_info(branch, full=True)
        info("Getting PR information for {}", branch)
        if not open_pr:
            die("Branch {} has no open PR", branch)
        if open_pr["headRefName"] != branch:
            die(
                "Branch {} is misconfigured: PR #{} head is {}",
                branch,
                open_pr["number"],
                open_pr["headRefName"],
            )
        if not open_pr["commits"]:
            die("PR #{} has no commits", open_pr["number"])
        first_commit = open_pr["commits"][0]["oid"]
        parent_commit = run(["git", "rev-parse", "{}^".format(first_commit)])
        next_branch = open_pr["baseRefName"]
        info(
            "Branch {}: PR #{}, parent is {} at commit {}",
            branch,
            open_pr["number"],
            next_branch,
            parent_commit,
        )
        branches.append((branch, parent_commit))
        branch = next_branch

    if not branches:
        return

    base_branch = branch
    branches.reverse()

    for b, parent_commit in branches:
        cout(
            "- Will set parent of {} to {} at commit {}\n",
            b,
            branch,
            parent_commit,
        )
        branch = b

    if not args.force:
        confirm()

    branch = base_branch
    for b, parent_commit in branches:
        set_parent(b, branch, set_origin=True)
        set_parent_commit(b, parent_commit)
        branch = b


def get_merge_base(b1, b2):
    return run(["git", "merge-base", b1, b2])


def cmd_adopt(stack, args):
    """
    Adopt a branch that is based on the current branch (which must be a
    valid stack bottom or the stack bottom (master or main) will be used
    if change_to_main option is set in the config file
    """
    branch = args.name
    global CURRENT_BRANCH
    if CURRENT_BRANCH not in STACK_BOTTOMS:
        main_branch = get_real_stack_bottom()

        if CONFIG.change_to_main and main_branch is not None:
            run(["git", "checkout", main_branch])
            CURRENT_BRANCH = main_branch
        else:
            die(
                "The current branch {} must be a valid stack bottom: {}",
                CURRENT_BRANCH,
                ", ".join(sorted(STACK_BOTTOMS)),
            )
    parent_commit = get_merge_base(CURRENT_BRANCH, branch)
    set_parent(branch, CURRENT_BRANCH, set_origin=True)
    set_parent_commit(branch, parent_commit)
    if CONFIG.change_to_adopted:
        run(["git", "checkout", branch])


def cmd_land(stack, args):
    forest = get_current_downstack_as_forest(stack)
    assert len(forest) == 1
    branches = []
    p = forest[0]
    while p:
        assert len(p) == 1
        _, (b, p) = next(iter(p.items()))
        branches.append(b)
    assert branches
    assert branches[0] in stack.bottoms
    if len(branches) == 1:
        die("May not land {}", branches[0].name)

    b = branches[1]
    if not b.is_synced_with_parent():
        die(
            "Branch {} is not synced with parent {}, sync before landing",
            b.name,
            b.parent.name,
        )
    if not b.is_synced_with_remote():
        die(
            "Branch {} is not synced with remote branch, push local changes before landing",
            b.name,
        )

    b.load_pr_info()
    pr = b.open_pr_info
    if not pr:
        die("Branch {} does not have an open PR", b.name)

    if pr["mergeable"] != "MERGEABLE":
        die(
            "PR #{} for branch {} is not mergeable: {}",
            pr["number"],
            b.name,
            pr["mergeable"],
        )

    if len(branches) > 2:
        cout(
            "The `land` command only lands the bottom-most branch {}; the current stack has {} branches, ending with {}\n",
            b.name,
            len(branches) - 1,
            CURRENT_BRANCH,
            fg="yellow",
        )

    msg = fmt("- Will land PR #{} (", pr["number"], color=COLOR_STDOUT)
    msg += fmt("{}", pr["url"], color=COLOR_STDOUT, fg="blue")
    msg += fmt(") for branch {}", b.name, color=COLOR_STDOUT)
    msg += fmt(" into branch {}\n", b.parent.name, color=COLOR_STDOUT)
    sys.stdout.write(msg)

    if not args.force:
        confirm()

    head_commit = run(["git", "rev-parse", b.name])
    cmd = ["gh", "pr", "merge", b.name, "--squash", "--match-head-commit", head_commit]
    if args.auto:
        cmd.append("--auto")
    run(cmd, out=True)
    cout("\n✓ Success! Run `stacky update` to update local state.\n", fg="green")


def main():
    logging.basicConfig(format=_LOGGING_FORMAT, level=logging.INFO)
    try:
        parser = ArgumentParser(description="Handle git stacks")
        parser.add_argument(
            "--log-level",
            default="info",
            choices=LOGLEVELS.keys(),
            help="Set the log level",
        )
        parser.add_argument(
            "--color",
            default="auto",
            choices=["always", "auto", "never"],
            help="Colorize output and error",
        )

        subparsers = parser.add_subparsers(required=True, dest="command")

        # continue
        continue_parser = subparsers.add_parser(
            "continue", help="Continue previously interrupted command"
        )
        continue_parser.set_defaults(func=None)

        # down
        down_parser = subparsers.add_parser(
            "down", help="Go down in the current stack (towards master/main)"
        )
        down_parser.set_defaults(func=cmd_branch_down)
        # up
        up_parser = subparsers.add_parser(
            "up", help="Go up in the current stack (away master/main)"
        )
        up_parser.set_defaults(func=cmd_branch_up)
        # info
        info_parser = subparsers.add_parser("info", help="Stack info")
        info_parser.add_argument("--pr", action="store_true", help="Get PR info (slow)")
        info_parser.set_defaults(func=cmd_info)

        # commit
        commit_parser = subparsers.add_parser("commit", help="Commit")
        commit_parser.add_argument("-m", help="Commit message", dest="message")
        commit_parser.add_argument(
            "--amend", action="store_true", help="Amend last commit"
        )
        commit_parser.add_argument(
            "--allow-empty", action="store_true", help="Allow empty commit"
        )
        commit_parser.add_argument("--no-edit", action="store_true", help="Skip editor")
        commit_parser.set_defaults(func=cmd_commit)

        # amend
        amend_parser = subparsers.add_parser(
            "amend", help="Shortcut for amending last commit"
        )
        amend_parser.set_defaults(func=cmd_amend)

        # branch
        branch_parser = subparsers.add_parser(
            "branch", aliases=["b"], help="Operations on branches"
        )
        branch_subparsers = branch_parser.add_subparsers(
            required=True, dest="branch_command"
        )
        branch_up_parser = branch_subparsers.add_parser(
            "up", aliases=["u"], help="Move upstack"
        )
        branch_up_parser.set_defaults(func=cmd_branch_up)

        branch_down_parser = branch_subparsers.add_parser(
            "down", aliases=["d"], help="Move downstack"
        )
        branch_down_parser.set_defaults(func=cmd_branch_down)

        branch_new_parser = branch_subparsers.add_parser(
            "new", aliases=["create"], help="Create a new branch"
        )
        branch_new_parser.add_argument("name", help="Branch name")
        branch_new_parser.set_defaults(func=cmd_branch_new)

        branch_checkout_parser = branch_subparsers.add_parser(
            "checkout", aliases=["co"], help="Checkout a branch"
        )
        branch_checkout_parser.add_argument("name", help="Branch name", nargs="?")
        branch_checkout_parser.set_defaults(func=cmd_branch_checkout)

        # stack
        stack_parser = subparsers.add_parser(
            "stack", aliases=["s"], help="Operations on the full current stack"
        )
        stack_subparsers = stack_parser.add_subparsers(
            required=True, dest="stack_command"
        )

        stack_info_parser = stack_subparsers.add_parser(
            "info", aliases=["i"], help="Info for current stack"
        )
        stack_info_parser.add_argument(
            "--pr", action="store_true", help="Get PR info (slow)"
        )
        stack_info_parser.set_defaults(func=cmd_stack_info)

        stack_push_parser = stack_subparsers.add_parser("push", help="Push")
        stack_push_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        stack_push_parser.add_argument(
            "--no-pr", dest="pr", action="store_false", help="Skip Create PRs"
        )
        stack_push_parser.set_defaults(func=cmd_stack_push)

        stack_sync_parser = stack_subparsers.add_parser("sync", help="Sync")
        stack_sync_parser.set_defaults(func=cmd_stack_sync)

        stack_checkout_parser = stack_subparsers.add_parser(
            "checkout", aliases=["co"], help="Checkout a branch in this stack"
        )
        stack_checkout_parser.set_defaults(func=cmd_stack_checkout)

        # upstack
        upstack_parser = subparsers.add_parser(
            "upstack", aliases=["us"], help="Operations on the current upstack"
        )
        upstack_subparsers = upstack_parser.add_subparsers(
            required=True, dest="upstack_command"
        )

        upstack_info_parser = upstack_subparsers.add_parser(
            "info", aliases=["i"], help="Info for current upstack"
        )
        upstack_info_parser.add_argument(
            "--pr", action="store_true", help="Get PR info (slow)"
        )
        upstack_info_parser.set_defaults(func=cmd_upstack_info)

        upstack_push_parser = upstack_subparsers.add_parser("push", help="Push")
        upstack_push_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        upstack_push_parser.add_argument(
            "--no-pr", dest="pr", action="store_false", help="Skip Create PRs"
        )
        upstack_push_parser.set_defaults(func=cmd_upstack_push)

        upstack_sync_parser = upstack_subparsers.add_parser("sync", help="Sync")
        upstack_sync_parser.set_defaults(func=cmd_upstack_sync)

        upstack_onto_parser = upstack_subparsers.add_parser(
            "onto", aliases=["restack"], help="Restack"
        )
        upstack_onto_parser.add_argument("target", help="New parent")
        upstack_onto_parser.set_defaults(func=cmd_upstack_onto)

        # downstack
        downstack_parser = subparsers.add_parser(
            "downstack", aliases=["ds"], help="Operations on the current downstack"
        )
        downstack_subparsers = downstack_parser.add_subparsers(
            required=True, dest="downstack_command"
        )

        downstack_info_parser = downstack_subparsers.add_parser(
            "info", aliases=["i"], help="Info for current downstack"
        )
        downstack_info_parser.add_argument(
            "--pr", action="store_true", help="Get PR info (slow)"
        )
        downstack_info_parser.set_defaults(func=cmd_downstack_info)

        downstack_push_parser = downstack_subparsers.add_parser("push", help="Push")
        downstack_push_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        downstack_push_parser.add_argument(
            "--no-pr", dest="pr", action="store_false", help="Skip Create PRs"
        )
        downstack_push_parser.set_defaults(func=cmd_downstack_push)

        downstack_sync_parser = downstack_subparsers.add_parser("sync", help="Sync")
        downstack_sync_parser.set_defaults(func=cmd_downstack_sync)

        # update
        update_parser = subparsers.add_parser("update", help="Update repo")
        update_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        update_parser.set_defaults(func=cmd_update)

        # import
        import_parser = subparsers.add_parser("import", help="Import Graphite stack")
        import_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        import_parser.add_argument("name", help="Foreign stack top")
        import_parser.set_defaults(func=cmd_import)

        # adopt
        adopt_parser = subparsers.add_parser("adopt", help="Adopt one branch")
        adopt_parser.add_argument("name", help="Branch name")
        adopt_parser.set_defaults(func=cmd_adopt)

        # land
        land_parser = subparsers.add_parser(
            "land", help="Land bottom-most PR on current stack"
        )
        land_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        land_parser.add_argument(
            "--auto",
            "-a",
            action="store_true",
            help="Automatically merge after all checks pass",
        )
        land_parser.set_defaults(func=cmd_land)

        # shortcuts
        push_parser = subparsers.add_parser("push", help="Alias for downstack push")
        push_parser.add_argument(
            "--force", "-f", action="store_true", help="Bypass confirmation"
        )
        push_parser.add_argument(
            "--no-pr", dest="pr", action="store_false", help="Skip Create PRs"
        )
        push_parser.set_defaults(func=cmd_downstack_push)

        sync_parser = subparsers.add_parser("sync", help="Alias for stack sync")
        sync_parser.set_defaults(func=cmd_stack_sync)

        checkout_parser = subparsers.add_parser(
            "checkout", aliases=["co"], help="Checkout a branch"
        )
        checkout_parser.add_argument("name", help="Branch name", nargs="?")
        checkout_parser.set_defaults(func=cmd_branch_checkout)

        checkout_parser = subparsers.add_parser(
            "sco", help="Checkout a branch in this stack"
        )
        checkout_parser.set_defaults(func=cmd_stack_checkout)

        global CONFIG
        CONFIG = read_config()

        args = parser.parse_args()
        logging.basicConfig(
            format=_LOGGING_FORMAT, level=LOGLEVELS[args.log_level], force=True
        )

        global COLOR_STDERR
        global COLOR_STDOUT
        if args.color == "always":
            COLOR_STDERR = True
            COLOR_STDOUT = True
        elif args.color == "never":
            COLOR_STDERR = False
            COLOR_STDOUT = False

        init_git()

        stack = StackBranchSet()
        load_all_stacks(stack)

        global CURRENT_BRANCH
        if args.command == "continue":
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
            except FileNotFoundError as e:  # noqa: F841
                die("No previous command in progress")
            branch = state["branch"]
            run(["git", "checkout", branch])
            CURRENT_BRANCH = branch
            if CURRENT_BRANCH not in stack.stack:
                die("Current branch {} is not in a stack", CURRENT_BRANCH)

            sync_names = state["sync"]
            syncs = [stack.stack[n] for n in sync_names]

            inner_do_sync(syncs, sync_names)
        else:
            if CURRENT_BRANCH not in stack.stack:
                main_branch = get_real_stack_bottom()

                if CONFIG.change_to_main and main_branch is not None:
                    run(["git", "checkout", main_branch])
                    CURRENT_BRANCH = main_branch
                else:
                    die("Current branch {} is not in a stack", CURRENT_BRANCH)

            args.func(stack, args)

        # Success, delete the state file
        try:
            os.remove(STATE_FILE)
        except FileNotFoundError:
            pass
    except ExitException as e:
        error("{}", e.args[0])
        sys.exit(1)


if __name__ == "__main__":
    main()
