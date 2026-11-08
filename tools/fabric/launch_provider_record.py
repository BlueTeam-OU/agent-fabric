"""tools/fabric/launch_provider_record.py — the one writer of an account's
launch-provider.json (<state>/agents/<login>/): the provider the agent files
were last installed for, so a run with no provider of its own (bootstrap from
the control agent, an upgrade, fabric-model apply) installs for this one
rather than for anthropic (install_agent_files.py reads it; fabric-resume
reads it and `transport`). Standard library only, because two callers with
different surroundings share it: the launcher (launcher/session.py, after a
launch) and provisioning (provisioning/launch_record.py, before the account
has launched, in a checkout that holds nothing of the launcher).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
from collections.abc import Callable

# By path: provisioning runs this in a checkout whose tools/fabric/ is not on sys.path.
_spec = importlib.util.spec_from_file_location(
    "fabric_launch_provider_record_identity",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runtime", "identity.py"))
identity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(identity)

RECORD = "launch-provider.json"


def write(state_dir: str, provider: str, transport: str = "", keep_existing: bool = False,
          say: Callable[[str], None] = lambda m: None) -> bool:
    """Atomic; a failure is said, not fatal (the caller's files are installed).
    True when this call wrote it. `keep_existing` is for provisioning, which
    records a guess before the account has launched and must never put it over
    the account's own launch: the record is linked into place, which refuses
    rather than replace, and False is returned."""
    path = os.path.join(state_dir, RECORD)
    try:
        os.makedirs(state_dir, exist_ok=True)
        # `transport` only when it is not direct: install_agent_files reads "provider" alone.
        doc = {"provider": provider, **({"transport": transport} if transport else {}),
               "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            identity.atomic_write(path, json.dumps(doc) + "\n", 0o600, replace=not keep_existing)
        except FileExistsError:
            return False
        return True
    except OSError as exc:
        say(f"launch: could not record the provider in {path}: {exc}")
        return False
