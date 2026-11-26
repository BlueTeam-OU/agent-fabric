"""The names of the control ops, apart from the code that answers them: control/ops/__init__ imports every op's module
(usage, keys, host, memory, ...), which a caller that only asks "is this word an op" -- fabric-ctl's argument parser --
must not pay for. control.ops re-exports both lists, the same objects. Imports gzcoord.carrier, so tools/fabric must
already be on sys.path (control.opsutil puts it there)."""
from __future__ import annotations

from gzcoord.carrier import CARRIER_NAME

OPS = ["ping", "identity", "usage", "keys", "fabric", "session", "script", "recall", "tokens", "memory", "host", "disk",
       "accounts", "upgrade", "secrets-sync", "status", "presence", "jobs", "jobs-add", "job-state", "tools", "tools-install", "local", "local-prune",
       "secrets-selftest", "pool-add", "pool-list", "pool-claim", "gateway", "gateway-install", CARRIER_NAME, f"{CARRIER_NAME}-install", f"{CARRIER_NAME}-start", f"{CARRIER_NAME}-stop", f"{CARRIER_NAME}-evidence", "branches", "branches-sweep", "restart",
       "switch", "state", "drift", "clone", "hold", "unhold", f"{CARRIER_NAME}-mode", "deaf"]

# Answered for any placed account, not only an operator: whether a session
# is running is what every sender needs before it writes to one, and it
# names nothing a relay reader could not already infer (the owner,
# 2026-09-25: presence moves from HELLO/GOODBYE, now retired, to the
# control plane). And a role's pool (pool, ADR-037 rule 9): every placed
# agent lists its role's pool and claims from it, for itself. And one job's
# state, to the sender of the request it was taken from (job-state,
# control/jobs.py): the blocker `job:` of a login that is not an operator.
# And an account's newest state record (state, control/state_record.py): what
# the relay's state channel showed to any holder of its token, read by the
# pool holder and by read_waits' caller as well as by the operator.
PUBLIC_OPS = ["presence", "pool-list", "pool-claim", "job-state", "state"]
