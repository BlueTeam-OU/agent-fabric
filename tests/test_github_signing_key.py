#!/usr/bin/env python3
"""tools/fabric/provisioning/github_signing_key.py (ADR-057 §5 rule 6): an
agent's signing subkey registered on GitHub in SSH form, against a fake `gh`
that keeps the account's signing keys in a file and records every call, and a
real gpg for the SSH form. What is proved: the key sent is the one `gpg
--export-ssh-key` makes of the agent's signing subkey, under the title the
rule gives; a second add is "present"; a conflicting title or key is refused
and nothing is overwritten; remove deletes that login's keys and no other's;
--dry-run sends nothing; a token without the scope is a refusal that names
the fix.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "provisioning"))
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
from signing_fixture import drop_key, make_agent_key  # noqa: E402
import github_signing_key as gsk  # noqa: E402

T = tempfile.mkdtemp(prefix="test_github_signing_key.")
GNUPG, PRIMARY, SUB = make_agent_key(T)
ROOT = f"{T}/fabric"
KEYS = f"{ROOT}/identities/keys"
ACCOUNT = f"{T}/account.json"
CALLS = f"{T}/calls.log"
BIN = f"{T}/bin"
AGENT_ID = "01a11a69-f363-7de9-b212-88785c3128e2"
fails = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def fixture() -> None:
    os.makedirs(KEYS)
    os.makedirs(BIN)
    armored = subprocess.run(["gpg", "--homedir", GNUPG, "--armor", "--export", PRIMARY], capture_output=True, check=True, timeout=30).stdout
    with open(f"{KEYS}/{AGENT_ID}.asc", "wb") as f:
        f.write(armored)
    with open(f"{KEYS}/lineage.json", "w", encoding="utf-8") as f:
        json.dump({AGENT_ID: {"born": "2026-10-08T00:00:00.000Z", "fingerprint": PRIMARY, "login": "python-dev-03", "parent": None},
                   "01a00000-0000-7000-8000-000000000000": {"born": "2026-01-01T00:00:00.000Z", "fingerprint": "X", "login": "other", "parent": None}}, f)
    with open(ACCOUNT, "w", encoding="utf-8") as f:
        json.dump([], f)
    with open(f"{BIN}/gh", "w", encoding="utf-8") as f:
        f.write(f'''#!{sys.executable}
import json, os, sys
a = sys.argv[1:]
open({CALLS!r}, "a").write(" ".join(a) + "\\n")
if os.environ.get("FAKE_GH_MODE") == "noscope":
    sys.stderr.write('gh: This API operation needs the "admin:ssh_signing_key" scope. To request it, run:  gh auth refresh -h github.com -s admin:ssh_signing_key\\n')
    sys.exit(4)
rows = json.load(open({ACCOUNT!r}))
def save(): json.dump(rows, open({ACCOUNT!r}, "w"))
assert a[0] == "api"
if "-X" not in a:
    for r in rows: print(json.dumps(r))
elif a[a.index("-X") + 1] == "POST":
    f = dict(x.split("=", 1) for x in a if x.startswith(("title=", "key=")))
    rows.append({{"id": len(rows) + 100, "title": f["title"], "key": f["key"]}}); save()
else:
    rid = int(a[-1].rsplit("/", 1)[1]); rows[:] = [r for r in rows if r["id"] != rid]; save()
''')
    os.chmod(f"{BIN}/gh", 0o755)
    os.environ["PATH"] = f"{BIN}:/usr/bin:/bin"


def account() -> list[dict]:
    with open(ACCOUNT, encoding="utf-8") as f:
        return json.load(f)


def seed(rows: list[dict]) -> None:
    with open(ACCOUNT, "w", encoding="utf-8") as f:
        json.dump(rows, f)


def posts() -> int:
    with open(CALLS, encoding="utf-8") as f:
        return sum(1 for l in f if "-X POST" in l or "-X DELETE" in l)


def refused(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
    except gsk.Refused as e:
        return str(e)
    return ""


def run() -> None:
    fixture()
    want_key = subprocess.run(["gpg", "--homedir", GNUPG, "--export-ssh-key", SUB + "!"], capture_output=True, text=True, check=True, timeout=30).stdout.split()
    title = f"fabric-agent python-dev-03 ({AGENT_ID})"

    print("add")
    check("the SSH form is the signing subkey's", gsk.ssh_form(f"{KEYS}/{AGENT_ID}.asc") == f"{want_key[0]} {want_key[1]}")
    check("a dry run says what it would add and sends nothing", gsk.add("python-dev-03", root=ROOT, dry=True) == f"would add {title}" and posts() == 0)
    check("add registers it under the rule's title", gsk.add("python-dev-03", root=ROOT) == f"added {title}"
          and [(r["title"], r["key"]) for r in account()] == [(title, f"{want_key[0]} {want_key[1]}")], str(account()))
    check("a second add is present, and sends nothing", gsk.add("python-dev-03", root=ROOT) == f"present {title}" and posts() == 1)
    check("a login the lineage does not hold is refused", "not in" in refused(gsk.add, "nobody", root=ROOT))

    print("conflicts are refused, never overwritten")
    seed([{"id": 7, "title": "someone's laptop", "key": f"{want_key[0]} {want_key[1]}"}])
    msg = refused(gsk.add, "python-dev-03", root=ROOT)
    check("the same key under another title", "someone's laptop" in msg and len(account()) == 1 and account()[0]["id"] == 7, msg)
    seed([{"id": 8, "title": title, "key": "ssh-ed25519 AAAAdifferent"}])
    msg = refused(gsk.add, "python-dev-03", root=ROOT)
    check("the same title over another key", "different" not in msg and "id 8" in msg and account()[0]["key"] == "ssh-ed25519 AAAAdifferent", msg)

    print("remove")
    seed([{"id": 1, "title": title, "key": "k1"}, {"id": 2, "title": "fabric-agent python-dev-030 (x)", "key": "k2"},
          {"id": 3, "title": "fabric-agent other (y)", "key": "k3"}])
    out = gsk.remove("python-dev-03", dry=True)
    check("a dry run lists and removes nothing", out == [f"would remove {title}"] and len(account()) == 3, str(out))
    out = gsk.remove("python-dev-03")
    check("it deletes that login's keys only (a longer login sharing the prefix stays)",
          out == [f"removed {title}"] and sorted(r["id"] for r in account()) == [2, 3], str(account()))
    check("an absent login is said so", gsk.remove("python-dev-03")[0].startswith("absent"))

    print("a token without the scope")
    os.environ["FAKE_GH_MODE"] = "noscope"
    msg = refused(gsk.add, "python-dev-03", root=ROOT)
    check("is refused, with gh's fix said once", "admin:ssh_signing_key" in msg and msg.count("gh auth refresh") == 1, msg)
    del os.environ["FAKE_GH_MODE"]

    print("the command line")
    p = subprocess.run([sys.executable, gsk.__file__, "add"], capture_output=True, text=True, timeout=30)
    check("a bad verb is a usage error", p.returncode == 2 and "usage" in p.stderr, p.stderr)


try:
    run()
finally:
    drop_key(GNUPG)
    shutil.rmtree(T, ignore_errors=True)
print(f"{fails} failed" if fails else "all passed")
sys.exit(1 if fails else 0)
