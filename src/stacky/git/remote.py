"""Remote and SSH operations for stacky."""

import os
import re
import subprocess
import time
from typing import Optional, Tuple

from stacky.utils.config import get_config
from stacky.utils.logging import die, error, info
from stacky.utils.shell import run, run_always_return
from stacky.utils.types import BranchName, CmdArgs, Commit, MAX_SSH_MUX_LIFETIME, STACK_BOTTOMS


def validate_local_remote(branch: BranchName, remote_config: Optional[str]):
    """Die if a non-bottom branch's tracking remote isn't the local sentinel `.`.

    stacky records stack parents via `branch.<X>.remote = "."` (local) plus
    `branch.<X>.merge = refs/heads/<parent>`. Any other value means the
    branch was configured by something other than stacky.
    """
    if branch in STACK_BOTTOMS:
        return
    if remote_config != ".":
        die("Misconfigured branch {}: remote {}", branch, remote_config)


def get_remote_info(branch: BranchName) -> Tuple[str, BranchName, Optional[Commit]]:
    """Get remote info for a branch: (remote, remote_branch, remote_branch_commit)."""
    if branch not in STACK_BOTTOMS:
        remote_config = run(CmdArgs(["git", "config", "branch.{}.remote".format(branch)]), check=False)
        validate_local_remote(branch, remote_config)

    # TODO(tudor): Maybe add a way to change these.
    remote = "origin"
    remote_branch = branch

    remote_commit = run(
        CmdArgs(["git", "rev-parse", "refs/remotes/{}/{}".format(remote, remote_branch)]),
        check=False,
    )

    commit = None
    if remote_commit is not None:
        commit = Commit(remote_commit)

    return (remote, BranchName(remote_branch), commit)


def get_remote_type(remote: str = "origin") -> Optional[str]:
    """Get the SSH host type for a remote."""
    out = run_always_return(CmdArgs(["git", "remote", "-v"]))
    for l in out.split("\n"):
        match = re.match(r"^{}\s+(?:ssh://)?([^/]*):(?!//).*\s+\(push\)$".format(remote), l)
        if match:
            sshish_host = match.group(1)
            return sshish_host

    return None


def gen_ssh_mux_cmd() -> list[str]:
    """Generate SSH multiplexing command arguments."""
    args = [
        "ssh",
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPersist={MAX_SSH_MUX_LIFETIME}",
        "-o",
        "ControlPath=~/.ssh/stacky-%C",
    ]
    return args


def start_muxed_ssh(remote: str = "origin"):
    """Start a multiplexed SSH connection."""
    if not get_config().share_ssh_session:
        return
    hostish = get_remote_type(remote)
    if hostish is not None:
        info("Creating a muxed ssh connection")
        cmd = gen_ssh_mux_cmd()
        os.environ["GIT_SSH_COMMAND"] = " ".join(cmd)
        cmd.append("-MNf")
        cmd.append(hostish)
        # We don't want to use the run() wrapper because
        # we don't want to wait for the process to finish

        p = subprocess.Popen(cmd, stderr=subprocess.PIPE)
        # Wait a little bit for the connection to establish
        # before carrying on
        while p.poll() is None:
            time.sleep(1)
        if p.returncode != 0:
            if p.stderr is not None:
                err = p.stderr.read()
            else:
                err = b"unknown"
            die(f"Failed to start ssh muxed connection, error was: {err.decode('utf-8').strip()}")


def stop_muxed_ssh(remote: str = "origin"):
    """Stop a multiplexed SSH connection."""
    if get_config().share_ssh_session:
        hostish = get_remote_type(remote)
        if hostish is not None:
            cmd = gen_ssh_mux_cmd()
            cmd.append("-O")
            cmd.append("exit")
            cmd.append(hostish)
            subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
