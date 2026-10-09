#!/usr/bin/env python3
"""runtime/openrouter/model-audit.sh against the outputs the bash script gave
(tests/fixtures/model-audit/*.out, taken from it under LC_ALL=C before the
port, ADR-040 Wave 9), byte for byte, in seven environments: none set, a
broker launch, hostile values (a newline that poses as a variable, a URL with
userinfo and a query, multibyte), a look-alike host, a string that is no URL,
a port that is no number, and an environment that is not in sorted order. Plus
what the golden files cannot say by themselves: no secret value in any of
them, and a positive control that the audit does print what it is allowed to.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "runtime", "openrouter", "model-audit.sh")
GOLDEN = os.path.join(HERE, "tests", "fixtures", "model-audit")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with open(os.path.join(GOLDEN, "cases.json"), encoding="utf-8") as fh:
        cases = json.load(fh)
    base = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    if os.environ.get("AGENT_FABRIC_PYTHON"):
        base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
    outs = {}
    for name, env in cases.items():
        r = subprocess.run([TOOL], env={**base, **env}, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        outs[name] = r.stdout
        with open(os.path.join(GOLDEN, f"{name}.out"), "rb") as fh:
            golden = fh.read()
        check(f"{name}: the bash script's output, byte for byte, exit 0, nothing on stderr",
              r.stdout == golden and r.returncode == 0 and not r.stderr, (r.returncode, r.stderr[:200], r.stdout[:200]))
    secrets = ("sk-or-v1-SECRET", "pw@", "api_key=SECRET", "Bearer SECRET", "not a url at all with secret", "frag")
    check("no secret value reaches any output", not any(s.encode() in o for o in outs.values() for s in secrets),
          [s for s in secrets if any(s.encode() in o for o in outs.values())])
    check("positive control: an alias pin and the routing URL are printed",
          b"  haiku      z-ai/glm-5.3-flash@preset/glm2claude-shim" in outs["broker"] and b"ANTHROPIC_BASE_URL = https://openrouter.ai\n" in outs["broker"]
          and b"routed through OpenRouter" in outs["broker"] and b"routed through OpenRouter" not in outs["lookalike"], outs["broker"][:300])
    r = subprocess.run([TOOL], env={**base, "PATH": "/usr/bin:/bin", "ANTHROPIC_BASE_URL": "https://o.example"}, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=60, stdin=subprocess.DEVNULL, bufsize=0)
    check("the report is one piece of stdout, exit 0", r.returncode == 0 and r.stdout.endswith(b"do not parse it.)\n"))
    print(f"\ntest_model_audit: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
