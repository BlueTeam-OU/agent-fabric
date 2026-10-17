#!/usr/bin/env python3
"""tools/fabric/fabric_secrets.py — an identity's secrets, from its own store
(ADR-038), into the places the tools read them: the verb dispatch of
runtime/provisioning/secrets/fabric-secrets (agent-fabric ADR-040 Wave 9,
batch 1). Runs AS THE ACCOUNT. The runtime path is the contract
(bin/fabric-secrets, moveto and the control agent call it); it is a forwarder
that checks the pinned Python and execs this.

THE CONTRACT (frozen from the bash, ADR-040 §5 rule 3)
  fabric-secrets store …       tools/fabric/secret_store.py
  fabric-secrets provision …   tools/fabric/store_provision.py (a parent fills
                               its children's stores)
  fabric-secrets selftest …    tools/fabric/secret_selftest.py (an own secret
                               set, used, removed)
  fabric-secrets state …       tools/fabric/secret_state.py (this login's working state backed
                               up to its own store; its parent's backup carries it to Proton)
  fabric-secrets child …       tools/fabric/secret_child.py (a parent installs its
                               children's role addenda, ADR-060)
  fabric-secrets <anything>    tools/fabric/secrets_sync.py with ALL the
                               arguments, the first included: `sync`, `status`,
                               no argument, an unknown word, an empty one. The
                               default is the sync module's, which answers its
                               own usage.
  The verb is matched exactly and only as the first argument; its module gets
  the rest. stdout, stderr and exit status are the module's: this process is
  replaced by it (os.execv), on the interpreter the forwarder named
  (AGENT_FABRIC_PYTHON, the one variable read; else sys.executable). The
  environment is not changed here.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = {"store": "secret_store.py", "provision": "store_provision.py", "selftest": "secret_selftest.py",
           "state": "secret_state.py", "child": "secret_child.py"}
DEFAULT = "secrets_sync.py"


def main(argv: list[str]) -> int:
    verb = argv[1] if len(argv) > 1 else ""
    if verb in MODULES:
        rest = argv[2:]
        module = MODULES[verb]
    else:
        rest, module = argv[1:], DEFAULT
    py = os.environ.get("AGENT_FABRIC_PYTHON") or sys.executable
    os.execv(py, [py, os.path.join(HERE, module), *rest])
    return 127  # unreachable: execv returns only by raising


if __name__ == "__main__":
    sys.exit(main(sys.argv))
