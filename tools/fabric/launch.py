#!/usr/bin/env python3
"""tools/fabric/launch.py — launch this agent's Claude Code session through
OpenRouter (or plain claude), with the capability classes resolved from
agent-fabric's routing files (ADR-040 Wave 4; runtime/openrouter/launch is
its shim, and every caller — the README, moveto, fabric-fresh, the restart
below — keeps that path).

    runtime/openrouter/launch [claude args...]     # resolve, export, exec (broker)
    runtime/openrouter/launch --provider anthropic # the same, on plain claude
    runtime/openrouter/launch --print              # resolve and print; no exec

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      --print, anywhere: resolve and print, never start a session.
            --provider <p> | --provider=<p>, anywhere, p in openrouter
            (the default) | anthropic; any other value: exit 1. Both are
            the launcher's and are removed; every other argument passes
            through to claude in order, after the refusals below. There is
            no help text: --help and --version pass through to claude. A
            --help (or -h) before any `--` installs no agent files: a help
            read rewrote the account's for the launcher's default provider
            and the dispatch guard then refused reviews (2026-10-02).
  stdin     never read; the session inherits it.
  env       AGENT_FABRIC_ROOT (defaults to the repository this file is in),
            AGENT_FABRIC_STATE_DIR (identity.py), AGENT_FABRIC_ALLOW_STALE,
            AGENT_FABRIC_PULLED, AGENT_FABRIC_RESTART_WAIT_S,
            AGENT_FABRIC_FRESH_NOTE, AGENT_FABRIC_FRESH_JOB,
            AGENT_FABRIC_NO_OPENING, CLAUDE_CONFIG_DIR,
            CLAUDE_CODE_SUBAGENT_MODEL, CLAUDE_CODE_SUBAGENT_MODEL_FORCE,
            CLAUDE_CODE_EFFORT_LEVEL (refused when set), ANTHROPIC_* and the
            broker's tuning variables (cleared on the plain-claude path, see
            BROKER_ENV), OPENROUTER_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, TMPDIR,
            HOME, PATH, PWD (the launch directory, as the shell names it).
            Written into the session's environment: the alias pins, every
            AGENT_FABRIC_LAUNCH_* stamp, CLAUDE_CODE_DISABLE_TERMINAL_TITLE,
            TMPDIR.
  files     reads the settings scopes, ~/.config/agent-fabric/secrets.env,
            the agent's state directory (binding.json,
            model-profile.local.json, restart.json); writes
            $STATE_DIR/launch-prompt.md (launch_prompt.py),
            ${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json (onboarding, plain
            claude only), the agent files (install-agent-files.sh), and
            creates /var/tmp/agent-fabric-<agent>. Fast-forwards the fabric
            checkout and the launch working copy when they are behind.
  stdout    --print's report, byte for byte the bash's (compared for every
            role and both providers on the Wave 4 branch); otherwise
            nothing of the launcher's own.
  stderr    one `launch: …` line (or a few indented ones) per refusal,
            warning or notice; a module this file loads that crashes adds
            its traceback, as the bash's heredocs did.
  exit      0 after --print; 1 for every refusal; otherwise the session's
            own status, 128+n when a signal ended it; 127 when the shim
            finds no pinned interpreter. A relaunch (after a pull, an
            upgrade, a fresh job) re-executes the shim and its status is
            that run's.

Deliberate differences from the bash, each where it could only print a
traceback or hang: a settings file that is JSON but not an object is
skipped with one line instead of a traceback (it was never refused); an
unreadable ~/.claude.json is one line before the refusal; every subprocess
is bounded (ori auth 60 s, the harness's --version 30 s, the agent-file
install 300 s; a fetch was already 20 s), and a bound that is hit reads as
that call's failure, ori's as exit 124; every git call is bounded too, at
git.py's 120 s, the fabric's `pull --ff-only` included (a pull the bound
ends is said as a timeout, never as "cannot fast-forward"), and so are
the helpers (identity, routing, launch_prompt, jobs) at HELPER_TIMEOUT_S; a
closed stdout (`--print | head`) ends quietly with 141, as bash's SIGPIPE
did. The helper processes run on this interpreter (the fleet's pin),
where the bash ran whichever python3 PATH named. The session inherits
descriptors 0-2 only (close_fds): the bash passed it every descriptor
its caller left open, and no caller hands one on (fabric-lease closes its
lock's before the command; moveto's shell, the control agent and
fabric-fresh hold none), while a leaked pipe end would hold the caller's
pipeline open for the session's life. AGENT_FABRIC_RESTART_WAIT_S that
is not a number is said in one line before the resume is given up, where
the bash printed a traceback.

WHY THIS EXISTS. Launching is a decision no session can make for itself:
one launch decides the provider for EVERYTHING under it, subagents
included. Neither modelOverrides nor repo settings can do this:
modelOverrides is taken as the WHOLE MAP from the highest precedence
scope that sets it (so any scope both paths share binds both paths),
while ANTHROPIC_DEFAULT_*_MODEL are OVERRIDABLE process env — the
launcher exports them, `ori claude` carries them to every agent.

WHAT IT RESOLVES (tools/fabric/routing.py is the one implementation):
  capability class -> model     routing/capabilities.json (the provider's column)
                                <- routing/profiles.json defaults
                                <- roles.<role>        (the agent's binding)
                                <- agents.<login>      (the agent itself)
                                <- $STATE_DIR/model-profile.local.json (gitignored;
                                   bin/fabric-model writes it)
  model -> family shim          routing/shims.json
  class -> harness alias        runtime/claude-code/aliases.json
Every layer is per provider (providers.openrouter / providers.anthropic)
and speaks the CLASS — code-low, code-medium, code-high, code-plan,
code-review — and the provider's model id; the tier alias a class
rides is the adapter's (aliases.json), never a user's word. Each coding
class is exported as ANTHROPIC_DEFAULT_<ALIAS>_MODEL for the tier it
rides: on the broker <model@shim>, on plain claude the native pin (the
column's top-of-tier, or a layer's). The composite string exists only
here, in the child's environment.
Every class rides an alias: the Agent tool's `model` field accepts
only the tier aliases, so a "declared full id" in an agent file can
never be named by a dispatch (verified live 2026-09-13 — the reviewer
fell through to the opus alias and ran on GLM). The review class
rides `fable` with code-plan, and one alias carries one export, so it
is never exported: its model is written into the reviewer's agent file
for this launch's provider (install-agent-files.sh, below) and the
dispatch guard drops the dispatch's alias so the file decides. The
review gate guards that model.

WHO IS LAUNCHING. The agent is the Linux login (runtime/identity.py);
the role comes from that agent's runtime binding, written from a login
shell by bin/fabric-role (tools/fabric/role.py) — never from inside a
session. The launch DIRECTORY decides which settings scopes are fenced
and which working copy the child starts in; it never decides who the
agent is.

THE ROLE RIDES IN THE SYSTEM PROMPT. tools/fabric/launch_prompt.py
renders, for the bound role, the identity header, the charter, the
brief and the shared team/memory sections into $STATE_DIR/launch-
prompt.md, and every exec below passes it as --append-system-prompt-file
(read back live on both paths, print and interactive:
docs/live-checks/2026-09-15-append-system-prompt.md). The session holds
its role from its first request, through every compaction, and cannot
edit it; the old /role command asked the model to Read a charter after
the fact. The project layer (the remit, the INDEX) is NOT in that file —
it follows the cwd and reaches the session from the SessionStart hook.
The role, and the prompt's sha256, are stamped into the child's
environment (AGENT_FABRIC_LAUNCH_ROLE, _PROMPT_DIGEST) so fabric-status
can say what this session was launched as and see a rebind under it.
The launcher announces nothing: whether a session is running is the
control plane's to answer, from the process table (runtime/control/
presence.mjs, docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md) — HELLO/GOODBYE are retired.

The merged REVIEW model MUST be in routing/policies/review-grade.json:
a review's failure mode is a green PR that merges, so the reviewer's
model is never a cost cut. Lint enforces this on the committed files;
the launcher enforces it again on the MERGED result, because the local
override layer is where a cheap-reviewer experiment would sneak in.
The coding classes are not gated.

REFUSES, fail-closed, before spawning anything:
  - no runtime binding for this agent      -> "bin/fabric-role bind first"
  - pass-through args carrying --system-prompt, --system-prompt-file,
    --append-system-prompt or --append-system-prompt-file: the role's
    prompt is the launcher's, and claude refuses two of them anyway
  - routing/capabilities.json missing
  - merged review model not review-grade
  - pass-through args carrying --settings or --setting-sources
    (ori's own provider fence uses --settings; a caller's one would
    override it and the session could silently leave OpenRouter)
  - any settings scope (the managed-policy file, ~/.claude/settings.json,
    ~/.claude/settings.local.json, $CLAUDE_CONFIG_DIR/settings.json, the
    launch working copy's and $PWD's .claude/settings{,.local}.json)
    carrying a model pin — env.ANTHROPIC_*, env.CLAUDE_CODE_SUBAGENT_MODEL,
    modelOverrides — or an EFFORT pin: effortLevel, maxEffortLevel,
    modelSettings, env.CLAUDE_CODE_EFFORT_LEVEL; or
    CLAUDE_CODE_SUBAGENT_MODEL or CLAUDE_CODE_EFFORT_LEVEL (set to
    anything, the empty string included) in the caller's environment
    (a settings-scope pin outranks the profile's exports; the subagent
    variable overrides every dispatch's model, and the effort variable
    outranks every agent file's effort: in every subagent at once)
  - a merged model that is not a model id (a local override of null, a
    number, "" or prose)
  - ori not authenticated, or authenticated from anything but the
    environment (`ori auth --json`: authenticated AND source.kind ==
    environment, exit 0)

NEVER: CLAUDE_CODE_SUBAGENT_MODEL_FORCE. It discards every dispatch's
own model and forces the parent's; capability classes would stop
meaning anything.

CREDENTIAL: an OpenRouter API key per agent account, as
OPENROUTER_API_KEY in that account's environment — exported by
~/.config/agent-fabric/secrets.env, which `fabric-secrets sync` writes
from the account's own store (runtime/provisioning/README.md,
"Secrets"; ADR-038) — never in the repo.

The environment is handled as the bash's shell environment was: this
process's os.environ IS what the session and every helper inherit, set and
cleared in the bash's order, so a helper sees exactly what it saw there.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
import traceback
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.realpath(__file__))
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

# This file's shim by absolute path: every re-exec below runs it again, and
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
# The options of claude's that take a value, for the opening scan below.
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


# ── argv ────────────────────────────────────────────────────────────────
# --print may sit anywhere in the arguments; as $1 only, `launch --verbose
# --print` passed it through to claude and exec'd a real session.
# --provider openrouter (default) | anthropic: the same resolution and the
# same refusals, then `ori claude` with every class exported as a
# composite, or plain `claude` with only the tier aliases the profile
# binds exported — an alias nothing binds is left to the harness, and the
# review pin goes through the agent file. Either way the session is the
# fabric's: bound role, gated review model, no pin outside the profile.
def parse_argv(argv: list[str]) -> tuple[bool, str, list[str]]:
    print_only, provider, args, prev = False, "openrouter", [], ""
    for arg in argv:
        if arg == "--print":
            print_only = True
        elif prev == "--provider":
            provider = arg
        elif arg.startswith("--provider="):
            provider = arg[len("--provider="):]
        elif arg == "--provider":
            pass
        else:
            args.append(arg)
        prev = arg
    return print_only, provider, args


# ── the fabric itself must be current ───────────────────────────────
# A session is fixed at exec: it runs on the launcher, hooks, prompt
# sections and routing of the checkout it was launched from. "Pull, then
# relaunch" was the rule, and moveto pulls on entry — but an account
# that keeps its moveto shell open for a day relaunches from it without
# a pull, and on 2026-09-16 two accounts came back on the previous
# launcher (no GOODBYE, two HELLOs) after a DECISION told everyone to
# pull. So the launcher checks: a fetch, and a checkout behind
# origin/main is PULLED — fast-forward only; every role but the
# coordinator is read-only here, so there is nothing local to lose, and
# --ff-only refuses on its own if the checkout ever diverged — and the
# launcher re-executes itself so the session runs on what was pulled
# (the code under a running launcher must not change).
# It was a refusal naming the pull command until the CEO asked, the same
# day, why the person had to type what the launcher already knew. A pull
# that cannot fast-forward is refused with the reason; offline (the fetch
# fails) it launches on what is checked out and says so.
# AGENT_FABRIC_ALLOW_STALE=1 overrides, loudly, for the case where the
# push itself is what a session is about to do.
def git_status_ok(repo: str, *args: str, timeout: float = git.TIMEOUT_S) -> bool:
    try:
        return git.run(repo, *args, check=False, timeout=timeout).returncode == 0
    except git.GitError:
        return False


def git_text(repo: str, *args: str) -> str | None:
    try:
        r = git.run(repo, *args, check=False)
    except git.GitError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def behind_count(repo: str, rng: str) -> int:
    try:
        return int(git_text(repo, "rev-list", "--count", rng) or 0)
    except ValueError:
        return 0


def pull_ff(repo: str) -> str:
    """"ok", "failed" (it could not fast-forward) or "timeout": a pull the
    bound ended is a different cause, said differently."""
    try:
        r = git.run(repo, "pull", "-q", "--ff-only", "origin", "main", check=False)
    except git.GitError as exc:
        return "timeout" if "no answer within" in exc.reason else "failed"
    return "ok" if r.returncode == 0 else "failed"


def keep_fabric_current(fabric_root: str, orig_args: list[str]) -> None:
    if not (git_status_ok(fabric_root, "rev-parse", "--is-inside-work-tree")
            and git_status_ok(fabric_root, "remote", "get-url", "origin")):
        return
    if not git_status_ok(fabric_root, "fetch", "-q", "origin", "main", timeout=FETCH_TIMEOUT_S):
        say(f"launch: could not fetch origin/main for {fabric_root} (offline?); launching on what is checked out.")
        return
    behind = behind_count(fabric_root, "HEAD..origin/main")
    if behind <= 0:
        return
    if os.environ.get("AGENT_FABRIC_ALLOW_STALE") == "1":
        say(f"launch: WARNING — agent-fabric is {behind} commit(s) behind origin/main; launching anyway (AGENT_FABRIC_ALLOW_STALE=1).")
    elif os.environ.get("AGENT_FABRIC_PULLED") == "1":
        die(f"agent-fabric at {fabric_root} is still {behind} commit(s) behind origin/main after a pull; not relaunching again.\n"
            f"  Look at the checkout: git -C \"{fabric_root}\" status")
    elif (pulled := pull_ff(fabric_root)) == "timeout":
        die(f"agent-fabric at {fabric_root}: git pull did not answer within {git.TIMEOUT_S:g} s; nothing was "
            "relaunched.\n"
            "  A pull ended by the bound may leave .git/index.lock behind. Look:\n"
            f"    git -C \"{fabric_root}\" status\n"
            "  and relaunch once origin is reachable.")
    elif pulled == "ok":
        head = git_text(fabric_root, "rev-parse", "--short", "HEAD") or ""
        say(f"launch: agent-fabric was {behind} commit(s) behind origin/main; pulled to {head} and relaunching on it.")
        reexec(env_with(AGENT_FABRIC_PULLED="1"), orig_args)
    else:
        die(f"agent-fabric at {fabric_root} is {behind} commit(s) behind origin/main and cannot fast-forward\n"
            "  (local commits or changes on this checkout). A session runs on the launcher,\n"
            "  hooks, prompt and routing of this checkout, so it must be current. Look:\n"
            f"    git -C \"{fabric_root}\" status\n"
            "  and bring it to origin/main, then relaunch.")


# ── the working copy the session starts in ──────────────────────────
# Its CLAUDE.md and rules are binding the moment the session loads them,
# and a clone left on a week-old main gave a session instructions its
# project had already replaced (a retired review flow, followed live on
# a managed project's PR). The same fetch as above, but this checkout is the
# session's own work, never the launcher's to refuse: on the default
# branch with nothing uncommitted it is fast-forwarded; on any other
# branch, or with changes, it is left alone and the gap is said, here
# and again to the session by the SessionStart hook.
def keep_working_copy_current(wc: str, fabric_root: str) -> None:
    if not wc or os.path.realpath(wc) == os.path.realpath(fabric_root):
        return
    if not git_status_ok(wc, "remote", "get-url", "origin"):
        return
    default = git_text(wc, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD") or "origin/main"
    default = default[len("origin/"):] if default.startswith("origin/") else default
    if not git_status_ok(wc, "fetch", "-q", "origin", default, timeout=FETCH_TIMEOUT_S):
        say(f"launch: could not fetch origin/{default} for {wc} (offline?); its CLAUDE.md is what is checked out.")
        return
    behind = behind_count(wc, f"HEAD..origin/{default}")
    if behind <= 0:
        return
    branch = git_text(wc, "symbolic-ref", "-q", "--short", "HEAD") or "(detached)"
    if (branch == default and git_status_ok(wc, "diff", "--quiet")
            and git_status_ok(wc, "diff", "--cached", "--quiet")
            and git_status_ok(wc, "merge", "-q", "--ff-only", f"origin/{default}")):
        head = git_text(wc, "rev-parse", "--short", "HEAD") or ""
        say(f"launch: {wc} was {behind} commit(s) behind origin/{default}; fast-forwarded to {head}.")
    else:
        say(f"launch: WARNING — {wc} ({branch}) lacks {behind} commit(s) of origin/{default}; "
            "its CLAUDE.md and rules may be older than the project's. Nothing was changed.")


def refuse_passthrough(args: list[str]) -> None:
    """Pass-through args must not be able to fence ori out of OpenRouter."""
    for arg in args:
        if arg == "--settings" or arg.startswith("--settings="):
            die("passing --settings would disable ori's provider fence (its own\n"
                "  --settings carries apiKeyHelper and blanks every other provider\n"
                "  variable). Launch without it; per-session settings go through the\n"
                "  profile layers, not the CLI.")
        if arg == "--setting-sources" or arg.startswith("--setting-sources="):
            die("passing --setting-sources would disable ori's provider fence.")
        # The role reaches the session through the launcher's own
        # --append-system-prompt-file; a caller's --system-prompt* would replace
        # or shadow it (and claude itself refuses --append-system-prompt beside
        # the -file form). Nothing a session needs is passed this way.
        name = arg.split("=", 1)[0]
        if name in PROMPT_FLAGS:
            die(f"passing {name} is refused: the role's system prompt is the\n"
                "  launcher's (tools/fabric/launch_prompt.py -> --append-system-prompt-file,\n"
                "  or --system-prompt-file for a locale that carries the harness text);\n"
                "  a second one would replace or shadow it.")


# A settings-scope pin outranks the profile's exports (ori composes the
# child env as settings-env-first for the four alias keys; Claude Code
# merges every scope's env block into the process, local > project >
# user), so the launcher refuses rather than race — in EVERY scope. The
# predicate: env.ANTHROPIC_* (not only _DEFAULT_ — ANTHROPIC_MODEL is a
# pin too), env.CLAUDE_CODE_SUBAGENT_MODEL, modelOverrides. NOT a top-
# level `model`: that is the session default, which the explicit
# `--model <session>` this launcher passes outranks. An unreadable file
# is not evidence of pins. $PWD's .claude/ is scanned as well when the
# launch directory is not the toplevel, and the managed-policy file
# (root-owned; outranks every other scope) — a missing file is skipped.
def settings_scopes(home: str, cwd: str) -> list[str]:
    # Derived from the launch directory ONLY — never inherited. The scopes this
    # fence inspects must be the scopes the child loads, and the child starts
    # in $PWD: an inherited REPO_ROOT pointing at another clone let the fence
    # pass on that clone's clean .claude/ while exec'ing in this one, pinned
    # (a review finding on a managed project's PR #679, judged CONFIRMED).
    repo_root = toplevel(cwd) or cwd
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
    return ["/etc/claude-code/managed-settings.json",
            f"{home}/.claude/settings.json", f"{home}/.claude/settings.local.json",
            f"{config_dir}/settings.json" if config_dir else "",
            f"{repo_root}/.claude/settings.json", f"{repo_root}/.claude/settings.local.json",
            f"{cwd}/.claude/settings.json", f"{cwd}/.claude/settings.local.json"]


def settings_pins(path: str) -> list[str] | None:
    """The pins a settings file carries; None for a file that is JSON but
    not an object (the bash crashed there and the launch went on)."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh) or {}
    except Exception:
        return []
    if not isinstance(d, dict):
        return None
    bad = []
    env = d.get("env") or {}
    if isinstance(env, dict):
        # env.CLAUDE_CODE_EFFORT_LEVEL is merged into the CHILD by the harness,
        # so a settings scope carrying it walks straight past the process-env
        # refusal below — the scan and that refusal have to name the same
        # variables or neither is a fence (review of 2026-09-23, F1).
        bad += sorted("env." + k for k in env
                      if k.startswith("ANTHROPIC_")
                      or k in ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
                               "CLAUDE_CODE_EFFORT_LEVEL"))
    if "modelOverrides" in d:
        bad.append("modelOverrides")
    # Only `maxEffortLevel` here, and NOT effortLevel/modelSettings, which the
    # committed-scope guard still refuses. Two reasons, both measured:
    #   - precedence. `--effort` (turnEffort) is resolved BEFORE the configured
    #     level that effortLevel and modelSettings feed, so the launcher's own
    #     flag already outranks them. maxEffortLevel is different in kind: it
    #     is a CAP, and the LOWEST value across all scopes wins, so nothing the
    #     launcher passes can raise it back.
    #   - the harness writes modelSettings itself. `/effort` persists
    #     `modelSettings.<model>.effortLevel` into ~/.claude/settings.json
    #     ("saved as your default for new sessions"), so refusing it here would
    #     stop a launch on every account that has ever used the command — found
    #     when this fence refused its own author's account.
    # A COMMITTED scope is different: nothing should pin anything there and no
    # harness writes to it, so all four stay refused in
    # policies/check_repo_settings_carry_no_model_pins.sh.
    bad += [k for k in ("maxEffortLevel",) if k in d]
    return bad


def refuse_pins(scopes: list[str], local_override: str) -> None:
    for f in scopes:
        if not f or not os.path.isfile(f):
            continue
        pins = settings_pins(f)
        if pins is None:
            say(f"launch: {f} is not a JSON object; not read for model pins.")
        elif pins:
            die(f"{f} carries model pins ({' '.join(pins)}), which would silently outrank the profile. "
                f"Remove them; per-agent tiers go through {local_override}.")
    if os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL"):
        die("CLAUDE_CODE_SUBAGENT_MODEL is set in the environment; it overrides every subagent's model "
            "regardless of the review gate. Unset it.")
    if os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE"):
        die("CLAUDE_CODE_SUBAGENT_MODEL_FORCE is set; it discards every dispatch's own model. Unset it.")
    # Same bug class as the two above, for the other routed dimension. Read
    # out of 2.1.280: this variable outranks --effort, /effort AND an agent
    # file's effort:, and process environment reaches every subagent — so one
    # value here flattens every per-class level the fabric writes. `unset` and
    # `auto` are not neutral: both mean "ignore the configured level and use
    # the model's own default", which defeats the routing just as thoroughly
    # (docs/live-checks/2026-09-23-effort-registry.md).
    # Presence, not emptiness: an EXPORTED-but-empty value is still set, and
    # the harness reads the variable rather than testing it for emptiness.
    # "For any value" has to include the empty one (review of 2026-09-23).
    if "CLAUDE_CODE_EFFORT_LEVEL" in os.environ:
        die(f"CLAUDE_CODE_EFFORT_LEVEL is set to '{os.environ['CLAUDE_CODE_EFFORT_LEVEL']}'; it outranks every "
            "per-class effort the fabric writes, in every subagent. Unset it (routing/effort.json is where a "
            "level is decided).")


# ── resolve ─────────────────────────────────────────────────────────
class ResolveError(Exception):
    """What the bash's resolver heredoc said with sys.exit(<message>)."""


def load_routing(routing_path: str, fabric_root: str):
    """routing.py from the fabric being launched, imported as the bash's
    heredoc did with AGENT_FABRIC_ROOT set to it — routing reads its root
    once, at import — and without leaving that variable in the session's
    environment when the caller did not set it."""
    saved = os.environ.get("AGENT_FABRIC_ROOT")
    os.environ["AGENT_FABRIC_ROOT"] = fabric_root
    try:
        return _load("fabric_routing", routing_path)
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_ROOT", None)
        else:
            os.environ["AGENT_FABRIC_ROOT"] = saved


def resolve(routing, aliases_path: str, local_path: str, role: str, agent: str, provider: str) -> dict:
    local = {}
    if os.path.exists(local_path):
        with open(local_path) as fh:
            local = json.load(fh)
        if not isinstance(local, dict):
            raise ResolveError("model-profile.local.json is %s, not an object" % type(local).__name__)
    with open(aliases_path) as fh:
        aliases = json.load(fh)
    # Every merged value must be a model reference in its provider's
    # vocabulary: the committed files are linted, the local layer is not, and
    # a null/number/""/prose there once passed the emptiness checks as the
    # string "None" and reached `--model`. normalize_layer names the field.
    try:
        routing.normalize_layer(local, "local")
        out = {"role": role, "agent": agent, "provider": provider, "exports": {}, "classes": {}, "files": {}}
        for klass in aliases["aliases"]:
            res = routing.resolve(klass, provider, role, agent, local)
            # via "harness" is the tier's alias, the harness's own choice; anything
            # pinned must be a model reference the provider's adapter accepts.
            if res["via"] != "harness" and not routing.ADAPTERS[provider].is_runtime(res["composite"]):
                raise ResolveError("resolved %s is %r, not a model reference the %s adapter accepts"
                                   % (klass, res["composite"], provider))
            out["classes"][klass] = res
            # A file-pinned class (the review class) is never exported: its
            # alias is also code-plan's, and through the export the reviewer
            # would follow code-plan (as it once followed code-high on opus).
            # Its model reaches its agent file — install-agent-files.sh, run
            # below for this provider — and the dispatch guard drops the
            # dispatch's alias under a fabric launch so the file decides.
            if res["via"] == "file":
                out["files"][klass] = res["composite"]
        # Every other class rides its alias's ANTHROPIC_DEFAULT_*_MODEL: on
        # the broker the composite, on plain claude the native pin (a class
        # the column leaves null is the harness's and exports nothing).
        for var, entry in routing.exports(provider, role, agent, local).items():
            out["exports"][var] = entry["model"]
        session = routing.resolve_session(role, agent, local, provider=provider)
    except (KeyError, ValueError) as exc:
        raise ResolveError("merged profile: %s" % exc) from None
    out["session"] = session
    grade = routing.load_review_grade()
    review = out["classes"].get(grade.get("capability", "code-review"))
    if review and not routing.review_grade_ok(review["model"]):
        out["review_violation"] = review["model"]
    # Through JSON and back, as the bash's resolution reached every later
    # step: what the report prints is the serialised value, never a tuple.
    return json.loads(json.dumps(out))


def resolve_or_die(*a) -> dict:
    try:
        return resolve(*a)
    except ResolveError as exc:
        say(str(exc))
    except Exception:
        traceback.print_exc()
    die("could not resolve the profile (see the message above).")


def is_broker_url(url: str) -> bool:
    try:
        h = urlsplit(url).hostname or ""
    except ValueError:
        h = ""
    return h == "openrouter.ai" or h.endswith(".openrouter.ai")


# PLAIN CLAUDE MEANS ANTHROPIC DIRECT, and it carries nothing the broker
# set for its own model. `ori claude` builds its child's environment in one
# function (read out of the ori binary, `rIa`), and a launch started from
# inside such a session inherits all of it:
#   pointing and credentials, forced: ANTHROPIC_BASE_URL=https://openrouter.ai/api,
#     ANTHROPIC_AUTH_TOKEN="" (present, EMPTY), ANTHROPIC_API_KEY=<the account's
#     OpenRouter key>, OPENROUTER_API_KEY=<the same key>, ANTHROPIC_MODEL=<its
#     model>, and sometimes ANTHROPIC_CUSTOM_HEADERS;
#   tuning for the BROKER'S model: CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1,
#     CLAUDE_CODE_MAX_CONTEXT_TOKENS, CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY,
#     CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK, ENABLE_TOOL_SEARCH;
#   privacy opt-outs: DISABLE_TELEMETRY=1, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1,
#     DISABLE_GROWTHBOOK, CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF;
#   and more this was NOT enumerated for: a helper (`tIa`) and two computed
#     names. Nothing below claims to clear "everything ori set".
#
# History, because the next change here must not repeat it (review of #31,
# three rounds). Nothing cleared: the child ran and billed on the broker
# while stamped "anthropic". Then the URL alone: the key stayed, and the
# child would have sent the account's OpenRouter SECRET to
# api.anthropic.com. Then the credentials: the broker's system-prompt and
# context-cap tuning still followed onto an Anthropic session.
#
# So, when the base URL names OpenRouter (the host test model-audit.sh
# classifies a session by), the pointing, the credentials and the model
# tuning go. The privacy opt-outs STAY: clearing them could switch
# telemetry back on against a person's own choice, and leaving them costs
# nothing. OPENROUTER_API_KEY stays: it is the account's own (secrets.env)
# and the broker path needs it. A base URL naming anything else is someone's
# deliberate choice, unreviewed, and is left exactly as it was. What is
# dropped is said once on stderr — names, never values.
def drop_broker_env() -> None:
    env = os.environ
    dropped = []
    if env.get("ANTHROPIC_BASE_URL") and is_broker_url(env["ANTHROPIC_BASE_URL"]):
        for v in BROKER_ENV:
            if v in env:
                dropped.append(v)
                del env[v]
    # And the SECRET, independently of the base URL: an ANTHROPIC_API_KEY that
    # is the OpenRouter key — equal to OPENROUTER_API_KEY, or shaped like one
    # (sk-or-) — is never an Anthropic credential, whatever else the
    # environment says, so it never reaches a plain-claude child. Precise on
    # purpose: a real Anthropic key (sk-ant-) is not touched.
    key = env.get("ANTHROPIC_API_KEY", "")
    if key and (key.startswith("sk-or-") or (env.get("OPENROUTER_API_KEY") and key == env["OPENROUTER_API_KEY"])):
        dropped.append("ANTHROPIC_API_KEY")
        del env["ANTHROPIC_API_KEY"]
    if dropped:
        say("launch: plain claude goes to Anthropic direct — dropped what a broker session left in this "
            "environment: " + " ".join(dropped))


def synced_oauth_token(home: str) -> str:
    try:
        with open(f"{home}/.config/agent-fabric/secrets.env", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("export CLAUDE_CODE_OAUTH_TOKEN="):
                    return shlex.split(line[len("export "):])[0].split("=", 1)[1].rstrip("\n")
    except (OSError, ValueError, IndexError):
        pass
    return ""


# The other way round: a login moved to a Claude-account template carries
# CLAUDE_CODE_OAUTH_TOKEN in every shell (fabric-secrets sync), and a broker
# session must never hold it — whichever credential the harness prefers
# with a base URL set, an Anthropic subscription token has no business in
# a process whose requests go to a third party (review of #33). Dropped
# unconditionally on the broker path, by name.
# Which Claude account a plain-claude session runs on is the login's synced
# record, not the shell this launcher inherited: a shell opened before
# `fabric-accounts assign` moved the login still holds the old token (or
# none), and a relaunch from it — including the upgrade's automatic resume
# — would start on the old account (2026-09-25, devex-tooling). Read from
# ~/.config/agent-fabric/secrets.env at every launch; absent there, an
# inherited one is dropped. Said by name when it replaces or drops one.
def settle_oauth_token(provider: str, home: str) -> None:
    env = os.environ
    if provider == "anthropic":
        synced = synced_oauth_token(home)
        if synced:
            if env.get("CLAUDE_CODE_OAUTH_TOKEN") and env["CLAUDE_CODE_OAUTH_TOKEN"] != synced:
                say("launch: CLAUDE_CODE_OAUTH_TOKEN taken from the login's synced record, not the older one "
                    "this shell inherited")
            env["CLAUDE_CODE_OAUTH_TOKEN"] = synced
        elif "CLAUDE_CODE_OAUTH_TOKEN" in env:
            del env["CLAUDE_CODE_OAUTH_TOKEN"]
            say("launch: dropped the CLAUDE_CODE_OAUTH_TOKEN this shell inherited — the login's synced record "
                "has none")
    elif "CLAUDE_CODE_OAUTH_TOKEN" in env:
        del env["CLAUDE_CODE_OAUTH_TOKEN"]
        say("launch: the broker path — dropped CLAUDE_CODE_OAUTH_TOKEN (a Claude-account template's token "
            "never reaches a broker session)")


# ── the pins ─────────────────────────────────────────────────────────
# Every alias variable starts EMPTY, then only the resolved ones are set.
# A class whose column is null rides the harness's own tier, which means
# NO export — and a launch started from inside another fabric session
# arrived carrying that session's export for the alias, silently pinning
# the tier to the parent's model (review of #31). The four names are the
# adapter's (runtime/claude-code/aliases.json), read, never repeated here.
def set_pins(aliases_path: str, exports: dict) -> None:
    with open(aliases_path) as fh:
        for name in json.load(fh)["env"].values():
            if name:
                os.environ.pop(name, None)
    for name, value in sorted(exports.items()):
        if name:
            os.environ[name] = value


# Auth: ori must be working from the environment BEFORE we exec, because a
# prompt at this point would come after we already exported the pins.
# The check is a CONJUNCTION on the documented shape — {"ok":true,"data":
# {"authenticated":true,"source":{"kind":"environment",...}}} — and keeps
# ori's exit status. Plain claude carries its own login; nothing to check.
def ori_auth_ok(text: str) -> bool:
    try:
        d = json.loads(text or "{}")
    except Exception:
        return False
    if not isinstance(d, dict):
        return False
    data = d.get("data") if isinstance(d.get("data"), dict) else d
    src = data.get("source") if isinstance(data.get("source"), dict) else {}
    return data.get("authenticated") is True and src.get("kind") == "environment"


def check_ori_auth() -> None:
    try:
        r = subprocess.run(["ori", "auth", "--json"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, errors="surrogateescape",
                           timeout=ORI_AUTH_TIMEOUT_S)
        rc, text = r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        rc, text = 124, ""
    except OSError:
        rc, text = 127, ""
    if rc != 0 or not ori_auth_ok(text):
        die(f"ori is not authenticated from the environment (ori auth exit {rc}). This account needs "
            "OPENROUTER_API_KEY in its environment (~/.config/agent-fabric/secrets.env via fabric-secrets sync) "
            "— a stored `ori login` credential is deliberately not accepted, because per-agent spend follows "
            "the key (ori auth --json to inspect).")


def caller_value(args: list[str], flag: str) -> tuple[str | None, bool, bool]:
    """What the caller passed for `flag` (spaced or `=`), whether they
    passed it at all, and whether the last argument is the bare flag."""
    value, given, prev = None, False, ""
    for arg in args:
        if prev == flag:
            value, given = arg, True
        if arg.startswith(flag + "="):
            value, given = arg[len(flag) + 1:], True
        prev = arg
    trailing = prev == flag
    return value, given or trailing, trailing


def effort_for(args: list[str], routed: str) -> tuple[str, bool]:
    """The session's effort and whether the caller decided it: the caller's
    own --effort wins over the routed level."""
    value, given, trailing = caller_value(args, "--effort")
    if trailing:
        # A TRAILING `--effort` with no value never entered the scan as a value,
        # so the launcher appended its own and the child saw
        # `--effort --effort <level>` — claude would read "--effort" as the level.
        # The caller meant to pass one; let their (malformed) flag stand and let
        # claude report it, rather than adding a second — and stamp nothing.
        return "", True
    return (value if value is not None else routed), given


def require_files(*paths: str) -> None:
    for path in paths:
        if not os.path.isfile(path):
            die(f"{path} is missing.")


def toplevel(cwd: str) -> str:
    """The launch directory's repository, or "" when it is in none."""
    try:
        return git.toplevel(cwd) or ""
    except git.GitError:
        return ""


def make_tmpdir(path: str, *, ours: bool = True) -> None:
    """mkdir -p -m 700: the mode on the directory made, whatever the umask;
    one that exists is left as it is, if it is this account's own directory.
    /var/tmp is world-writable and sticky: another account can make
    /var/tmp/agent-fabric-<agent> first, or a symlink by that name, and the
    session would write its scratch where that account reads it and this one
    cannot remove it. The bash's mkdir -p took either (review of #80); the
    launch is refused instead, naming the path, so the person moves it. A
    TMPDIR the account set itself (`ours` false) is its own choice, /tmp
    included, and is taken as it is."""
    # Made first, checked after: a check before the mkdir left a window in
    # which another account's directory or symlink, made between the two,
    # was taken unchecked (review of #87). mkdir never follows a symlink.
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
    except OSError:
        pass
    if not ours:
        return
    try:
        st = os.lstat(path)
    except OSError:
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        die(f"TMPDIR {path} exists and is not a directory (a symlink is refused too); remove it or set TMPDIR")
    if st.st_uid != os.geteuid():
        die(f"TMPDIR {path} belongs to uid {st.st_uid}, not this account; remove it as that account or root, "
            "or set TMPDIR")


def print_report(d: dict, routing, *, label: str, agent: str, role: str, provider: str, session: str,
                 effective_session: str, session_effort: str, caller_effort: bool, prompt_file: str,
                 prompt_flag: str) -> None:
    s = d["session"]
    cap = s.get("capability")
    print(f"# resolved profile for {label} (agent {agent}, role {role}, provider {provider})")
    print(f"  session : {session}" + (f"  (the {cap} class)" if cap else ""))
    skipped = s.get("skipped") or ""
    if skipped:
        print(f"  (the merged session {skipped} is not an Anthropic model; the {s['source']} layer's is used "
              "on plain claude)")
    print(f"  (from the {s['source']} layer; bin/fabric-model list --provider {provider} shows every choice with "
          "its source)")
    if effective_session != session:
        print(f"  (overridden by --model on the command line: {effective_session})")
    if session_effort:
        print(f"  effort  : {session_effort}" + ("  (--effort on the command line)" if caller_effort
                                                 else "  (routing/effort.json)"))
    # Never "the model expresses none" without knowing that: a caller's
    # valueless --effort empties this too (re-review, N4).
    elif caller_effort:
        print("  effort  : -  (--effort on the command line carries no value; none is added)")
    else:
        print("  effort  : -  (this session's model expresses none; no --effort is passed)")
    # A --print missing half its profile must fail, not look successful:
    # the bash's block here could die on its first class, print a traceback
    # to stderr, and leave --print exiting 0 with the lines around it intact
    # — measured. A crash here is exit 1.
    try:
        for klass, res in d["classes"].items():
            if res["via"] == "harness":
                how = "(harness default for its tier)"
            elif res["via"] == "file":
                how = "(pinned in the agent file; the dispatch guard applies it; from %s)" % res["source"]
            else:
                how = "(exported for its tier; from %s)" % res["source"]
            # Effort is routed beside the model (routing/effort.json), so it is
            # printed beside it: `asked -> served` whenever they differ, because
            # a downgrade nobody can see is the defect the dimension exists for.
            eff = routing.effort_phrase(res.get("effort"))
            eff = "  " + eff if eff else ""
            if d.get("provider") == "anthropic":
                print("  %-12s: %s  %s%s" % (klass, res["model"], how, eff))
            else:
                print("  %-12s: %s  shim %s  => %s  %s%s" % (klass, res["model"], res["shim"] or "-",
                                                            res["composite"], how, eff))
        print()
        for k, v in sorted(d["exports"].items()):
            print("  export %s=%s" % (k, v))
    except Exception:
        sys.stdout.flush()
        traceback.print_exc()
        sys.exit(1)
    env = os.environ
    for var in ("AGENT_FABRIC_LAUNCH_SESSION_MODEL", "AGENT_FABRIC_LAUNCH_PROFILE", "AGENT_FABRIC_LAUNCH_PROVIDER",
                "AGENT_FABRIC_LAUNCH_ROLE", "AGENT_FABRIC_LAUNCH_PROMPT_DIGEST"):
        print(f"  export {var}={env.get(var, '')}")
    with open(prompt_file, "rb") as fh:
        prompt = fh.read()
    print(f"  prompt  : {prompt_file} ({len(prompt)} bytes; {prompt_flag})")
    if env.get("AGENT_FABRIC_LAUNCH_CLAUDE_VERSION"):
        print(f"  export AGENT_FABRIC_LAUNCH_CLAUDE_VERSION={env['AGENT_FABRIC_LAUNCH_CLAUDE_VERSION']} (the prompt is "
              "replaced; runtime/claude-code/harness/en.md names the build it was captured from)")
    first = prompt.split(b"\n", 1)[0].decode("utf-8", "surrogateescape")
    print(f"            {first}")


def record_launch_provider(state_dir: str, provider: str) -> None:
    """The provider the agent files were last installed for, so a run with
    no provider of its own (bootstrap from the control agent, an upgrade,
    fabric-model apply) installs for this one rather than for anthropic
    (install_agent_files.py reads it). Atomic; a failure is said, not fatal:
    the files themselves are installed."""
    path = os.path.join(state_dir, "launch-provider.json")
    try:
        os.makedirs(state_dir, exist_ok=True)
        tmp = f"{path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"provider": provider, "at": datetime.datetime.now(datetime.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        say(f"launch: could not record the provider in {path}: {exc}")


def install_agent_files(fabric_root: str, provider: str, state_dir: str | None = None) -> None:
    try:
        r = subprocess.run(["bash", f"{fabric_root}/runtime/claude-code/install-agent-files.sh", "--provider",
                            provider], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           timeout=INSTALL_TIMEOUT_S)
        installed = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        installed = False
    if not installed:
        die(f"could not install the capability-class agent files for {provider} "
            "(runtime/claude-code/install-agent-files.sh).")
    if state_dir:
        record_launch_provider(state_dir, provider)


def mark_onboarding_done(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        d = {}
    except (OSError, ValueError) as exc:
        say(f"launch: {path}: {exc}")
        die(f"could not mark the harness's onboarding done in {path}; nothing started.")
    if not isinstance(d, dict):
        say(f"launch: {path} is not a JSON object")
        die(f"could not mark the harness's onboarding done in {path}; nothing started.")
    if d.get("hasCompletedOnboarding") is not True:
        d["hasCompletedOnboarding"] = True
        tmp = f"{path}.fabric-tmp"
        try:
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            say(f"launch: {path}: {exc}")
            die(f"could not mark the harness's onboarding done in {path}; nothing started.")
        say("launch: marked the harness's onboarding done — a template login has no /login to onboard")


def session_command(provider: str, session: str, caller_model: bool, session_effort: str, caller_effort: bool,
                    prompt_flag: str, prompt_file: str, args: list[str]) -> list[str]:
    """The session's command line up to the caller's own arguments: the
    launcher's --model and --effort only where the caller passed none, so
    the child sees one of each and the stamps say what it applies."""
    cmd = ([] if provider == "anthropic" else ["ori"]) + ["claude"]
    if not caller_model:
        cmd += ["--model", session]
    if not caller_effort and session_effort:
        cmd += ["--effort", session_effort]
    return cmd + [prompt_flag, prompt_file, *args]


def asks_help(args: list[str]) -> bool:
    """claude's own help, asked before any `--`: no session will dispatch,
    so nothing of the account's is rewritten for it."""
    for a in args:
        if a == "--":
            return False
        if a in ("-h", "--help"):
            return True
    return False


def wants_opening(args: list[str]) -> bool:
    opening, expect_value = True, False
    for a in args:
        if expect_value:
            expect_value = False
            if not a.startswith("-"):
                continue
        if a in ("-p", "-v", "--version", "-h", "--help", "--"):
            opening = False
        elif a in VALUE_OPTIONS:
            expect_value = True
        elif a.startswith("-"):
            pass
        else:
            opening = False   # a positional word: the caller's own prompt
    if os.environ.get("AGENT_FABRIC_NO_OPENING"):
        opening = False
    return opening


def opening_prompt(fabric_root: str) -> str:
    text = OPENING
    # A session that ended its own job (bin/fabric-fresh) left a note for this
    # one: said in the opening prompt, then dropped from the environment.
    if "AGENT_FABRIC_FRESH_NOTE" in os.environ:
        note = os.environ.pop("AGENT_FABRIC_FRESH_NOTE")
        text = (text.removesuffix(WAIT_TAIL) + " The previous session of this agent finished its job and started "
                "this one fresh" + (f": {note}" if note else "") + "." + WAIT_TAIL)
    # fabric-fresh --job: the fresh session is for that job (ADR-037), and
    # the job, as the list holds it, replaces the wait for instructions.
    job = os.environ.get("AGENT_FABRIC_FRESH_JOB", "")
    if job:
        line = stripped(helper([sys.executable, f"{fabric_root}/tools/fabric/jobs.py", "show", job, "--line"],
                               env=env_with(AGENT_FABRIC_ROOT=fabric_root), quiet=True))
        if line:
            text = (text.removesuffix(WAIT_TAIL) + f" It is for your job {line}: read it in full with "
                    f"fabric-jobs show {job}, and start on it.")
        del os.environ["AGENT_FABRIC_FRESH_JOB"]
    return text


def ignore_quit() -> None:
    """In the session, before it starts: SIGQUIT ignored, as bash gave every
    `&` job of a script (without job control, an asynchronous command
    ignores SIGINT and SIGQUIT). SIGINT is ignored here already, and
    inherited."""
    signal.signal(signal.SIGQUIT, signal.SIG_IGN)


def run_session(cmd: list[str]) -> int:
    """THE SESSION IS A CHILD, NOT AN EXEC (owner, 2026-09-16). This process
    outlives the session, which is what lets it bring the session back
    after an upgrade or an account move (the restart marker, below). It
    once also sent a GOODBYE, a type now retired; presence is the control
    plane's.
    Signals: Ctrl-C is the session's (one interrupts a turn, two end it),
    so the launcher ignores SIGINT while the child runs; SIGTERM and SIGHUP
    — the terminal closing — are forwarded so the child can end. The
    child's exit status is the launcher's, 128+n for a signal, as bash's
    `wait` reported it. Same process group and the terminal as stdin, so
    Ctrl-C reaches the child directly."""
    child: subprocess.Popen | None = None

    def forward(signum, _frame):  # end the child the way we were asked to
        if child is not None and child.returncode is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    sys.stdout.flush()
    sys.stderr.flush()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGHUP, forward)
    try:
        child = subprocess.Popen(cmd, preexec_fn=ignore_quit)
        status = child.wait()
    except OSError as exc:
        say(f"launch: {cmd[0]}: {exc.strerror}")
        status = 127 if isinstance(exc, FileNotFoundError) else 126
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_DFL)
    return 128 - status if status < 0 else status


# ── back on the new version: the restart an action asked for ─────────
# The control agent's `upgrade` or `secrets-sync --restart`
# (runtime/control/{upgrade,secrets}.mjs) writes
# $STATE_DIR/restart.json, then stops this session with SIGTERM — the
# harness's graceful shutdown. This process is still in the session's
# terminal, so it is the one that can bring the session back: it waits
# while the upgrade runs, then re-executes itself — through the same pull
# and checks as any launch — resuming the session it was running
# (ADR-009). A marker older than this launch belongs to
# another session and is removed, never obeyed; an upgrade that failed
# still restarts, on what is installed, and says so.
def read_restart(marker: str, started: int, binding: str, wait_s_text: str) -> str | None:
    """What to come back as: "fresh:<job>:<note>", the session id to resume
    ("" for --continue), or None for a marker not to obey."""
    try:
        wait_s = int(wait_s_text)
    except ValueError:
        say(f"launch: AGENT_FABRIC_RESTART_WAIT_S is '{wait_s_text}', not a number of seconds; not resuming the "
            f"session (unset it for the default, {RESTART_WAIT_S} s).")
        return None

    def load():
        try:
            with open(marker, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}
    m = load()
    try:
        at = datetime.datetime.fromisoformat(str(m.get("requested_at", "")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        at = 0
    if at < started:
        return None
    if m.get("fresh"):
        # The session ended its own job (bin/fabric-fresh): nothing to wait
        # for, nothing to resume. The note travels to the next opening prompt.
        note = " ".join(str(m.get("note") or "").split())[:300]
        job = str(m.get("job") or "").replace(":", "")
        say(f"launch: the session finished its job{': ' + note if note else ''}; starting a fresh one"
            f"{' for job ' + job if job else ''}.")
        return f"fresh:{job}:{note}"
    deadline = time.time() + wait_s
    if m.get("status") == "pending":
        say(f"launch: the session was stopped for an upgrade of {m.get('piece')} to {m.get('to')}; waiting for it…")
    while m.get("status") == "pending" and time.time() < deadline:
        time.sleep(1)
        m = load()
    st = m.get("status")
    if st == "done":
        verb = "moved" if m.get("piece") == "the Claude account" else "upgraded"
        say(f"launch: {m.get('piece')} {verb} {m.get('from')} → {m.get('installed') or m.get('to')}; "
            "resuming the session on it.")
    elif st == "failed":
        say(f"launch: the upgrade of {m.get('piece')} to {m.get('to')} FAILED ({m.get('reason') or 'no reason given'}); "
            "resuming the session on what is installed.")
    else:
        say(f"launch: the upgrade of {m.get('piece')} did not finish within {wait_s} s; resuming the session on "
            "what is installed.")
    try:
        with open(binding, encoding="utf-8") as fh:
            return str(json.load(fh).get("session") or "").rstrip("\n")
    except (OSError, ValueError):
        return ""


def without_resume(orig_args: list[str]) -> list[str]:
    """The caller's own resume flags are replaced by the one that names the
    session just stopped; everything else is passed on as given."""
    nxt, skip = [], False
    for a in orig_args:
        if skip:
            skip = False
            if not a.startswith("-"):
                continue
        if a in ("--continue", "-c", "--resume=") or a.startswith("--resume="):
            continue
        if a in ("--resume", "-r"):
            skip = True
            continue
        nxt.append(a)
    return nxt


def absolute_path_options(args: list[str], cwd: str) -> list[str]:
    """A path relative to here would name nothing there: the values of the
    options that take paths are made absolute first, spaced or `=`, existing
    or not — and nothing else, since a model or provider name can match a
    file here too. One value each, as the opening scan reads them: a second
    word is the caller's prompt, and such a launch is never relaunched
    fresh. A --settings value that is JSON is not a path."""
    out, takes = list(args), False
    for i, a in enumerate(out):
        if a in PATH_OPTIONS:
            takes = True
            continue
        name, eq, v = a.partition("=")
        if eq and name in PATH_OPTIONS:
            if v and not v.startswith(("/", "{")):
                out[i] = f"{name}={cwd}/{v}"
            takes = False
            continue
        if a.startswith("-"):
            takes = False
            continue
        if not takes:
            continue
        if not a.startswith(("/", "{")):
            out[i] = f"{cwd}/{a}"
        takes = False
    return out


def reexec(env: dict, args: list[str]) -> "NoReturn":  # noqa: F821
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execvpe("bash", ["bash", SELF, *args], env)
    except OSError as exc:
        say(f"launch: could not re-execute {SELF}: {exc.strerror}")
        sys.exit(127)


def restart(state_dir: str, started: int, opening: bool, status: int, orig_args: list[str],
            fabric_root: str, cwd: str) -> None:
    marker = f"{state_dir}/restart.json"
    if not os.path.isfile(marker):
        return
    resume = read_restart(marker, started, f"{state_dir}/binding.json",
                          os.environ.get("AGENT_FABRIC_RESTART_WAIT_S") or str(RESTART_WAIT_S))
    try:
        os.remove(marker)
    except OSError:
        pass
    if resume is None:
        return
    nxt = without_resume(orig_args)
    base = {k: v for k, v in os.environ.items() if k != "AGENT_FABRIC_PULLED"}
    if resume.startswith("fresh:"):
        if not opening:
            # A marker not written by fabric-fresh's own check: never
            # relaunch a caller's prompt as if it were a new job.
            say("launch: a fresh session was asked for, but this launch carried its own prompt; not relaunching.")
            sys.exit(status)
        rest = resume[len("fresh:"):]
        job = rest.split(":", 1)[0]
        note = rest.split(":", 1)[1] if ":" in rest else rest
        base["AGENT_FABRIC_FRESH_NOTE"] = note
        if job:
            base["AGENT_FABRIC_FRESH_JOB"] = job
            # The job's working copy, when it is there and clean: the
            # rule a finished job's own tree met before fabric-fresh
            # let it go. Otherwise the old directory, and why.
            r = helper([sys.executable, f"{fabric_root}/tools/fabric/jobs.py", "show", job, "--field",
                        "working_copy"], env=env_with(AGENT_FABRIC_ROOT=fabric_root), quiet=True)
            wc = stripped(r) if r is not None and r.returncode == 0 else ""
            if wc:
                if not os.path.isdir(wc):
                    say(f"launch: job {job}'s working copy {wc} is not there; starting in {cwd}.")
                elif git_text(wc, "status", "--porcelain"):
                    say(f"launch: job {job}'s working copy {wc} has uncommitted changes; starting in {cwd}.")
                elif wc != cwd:
                    nxt = absolute_path_options(nxt, cwd)
                    try:
                        os.chdir(wc)
                        base["PWD"] = os.path.normpath(os.path.join(cwd, wc))
                        say(f"launch: starting job {job} in {wc}.")
                    except OSError:
                        pass
            else:
                say(f"launch: job {job} names no working copy; starting in {cwd}.")
        reexec(base, nxt)
    reexec(base, nxt + (["--resume", resume] if resume else ["--continue"]))


def launch(argv: list[str]) -> int:
    orig_args = list(argv)   # for the re-exec after a pull, below
    started = int(time.time())   # a restart marker older than this is not this session's
    print_only, provider, args = parse_argv(argv)
    if provider not in ("openrouter", "anthropic"):
        say(f"launch: --provider must be openrouter or anthropic, not '{provider}'")
        return 1

    env = os.environ
    fabric_root = env.get("AGENT_FABRIC_ROOT") or CODE_ROOT
    identity = f"{fabric_root}/runtime/identity.py"
    routing_path = f"{fabric_root}/tools/fabric/routing.py"
    capabilities = f"{fabric_root}/routing/capabilities.json"
    aliases = f"{fabric_root}/runtime/claude-code/aliases.json"
    cwd = logical_cwd()
    home = env.get("HOME", "")
    wc = toplevel(cwd)

    keep_fabric_current(fabric_root, orig_args)
    keep_working_copy_current(wc, fabric_root)

    # ── who is launching ────────────────────────────────────────────────
    if not os.path.isfile(identity):
        die(f"{identity} is missing — is AGENT_FABRIC_ROOT right?")
    r = helper([sys.executable, identity, "--json", "--cwd", cwd])
    try:
        context = json.loads(r.stdout) if r is not None and r.returncode == 0 else None
        agent, state_dir = context["agent"], context["state_dir"]
        role = context.get("role") or ""
    except (TypeError, ValueError, KeyError):
        die("could not resolve the agent identity.")
    local_override = f"{state_dir}/model-profile.local.json"

    # ── refusals ────────────────────────────────────────────────────────
    if not role:
        die(f"agent '{agent}' has no active role binding ({state_dir}/binding.json).\n"
            "  The launcher resolves the profile and the system prompt from the agent's\n"
            "  role. From a login shell run: bin/fabric-role bind <role>; then re-run.")
    require_files(capabilities, aliases)
    if provider == "openrouter":
        if not shutil.which("ori"):
            die("the ori CLI is not on PATH.")
    elif not shutil.which("claude"):
        die("claude is not on PATH.")
    refuse_passthrough(args)
    refuse_pins(settings_scopes(home, cwd), local_override)

    # ── resolve ─────────────────────────────────────────────────────────
    try:
        routing = load_routing(routing_path, fabric_root)
    except Exception:
        traceback.print_exc()
        die("could not resolve the profile (see the message above).")
    resolved = resolve_or_die(routing, aliases, local_override, role, agent, provider)
    if resolved.get("review_violation"):
        die(f"merged review model '{resolved['review_violation']}' is not in routing/policies/review-grade.json.\n"
            "  A review's failure mode is a green PR that merges, so the reviewer's\n"
            "  model is policy, not a cost dial. Change the profile or extend\n"
            "  review-grade.json through fabric-coordinator (policies/AUTHORITY.md).")
    session = str(resolved["session"]["composite"])

    if provider == "anthropic":
        drop_broker_env()
    settle_oauth_token(provider, home)
    set_pins(aliases, resolved["exports"])
    if provider == "openrouter":
        check_ori_auth()

    label = f"{role}/{agent}"
    # The session model reaches claude only as `--model`, which nothing inside
    # the session can read back — so model-audit.sh could not report it. Stamp
    # it into the child's environment, together with the profile it came from.
    # The stamp records what is ACTUALLY applied: an explicit --model on the
    # command line wins, so when the caller passes one, that value is stamped.
    # A trailing --model with no value is the caller's too: the launcher's own
    # is not appended (the same trailing-flag hole --effort had, and older).
    caller_model_value, caller_model, _ = caller_value(args, "--model")
    effective_session = caller_model_value if caller_model_value is not None else session
    # The session's own effort, beside its model: routing/effort.json names a
    # level or a class whose level to take, and the adapter has already
    # clamped it to what this model admits. The caller's own --effort wins and
    # is stamped instead, exactly as --model is — the stamp must never
    # disagree with what the child applies. Empty when the session's model
    # expresses no effort; then no flag is passed and nothing is stamped,
    # because a level the model cannot take is not a decision to record.
    routed_effort = stripped(helper([sys.executable, routing_path, "session-effort", "--me", "--provider",
                                     provider], env=env_with(AGENT_FABRIC_ROOT=fabric_root), quiet=True))
    session_effort, caller_effort = effort_for(args, routed_effort)
    # Cleared, not just left unset, when there is no level: this stamp is
    # CONDITIONAL, so a launch started from inside another fabric session
    # would otherwise inherit it (so is AGENT_FABRIC_LAUNCH_CLAUDE_VERSION,
    # cleared the same way below; the alias pins and the broker's own
    # environment are cleared above) — a child given no --effort
    # carrying its parent's `high`, which fabric-status then compares with a
    # level the child never had. Found when a relaunched session ran the suite.
    if session_effort:
        env["AGENT_FABRIC_LAUNCH_EFFORT"] = session_effort
    else:
        env.pop("AGENT_FABRIC_LAUNCH_EFFORT", None)
    env["AGENT_FABRIC_LAUNCH_SESSION_MODEL"] = effective_session
    env["AGENT_FABRIC_LAUNCH_PROFILE"] = label
    env["AGENT_FABRIC_LAUNCH_AGENT"] = agent
    env["AGENT_FABRIC_LAUNCH_PROVIDER"] = provider

    # The role's system prompt, rendered for THIS binding from the OS and the
    # state directory (nothing about who is passed in), written atomically so
    # a launch that dies mid-write leaves the previous prompt whole. The
    # digest is stamped so a session can say what it was launched with and
    # fabric-status can see the file change under it.
    prompt_file = f"{state_dir}/launch-prompt.md"
    r = helper([sys.executable, f"{fabric_root}/tools/fabric/launch_prompt.py", "--out", prompt_file], quiet=True)
    if r is None or r.returncode != 0:
        die("could not render the role's system prompt (tools/fabric/launch_prompt.py).")
    prompt_digest = stripped(r)
    # THE PROMPT IN THE LOCALE. A language-culture login whose locale carries
    # a translation of the harness's own text (identities/roles/language-
    # culture/locale/<suffix>/harness.md, of runtime/claude-code/harness/en.md)
    # is launched with the WHOLE prompt replaced — the fabric's part in the
    # locale, then the harness text in the locale, in that order, rendered by
    # launch_prompt.py — instead of the fabric's part appended after the
    # harness's English (the CEO, 2026-09-17; docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).
    # The harness still sends the function-calling grammar, every tool
    # schema, the listings and CLAUDE.md outside the replaceable text, so
    # nothing about how tools are called changes. The absence of that file
    # is the kill switch: append, as for every other login. On that branch
    # the build is stamped beside the capture's `build:`, so a build that
    # moved past it is visible — never a gate.
    suffix = pwd.getpwuid(os.getuid()).pw_name.rsplit("-", 1)[-1]
    locale_dir = f"{fabric_root}/identities/roles/language-culture/locale/{suffix}"
    prompt_flag = "--append-system-prompt-file"
    if role == "language-culture" and os.path.isfile(f"{locale_dir}/harness.md"):
        prompt_flag = "--system-prompt-file"
        out = stripped(helper(["claude", "--version"], quiet=True, timeout=CLAUDE_VERSION_TIMEOUT_S))
        env["AGENT_FABRIC_LAUNCH_CLAUDE_VERSION"] = out.split("\n", 1)[0]
    else:
        # Its documented meaning is "the prompt is replaced", so inherited
        # from a replaced session it would say that of a child whose prompt
        # is only appended (review of #31).
        env.pop("AGENT_FABRIC_LAUNCH_CLAUDE_VERSION", None)
    env["AGENT_FABRIC_LAUNCH_ROLE"] = role
    env["AGENT_FABRIC_LAUNCH_PROMPT_DIGEST"] = prompt_digest

    # The tab title is the hook's (runtime/claude-code/hooks/tab-title.sh:
    # "<agent> <working copy>/<branch>", so a pane is told apart by who is in
    # it), and the harness's own writer must be off or it overwrites that
    # with a prompt-derived topic after every turn. The workspace settings
    # template carries the switch, but that scope applies only to a session
    # started from ~/projects — every agent starts inside its clone, whose
    # .claude/settings.json is the project's, and the switch never reached
    # the process (read on two live sessions, 2026-09-16). The launcher
    # decides the child's environment on every path, so it is exported here.
    env["CLAUDE_CODE_DISABLE_TERMINAL_TITLE"] = "1"

    # Temporary files go to a per-account directory under /var/tmp, not to
    # the host's shared tmpfs and not under the home. /tmp on a host is one
    # small memory filesystem for every agent account; a bare dotnet, flutter
    # or marp run outside make writes its build and test scratch there and
    # leaves it, and on 2026-09-17 it hit 100% and stopped every session at
    # once (the CEO's decision, seq 748; the make half is each project's,
    # this is the launcher's — the one place every session's environment is
    # decided). /var/tmp is disk-backed and world-writable on every platform
    # the fabric runs on; on a Qubes AppVM it sits on the volatile root
    # volume and is emptied at every reboot, elsewhere systemd-tmpfiles
    # clears entries older than thirty days — either way nothing
    # accumulates under a home for ever (the CEO, 2026-09-17). One directory
    # per login straight under /var/tmp, 700, so no account has to own a
    # shared parent. A TMPDIR the account set itself wins.
    own_tmpdir = env.get("TMPDIR")
    env["TMPDIR"] = own_tmpdir or f"/var/tmp/agent-fabric-{agent}"
    make_tmpdir(env["TMPDIR"], ours=not own_tmpdir)

    if print_only:
        print_report(resolved, routing, label=label, agent=agent, role=role, provider=provider, session=session,
                     effective_session=effective_session, session_effort=session_effort,
                     caller_effort=caller_effort, prompt_file=prompt_file, prompt_flag=prompt_flag)
        return 0

    # The review class's model is per launch (the broker's composite, or the
    # native pin) and reaches the reviewer through its agent file, so the
    # account's agent files are installed for THIS provider now, before the
    # session that will dispatch from them exists. The dispatch guard checks
    # the file against the same resolution and denies a review when another
    # launch on this account has since rewritten it.
    if not asks_help(args):
        install_agent_files(fabric_root, provider, state_dir)

    login = pwd.getpwuid(os.getuid()).pw_name
    # A plain-claude session runs only on a long-lived sign-in: a template's
    # setup-token, valid a year (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md). A login's own /login
    # is an 8-hour token with one refresh holder, and a fleet that silently fell
    # back to it ran on whichever account last signed in on that login — the
    # owner, 2026-09-25: no long-lived token, no session. Checked here, after
    # --print (a read-back needs no sign-in) and before anything starts.
    if provider == "anthropic" and not SETUP_TOKEN.fullmatch(env.get("CLAUDE_CODE_OAUTH_TOKEN", "")):
        die(f"no long-lived Claude sign-in for {login}: the login's synced record "
            f"({home}/.config/agent-fabric/secrets.env) has no CLAUDE_CODE_OAUTH_TOKEN of a setup-token's shape. "
            f"The coordinator assigns one (bin/fabric-accounts assign {login} <account>), then "
            "bin/fabric-secrets sync here. Nothing started.")
    # The harness's first-run wizard ignores that token: until
    # hasCompletedOnboarding is set it asks for a theme, then a login method,
    # and opens a browser for the /login refused above (web-dev-01, which never
    # signed in, 2026-09-25; read back in a pty on 2.1.282). A login that runs
    # on a template has nothing to onboard, so the flag is set here, in the
    # file the harness reads — under CLAUDE_CONFIG_DIR when that is set.
    if provider == "anthropic":
        mark_onboarding_done(f"{env.get('CLAUDE_CONFIG_DIR') or home}/.claude.json")

    # Plain claude: no broker, no shim; the exports above are the column's
    # and the profile's native pins, the review pin is served by its agent
    # file under the dispatch guard; the session model, the role's system
    # prompt and the refusals are what the launcher contributed.
    # When the caller supplied --model, the launcher's own is OMITTED rather
    # than placed first: "last wins" would be an assumption about claude's
    # argv handling, and the stamp above must not be able to disagree with
    # what the child actually applies.
    cmd = session_command(provider, session, caller_model, session_effort, caller_effort, prompt_flag,
                          prompt_file, args)
    # A language-culture login whose locale the fabric authored a search for
    # (identities/roles/language-culture/locale/<suffix>/locale.json, served
    # by runtime/mcp/websearch-locale) searches through that alone: the
    # harness's own WebSearch — US-only, no locale — is removed from the
    # session at exec (the CEO, 2026-09-17). install-agent-files.sh writes the
    # same as a permissions.deny in the login's user settings, the fence for
    # a session launched without this launcher.
    # Last among the options, after the caller's own: --disallowedTools is
    # variadic and swallows whatever follows it that is not an option (read
    # back 2026-09-18: it ate a positional prompt in a -p probe).
    if role == "language-culture" and os.path.isfile(f"{locale_dir}/locale.json"):
        cmd += ["--disallowedTools", "WebSearch"]
    # THE WATCH STARTS WITH THE SESSION. Only a session can call Monitor, and a
    # session acts only on a turn: the start hook's "arm it now" waited for
    # whatever prompt came first, and an agent left alone after a launch or a
    # resume had no inbox (the owner, 2026-09-26). So an interactive launch the
    # caller gave no prompt of its own opens with one: arm the watch, by the
    # bare name the user settings allow, so the turn runs without asking.
    # AFTER `--`, the very last argument: an option the caller left without a
    # value (a bare --resume opening the picker) or a variadic one (--add-dir)
    # would otherwise take the prompt as its value (the review of #43; read
    # back: claude reads a prompt after `--`, a variadic option before it).
    # None in print mode (-p), for --version/--help, where the caller passed a
    # prompt of its own, or where the caller already wrote `--` (the scan
    # cannot tell what follows it). AGENT_FABRIC_NO_OPENING is for a caller
    # that drives the session itself, a probe or a script, and wants its own
    # first turn.
    # The prompt names no command. It stays in claude's argv for the whole
    # session, and a process pattern built from the watch's command
    # (`pgrep -f 'gzcoord-inbox --follow' | xargs kill`, clearing a "stale"
    # watcher) matched the session itself and killed it: architect-cto-01,
    # twice, 2026-09-29. The exact Monitor call is the session-start hook's
    # NO INBOX WATCH line, which is context, never argv, and which it gives
    # exactly when no watch runs; hooks/self-kill-guard.py refuses the kill.
    text = opening_prompt(fabric_root)
    opening = wants_opening(args)
    if opening:
        cmd += ["--", text]
    # Said to the session, for bin/fabric-fresh: a fresh session gets the
    # launcher's opening prompt with the note. A launch that carried its own
    # prompt (or -p) would be relaunched with that prompt again and no note,
    # so fabric-fresh refuses it rather than replay a finished job.
    env["AGENT_FABRIC_LAUNCH_OPENING"] = "1" if opening else "0"

    status = run_session(cmd)
    restart(state_dir, started, opening, status, orig_args, fabric_root, cwd)
    return status


def main(argv: list[str]) -> int:
    # Ctrl-C before the session starts ends the launcher as it ended the
    # bash: by the signal, with no traceback.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    # Every line is written as the bash wrote it, UTF-8 whatever the locale,
    # and a byte the prompt file holds goes out as that byte.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        status = launch(argv)
        sys.stdout.flush()
        return status
    except Refused as exc:
        say(f"launch: {exc}")
        return 1
    except BrokenPipeError:
        # `--print | head`: the reader left; bash's echo died of SIGPIPE.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 141


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
