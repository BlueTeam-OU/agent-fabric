"""tools/fabric/github/common.py — what the GitHub tools share, kept where
one change reaches all: how a body is read from stdin, where a project's own
JSON config for a tool lives, and the project's environment names for the
fabric's settings (pr-tools.json). Nothing else is shared here on purpose:
the tools' messages, exit codes and exception classes differ, and unifying
them would change their output."""
from __future__ import annotations

import json
import os
import re
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


def project_config_path(setting: str, filename: str, subdir: str | None = "gh") -> str:
    """The file the environment variable `setting` names, else
    projects/<id>/integration/[<subdir>/]<filename> for the project the
    current working copy belongs to, else "" (the caller says which tool
    found no project). Unlike cli_root.project_config the file need not
    exist: the caller names a missing one in its own words."""
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
    if not pid:
        return ""
    return roots.project_integration(pid, subdir, filename) if subdir else roots.project_integration(pid, filename)


PR_TOOLS_SETTING = "AGENT_FABRIC_PR_TOOLS_CONFIG"
PR_TOOLS_KEYS = ("description", "env_aliases", "legacy_review_markers")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def apply_project_env(prog: str, environ: dict[str, str] | None = None) -> None:
    """Give the tool the project's own names for the fabric's settings, from
    projects/<id>/integration/pr-tools.json (AGENT_FABRIC_PR_TOOLS_CONFIG
    names another file): env_aliases maps a variable the project's callers
    set to the fabric's, used when the fabric's is unset or empty; and
    legacy_review_markers are the project's earlier review markers, the
    default of AGENT_FABRIC_LEGACY_REVIEW_MARKERS when that is unset or
    empty. A project with no such file gets neither. A file that exists and
    cannot be used stops the tool, exit 2: reading a mistyped one as "no
    aliases" would judge a review with markers the project did not mean.
    The forwarders under integration/gh/ did this in bash for every tool
    that had one; the bare commands do it here."""
    env = os.environ if environ is None else environ
    path = project_config_path(PR_TOOLS_SETTING, "pr-tools.json", subdir=None)
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise TypeError("not an object")
        unknown = sorted(set(doc) - set(PR_TOOLS_KEYS))
        if unknown:
            raise ValueError(f"unknown key(s) {', '.join(unknown)}; the keys are {', '.join(PR_TOOLS_KEYS)}")
        aliases = doc.get("env_aliases", {})
        if not isinstance(aliases, dict) or not all(
                isinstance(k, str) and isinstance(v, str) and ENV_NAME.fullmatch(k) and ENV_NAME.fullmatch(v)
                for k, v in aliases.items()):
            raise TypeError("env_aliases is not an object of variable names to variable names")
        markers = doc.get("legacy_review_markers", [])
        if not isinstance(markers, list) or not all(isinstance(m, str) and m and "\n" not in m for m in markers):
            raise TypeError("legacy_review_markers is not a list of one-line, non-empty strings")
    except (OSError, ValueError, TypeError) as e:
        print(f"{prog}: {path} is not a usable pr-tools.json ({type(e).__name__}: {e})", file=sys.stderr)
        raise SystemExit(2) from None
    for theirs, ours in aliases.items():
        if env.get(theirs) and not env.get(ours):
            env[ours] = env[theirs]
    if markers and not env.get("AGENT_FABRIC_LEGACY_REVIEW_MARKERS"):
        env["AGENT_FABRIC_LEGACY_REVIEW_MARKERS"] = "\n".join(markers)
