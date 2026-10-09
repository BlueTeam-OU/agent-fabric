#!/usr/bin/env python3
"""The hosts registry's schema admits what the fabric writes into it.

`fabric-ctl keygen` writes a host's `operator_key`; the schema had no such
property, so the first real key failed lint on the commit that registered
it (2026-09-25). This builds a scratch registry with a key the real
generator makes, and one that is malformed, and runs lint's own check.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import lint  # noqa: E402


def generated_key() -> str:
    js = "import('./runtime/control/sign.mjs').then(s => console.log(s.generateOperatorKey().publicKeySpec))"
    return subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def findings_for(tmp: str, host_extra: dict) -> list[str]:
    root = os.path.join(tmp, "fabric")
    shutil.copytree(os.path.join(ROOT, "runtime", "hosts", "schema"), os.path.join(root, "runtime", "hosts", "schema"))
    reg = {"version": 1, "description": "fixture", "placement": {"user": "h"},
           "hosts": {"h": {"platform": "fedora", "ssh": None, "operator": "user", "fabric": "~/projects/agent-fabric", **host_extra}}}
    with open(os.path.join(root, "runtime", "hosts", "registry.json"), "w", encoding="utf-8") as fh:
        json.dump(reg, fh)
    return lint.host_registry_findings(root)


def test_a_generated_operator_key_is_admitted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        key = generated_key()
        assert key.startswith("ed25519:"), key
        assert findings_for(tmp, {"operator_key": key}) == [], "keygen's own output must pass the schema"


def test_a_host_without_a_key_is_admitted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert findings_for(tmp, {}) == [], "the key is optional: read ops need none"


def test_a_malformed_key_is_refused() -> None:
    good = generated_key()
    truncated = good[:len("ed25519:") + 47] + "="   # the shape a hand-pasted, cut-short key takes: base64, but not an SPKI
    for bad in ("ed25519:####", "rsa:AAAA", "MCowBQYDK2VwAyEA", truncated, good[:-1]):
        with tempfile.TemporaryDirectory() as tmp:
            f = findings_for(tmp, {"operator_key": bad})
            assert f and "operator_key" in " ".join(f), (bad, f)


def test_a_registered_key_parses_as_a_daemon_reads_it() -> None:
    """A registry's key, through the same parser the daemons use: a key the
    schema admitted but publicKeyFrom refused would disable every action with
    a refusal that blames the signature, not the registry. The registry is a
    fixture holding keys the generator makes; the committed one is read by
    tests/test_operator_data.py, as lint admits a key by its shape only."""
    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "placement": {}, "hosts": {"h1": {"operator": "boss", "operator_key": generated_key()},
                                                                "h2": {}, "h3": {"operator_key": generated_key()}}}, fh)
        js = "import('./runtime/control/agentd.mjs').then(m => console.log(JSON.stringify([...m.operatorKeys(process.argv[1]).keys()])))"
        out = subprocess.run(["node", "-e", js, reg], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        assert sorted(json.loads(out)) == ["h1/boss", "h3/user"], out


def test_keygen_writes_a_registry_the_schema_admits() -> None:
    """keygen's own output, not a hand-made fixture: the first real key
    failed lint because nothing had put the writer's output through the
    schema. The store is faked; the registry keygen writes is then linted."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "fabric")
        shutil.copytree(os.path.join(ROOT, "runtime", "hosts", "schema"), os.path.join(root, "runtime", "hosts", "schema"))
        reg_path = os.path.join(root, "runtime", "hosts", "registry.json")
        with open(reg_path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "description": "fixture", "placement": {"user": "h"},
                       "hosts": {"h": {"platform": "fedora", "ssh": None, "operator": "user", "fabric": "~/projects/agent-fabric"}}}, fh)
        js = ("import('./runtime/control/ctl.mjs').then(m => { console.log = () => {}; "
              "process.exit(m.keygen({ force: false }, { registry: process.env.REG, who: { host: 'h', agent: 'user' }, "
              "exec: () => '' })); })")
        run = subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "REG": reg_path})
        assert run.returncode == 0, run.stderr[-600:]
        assert json.load(open(reg_path, encoding="utf-8"))["hosts"]["h"].get("operator_key", "").startswith("ed25519:")
        assert lint.host_registry_findings(root) == [], lint.host_registry_findings(root)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
