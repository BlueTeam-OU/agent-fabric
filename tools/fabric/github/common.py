"""tools/fabric/github/common.py — the two things the GitHub tools each
carried a copy of, kept where one change reaches all: how a body is read
from stdin, and where a project's own JSON config for a tool lives. Nothing
else is shared here on purpose: the tools' messages, exit codes and
exception classes differ, and unifying them would change their output."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import roots  # noqa: E402
from github import local  # noqa: E402


def read_body() -> str | None:
    """The body, read only once the arguments are known to need it: read
    first, `--help` or a usage error with an open stdin waited on it (the
    bash read it after parsing). Bytes, decoded here: invalid UTF-8 becomes
    U+FFFD, never a lone surrogate that JSON cannot carry to GitHub. None
    on a terminal: a person at a prompt is not a body."""
    return None if sys.stdin.isatty() else sys.stdin.buffer.read().decode("utf-8", "replace")


def project_config_path(setting: str, filename: str) -> str:
    """The file the environment variable `setting` names, else
    projects/<id>/integration/gh/<filename> for the project the current
    working copy belongs to, else "" (the caller says which tool found no
    project). Unlike cli_root.project_config the file need not exist: the
    caller names a missing one in its own words."""
    explicit = os.environ.get(setting, "")
    if explicit:
        return explicit
    top = local.toplevel()
    if not top:
        return ""
    try:
        import workingcopy
        pid = workingcopy.resolve(top).get("project")
    except (Exception, SystemExit):   # a marker naming nothing the registry knows exits
        pid = None
    return roots.project_integration(pid, "gh", filename) if pid else ""
