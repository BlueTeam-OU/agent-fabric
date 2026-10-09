#!/usr/bin/env python3
"""tools/fabric/status.py — one call, the whole picture: who this session is,
what it is bound to, which API path it runs on, and how the capability
classes resolve there (ADR-040 Wave 2; bin/fabric-status is its shim, and
every caller — the commands.json link in ~/.local/bin, the session's own
`fabric-status`, the docs — keeps that path). Read-only; prints no
credentials (a provider variable is reported set or unset, never echoed).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      [--json]. The bash read `${1:-}` and nothing else: the first
            argument only, `--json` selects the object, ANYTHING else
            (including -h and --help) is ignored and prints the human
            report. There is no help text, so none is frozen here.
  stdin     never read.
  env       AGENT_FABRIC_ROOT (defaults to the repository this file is in,
            and is exported to the modules it loads — identity.py takes its
            FABRIC_ROOT from it), AGENT_FABRIC_STATE_DIR (identity.py),
            AGENT_FABRIC_HOSTS_REGISTRY, AGENT_FABRIC_FALLBACK_DIR,
            AGENT_FABRIC_LAUNCH_{PROVIDER,SESSION_MODEL,ROLE,PROMPT_DIGEST,
            PROFILE,EFFORT}, ANTHROPIC_BASE_URL, ANTHROPIC_DEFAULT_{HAIKU,
            SONNET,OPUS,FABLE}_MODEL (the pins), every other ANTHROPIC_*,
            OPENROUTER_API_KEY, CLAUDE_CODE_SUBAGENT_MODEL,
            CLAUDE_CODE_EFFORT_LEVEL (reported set, never echoed),
            CLAUDE_CODE_OAUTH_TOKEN, CLAUDE_CONFIG_DIR, CLAUDE_EFFORT,
            CLAUDE_PID, MOVETO_PREFIX (hosttools.py), HOME.
  files     ~/.config/agent-fabric/secrets.env (the synced token line),
            $CLAUDE_CONFIG_DIR/.claude.json or ~/.claude.json (the sign-in
            email), the fallback markers, runtime/hosts/registry.json, the
            binding, job list and launch-prompt.md of the login, the
            working copy's last-drain-report.json and the harness's memory
            directory for it.
  stdout    the human report (below), or with --json one object, indent 2,
            ensure_ascii. Nothing on stderr by design; a module this file
            loads that fails writes its own traceback there.
  exit      0. A crash in a loaded module or an unreadable fallback
            directory is an uncaught exception: exit 1 and a traceback,
            as in the bash (replicated, not fixed). A closed stdout
            (`| head -1`) ends quietly with 1 where the bash printed a
            BrokenPipeError traceback; the only deliberate difference.

The human report, in order: `agent`, `role`, `launched as` (only with a
launch role stamp), one `DRIFT` line per drift, `project`, `session`,
`jobs`, a blank line, `api`, `session model`, `session effort` (only when
asked or stamped), `launch profile` (only when stamped), `pins`,
`credentials`, `claude sign-in`, a blank line, `capabilities on <provider>`
and one line per class, `routing`, `memory` (only when there is something
to count), `moveto` (only when installed), `control plane`.

The --json object: agent, host, placement, role, project, working_copy,
session, binding_updated, launched_role, launch_prompt_digest, drift (a
list or null), session_effort ({asked, reported, launched} or null),
undrained_memories ({drainable, no_roles_class, since, dir} or null), jobs
({active, queued, blocked, delivered} or {error}), api ({provider, path,
base_url_host, session_model, launch_profile, pins, credentials,
claude_sign_in}), capabilities ({class: line}), routing_check ("clean" or
a list), host_tools ({moveto}), control_plane.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import roots  # noqa: E402

PIN_VARS = ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL")
DRIFT_ORDER = ("role", "model", "effort", "prompt", "placement", "fallback", "signin")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def api_path(environ=None):
    """(provider, path, host, base) for the process's ANTHROPIC_BASE_URL."""
    environ = os.environ if environ is None else environ
    base = environ.get("ANTHROPIC_BASE_URL", "")
    try:
        host = (urlsplit(base).hostname or "") if base else ""
    except ValueError:
        host = ""
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        provider, path = "openrouter", "broker (ori)"
    elif base:
        provider, path = "anthropic", "custom base URL (%s)" % host
    else:
        provider, path = "anthropic", "vanilla claude, Anthropic direct"
        # Launched by the fabric (runtime/openrouter/launch --provider anthropic):
        # the review pin and the session model are the fabric's; unlaunched, every
        # tier is the harness's own default.
        if environ.get("AGENT_FABRIC_LAUNCH_PROVIDER") == "anthropic":
            path += ", launched by the fabric"
        else:
            path += ", not launched by the fabric (harness defaults for every tier)"
    return provider, path, host, base


# A safeguard flagged a request and the harness switched this session's
# model on its own (runtime/claude-code/hooks/model-fallback-note.sh
# leaves the marker, per harness pid): the session runs on a tier it was
# not launched with, until /model. Said here as drift.
def fallback_marker(environ=None):
    environ = os.environ if environ is None else environ
    d = environ.get("AGENT_FABRIC_FALLBACK_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "agent-fabric", "fallback")
    pid = environ.get("CLAUDE_PID")
    names = [f"{pid}.json"] if pid and os.path.isfile(os.path.join(d, f"{pid}.json")) else (sorted(os.listdir(d)) if os.path.isdir(d) else [])
    for n in names:
        f = os.path.join(d, n)
        try:
            if os.lstat(f).st_uid != os.getuid():
                continue
            with open(f, encoding="utf-8") as fh:
                m = json.load(fh)
            p = int(m.get("pid") or 0)
            if p <= 0:
                continue
            os.kill(p, 0)
            return m
        except Exception:
            continue
    return None


def fallback_drift_line(fallback):
    if not fallback:
        return None
    return (f"session model fell back from {fallback.get('from_model') or '?'} to {fallback.get('to_model') or '?'} at {fallback.get('at') or '?'} "
            "after a safeguard flagged a request (sticky until /model; nothing from that exchange travels)")


# Which Claude sign-in plain claude uses: a template's setup-token when
# CLAUDE_CODE_OAUTH_TOKEN is set (it outranks /login), otherwise the login's
# own sign-in — whose ~/.claude.json keeps naming its account either way,
# so that file alone would report the wrong account for a switched login.
def synced_template_token():
    """The login's own record — the `export CLAUDE_CODE_OAUTH_TOKEN=` line
    fabric-secrets sync writes. The launcher removes the variable from a
    broker session's environment, and that session must still report the
    account the login is on (re-review of #33)."""
    env_file = os.path.join(os.path.expanduser("~"), ".config", "agent-fabric", "secrets.env")
    try:
        with open(env_file, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("export CLAUDE_CODE_OAUTH_TOKEN="):
                    v = line.split("=", 1)[1].strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                        v = v[1:-1]
                    return v or None
    except OSError:
        pass
    return None


def fp12(v):
    return hashlib.sha256(v.encode()).hexdigest()[:12]


# What THIS session's plain claude uses is its environment; the login's
# synced record is what the next launch will use. Environment first, the
# record when the environment has none (a broker session, where the
# launcher removed it); the line names which, and the two disagreeing is
# drift — a session launched before the sync that moved the login.
def signin_drift_line(sign_env, sign_file, base):
    if (sign_env or None) != (sign_file or None) and not (not sign_env and base):
        return (f"this session runs on {'setup-token ' + fp12(sign_env) if sign_env else 'no token'}, the login's synced record "
                f"names {'setup-token ' + fp12(sign_file) if sign_file else 'none'} — the next launch uses the record")
    return None


def claude_sign_in(sign_env, sign_file, environ=None):
    environ = os.environ if environ is None else environ
    tok, source = (sign_env, "CLAUDE_CODE_OAUTH_TOKEN in this session") if sign_env else (sign_file, "the login's synced record")
    if tok:
        return f"setup-token {fp12(tok)} ({source}; fabric-accounts templates names its account)"
    cfg = environ.get("CLAUDE_CONFIG_DIR")
    prof = os.path.join(cfg, ".claude.json") if cfg else os.path.join(os.path.expanduser("~"), ".claude.json")
    try:
        with open(prof, encoding="utf-8") as fh:
            email = (json.load(fh).get("oauthAccount") or {}).get("emailAddress")
    except (OSError, ValueError):
        email = None
    return f"own /login ({email})" if email else "own /login (none recorded)"


def undrained_memories(ctx, root):
    # --- memory: what this agent wrote that no drain has taken yet -----------
    # The drain reads ~/.claude/projects/<launch-dir-slug>/memory/ and takes a
    # file only if it carries metadata.roles_class; the project's last drain
    # report records the watermark (ms since the epoch, per agent@host). Counting
    # what is newer than it, with and without the class, is the one number
    # that says whether a drain is owed — a rule (memory/README.md, "When a
    # drain runs") that nothing else makes visible. Best effort: no working
    # copy, no report or no memory directory is "n/a", never a failure.
    try:
        if ctx["working_copy"] and ctx["project"]:
            harvest = load("fabric_harvest", os.path.join(root, "tools", "fabric", "harvest_memory.py"))
            mem_dir = harvest.default_memory_dir(ctx["working_copy"])
            # The harvester's own reading of the mark, so the count and the
            # next drain agree on where this agent's store was read up to.
            watermark_ms, _ = harvest.previous_watermark(ctx["working_copy"], ctx["host"], ctx["agent"])
            drainable, private = 0, 0
            if os.path.isdir(mem_dir):
                for name in os.listdir(mem_dir):
                    if not name.endswith(".md") or name == "MEMORY.md":
                        continue
                    rec = harvest.parse_memory(os.path.join(mem_dir, name))
                    if not rec or rec["mtime"] * 1000 <= watermark_ms:
                        continue
                    if rec["roles_class"]:
                        drainable += 1
                    else:
                        private += 1
            return {"drainable": drainable, "no_roles_class": private,
                    "since": "the last drain" if watermark_ms else "ever (no drain report)", "dir": mem_dir}
    except Exception:  # noqa: BLE001 — a status line, not a guard
        pass
    return None


def prompt_drift_line(digest, state_dir):
    if not digest:
        return None
    prompt_path = os.path.join(state_dir, "launch-prompt.md")
    try:
        with open(prompt_path, "rb") as fh:
            actual = "sha256:" + hashlib.sha256(fh.read()).hexdigest()
        if actual != digest:
            return f"the prompt file was rewritten since launch ({prompt_path}); this session still holds the launched text"
    except OSError:
        return f"the launched prompt file is gone ({prompt_path})"
    return None


def placement_of(ctx, root, environ=None):
    """(placement, drift line). An unreadable or invalid registry says nothing."""
    environ = os.environ if environ is None else environ
    placement = None
    placement_drift = None
    try:
        with open(roots.hosts_registry(environ=environ, engine=root), encoding="utf-8") as fh:
            reg = json.load(fh)
        placement = (reg.get("placement") or {}).get(ctx["agent"])
        if placement and placement != ctx["host"]:
            placement_drift = f"registered on {placement}, running on {ctx['host']} — update runtime/hosts/registry.json placement, or the account was moved"
        elif not placement:
            placement_drift = f"not placed in runtime/hosts/registry.json (running on {ctx['host']}); add the placement"
    except (OSError, ValueError):
        pass
    return placement, placement_drift


def jobs_summary(identity, agent):
    # The job list (ADR-037): open jobs by state, and the active one.
    try:
        _jobs = [j for j in identity.read_jobs(agent)["jobs"]
                 if isinstance(j, dict) and j.get("state") in ("queued", "active", "blocked", "delivered")]
    except SystemExit as exc:
        _jobs = str(exc.code)
    except OSError as exc:
        _jobs = f"{exc.strerror or exc}"
    if isinstance(_jobs, str):
        return {"error": _jobs}
    _active = next((j for j in _jobs if j["state"] == "active"), None)
    return {"active": {"id": _active.get("id"), "title": _active.get("title") or "", "working_copy": _active.get("working_copy")} if _active else None,
            **{st: sum(1 for j in _jobs if j["state"] == st) for st in ("queued", "blocked", "delivered")}}


# A session's Bash no longer holds the harness's credentials (the
# SessionStart hook unsets them, ADR-038 rule 9), so what this session
# signs in with is read where it is: the environment of the nearest
# ancestor that is the harness itself, by its process name. Read in this
# process, fingerprinted or reduced to "set", never printed. None outside
# a session, or where /proc is not readable: the process's own then.
def harness_environ(start_pid=None, proc="/proc"):
    pid = os.getppid() if start_pid is None else start_pid
    for _ in range(64):
        try:
            with open(f"{proc}/{pid}/comm", encoding="utf-8") as fh:
                comm = fh.read().strip()
            if comm == "claude":
                with open(f"{proc}/{pid}/environ", "rb") as fh:
                    pairs = [e.split(b"=", 1) for e in fh.read().split(b"\0") if b"=" in e]
                return {k.decode(errors="replace"): v.decode(errors="replace") for k, v in pairs}
            with open(f"{proc}/{pid}/status", encoding="utf-8") as fh:
                pid = int(next(line.split()[1] for line in fh if line.startswith("PPid:")))
        except (OSError, ValueError, StopIteration):
            return None
        if pid <= 1:
            return None
    return None


def session_environ(environ, find=None):
    """Where the session's credentials are: the harness's environment, but
    only inside a session's Bash. The harness marks its children with
    CLAUDECODE, and a process outside one (CI, a suite that cleared it) has
    no harness to ask: an unrelated claude up the chain is not its session."""
    if environ.get("CLAUDECODE") != "1":
        return None
    return (find or harness_environ)()


def build_report(root, environ=None, cred_environ=None):
    """(report, base): the whole picture as the --json object, and the
    ANTHROPIC_BASE_URL the human report's sign-in line is conditional on.
    cred_environ is where the session's credentials are read: the harness
    process's environment by default (harness_environ)."""
    if environ is None:
        environ = os.environ
        if cred_environ is None:
            cred_environ = session_environ(environ)
    cred_environ = environ if cred_environ is None else cred_environ
    identity = load("fabric_identity", os.path.join(root, "runtime", "identity.py"))
    routing = load("fabric_routing", os.path.join(root, "tools", "fabric", "routing.py"))
    hosttools = load("fabric_hosttools", os.path.join(root, "tools", "fabric", "hosttools.py"))

    ctx = identity.resolve_context()
    binding = identity.read_binding(ctx["agent"])

    # --- which API path is this process on? --------------------------------
    provider, path, host, base = api_path(environ)
    stamp = environ.get("AGENT_FABRIC_LAUNCH_SESSION_MODEL")
    fallback_drift = fallback_drift_line(fallback_marker(environ))
    pins = {k: environ.get(k) for k in PIN_VARS}
    present = sorted(set(k for k in environ if k.startswith("ANTHROPIC_")
                         or k in ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL"))
                     | set(k for k in cred_environ if k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                                                              "OPENROUTER_API_KEY")))
    credentials = {k: "set" for k in present if k not in pins and k != "ANTHROPIC_BASE_URL"}
    sign_env, sign_file = cred_environ.get("CLAUDE_CODE_OAUTH_TOKEN"), synced_template_token()
    signin_drift = signin_drift_line(sign_env, sign_file, base)

    # --- how the classes resolve on that provider --------------------------
    # The merge includes this login's own layer (bin/fabric-model writes it);
    # a malformed one is reported per class rather than hidden.
    classes = {}
    try:
        local = routing.load_local(ctx["agent"])
        routing.normalize_layer(local, "local")
    except ValueError as exc:
        local, local_error = {}, str(exc)
    else:
        local_error = None
    alias_env = routing.load_aliases(root)["env"]
    for klass in routing.load_capabilities(root)["classes"]:
        try:
            r = routing.resolve(klass, provider, binding.get("role"), ctx["agent"], local, root=root)
            how = {"export": " (exported)" if pins.get(alias_env.get(r.get("alias") or "", "")) else " (not exported in this session)",
                   "file": " (the agent file)", "harness": " (the harness's tier)"}[r["via"]]
            eff = routing.effort_phrase(r.get("effort"))
            classes[klass] = r["composite"] + how + " (from %s)" % r["source"] + (" " + eff if eff else "")
        except (KeyError, ValueError) as exc:
            classes[klass] = "unresolved: %s" % exc
        if local_error:
            classes[klass] += " (local layer ignored: %s)" % local_error
    # One implementation of one decision: the launcher asks
    # `routing.py session-effort`, so this asks the same function rather than
    # walking effort.json again. The two had drifted — a session pinned to a
    # model with no effort control got no flag from the launcher and a
    # confident level from here (review of 2026-09-23, F4).
    session_effort = None
    try:
        session_effort = {"asked": routing.session_effort(provider, binding.get("role"), ctx["agent"], local, root),
                          "reported": environ.get("CLAUDE_EFFORT"),
                          "launched": environ.get("AGENT_FABRIC_LAUNCH_EFFORT")}
    except (KeyError, ValueError):
        pass
    checks = routing.check(root)

    undrained = undrained_memories(ctx, root)

    # --- drift: what this session was launched with vs. what is bound now ---
    # A rebind from a login shell, or a new default in routing/, does not
    # reach a running session (its prompt and --model are fixed at exec);
    # say so rather than let the two disagree silently (backend-dev-01's
    # session on the previous session default, 2026-09-15).
    role_drift = identity.launch_role_drift(binding)
    model_drift = None
    launch_provider = environ.get("AGENT_FABRIC_LAUNCH_PROVIDER")
    if stamp and launch_provider in ("openrouter", "anthropic"):
        try:
            now = routing.resolve_session(binding.get("role"), ctx["agent"], local, root=root, provider=launch_provider)
            current_session = now.get("composite") or now.get("model")
            if current_session and current_session != stamp:
                model_drift = f"launched on {stamp}, the {launch_provider} session now resolves to {current_session} — relaunch to apply"
        except (KeyError, ValueError):
            pass
    # Effort drift is gated on the launcher having actually DELIVERED a level,
    # exactly as model drift is gated on AGENT_FABRIC_LAUNCH_SESSION_MODEL.
    # Nothing sets this stamp yet: routing/effort.json records what each class
    # SHOULD get, and until the launcher pins it the asked-for level is an
    # intention, not something this session was started with — reporting the
    # gap as drift would accuse the fabric of a change it never made. It is
    # also not a one-way clamp: measured 2026-09-23, one session read `high`
    # and, untouched, `xhigh` an hour later, so the harness re-resolves effort
    # mid-session and a difference in either direction is ordinary.
    effort_drift = None
    effort_stamp = environ.get("AGENT_FABRIC_LAUNCH_EFFORT")
    if effort_stamp and session_effort and session_effort["reported"] \
            and effort_stamp != session_effort["reported"]:
        effort_drift = (f"launched at effort {effort_stamp}, the session is running at "
                        f"{session_effort['reported']} — a settings maxEffortLevel, an organisation cap or a "
                        "model that does not admit the level clamped it (CLAUDE_EFFORT is the harness's read-back)")
    digest = environ.get("AGENT_FABRIC_LAUNCH_PROMPT_DIGEST")
    prompt_drift = prompt_drift_line(digest, ctx["state_dir"])

    # --- host tooling installed from this repository ------------------------
    # moveto is a copy under /usr/local; the source moved on and nobody re-ran
    # install.sh is invisible anywhere else (review, 2026-09-16).
    moveto = hosttools.moveto_drift(root=root)
    python = pinned_python(root)
    journal = episodic_journal(root)

    # --- placement: is this account on the host the registry says? ----------
    # The registry records where an account was provisioned; a session on
    # another host is either a moved account or a stale registry, and either
    # is said here rather than left for a message addressed to the wrong host.
    placement, placement_drift = placement_of(ctx, root, environ)

    jobs = jobs_summary(identity, ctx["agent"])

    report = {
        "agent": ctx["agent"], "host": ctx["host"], "placement": placement,
        "role": binding.get("role"), "project": ctx["project"], "working_copy": ctx["working_copy"],
        "session": binding.get("session"), "binding_updated": binding.get("updated_at"),
        "launched_role": environ.get("AGENT_FABRIC_LAUNCH_ROLE"),
        "launch_prompt_digest": digest,
        "drift": [d for d in (role_drift, model_drift, effort_drift, prompt_drift, placement_drift, fallback_drift, signin_drift) if d] or None,
        "session_effort": session_effort,
        "undrained_memories": undrained,
        "jobs": jobs,
        "api": {"provider": provider, "path": path, "base_url_host": host or None,
                "session_model": stamp or "harness default (not visible from the environment; /status shows it)",
                "launch_profile": environ.get("AGENT_FABRIC_LAUNCH_PROFILE"),
                "pins": {k: v for k, v in pins.items() if v} or "none (harness defaults)",
                "credentials": credentials or "none visible in the environment",
                "claude_sign_in": claude_sign_in(sign_env, sign_file, environ)},
        "capabilities": classes,
        "routing_check": "clean" if not checks else checks,
        "host_tools": {"moveto": moveto, "python": python, "journal": journal},
        "control_plane": root,
    }
    return report, base


def pinned_python(root):
    """The fleet's pinned Python on this host (runtime/python.json): every
    shim runs it, so a host without it is a host where the fabric's
    commands refuse. The answer is python_pin.py's own check."""
    try:
        pp = load("fabric_python_pin", os.path.join(root, "tools", "fabric", "python_pin.py"))
        pin = pp.pin(os.path.join(root, "runtime", "python.json"))
    except Exception as e:  # noqa: BLE001 — a status line, never a traceback
        return {"status": "unknown", "detail": str(e)}
    problem = pp.check(pin)
    if problem:
        return {"status": "missing", "detail": f"{problem}; as root: /usr/bin/python3 {root}/tools/fabric/python_pin.py install"}
    return {"status": "ok", "detail": f"fabric-python {pin['python']} ({pin['release']}), as pinned"}


def episodic_journal(root):
    """This agent's episodic journal (ADR-041): where it is, how many
    episodes, the last one. Read-only: never created here."""
    try:
        ep = load("fabric_episodic", os.path.join(root, "tools", "fabric", "episodic.py"))
        path = ep.db_path()
        if not os.path.exists(path):
            return {"status": "none", "detail": f"none yet ({path}): it starts with the first message sent or received"}
        import sqlite3
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            owner = conn.execute("SELECT owner_agent_id FROM meta").fetchone()
            n, last = conn.execute("SELECT count(*), max(recorded_at) FROM episodes").fetchone()
        finally:
            conn.close()
        mine = ep.own_agent_id()
        if owner and mine and owner[0] != mine:
            return {"status": "foreign", "detail": f"{path} belongs to agent {owner[0]}, not this one ({mine})"}
        return {"status": "ok", "detail": f"{n} episode(s), last {last or '-'} (fabric-history)", "path": path}
    except Exception as e:  # noqa: BLE001 — a status line, never a traceback
        return {"status": "unknown", "detail": str(e)}


def render(report, base):
    """The human report, as lines."""
    out = []
    p = out.append
    provider, path = report["api"]["provider"], report["api"]["path"]
    jobs, undrained, moveto = report["jobs"], report["undrained_memories"], report["host_tools"]["moveto"]
    p(f"agent        {report['agent']}@{report['host']}")
    p(f"role         {report['role'] or '(none — fabric-role bind <role>, from a login shell)'}")
    if report["launched_role"]:
        p(f"launched as  {report['launched_role']}    prompt {report['launch_prompt_digest'] or '(no digest stamped)'}")
    for d in report["drift"] or []:
        p(f"DRIFT        {d}")
    p(f"project      {report['project'] or '(none)'}    working copy  {report['working_copy'] or '(none)'}")
    p(f"session      {report['session'] or '(unknown)'}    binding updated {report['binding_updated'] or '-'}")
    if "error" in jobs:
        p(f"jobs         unreadable: {jobs['error']}")
    else:
        _a = jobs["active"]
        p("jobs         " + (f"active {_a['id']} ({_a['title'][:60]})" if _a else "none active") + "; "
          + ", ".join(f"{jobs[st]} {st}" for st in ("queued", "blocked", "delivered")) + "  (fabric-jobs list)")
    p("")
    p(f"api          {path}")
    p(f"session model {report['api']['session_model']}")
    if report.get("session_effort") and (report["session_effort"].get("asked")
                                        or report["session_effort"].get("launched")):
        _se = report["session_effort"]
        _rep, _stamp = _se.get("reported"), _se.get("launched")
        # "asks for" until the launcher pins one: routing/effort.json is the
        # fabric's intent, and the running level is the harness's own, so the
        # two are printed side by side without either claiming to cause the other.
        # The stamp is what this session was STARTED with, so it is the
        # headline once there is one; the resolved intent only describes what
        # a relaunch would do, and saying it first described another session.
        _head = _stamp or _se["asked"]
        _verb = "session effort %s" % _head if _stamp else "session effort %s (asked; not pinned at launch)" % _head
        p("%s%s" % (_verb, "" if not _rep else (" (running %s)" % _rep if _rep != _head else " (confirmed)")))
    if report['api']['launch_profile']:
        p(f"launch profile {report['api']['launch_profile']}")
    p(f"pins         {report['api']['pins'] if isinstance(report['api']['pins'], str) else ', '.join(f'{k}={v}' for k, v in report['api']['pins'].items())}")
    p(f"credentials  {report['api']['credentials'] if isinstance(report['api']['credentials'], str) else ', '.join(f'{k}: set' for k in report['api']['credentials'])}")
    p(f"claude sign-in {report['api']['claude_sign_in']}" + ("" if provider == "anthropic" and not base else f"  (plain claude's; this session goes to {path} and uses neither)"))
    p("")
    p(f"capabilities on {provider} (fabric-model list for every choice, per provider, with its source):")
    for k, v in report["capabilities"].items():
        p(f"  {k:12} {v}")
    checks = report["routing_check"]
    p(f"routing      {checks if isinstance(checks, str) else str(len(checks)) + ' finding(s): ' + '; '.join(checks)}")
    if undrained:
        p(f"memory       {undrained['drainable']} drainable (roles_class set) and {undrained['no_roles_class']} private "
          f"(none) written since {undrained['since']} — {undrained['dir']}")
    if moveto["installed"]:
        p(f"moveto       {moveto['status']}: {moveto['detail']}" if moveto["status"] == "drift" else f"moveto       {moveto['status']}")
    journal = report["host_tools"].get("journal")
    if journal:
        p(f"journal      {journal['detail']}" if journal["status"] in ("ok", "none") else f"journal      {journal['status'].upper()}: {journal['detail']}")
    python = report["host_tools"].get("python")
    if python:
        p(f"python       {python['detail']}" if python["status"] == "ok" else f"python       {python['status'].upper()}: {python['detail']}")
    p(f"control plane {report['control_plane']}")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else ""
    # The bash exported this before any module was loaded: identity.py reads
    # it at import for its FABRIC_ROOT.
    if not os.environ.get("AGENT_FABRIC_ROOT"):
        os.environ["AGENT_FABRIC_ROOT"] = ROOT
    report, base = build_report(ROOT)
    text = json.dumps(report, indent=2) + "\n" if mode == "--json" else "".join(line + "\n" for line in render(report, base))
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        # Python's own recipe: point stdout at devnull so the interpreter's
        # flush at exit does not raise again. SIGPIPE's default is not
        # restored — it would skip every finally.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
