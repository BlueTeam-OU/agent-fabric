#!/usr/bin/env python3
"""Tests for runtime/claude-code/retire-doppler.py: what Doppler left in an
account is removed, only that, and a dry run removes nothing."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "runtime", "claude-code", "retire-doppler.py")
spec = importlib.util.spec_from_file_location("retire_doppler", TOOL)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as home:
        os.makedirs(os.path.join(home, ".doppler", "fallback"))
        open(os.path.join(home, ".doppler", ".doppler.yaml"), "w").write("token: fixture\n")
        os.makedirs(os.path.join(home, ".local", "bin"))
        open(os.path.join(home, ".local", "bin", "doppler"), "w").write("#!/bin/sh\n")
        open(os.path.join(home, ".local", "bin", "fabric-status"), "w").write("#!/bin/sh\n")
        os.makedirs(os.path.join(home, ".config", "agent-fabric"))
        open(os.path.join(home, ".config", "agent-fabric", "secrets-source"), "w").write("store\n")
        open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), "w").write("# kept\n")
        env = {**os.environ, "HOME": home}
        p = subprocess.run([sys.executable, TOOL, "--dry-run"], env=env, capture_output=True, text=True)
        check("a dry run names all three and removes nothing", p.returncode == 0 and "would remove" in p.stdout
              and os.path.exists(os.path.join(home, ".doppler")), p.stdout)
        p = subprocess.run([sys.executable, TOOL], env=env, capture_output=True, text=True)
        check("the config and token, the CLI copy and the source file are removed",
              p.returncode == 0 and not any(os.path.lexists(os.path.join(home, x)) for x in r.RETIRED), p.stdout + p.stderr)
        check("…and nothing else: the other commands and secrets.env stay",
              os.path.exists(os.path.join(home, ".local", "bin", "fabric-status"))
              and os.path.exists(os.path.join(home, ".config", "agent-fabric", "secrets.env")))
        check("the line names what went, and no value", "~/.doppler" in p.stdout and "fixture" not in p.stdout, p.stdout)
        p = subprocess.run([sys.executable, TOOL], env=env, capture_output=True, text=True)
        check("a second run is silent: nothing left to remove", p.returncode == 0 and p.stdout == "", p.stdout)
    boot = open(os.path.join(HERE, "runtime", "claude-code", "bootstrap.sh"), encoding="utf-8").read()
    check("bootstrap runs it, and a failure counts as not written",
          'retire-doppler.py" "${dry_arg[@]}" || failed=$((failed+1))' in boot)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
