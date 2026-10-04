#!/usr/bin/env python3
"""tools/fabric/model_profile.py — this agent's model choices, per provider.

>>> help
    model_profile.py list [--provider P] [--json]     every choice, resolved, with its source layer
    model_profile.py set --provider P <target> <model> write one choice into this agent's local layer
    model_profile.py unset --provider P <target>       remove it (the layers below decide again)
    model_profile.py seed [--provider P]               copy the merged repo defaults into the local layer
    model_profile.py apply                             re-install the agent files (the review pin)

    targets, on either provider: session  code-low  code-medium  code-high  code-plan  code-review
    models: an OpenRouter id (z-ai/glm-5.3) on openrouter; a native Claude id
            (claude-opus-5[1m]) on anthropic; the session may also name a class.

Installed as bin/fabric-model. The AGENT is the Linux login
(runtime/identity.py) and the ROLE is its binding; the file written is
that login's $STATE_DIR/model-profile.local.json — the top layer of the
merge tools/fabric/routing.py does at launch:

    capabilities.json column <- profiles.json defaults <- roles.<role>
                             <- agents.<login> <- this local layer

The repository holds the general default per provider; a choice set here
is the agent's own and outranks it until unset. `seed` writes the merged
defaults in explicitly so the file can be edited by hand — every seeded
value is then a pin that no longer follows the repo default; `unset`
restores following.

The vocabulary is the capability class and the provider's model id. Which
harness tier alias a class rides — and so which ANTHROPIC_DEFAULT_*_MODEL
the launcher exports it under — is the Claude Code adapter's business
(runtime/claude-code/aliases.json) and never appears here. The review
class is the one class that is not an export: its model reaches the
reviewer's agent file (it shares its tier with code-plan and must never
follow it), and it is gated on both providers by routing/policies/
review-grade.json — `set` refuses a model outside it, as the launcher
would. Everything takes effect at the next launch (runtime/openrouter/
launch installs the agent files for its provider); `apply` re-installs
them now, for the provider this session was launched on.

Exit 0 on success, 1 on a refusal, 2 on usage error.
<<< help
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


identity = _load("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
routing = _load("fabric_routing", os.path.join(HERE, "routing.py"))

CLASSES = tuple(routing.load_capabilities()["classes"])
# `<class>-effort` is a target beside `<class>`, because effort layers
# exactly as a model id does (the owner, 2026-09-23): routing/effort.json,
# then the profile layers, then this file. The suffix keeps one flat
# namespace — `set code-high opus` and `set code-high-effort max` are the
# same shape — and the model's own name stays what it always was.
EFFORT_SUFFIX = "-effort"
EFFORT_TARGETS = tuple(k + EFFORT_SUFFIX for k in CLASSES)
TARGETS = {p: ("session",) + CLASSES + EFFORT_TARGETS for p in routing.PROVIDERS}
fabric_writes = _load("fabric_writes", os.path.join(HERE, "fabric_writes.py"))


# The provider this account last launched on, as the launcher records it:
# read by install_agent_files's reader, the one copy (review of #91). From a
# login shell, `apply`, `seed` and `set code-review` wrote the agent files
# for anthropic whatever the account ran on, and a broker session's reviews
# were then refused.
install_agent_files = _load("install_agent_files", os.path.join(HERE, "install_agent_files.py"))


PROVIDER_OF_THIS_SESSION = (os.environ.get("AGENT_FABRIC_LAUNCH_PROVIDER") or install_agent_files.last_launch_provider()
                            or "anthropic")


class Refusal(Exception):
    pass


# ── the local layer ──────────────────────────────────────────────────

def read_local(path: str) -> dict[str, Any]:
    local = routing.load_local(path=path)
    try:
        routing.normalize_layer(local, "local")
    except ValueError as exc:
        raise Refusal(f"{path}: {exc}\n  Fix the file by hand; nothing was written.") from exc
    return local


def migrate(local: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The flat `session`/`capabilities` are the OpenRouter form; a file
    this tool writes spells every choice under its provider, so a flat
    key is moved there (an `anthropic/<id>` session also names plain
    claude's, unless the file already says otherwise). Returns the new
    layer and what moved."""
    out = json.loads(json.dumps(local))
    notes: list[str] = []
    providers = out.setdefault("providers", {})
    if "session" in out:
        session = out.pop("session")
        providers.setdefault("openrouter", {}).setdefault("session", session)
        notes.append(f"session {session!r} -> providers.openrouter.session")
        if isinstance(session, str) and session.startswith("anthropic/") \
                and "session" not in providers.setdefault("anthropic", {}):
            native = session[len("anthropic/"):]
            providers["anthropic"]["session"] = native
            notes.append(f"  (and {native!r} -> providers.anthropic.session, as the flat form implied)")
    if "capabilities" in out:
        caps = out.pop("capabilities") or {}
        target = providers.setdefault("openrouter", {}).setdefault("capabilities", {})
        for klass, model in caps.items():
            target.setdefault(klass, model)
        notes.append(f"capabilities {sorted(caps)} -> providers.openrouter.capabilities")
    for provider in list(providers):
        if not providers[provider]:
            del providers[provider]
    if not providers:
        del out["providers"]
    return out, notes


def place(local: dict[str, Any], provider: str, target: str, model: str | None) -> dict[str, Any]:
    """The local layer with one target set (model) or removed (None)."""
    out = json.loads(json.dumps(local))
    layer = out.setdefault("providers", {}).setdefault(provider, {})
    if target == "session":
        container, key = layer, "session"
    elif target.endswith(EFFORT_SUFFIX):
        container, key = layer.setdefault("effort", {}), target[:-len(EFFORT_SUFFIX)]
    else:
        container, key = layer.setdefault("capabilities", {}), target
    if model is None:
        container.pop(key, None)
    else:
        container[key] = model
    # Drop what became empty, so an unset file reads as no choice at all.
    for sub in ("capabilities", "effort"):
        if sub in layer and not layer[sub]:
            del layer[sub]
    if not layer:
        del out["providers"][provider]
    if not out["providers"]:
        del out["providers"]
    return out


def write_local(path: str, local: dict[str, Any]) -> None:
    # Per-agent state: all-or-nothing, like every write under agents/<login>/
    # (agent-fabric ADR-003). The callers hold agent_lock across the read
    # and this write, so two `fabric-model set` never lose one another.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    identity.atomic_write(path, json.dumps(local, indent=2, ensure_ascii=False) + "\n")


# ── resolution, for the reader ───────────────────────────────────────

def resolved(provider: str, role: str | None, agent: str, local: dict[str, Any]) -> dict[str, Any]:
    """Every target of the provider as {"model", "source", ...}."""
    rows: dict[str, Any] = {}
    try:
        s = routing.resolve_session(role, agent, local, provider=provider)
        rows["session"] = {"model": s["composite"], "source": s["source"], "capability": s.get("capability")}
    except KeyError as exc:
        rows["session"] = {"model": None, "source": None, "error": str(exc)}
    for klass in CLASSES:
        r = routing.resolve(klass, provider, role, agent, local)
        rows[klass] = {"model": r["composite"], "source": r["source"], "via": r["via"],
                       "pinned": r["pinned"]}
        e = r.get("effort") or {}
        rows[klass + EFFORT_SUFFIX] = {"model": e.get("level"), "source": e.get("source"),
                                       "effort": e, "via": e.get("how") or "none", "pinned": bool(e.get("level"))}
    return rows


def print_list(provider: str, rows: dict[str, Any]) -> None:
    print(f"provider {provider}")
    for target, row in rows.items():
        if row.get("error"):
            print(f"  {target:18} (unresolved: {row['error']})")
            continue
        if target == "session":
            extra = f"  (the {row['capability']} class)" if row.get("capability") else ""
            print(f"  {target:18} {row['model']:38} {row['source']}{extra}")
            continue
        if target.endswith(EFFORT_SUFFIX):
            e = row.get("effort") or {}
            # asked -> served whenever they differ, the same phrasing
            # --print and fabric-status use (routing.effort_phrase).
            level = routing.effort_phrase(e).removeprefix("effort ") or "(no level configured for this class)"
            print(f"  {target:18} {level:38} {row['source'] or '-'}")
            continue
        if row["via"] == "harness":
            model, source, how = "(harness default for its tier)", "-", ""
        else:
            model, source = row["model"], row["source"]
            how = "  via the agent file" if row["via"] == "file" else ""
        print(f"  {target:18} {model:38} {source}{how}")


# ── commands ─────────────────────────────────────────────────────────

def check_review_gate(provider: str, role: str | None, agent: str, local: dict[str, Any]) -> None:
    gated = routing.load_review_grade().get("capability", "code-review")
    r = routing.resolve(gated, provider, role, agent, local)
    if not r["pinned"]:
        return
    if not routing.review_grade_ok(r["model"]):
        raise Refusal(f"{gated} on {provider} would resolve to {r['model']!r}, which is not in "
                      "routing/policies/review-grade.json. A review's failure mode is a green PR that "
                      "merges, so the reviewer's model is policy, not a cost dial; extend the grade "
                      "through fabric-coordinator (policies/AUTHORITY.md). Nothing was written.")


def apply_agent_files(quiet: bool = False) -> int:
    """The agent files for the provider THIS session was launched on (an
    unlaunched one: the account's last launch, else anthropic) — one file
    serves one launch."""
    script = os.path.join(FABRIC_ROOT, "runtime", "claude-code", "install-agent-files.sh")
    proc = subprocess.run(["bash", script, "--provider", PROVIDER_OF_THIS_SESSION], capture_output=True, text=True,
                          env={**os.environ, "AGENT_FABRIC_ROOT": FABRIC_ROOT})
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr, file=sys.stderr)
        return proc.returncode
    if not quiet:
        print(proc.stdout, end="")
    return 0


def cmd_list(args: argparse.Namespace, ctx: dict[str, Any], path: str) -> int:
    local = read_local(path)
    providers = [args.provider] if args.provider else list(routing.PROVIDERS)
    report = {"agent": ctx["agent"], "role": ctx["role"], "local": path,
              "providers": {p: resolved(p, ctx["role"], ctx["agent"], local) for p in providers}}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"agent {ctx['agent']}  role {ctx['role'] or '(none bound)'}  local layer {path}"
          f"{'' if os.path.exists(path) else ' (absent)'}")
    for p in providers:
        print_list(p, report["providers"][p])
    return 0


def _change(ctx: dict[str, Any], path: str, provider: str, target: str, model: str | None) -> int:
    if target not in TARGETS[provider]:
        raise Refusal(f"{target!r} is not a target on {provider}; one of: {', '.join(TARGETS[provider])}")
    with identity.agent_lock(ctx["agent"]):
        local, notes = migrate(read_local(path))
        new = place(local, provider, target, model)
        try:
            routing.normalize_layer(new, "local")
        except ValueError as exc:
            raise Refusal(f"{exc}. Nothing was written.") from exc
        check_review_gate(provider, ctx["role"], ctx["agent"], new)
        write_local(path, new)
    for note in notes:
        print(f"  moved: {note}")
    verb = "unset" if model is None else f"set to {model}"
    print(f"{provider}.{target} {verb} in {path}")
    rows = resolved(provider, ctx["role"], ctx["agent"], new)
    row = rows.get(target)
    if row and row.get("model"):
        print(f"  resolves now to {row['model']} (from {row['source']})")
    elif row:
        print("  resolves now to the harness default")
    # A model change moves the effort with it: the level a class asks for
    # is clamped to what the NEW model admits, so changing the model can
    # silently change the thinking — the exact bump that made effort a
    # routed dimension (docs/live-checks/2026-09-23-opus-5-5.md). Say the
    # resulting level here so the two are read in one step.
    if target in CLASSES:
        e = (rows.get(target + EFFORT_SUFFIX) or {}).get("effort") or {}
        phrase = routing.effort_phrase(e)
        print("  %s (%s)" % (phrase, e.get("source")) if phrase
              else "  no effort: this model expresses none, so the class runs on its own default")
    if target == "code-review" and provider == PROVIDER_OF_THIS_SESSION:
        return apply_agent_files()
    print("  takes effect at the next launch (runtime/openrouter/launch)")
    return 0


def cmd_set(args: argparse.Namespace, ctx: dict[str, Any], path: str) -> int:
    return _change(ctx, path, args.provider, args.target, args.model)


def cmd_unset(args: argparse.Namespace, ctx: dict[str, Any], path: str) -> int:
    return _change(ctx, path, args.provider, args.target, None)


def cmd_seed(args: argparse.Namespace, ctx: dict[str, Any], path: str) -> int:
    """The merged result, written in as explicit choices."""
    with identity.agent_lock(ctx["agent"]):
        local, notes = migrate(read_local(path))
        providers = [args.provider] if args.provider else list(routing.PROVIDERS)
        new = local
        written: list[str] = []
        for provider in providers:
            rows = resolved(provider, ctx["role"], ctx["agent"], local)
            for target, row in rows.items():
                if not row.get("model") or row.get("source") in ("local", "harness"):
                    continue  # a harness default has nothing to seed; a local choice is already one
                model = row["model"]
                if target.endswith(EFFORT_SUFFIX):
                    # The INTENT, never the served level. A level is a function
                    # of (intent, model): freezing what today's model happens
                    # to admit records a choice the fabric never made, and it
                    # keeps applying after the model moves under it — seeding
                    # openrouter's code-medium wrote `high` where effort.json
                    # says `medium` (review of 2026-09-23, F2).
                    e = row.get("effort") or {}
                    # …and for an ACKNOWLEDGED class the intent IS the
                    # acknowledgement, which compensates for one (provider,
                    # model) pair and is not this agent's choice. Seeding it
                    # copies a compensation into a layer that now outranks the
                    # acknowledgement it came from, so it survives the model
                    # change the acknowledgement existed for (re-review, N1).
                    if str(e.get("source") or "").startswith("effort.json:providers."):
                        continue
                    model = e.get("intent")
                    if not model:
                        continue
                if target == "session" and row.get("capability"):
                    model = row["capability"]  # a class-named session is seeded as the class
                if provider == "openrouter":
                    model = model.split("@", 1)[0]  # the shim is derived, never configured
                new = place(new, provider, target, model)
                written.append(f"{provider}.{target} = {model}  (was from {row['source']})")
        routing.normalize_layer(new, "local")
        write_local(path, new)
    for note in notes:
        print(f"  moved: {note}")
    for line in written:
        print(f"  {line}")
    print(f"seeded {len(written)} choice(s) into {path}; each is now this agent's own pin "
          "(unset restores the repo default)")
    return apply_agent_files(quiet=True)


def cmd_apply(args: argparse.Namespace, ctx: dict[str, Any], path: str) -> int:
    read_local(path)
    return apply_agent_files()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="this agent's model choices, per provider")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--provider", choices=routing.PROVIDERS); p.add_argument("--json", action="store_true")
    p = sub.add_parser("set"); p.add_argument("--provider", choices=routing.PROVIDERS, required=True)
    p.add_argument("target"); p.add_argument("model")
    p = sub.add_parser("unset"); p.add_argument("--provider", choices=routing.PROVIDERS, required=True)
    p.add_argument("target")
    p = sub.add_parser("seed"); p.add_argument("--provider", choices=routing.PROVIDERS)
    sub.add_parser("apply")
    args = ap.parse_args(argv)

    agent = identity.current_agent()
    ctx = {"agent": agent, "role": identity.read_binding(agent).get("role")}
    path = routing.local_override_path(agent)
    try:
        return {"list": cmd_list, "set": cmd_set, "unset": cmd_unset,
                "seed": cmd_seed, "apply": cmd_apply}[args.cmd](args, ctx, path)
    except Refusal as exc:
        print(f"fabric-model: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
