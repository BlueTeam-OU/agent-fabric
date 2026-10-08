#!/usr/bin/env python3
"""The readers moved onto roots (agent-fabric ADR-045 §5 rules 1-3) follow
AGENT_FABRIC_OPERATOR and, with it unset, still read the engine's own tree.
Each case builds its instance files under the test's own temp dir, with
names no engine file carries, so a reader that still joined the engine's tree
could not pass."""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_roots_seam import operator  # noqa: E402


def write(path: str, doc: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc if isinstance(doc, str) else json.dumps(doc))


class unset_operator:
    """No operator, no engine override: the readers' own-tree default."""
    def __enter__(self):
        self.saved = {k: os.environ.pop(k, None) for k in ("AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_ROOT")}

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v


def case_relay_reads_integrations_from_the_operator() -> None:
    import relay
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        write(os.path.join(op, "projects", "opproj", "integration", "gzcoord", "config.json"),
              {"relay_url": "https://op.example", "channel": "op-chan"})
        with operator(op):
            assert relay.integrated_projects() == ["opproj"], relay.integrated_projects()
            assert relay.channels(["opproj"], {}) == ([("https://op.example", "op-chan")], [])
        with unset_operator():
            assert relay.config_path("agent-fabric").startswith(ROOT + os.sep)
            assert "opproj" not in relay.integrated_projects()


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
    failures = 0
    for case in cases:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
