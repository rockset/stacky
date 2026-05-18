"""Shell execution utilities for stacky."""

import shlex
import subprocess
import sys
from typing import Optional

from stacky.utils.logging import debug, die
from stacky.utils.types import CmdArgs


def _check_returncode(sp: subprocess.CompletedProcess, cmd: CmdArgs):
    """Check the return code of a subprocess and die if non-zero."""
    rc = sp.returncode
    if rc == 0:
        return
    stderr = sp.stderr.decode("UTF-8")
    if rc < 0:
        die("Killed by signal {}: {}. Stderr was:\n{}", -rc, shlex.join(cmd), stderr)
    else:
        die("Exited with status {}: {}. Stderr was:\n{}", rc, shlex.join(cmd), stderr)


def run_multiline(cmd: CmdArgs, *, check: bool = True, null: bool = True, out: bool = False) -> Optional[str]:
    """Run a command and return its output (with newlines preserved)."""
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


def run_always_return(cmd: CmdArgs, **kwargs) -> str:
    """Run a command and always return output (asserts it's not None)."""
    out = run(cmd, **kwargs)
    assert out is not None
    return out


def run(cmd: CmdArgs, **kwargs) -> Optional[str]:
    """Run a command and return stripped output."""
    out = run_multiline(cmd, **kwargs)
    return None if out is None else out.strip()


def remove_prefix(s: str, prefix: str) -> str:
    """Remove a prefix from a string, dying if not present."""
    if not s.startswith(prefix):
        die('Invalid string "{}": expected prefix "{}"', s, prefix)
    return s[len(prefix):]
