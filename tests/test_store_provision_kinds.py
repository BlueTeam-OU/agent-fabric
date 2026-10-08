#!/usr/bin/env python3
"""fabric-secrets provision's `all` (tools/fabric/store_provision.py
placed_logins): every placed agent, never a human login (ADR-044 rule 4),
which holds none of an agent's shared credentials or minted keys."""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="test_store_provision_kinds.") as t:
        reg = os.path.join(t, "registry.json")
        with open(reg, "w", encoding="utf-8") as f:
            json.dump({"placement": {"web-dev-01": "h", "deck-human": "h", "db-admin": "h"},
                       "kinds": {"deck-human": "human"}}, f)
        os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = reg
        import store_provision
        got = store_provision.placed_logins()
    ok = got == ["db-admin", "web-dev-01"]
    print(f"  {'ok  ' if ok else 'FAIL'} all is every placed agent, never the human" + ("" if ok else f": {got}"))
    print(f"\n{'all passed' if ok else '1 FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
