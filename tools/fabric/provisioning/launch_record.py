#!/usr/bin/env python3
"""tools/fabric/provisioning/launch_record.py — the provider a new account's
first launch comes up on, recorded at provisioning (j125; seen on
rust-ui-dev-02, 2026-10-11: no launch-provider.json, so the first Fleet Deck
launch took the launcher's default instead of the account's).

    launch_record.py <provider>      run AS the account: write its launch-provider.json

The record is the one tools/fabric/launcher/session.py record_launch_provider
writes after a launch, in the same shape and place (its readers are
install_agent_files.last_launch_provider and fabric-resume); the account's own first launch
replaces it, and an existing record is never overwritten.

choose() is the worker's decision, from what provisioning already holds and
nothing it has to invent: routing/profiles.json's launch_provider for the
account when a layer names one (what fabric-resume would have chosen), else
the Claude account new-agent was told about — one assigned is the anthropic
column, `--no-claude-account` is "the broker path only" (new_agent.py), so
openrouter. A human has no session and no record.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))

RECORD = "launch-provider.json"
PROVIDERS = ("anthropic", "openrouter")


def profile_provider(profiles: str, login: str, role: str | None) -> str | None:
    """routing/profiles.json's launch_provider, nearest layer first (the agent's, the role's, the defaults'), as
    fabric-resume reads it for an account that never launched (tools/fabric/resume.py profile_provider, which this
    does not import: the worker runs in fixtures and on far hosts without the launcher's modules). Unreadable or
    not the schema's shape is none, as there."""
    try:
        with open(profiles, encoding="utf-8") as fh:
            prof = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(prof, dict):
        return None
    agents, roles = prof.get("agents"), prof.get("roles")
    for layer in (agents.get(login) if isinstance(agents, dict) else None,
                  roles.get(role or "") if isinstance(roles, dict) else None, prof.get("defaults")):
        p = layer.get("launch_provider") if isinstance(layer, dict) else None
        if p in (*PROVIDERS, "gateway"):
            return p
    return None


def choose(profile: str | None, account: str, no_account: bool) -> str | None:
    if profile in (*PROVIDERS, "gateway"):
        # "gateway" is the anthropic column reached through the gateway (launcher/gateway.py); the record
        # names the column, and the transport is the launcher's to stamp.
        return "anthropic" if profile == "gateway" else profile
    if account:
        return "anthropic"
    if no_account:
        return "openrouter"
    return None


def write(state_dir: str, provider: str) -> bool:
    """False when a record is already there: the account's own launch wrote it,
    and a re-run of new-agent must not put a guess over a fact."""
    path = os.path.join(state_dir, RECORD)
    os.makedirs(state_dir, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"provider": provider, "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
            fh.write("\n")
        try:
            os.link(tmp, path)       # refuses rather than replace
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in PROVIDERS:
        print(f"launch_record: usage: launch_record.py {'|'.join(PROVIDERS)}", file=sys.stderr)
        return 2
    # Here, not at the top: the module is imported by the worker, whose fixture fabric (tests/test_new_agent_cli.py)
    # holds no fabric_writes, and only this entry, run in the account's own checkout, needs it.
    sys.path.insert(0, os.path.dirname(HERE))
    import fabric_writes
    try:
        kept = not write(fabric_writes.state_dir(), argv[0])
    except OSError as exc:
        print(f"launch_record: {exc.filename or ''}: {exc.strerror}", file=sys.stderr)
        return 1
    if kept:
        print("launch_record: the account already has a launch record; kept", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
