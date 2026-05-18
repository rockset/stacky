"""Logging and output utilities for stacky."""

import logging
import os
import sys

import colors  # type: ignore

_LOGGING_FORMAT = "%(asctime)s %(module)s %(levelname)s: %(message)s"

# Terminal state - can be modified by main()
COLOR_STDOUT: bool = os.isatty(1)
COLOR_STDERR: bool = os.isatty(2)
IS_TERMINAL: bool = os.isatty(1) and os.isatty(2)


def set_color_mode(mode: str):
    """Set color mode: 'always', 'auto', or 'never'."""
    global COLOR_STDOUT, COLOR_STDERR
    if mode == "always":
        COLOR_STDOUT = True
        COLOR_STDERR = True
    elif mode == "never":
        COLOR_STDOUT = False
        COLOR_STDERR = False
    # 'auto' keeps the default based on isatty


def fmt(s: str, *args, color: bool = False, fg=None, bg=None, style=None, **kwargs) -> str:
    """Format a string with optional color."""
    s = colors.color(s, fg=fg, bg=bg, style=style) if color else s
    return s.format(*args, **kwargs)


def cout(*args, **kwargs):
    """Write colored output to stdout."""
    return sys.stdout.write(fmt(*args, color=COLOR_STDOUT, **kwargs))


def _log(fn, *args, **kwargs):
    """Internal log helper."""
    return fn("%s", fmt(*args, color=COLOR_STDERR, **kwargs))


def debug(*args, **kwargs):
    """Log debug message."""
    return _log(logging.debug, *args, fg="green", **kwargs)


def info(*args, **kwargs):
    """Log info message."""
    return _log(logging.info, *args, fg="green", **kwargs)


def warning(*args, **kwargs):
    """Log warning message."""
    return _log(logging.warning, *args, fg="yellow", **kwargs)


def error(*args, **kwargs):
    """Log error message."""
    return _log(logging.error, *args, fg="red", **kwargs)


class ExitException(BaseException):
    """Exception raised when the program should exit."""
    def __init__(self, fmt, *args, **kwargs):
        super().__init__(fmt.format(*args, **kwargs))


def die(*args, **kwargs):
    """Exit with an error message. Stops SSH mux if active."""
    # Import here to avoid circular dependency
    from stacky.git.remote import stop_muxed_ssh
    # We are taking a wild guess at what is the remote ...
    stop_muxed_ssh()
    raise ExitException(*args, **kwargs)
