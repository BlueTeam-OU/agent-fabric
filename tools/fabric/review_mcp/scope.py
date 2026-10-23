"""What a review tool may touch and with what environment (agent-fabric ADR-065 §2 A, §5 rule 2).

Every field is data from a hostile source, so the checks here are the ones that do not depend on git reading it kindly: a leading
"-" is refused in every field before any argv exists; a revision becomes a commit id git itself resolved, and only that id is used
afterwards; a repository must be the session clone or one of its worktrees. The environment is the review guard's CLEAN_ENV, read
from the guard's text and never executed, plus the switches that stop git reading a config that names a program.
"""
from __future__ import annotations

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GUARD = os.path.join(ROOT, "runtime", "claude-code", "hooks", "review-bash-guard.py")
MAX_FIELD = 4096
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class ToolError(Exception):
    """A call the tool refuses or cannot do: one line for the model, a result with isError and never a protocol error."""


def clean_env_names(guard: str = GUARD) -> tuple[str, ...]:
    """CLEAN_ENV as the review guard assigns it (runtime/claude-code/hooks/review-bash-guard.py). The guard is a hook that runs on every
    command, not a module, so it is read as syntax: one list of secret-free names for the shell and for these tools, never two."""
    try:
        with open(guard, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError) as e:
        raise ToolError(f"the environment list of the review guard cannot be read ({guard}: {e}); no child is started") from None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CLEAN_ENV" for t in node.targets):
            try:
                names = ast.literal_eval(node.value)
            except ValueError:
                break
            if isinstance(names, tuple) and names and all(isinstance(n, str) for n in names):
                return names
    raise ToolError(f"CLEAN_ENV is not a tuple of names in {guard}; no child is started")


def clean_env(source: dict[str, str] | None = None, guard: str = GUARD) -> dict[str, str]:
    """The names of CLEAN_ENV that `source` (default: the process) sets, and nothing else."""
    source = os.environ if source is None else source
    return {n: source[n] for n in clean_env_names(guard) if n in source}


def git_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """CLEAN_ENV and the switches that keep git off every config but the repository's, and off a lock a read would take."""
    return {**clean_env(source), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0"}


def field(name: str, value: object, required: bool = True) -> str:
    """A text field of a call: a string, within MAX_FIELD, with no control character and no leading "-" (option injection:
    git takes an option wherever a word starts with one, and --end-of-options is not available to every verb)."""
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ToolError(f"{name} must be a string")
    if not value:
        if required:
            raise ToolError(f"{name} is required")
        return ""
    if len(value) > MAX_FIELD:
        raise ToolError(f"{name} is longer than {MAX_FIELD} characters")
    if value.startswith("-"):
        raise ToolError(f"{name} may not start with \"-\"")
    if re.search(r"[\x00-\x1f\x7f]", value):
        raise ToolError(f"{name} may not hold a control character")
    return value


def path_field(name: str, value: object, required: bool = True) -> str:
    """A path inside a commit: a field, not climbing out of the tree it is read from and not relative to the process's directory."""
    path = field(name, value, required)
    if path and (path.startswith("/") or path.startswith("./") or ".." in path.split("/")):
        raise ToolError(f"{name} must be a path inside the repository, without a leading / or ./ and without ..")
    return path


def pathspec_field(name: str, value: object) -> str:
    """A path or glob. A ":" first begins pathspec magic (":(attr:...)", ":(top)"), which is more than a path, so it is not accepted."""
    spec = path_field(name, value)
    if spec.startswith(":"):
        raise ToolError(f"{name} may not start with \":\" (pathspec magic)")
    return spec


def pathspecs_field(value: object) -> list[str]:
    if value is None:
        return []
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or len(items) > 64:
        raise ToolError("pathspec must be a string or a list of at most 64 strings")
    return [pathspec_field("pathspec", i) for i in items]


def whole(name: str, value: object, low: int, high: int, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ToolError(f"{name} must be a whole number from {low} to {high}")
    return value
