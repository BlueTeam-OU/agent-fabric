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
    current working copy belongs to (or that AGENT_FABRIC_PR_PROJECT
    names), else "" (the caller says which tool found no project). Unlike cli_root.project_config the file need not
    exist: the caller names a missing one in its own words."""
    explicit = os.environ.get(setting, "")
    if explicit:
        return explicit
    # Set, even empty, it is the project of the repository `fabric-pr --repo`
    # named: empty is a repository no project registers, which has no rules,
    # and is never given the cwd's.
    if PR_PROJECT_SETTING in os.environ:
        pid = os.environ[PR_PROJECT_SETTING]
    else:
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


PR_PROJECT_SETTING = "AGENT_FABRIC_PR_PROJECT"
_OWNER_NAME = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")


class NoRepository(Exception):
    pass


def resolve_repository(value: str) -> tuple[str, str]:
    """(owner/name, project id or "") for what `fabric-pr --repo` was given:
    an owner/name, matched to a project as arm_policy matches it (the
    registry's canonical remotes), or a project id or repository name
    (pr_counts.resolve_name, case-insensitive, an ambiguous name refused).
    An owner/name no project registers is that repository with no project."""
    import workingcopy
    from github import pr_counts
    if "/" in value:
        if not _OWNER_NAME.fullmatch(value):
            raise NoRepository(f"{value!r} is not <owner>/<name> or a project id")
        try:
            registry = workingcopy.load_registry()
        except (OSError, ValueError) as e:
            raise NoRepository(f"projects/registry.json cannot be read ({type(e).__name__}: {e})") from None
        return value, workingcopy.project_for_remote(f"https://github.com/{value}", registry) or ""
    try:
        return pr_counts.resolve_name(value, pr_counts.registry_projects())
    except pr_counts.Unreadable as e:
        raise NoRepository(str(e)) from None


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
    cannot be used stops the tool, exit 2, as does a file the setting names
    that does not exist: reading a mistyped one as "no
    aliases" would judge a review with markers the project did not mean.
    The forwarders under integration/gh/ did this in bash for every tool
    that had one; the bare commands do it here."""
    env = os.environ if environ is None else environ
    path = project_config_path(PR_TOOLS_SETTING, "pr-tools.json", subdir=None)
    if not path:
        return
    # A project without the file is a project without aliases; a setting that
    # names a missing file is a typo, and reading it as that would count
    # reviews with markers the project did not mean.
    if not os.path.exists(path) and not os.environ.get(PR_TOOLS_SETTING):
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
