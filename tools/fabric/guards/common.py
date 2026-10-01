"""tools/fabric/guards/common.py — what the authority guards share (ADR-040
Wave 2). charter_authority.py and agent_fabric_dir_authority.py each keep
their own rules and their own contract; this holds the two things their bash
wrote twice, character for character, and the ways a guard ends.

WHY ONE SHARED MODULE AND TWO ENTRY POINTS, not one module with both. The
guards answer different questions (who opened the branch; what role the
commit declared), read different inputs and have different exit-code
contracts frozen in their own headers; merging them would put two contracts
in one header. What they share is small and was already identical: the base
ref's resolution (resolve_base), the role's name in policies/authority.json,
the way a list of paths is read from git's output, and the way a run ends.

RESOLVING THE BASE IS THE HARD PART IN CI, not locally. `actions/checkout`
defaults to depth 1 and, on a pull_request, checks out the MERGE ref -- so
there is no `origin/main` and no `HEAD^1` to diff against. The first
version assumed `origin/main` existed and exited 2 when it did not, which
failed the build for an environment limitation rather than a violation.

SIGPIPE stays ignored, as Python leaves it (never restore its default: the
default action skips `finally`). A closed stdout raises BrokenPipeError;
the run ends as a pipe-killed one does, quietly, 141.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402

DEFAULT_ROLE = "fabric-coordinator"


class Refused(Exception):
    """The guard could not examine what it guards. A guard fails closed: this
    is exit 2, never a pass."""


def say(text: str = "") -> None:
    print(text)


def err(text: str = "") -> None:
    print(text, file=sys.stderr)


def lines_of(text: str) -> list[str]:
    """What bash's `mapfile -t` makes of command output: split on newlines
    only (str.splitlines would split on \\x0b, \\x1c, U+2028 too), none for
    empty output."""
    if not text:
        return []
    parts = text.split("\n")
    if parts[-1] == "":
        parts.pop()
    return parts


def _resolves(repo: str, candidate: str) -> bool:
    return git.run(repo, "rev-parse", "--verify", "-q", candidate, check=False).returncode == 0


def resolve_base(repo: str, env: dict[str, str]) -> str | None:
    """The ref to diff against, or None. The candidates, in order: the
    caller's AGENT_FABRIC_CHARTER_BASE (both guards read it, the name is
    older than the second guard), origin/$GITHUB_BASE_REF, $GITHUB_BASE_REF,
    origin/main, main."""
    base_ref = env.get("GITHUB_BASE_REF", "")
    for candidate in (env.get("AGENT_FABRIC_CHARTER_BASE", ""), f"origin/{base_ref}", base_ref,
                      "origin/main", "main"):
        if not candidate or candidate == "origin/":
            continue
        if _resolves(repo, candidate):
            return candidate
    # Nothing local matched: fetch just the base tip. One shallow fetch, and
    # only on a pull_request where GITHUB_BASE_REF names the branch. A fetch
    # that fails or times out is "no base", as in the bash: the guard then
    # says, loudly, that it did not enforce.
    if base_ref:
        try:
            if git.run(repo, "fetch", "-q", "--depth=1", "origin", base_ref, check=False).returncode == 0:
                return "FETCH_HEAD"
        except git.GitError as e:
            if e.reason.startswith("no answer"):
                return None
            raise
    return None


def role_of(text: str) -> str | None:
    """role_definitions.role of a policies/authority.json's text: the
    committed name of the role that owns the definitions. None when the text
    is not JSON, has no such key, or names no role (empty, or not a string):
    the bash printed whatever it found, so an empty role became an
    `$agent == ""*` match for every agent."""
    try:
        role = json.loads(text)["role_definitions"]["role"]
    except (ValueError, KeyError, TypeError):
        return None
    return role if isinstance(role, str) and role else None


def run_main(name: str, body) -> int:
    """Run a guard's body. Refusals and git failures are exit 2, said on
    stderr under the guard's name; a vanished reader is 141."""
    sys.stdout.reconfigure(errors="surrogateescape")
    sys.stderr.reconfigure(errors="surrogateescape")
    try:
        return body()
    except (Refused, git.GitError) as e:
        err(f"{name}: {e}")
        return 2
    except BrokenPipeError:
        # The reader is gone; end as a pipe-killed run ends, with stdout on
        # /dev/null so the exit's own flush does not raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
