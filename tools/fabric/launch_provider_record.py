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
import json
import os
from collections.abc import Callable

RECORD = "launch-provider.json"


def write(state_dir: str, provider: str, transport: str = "", keep_existing: bool = False,
          say: Callable[[str], None] = lambda m: None) -> bool:
    """Atomic; a failure is said, not fatal (the caller's files are installed).
    True when this call wrote it. `keep_existing` is for provisioning, which
    records a guess before the account has launched and must never put it over
    the account's own launch: the record is linked into place, which refuses
    rather than replace, and False is returned."""
    path = os.path.join(state_dir, RECORD)
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            # `transport` only when it is not direct: install_agent_files reads "provider" alone.
            json.dump({"provider": provider, **({"transport": transport} if transport else {}),
                       "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
            fh.write("\n")
        if not keep_existing:
            os.replace(tmp, path)
            return True
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        finally:
            os.unlink(tmp)
        return True
    except OSError as exc:
        say(f"launch: could not record the provider in {path}: {exc}")
        return False
