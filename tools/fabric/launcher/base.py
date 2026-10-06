"""tools/fabric/launcher/base.py — the code's own paths and git, the bounds, the shared words, refusals and small helpers.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys


# One directory below launch.py: HERE is tools/fabric, as it was there.
HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


CODE_ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# By path, not on sys.path: routing.py is loaded from the fabric being
# launched, which in the suite is a fixture beside this code, and a
# directory on sys.path would answer for its imports.
git = _load("fabric_git", os.path.join(HERE, "git.py"))


# The launcher's shim by absolute path: every re-exec (launch.py's reexec) runs it again, and
# the fresh relaunch of a job changes directory first (ADR-022 rule 12),
# where a relative $0 — `agent-fabric/runtime/openrouter/launch` from
# projects/, as the README runs it — names nothing.
SELF = os.path.join(CODE_ROOT, "runtime", "openrouter", "launch")


FETCH_TIMEOUT_S = 20


ORI_AUTH_TIMEOUT_S = 60


CLAUDE_VERSION_TIMEOUT_S = 30


INSTALL_TIMEOUT_S = 300


HELPER_TIMEOUT_S = 120


# How long a launcher whose session was stopped for an upgrade waits for
# it before resuming on what is installed (AGENT_FABRIC_RESTART_WAIT_S
# overrides). It must exceed what the control agent does after the stop,
# the install and its read-back: runtime/control/tests/upgrade.test.mjs
# reads this line and checks it against POST_STOP_BUDGET_S.
RESTART_WAIT_S = 600


OPENING = ("Session start: arm your GZCoord inbox watch now, exactly as the session-start context's "
           "NO INBOX WATCH line gives it (with no such line, as the gzcoord-receive skill says); "
           "re-arm it at each expiry notice. Then wait for instructions.")


WAIT_TAIL = " Then wait for instructions."


BROKER_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS",
              "ANTHROPIC_MODEL", "CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT", "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
              "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK",
              "ENABLE_TOOL_SEARCH")


SETUP_TOKEN = re.compile(r"sk-ant-oat[0-9]+-[A-Za-z0-9_-]+")


PROMPT_FLAGS = ("--system-prompt", "--system-prompt-file", "--append-system-prompt", "--append-system-prompt-file")


# The options of claude's that take a value, for the opening scan (argv.wants_opening).
VALUE_OPTIONS = ("--model", "--effort", "--resume", "-r", "--permission-mode", "--session-id", "--add-dir",
                 "--settings", "--mcp-config", "--fallback-model", "--agents", "--allowedTools",
                 "--disallowedTools", "--output-format", "--input-format")


PATH_OPTIONS = ("--add-dir", "--mcp-config", "--settings")


class Refused(Exception):
    """A refusal: its message goes to stderr as `launch: <message>`, exit 1."""


def die(msg: str) -> "NoReturn":  # noqa: F821
    raise Refused(msg)


def say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def logical_cwd() -> str:
    """$PWD as bash has it: the inherited PWD when it names this directory,
    so a launch through a symlinked path names the path it was given."""
    p = os.environ.get("PWD", "")
    try:
        if os.path.isabs(p) and os.path.samefile(p, "."):
            return p
    except OSError:
        pass
    return os.getcwd()


def helper(args: list[str], *, env: dict | None = None, quiet: bool = False,
           timeout: float = HELPER_TIMEOUT_S) -> subprocess.CompletedProcess | None:
    """A helper's stdout with its trailing newlines stripped, as a command
    substitution has it; None when it could not run or ran out of time."""
    try:
        return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL if quiet else None, text=True,
                              errors="surrogateescape", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def stripped(r: subprocess.CompletedProcess | None) -> str:
    return r.stdout.rstrip("\n") if r is not None else ""


def env_with(**extra: str) -> dict:
    return {**os.environ, **extra}
