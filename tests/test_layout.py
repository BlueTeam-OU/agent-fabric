#!/usr/bin/env python3
"""tools/fabric/layout.py: where a project's .agent-fabric/ is read from.
The fabric's own is always the running checkout's, whatever the session's
binding names; another project's still follows the binding (python-dev-01,
seq 10894: lint from a worktree of the fabric read its index against the
main clone the binding named, and reported drift)."""
from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="test_layout.")
    saved = {k: os.environ.get(k) for k in ("AGENT_FABRIC_STATE_DIR", "AGENT_FABRIC_WORKING_COPY", "AGENT_FABRIC_ROOT")}
    try:
        login = pwd.getpwuid(os.geteuid()).pw_name
        host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state")
        os.environ.pop("AGENT_FABRIC_WORKING_COPY", None)
        os.environ.pop("AGENT_FABRIC_ROOT", None)
        import layout
        binding = os.path.join(tmp, "state", "agents", login, "binding.json")
        os.makedirs(os.path.dirname(binding))

        def bind(project: str, working_copy: str) -> None:
            with open(binding, "w") as f:
                json.dump({"agent": login, "host": host, "role": "fabric-coordinator", "project": project,
                           "working_copy": working_copy, "updated_at": "x"}, f)

        print("working_copy_for")
        bind("agent-fabric", os.path.join(tmp, "the-main-clone"))
        check("the fabric's own project is the running checkout, not the clone the binding names",
              layout.working_copy_for("agent-fabric") == layout.FABRIC_ROOT, layout.working_copy_for("agent-fabric"))
        os.environ["AGENT_FABRIC_WORKING_COPY"] = os.path.join(tmp, "the-main-clone")
        check("…nor the one AGENT_FABRIC_WORKING_COPY names",
              layout.working_copy_for("agent-fabric") == layout.FABRIC_ROOT, layout.working_copy_for("agent-fabric"))
        os.environ.pop("AGENT_FABRIC_WORKING_COPY")
        bind("gzapp", os.path.join(tmp, "gzapp"))
        check("another project still follows the binding (positive control)",
              layout.working_copy_for("gzapp") == os.path.join(tmp, "gzapp"), layout.working_copy_for("gzapp"))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
