"""tools/fabric/lint_rules/base.py — the paths and shared words every rule module reaches: layout and workingcopy by path, the frontmatter and payload shapes, the git helpers.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os
import re
import sys

_spec = importlib.util.spec_from_file_location(
    "fabric_layout", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "layout.py"))
layout = importlib.util.module_from_spec(_spec)
_wc_spec = importlib.util.spec_from_file_location(
    "fabric_workingcopy", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "workingcopy.py"))
workingcopy = importlib.util.module_from_spec(_wc_spec)
_roots_spec = importlib.util.spec_from_file_location(
    "fabric_roots", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "roots.py"))
# By path, like layout: a directory on sys.path would let a fixture fabric answer for imports.
roots = importlib.util.module_from_spec(_roots_spec)
_spec.loader.exec_module(layout)
_wc_spec.loader.exec_module(workingcopy)
_roots_spec.loader.exec_module(roots)
# The one parse cache of the process, registered under the name the checkers in tools/fabric/ look it up by, so a rule here and
# a checker there share each module's tree. Loaded once: a second lint.py in one process (the tests) meets the first one's.
syntax_tree = sys.modules.get("fabric_syntax_tree")
if syntax_tree is None:
    _st_spec = importlib.util.spec_from_file_location(
        "fabric_syntax_tree", os.path.join(os.path.dirname(os.path.realpath(__file__)), "syntax_tree.py"))
    syntax_tree = sys.modules["fabric_syntax_tree"] = importlib.util.module_from_spec(_st_spec)
    _st_spec.loader.exec_module(syntax_tree)


def lint_environ() -> dict[str, str]:
    """The environment a rule hands roots: an exported operator still outranks
    the tree the lint was given, but AGENT_FABRIC_HOSTS_REGISTRY, a one-file
    override for the daemons, never changes what the lint reads."""
    return {k: v for k, v in os.environ.items() if k != roots.ENV_HOSTS_REGISTRY}


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


PAYLOAD_DIRS = frozenset({"skills", "commands"})


# sibling_working_copies moved to workingcopy.py (2026-09-18): the
# assembler needs the same reach for the hygiene lists.
sibling_working_copies = workingcopy.sibling_working_copies


def _git():
    """tools/fabric/git.py (ADR-040 §5 rule 6), loaded by path: lint runs
    as a script and as a module the tests load under another name."""
    spec = importlib.util.spec_from_file_location("fabric_git", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "git.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Each rule asks which files are tracked, about eleven times a lint. The answer is held only between begin_run() and end_run(),
# i.e. inside one lint.main(): a test that calls a rule directly on a tree it `git add`s between calls is outside any run and
# always gets git's current answer. (Keying on the root alone would not survive that; keying on the index's mtime would need
# the git dir resolved, which is the cost this saves.)
_run_tracked: dict[str, list[str]] | None = None


def begin_run() -> None:
    global _run_tracked
    _run_tracked = {}
    syntax_tree.clear()


def end_run() -> None:
    global _run_tracked
    _run_tracked = None
    syntax_tree.clear()


def _tracked(root: str) -> list[str]:
    if _run_tracked is not None and root in _run_tracked:
        return list(_run_tracked[root])   # a copy: a rule may sort or edit what it was handed
    r = _git().run(root, "ls-files", "-z", check=False, timeout=60)
    files = [f for f in r.stdout.split("\0") if f] if r.returncode == 0 else []
    if _run_tracked is not None:
        _run_tracked[root] = files
    return list(files)


def _not_ours(root: str) -> tuple[str, ...]:
    """The paths ruff.toml's `exclude` names: third-party or archived code
    the fabric does not rewrite (a vendored skill, the retired transport).
    One list, so a Python rule of lint cannot hold code to a standard ruff
    already exempts it from."""
    import tomllib
    try:
        with open(os.path.join(root, "ruff.toml"), "rb") as f:
            return tuple(e.rstrip("/") for e in tomllib.load(f).get("exclude", []))
    except (OSError, tomllib.TOMLDecodeError):
        return ()


def _is_under(rel: str, prefixes: tuple[str, ...]) -> bool:
    return any(rel == p or rel.startswith(p + "/") for p in prefixes)
