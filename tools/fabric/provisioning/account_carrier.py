#!/usr/bin/env python3
"""tools/fabric/provisioning/account_carrier.py — the carrier's
install and start for a NEW account, run AS that account by new-agent's step
7c/7e (agent-fabric ADR-064 §5 rules 4 and 11; the cutover's W14).

    account_carrier.py install   the release runtime/interweave/release.json pins
    account_carrier.py start     the roster's profile, as two user units

Both are the control actions of the same name (control/carrier_install.py),
called in-process: a new account has no agentd yet that could be asked, and
the relay, which the daemon's `fabric:control` answers rode on, is not what
provisioning may need. The reply is printed as one JSON line on stdout; the
exit status is the action's: 0 installed / current / started, 1 refused or
failed (the reply's `reason` says which and why), 2 usage.

`start` needs the account's user manager (XDG_RUNTIME_DIR, which the worker
sets) and a roster row countersigned by the coordinator; a row that is not
there is the action's own refusal, said in `reason`, never a start on a
guess.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
# -I leaves the script's directory off sys.path; control/ and gzcoord/ are siblings of provisioning/.
sys.path.insert(0, os.path.dirname(HERE))

OK = {"install": ("installed", "current"), "start": ("started",)}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in OK:
        print("account_carrier: usage: account_carrier.py install|start", file=sys.stderr)
        return 2
    from control import carrier_install
    act = carrier_install.carrier_install if argv[0] == "install" else carrier_install.carrier_start
    reply = act({})
    print(json.dumps(reply, sort_keys=True))
    return 0 if reply.get("status") in OK[argv[0]] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
