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
            BROKER_ENV), every synced secret but the harness's own
            (dropped, settle_secrets), TMPDIR,
            HOME, PATH, PWD (the launch directory, as the shell names it).
            Written into the session's environment: the alias pins, every
            AGENT_FABRIC_LAUNCH_* stamp, CLAUDE_CODE_DISABLE_TERMINAL_TITLE,
            TMPDIR.
  files     reads the settings scopes, ~/.config/agent-fabric/secrets.env,
            the agent's state directory (binding.json,
            model-profile.local.json, restart.json); writes
            $STATE_DIR/launch-prompt.md (launch_prompt.py),
            ${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json (onboarding, plain
            claude only, none for --help), the agent files (install-agent-files.sh; none
            for --help), $STATE_DIR/launch-provider.json after they are
            installed (the provider, for a later install with none), and
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
its caller left open, while a leaked pipe end would hold the caller's
pipeline open for the session's life. One caller hands one on, to this
process and never further: bin/fabric-resume's flock on
<state>/resume.lock, inherited through its exec, which this launcher
holds for its own life — its restart wait and the sessions it relaunches
through the shim keep the same descriptor — so that no second activation
starts while it runs (tools/fabric/resume.py). The harness never gets
it, so a background child of a session cannot keep it past the launcher.
Every other caller holds none (fabric-lease closes its lock's before the
command; moveto's shell, the control agent and fabric-fresh hold none). AGENT_FABRIC_RESTART_WAIT_S that
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
  - no runtime binding for this agent      -> "fabric-role bind first"
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
OPENROUTER_API_KEY in ~/.config/agent-fabric/secrets.env, which
`fabric-secrets sync` writes from the account's own store
(runtime/provisioning/README.md, "Secrets"; ADR-038) and no shell
sources: the launcher reads it and hands it to ori alone, and drops every
other synced secret from the session (settle_secrets) — never in the repo.

The environment is handled as the bash's shell environment was: this
process's os.environ IS what the session and every helper inherit, set and
cleared in the bash's order, so a helper sees exactly what it saw there.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import shutil
import signal
import sys
import time
import traceback

# The parts, a package loaded BY PATH as fabric_launcher: the launcher
# loads its siblings by path on purpose (git.py, in launcher/base.py), so a
# fixture fabric on sys.path cannot answer for its imports; and the shim
# runs it under -I, which puts no directory of its own on sys.path.
# A second launch.py in one process — a fixture's copy beside the real one —
# loads its own parts, never the first one's from sys.modules (#102's
# review): the cached package is dropped first. A launcher loaded before
# keeps the parts it already bound.
for _name in [n for n in sys.modules if n == "fabric_launcher" or n.startswith("fabric_launcher.")]:
    del sys.modules[_name]
_spec = importlib.util.spec_from_file_location(
    "fabric_launcher", os.path.join(os.path.dirname(os.path.realpath(__file__)), "launcher", "__init__.py"),
    submodule_search_locations=[os.path.join(os.path.dirname(os.path.realpath(__file__)), "launcher")])
sys.modules["fabric_launcher"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sys.modules["fabric_launcher"])
# Every name the parts define, from here as before: the tests reach them as
# launch.<name>, and patch launch.reexec and launch.launch, which stay here
# with the functions that call them (restart, keep_fabric_current, main).
from fabric_launcher.base import HERE, CODE_ROOT, _load, git, roots, SELF, FETCH_TIMEOUT_S  # noqa: E402, F401
from fabric_launcher.base import ORI_AUTH_TIMEOUT_S, CLAUDE_VERSION_TIMEOUT_S  # noqa: E402, F401
from fabric_launcher.base import INSTALL_TIMEOUT_S, HELPER_TIMEOUT_S, RESTART_WAIT_S  # noqa: E402, F401
from fabric_launcher.base import OPENING, WAIT_TAIL, BROKER_ENV, SETUP_TOKEN, PROMPT_FLAGS  # noqa: E402, F401
from fabric_launcher.base import VALUE_OPTIONS, PATH_OPTIONS, Refused, die, say  # noqa: E402, F401
from fabric_launcher.base import logical_cwd, helper, stripped, env_with  # noqa: E402, F401
from fabric_launcher.argv import parse_argv, refuse_passthrough, asks_help, wants_opening  # noqa: E402, F401
from fabric_launcher.argv import without_resume, absolute_path_options  # noqa: E402, F401
from fabric_launcher.currency import git_status_ok, git_text, behind_count, pull_ff  # noqa: E402, F401
from fabric_launcher.currency import keep_working_copy_current, toplevel  # noqa: E402, F401
from fabric_launcher.settings import settings_scopes, settings_pins, refuse_pins  # noqa: E402, F401
from fabric_launcher.routing import ResolveError, load_routing, resolve, resolve_or_die  # noqa: E402, F401
from fabric_launcher.routing import is_broker_url, drop_broker_env, set_pins, ori_auth_ok  # noqa: E402, F401
from fabric_launcher.routing import check_ori_auth, caller_value, effort_for  # noqa: E402, F401
from fabric_launcher.secrets import synced_values, synced_oauth_token, settle_oauth_token  # noqa: E402, F401
from fabric_launcher.secrets import SYNCED_SECRETS, HARNESS_CREDENTIAL, HARNESS_EXPANDS  # noqa: E402, F401
from fabric_launcher.secrets import settle_secrets  # noqa: E402, F401
from fabric_launcher.session import require_files, make_tmpdir, print_report  # noqa: E402, F401
from fabric_launcher.session import record_launch_provider, install_agent_files  # noqa: E402, F401
from fabric_launcher.session import mark_onboarding_done, session_command, opening_prompt  # noqa: E402, F401
from fabric_launcher.session import ignore_quit, run_session, read_restart  # noqa: E402, F401
from fabric_launcher import gateway  # noqa: E402, F401


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
    if provider not in ("openrouter", "anthropic", "gateway"):
        say(f"launch: --provider must be openrouter, anthropic or gateway, not '{provider}'")
        return 1
    # The gateway path routes as plain claude does (the anthropic column's pins,
    # the same agent files); only the transport differs (launcher/gateway.py).
    routing_provider = "anthropic" if provider == "gateway" else provider

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
            "  role. From a login shell run: fabric-role bind <role>; then re-run.")
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
    resolved = resolve_or_die(routing, aliases, local_override, role, agent, routing_provider)
    if resolved.get("review_violation"):
        die(f"merged review model '{resolved['review_violation']}' is not in routing/policies/review-grade.json.\n"
            "  A review's failure mode is a green PR that merges, so the reviewer's\n"
            "  model is policy, not a cost dial. Change the profile or extend\n"
            "  review-grade.json through fabric-coordinator (policies/AUTHORITY.md).")
    session = str(resolved["session"]["composite"])

    if routing_provider == "anthropic":
        drop_broker_env()
    settle_oauth_token(provider, home)
    settle_secrets(provider, home)
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
                                     routing_provider], env=env_with(AGENT_FABRIC_ROOT=fabric_root), quiet=True))
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
    locale_dir = roots.locale_dir("language-culture", suffix, engine=fabric_root, environ=env)
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
        print_report(resolved, routing, label=label, agent=agent, role=role, provider=routing_provider, session=session,
                     effective_session=effective_session, session_effort=session_effort,
                     caller_effort=caller_effort, prompt_file=prompt_file, prompt_flag=prompt_flag)
        if provider == "gateway":
            print("  (launched through agent-fabric-gateway: the harness gets its loopback listener and a local key, "
                  "and no upstream credential)")
        return 0

    # The review class's model is per launch (the broker's composite, or the
    # native pin) and reaches the reviewer through its agent file, so the
    # account's agent files are installed for THIS provider now, before the
    # session that will dispatch from them exists. The dispatch guard checks
    # the file against the same resolution and denies a review when another
    # launch on this account has since rewritten it.
    if not asks_help(args):
        install_agent_files(fabric_root, routing_provider, state_dir, record_as=provider)

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
            f"The coordinator assigns one (fabric-accounts assign {login} <account>), then "
            "fabric-secrets sync here. Nothing started.")
    # The harness's first-run wizard ignores that token: until
    # hasCompletedOnboarding is set it asks for a theme, then a login method,
    # and opens a browser for the /login refused above (web-dev-01, which never
    # signed in, 2026-09-25; read back in a pty on 2.1.282). A login that runs
    # on a template has nothing to onboard, so the flag is set here, in the
    # file the harness reads — under CLAUDE_CONFIG_DIR when that is set. Not
    # for claude's own help: no session follows, and a help read writes
    # nothing of the account's (#91's review).
    if provider == "anthropic" and not asks_help(args):
        mark_onboarding_done(f"{env.get('CLAUDE_CONFIG_DIR') or home}/.claude.json")

    # Plain claude: no broker, no shim; the exports above are the column's
    # and the profile's native pins, the review pin is served by its agent
    # file under the dispatch guard; the session model, the role's system
    # prompt and the refusals are what the launcher contributed.
    # When the caller supplied --model, the launcher's own is OMITTED rather
    # than placed first: "last wins" would be an assumption about claude's
    # argv handling, and the stamp above must not be able to disagree with
    # what the child actually applies.
    cmd = session_command(routing_provider, session, caller_model, session_effort, caller_effort, prompt_flag,
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

    # The gateway is started only now, after every refusal: it needs the session
    # command's model and the pins in the environment (the plan must route what
    # the harness will send), and nothing else of the launch depends on it.
    gw = None
    if provider == "gateway" and not asks_help(args):
        gw = gateway.launch_gateway(env, fabric_root, agent, role, state_dir, effective_session)
    try:
        status = run_session(cmd)
    finally:
        if gw is not None:
            gateway.stop(gw)
            gateway.forget_state(state_dir)
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
