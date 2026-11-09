#!/usr/bin/env python3
"""tools/fabric/transport_calls.py (agent-fabric ADR-067): a relay api() call or a carrier adapter import outside
tools/fabric/gzcoord/transport/ is a finding unless policies/transport-calls.json names the module with its reason. Each
finding kind has a positive control (the planted site is found) beside the negatives that must stay quiet; the checker is
also run as the command on a scratch repository, and the inbox's and the sender's own modules are judged as they are in this
tree, with no policy to excuse them. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import transport_calls as T  # noqa: E402

fails = 0
SEND = "tools/fabric/gzcoord/send.py"


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def found(rel: str, text: str, allowed: dict[str, str] | None = None) -> list[str]:
    return T.scan(rel, text, allowed or {})


def main() -> int:
    # ── the relay's api(): the planted call, in the shapes the callers have written it ───────────────────────────
    for label, src in (
        ("a literal path through the inbox", 'inbox.api(tok, "/api/send", relay_url, method="POST")\n'),
        ("a bare api() with a literal path", 'api(tok, "/api/ack", url)\n'),
        ("an f-string path", 'api(tok, f"/api/wait?{q}", url)\n'),
        ("a concatenated path", 'api("/api/wait?" + urlencode(q))\n'),
        ("a path in a keyword", 'api(tok, path="/api/messages")\n'),
        ("a variable path with the relay's url named", 'api(tok, p, relay_url=cfg["relay_url"], **init)\n'),
        ("the relay's url positional", 'inbox.api(tok, path, relay_url)\n'),
        ("the relay's url as an attribute in an argument", 'api(tok, q, self.relay_url, method="POST")\n'),
        ("three positional arguments", 'relay.api(tok, p, u)\n'),
        ("a call through an alias of the relay's api", 'from .inbox_parts.relay import api as post\npost(tok, "/api/send", u)\n'),
        ("the call in a nested function", 'def f():\n    def g():\n        return client.api(t, "/api/x")\n'),
    ):
        got = found(SEND, src)
        check(f"relay: {label} is one finding in send.py", len(got) == 1 and got[0].startswith(f"{SEND}:") and "ADR-067" in got[0],
              str(got))
    for label, src in (
        ("gh.api of a repository path", 'gh.api("repos/o/r/pulls/7")\n'),
        ("gh.api of a path that starts like the relay's", 'gh.api("/api/v3/x")\n'),
        ("an api() with a path that is not the relay's", 'api("/repos/x")\n'),
        ("an alias import that is never called", 'from .inbox_parts.relay import api as post\n'),
        ("an api imported from a module that is not the relay's, called with one argument", 'from x import api as post\npost("p")\n'),
        ("a function named api that is only defined", 'def api(tok, path):\n    return path\n'),
        ("a string that mentions /api/ and is not a call's argument", 'URL = "/api/send"\n'),
        ("a call of something else with a relay path", 'fetch(tok, "/api/send")\n'),
    ):
        check(f"relay: {label} is no finding", found(SEND, src) == [], str(found(SEND, src)))

    # ── the carrier's adapter ────────────────────────────────────────────────────────────────────────────────────
    for label, src in (
        ("from .carrier import adapter", "from .carrier import adapter\n"),
        ("from gzcoord.carrier import adapter as A", "from gzcoord.carrier import adapter as A\n"),
        ("from gzcoord.carrier import CARRIER_NAME, adapter", "from gzcoord.carrier import CARRIER_NAME, adapter\n"),
        ("from gzcoord.carrier.adapter import Adapter", "from gzcoord.carrier.adapter import Adapter\n"),
        ("import gzcoord.carrier.adapter", "import gzcoord.carrier.adapter\n"),
        ("from . import adapter (inside the carrier package)", "from . import adapter\n"),
        ("an import inside a function", "def f():\n    from .carrier import adapter\n"),
    ):
        got = found("tools/fabric/gzcoord/inbox.py", src)
        check(f"carrier: {label} is one finding", len(got) == 1 and "adapter" in got[0], str(got))
    for label, src in (
        ("from .carrier import CARRIER_NAME", "from .carrier import CARRIER_NAME\n"),
        ("from .carrier import ledger, arrivals", "from .carrier import ledger, arrivals\n"),
        ("from gzcoord.carrier import parity, record", "from gzcoord.carrier import parity, record\n"),
        ("an unrelated adapter", "from something import adapter\n"),
    ):
        check(f"carrier: {label} is no finding", found("tools/fabric/gzcoord/inbox.py", src) == [])

    # ── who is judged ────────────────────────────────────────────────────────────────────────────────────────────
    plant = 'inbox.api(tok, "/api/send", url)\nfrom .carrier import adapter\n'
    check("the transport package is not judged, nor a test, nor the modules that define the calls, nor a file that is not Python",
          all(found(r, plant) == [] for r in (
              "tools/fabric/gzcoord/transport/relay.py", "tools/fabric/gzcoord/transport/mux.py", "tests/test_x.py",
              "tools/fabric/gzcoord/inbox_parts/relay.py", "tools/fabric/gzcoord/carrier/adapter.py", "docs/x.md")))
    check("a module of the same name elsewhere is judged (the package is a path, not a name)",
          len(found("tools/fabric/other/transport/relay.py", plant)) == 2)
    check("both findings of one module are reported, in line order", [x.split(":")[1] for x in found(SEND, plant)] == ["1", "2"])
    check("a module the policy names is admitted whole", found(SEND, plant, {SEND: "why"}) == [])
    check("a module that does not parse is not this rule's", found(SEND, "def (:\n") == [])

    # ── the policy ───────────────────────────────────────────────────────────────────────────────────────────────
    check("parse_calls keeps string reasons and drops the rest",
          T.parse_calls(json.dumps({"calls": {"a.py": "why", "b.py": "", "c.py": 3, "d.py": "  "}})) == {"a.py": "why"}
          and T.parse_calls("{}") == {} and T.parse_calls("[]") == {})
    try:
        T.parse_calls("{not json")
        bad = False
    except ValueError:
        bad = True
    check("parse_calls refuses what is not JSON", bad)

    # ── the tree, and the command, on a scratch repository ───────────────────────────────────────────────────────
    scratch = tempfile.mkdtemp(prefix="tc-")
    try:
        def put(rel: str, text: str) -> None:
            os.makedirs(os.path.dirname(os.path.join(scratch, rel)), exist_ok=True)
            with open(os.path.join(scratch, rel), "w", encoding="utf-8") as fh:
                fh.write(text)

        def policy(calls: dict) -> None:
            put(T.POLICY, json.dumps({"calls": calls}))

        env = {"PATH": os.environ.get("PATH", ""), "HOME": scratch, "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_CONFIG_SYSTEM": os.devnull}

        def command() -> subprocess.CompletedProcess:
            subprocess.run(["git", "-C", scratch, "add", "-A"], env=env, check=True, timeout=60, capture_output=True)
            return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "transport_calls.py"), scratch],
                                  env=env, capture_output=True, text=True, timeout=120)
        subprocess.run(["git", "init", "-q", scratch], env=env, check=True, timeout=60)
        put("tools/fabric/gzcoord/send.py", "def main():\n    return 0\n")
        put("tools/fabric/gzcoord/transport/relay.py", plant)
        put("tests/test_x.py", plant)
        policy({})
        r = command()
        check("clean tree: no output, exit 0", (r.returncode, r.stdout, r.stderr) == (0, "", ""), f"{r.returncode} {r.stdout}{r.stderr}")
        put("tools/fabric/gzcoord/send.py", "def main():\n    return inbox.api(tok, '/api/send', url)\n")
        r = command()
        check("positive control: a relay api() call planted in send.py is red, with the line and the policy to name",
              r.returncode == 1 and r.stdout.startswith(f"{SEND}:2: a call of the relay's api()") and T.POLICY in r.stdout,
              f"{r.returncode} {r.stdout}{r.stderr}")
        policy({SEND: "a reason"})
        r = command()
        check("... and green again once the policy names it", (r.returncode, r.stdout) == (0, ""), f"{r.returncode} {r.stdout}")
        put("tools/fabric/gzcoord/send.py", "def main():\n    return 0\n")
        r = command()
        check("an entry whose module no longer calls the relay is a finding (the gap's entry leaves with its fix)",
              r.returncode == 1 and f"{SEND} admits nothing" in r.stdout, f"{r.returncode} {r.stdout}")
        policy({"tools/fabric/gone.py": "x", "tools/fabric/gzcoord/transport/relay.py": "x", "tests/test_x.py": "x"})
        r = command()
        check("an entry for a file that is not tracked, and one for a path that is never judged, are findings",
              r.returncode == 1 and "gone.py is listed but is not a tracked file" in r.stdout
              and "transport/relay.py admits nothing" in r.stdout and "tests/test_x.py admits nothing" in r.stdout, r.stdout)
        put(T.POLICY, "{not json")
        r = command()
        check("a policy that is not JSON is said once and judges nothing", r.returncode == 1 and r.stdout.count("\n") == 1
              and "cannot be read as JSON" in r.stdout, r.stdout)
        os.remove(os.path.join(scratch, T.POLICY))
        put("tools/fabric/gzcoord/send.py", "from .carrier import adapter\n")
        r = command()
        check("no policy file is an empty policy: the adapter import is a finding",
              r.returncode == 1 and "an import of the carrier's adapter" in r.stdout, r.stdout)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "transport_calls.py"),
                            os.path.join(scratch, "not-a-repository")], env=env, capture_output=True, text=True, timeout=60)
        check("a root that cannot be listed is exit 2 with one line, not a traceback",
              r.returncode == 2 and "Traceback" not in r.stderr and r.stderr.count("\n") == 1, f"{r.returncode} {r.stderr}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # ── this tree: the inbox and the sender hold no site of their own ────────────────────────────────────────────
    own = [p for d in ("tools/fabric/gzcoord",) for p in T.tracked_files(ROOT) if p.startswith(d + "/") and T.judged_path(p)]
    sites = [f for rel in own for f in T.scan(rel, open(os.path.join(ROOT, rel), encoding="utf-8").read(), {})]
    check("in this tree no module of gzcoord outside transport/ calls the relay's api() or imports the carrier's adapter, "
          "with no policy to excuse it", own and sites == [], "\n".join(sites))
    check("... and inbox.py, send.py and inbox_parts/watch.py are among the modules judged",
          {"tools/fabric/gzcoord/inbox.py", SEND, "tools/fabric/gzcoord/inbox_parts/watch.py"} <= set(own))
    print(f"\ntest_transport_calls: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
