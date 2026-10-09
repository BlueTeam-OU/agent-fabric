#!/usr/bin/env python3
"""bin/fabric-pr and bin/fabric-query (ADR-040 §5 rule 7, step 1): each verb
reaches its module with argv, streams and exit status untouched, and a
verb's --help is the old shim's, byte for byte. The wiring runs against a
fake checkout whose modules print what they were given; the parity cases
run the real modules (--help reads no network)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERBS = {"gate": ("pr_gate", "pr-gate"), "review-status": ("pr_review_status", "pr-review-status"),
         "post-review": ("post_review", "post-review"), "reply": ("pr_reply", "pr-reply"),
         "arm": ("arm", "arm"), "sessions": ("pr_sessions", "pr-sessions"),
         "trial-merge": ("trial_merge", "trial-merge"), "wait-merged": ("wait_merged", "wait-merged"),
         "owed-supply": ("owed_supply", "owed-supply"), "compliance": ("pr_compliance", "pr-compliance")}
DEPRECATED = "deprecated: use fabric-pr {}\n"
LIST = ", ".join(VERBS)
FAKE = ('import os, sys\n'
        'print("module=%s argv=%r" % (os.path.basename(__file__), sys.argv[1:]))\n'
        'print("err", file=sys.stderr)\n'
        'sys.exit(int(os.environ.get("FAKE_RC", "0")))\n')


def run(argv: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "AGENT_FABRIC_PYTHON": sys.executable}
    env.update(env_extra or {})
    return subprocess.run(argv, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=60)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_fabric_pr.") as tmp:
        fake = os.path.join(tmp, "fabric")
        os.makedirs(f"{fake}/bin")
        os.makedirs(f"{fake}/tools/fabric/github")
        for b in ("fabric-pr", "fabric-query"):
            shutil.copy(f"{ROOT}/bin/{b}", f"{fake}/bin/{b}")
        for mod, _ in VERBS.values():
            with open(f"{fake}/tools/fabric/github/{mod}.py", "w") as fh:
                fh.write(FAKE)
        with open(f"{fake}/tools/fabric/query.py", "w") as fh:
            fh.write(FAKE)
        pr = f"{fake}/bin/fabric-pr"

        print("fabric-pr — every verb reaches its module")
        for verb, (mod, _) in VERBS.items():
            r = run([pr, verb, "7", "--x", "a b"], {"FAKE_RC": "5"})
            check(f"{verb}: module, argv, both streams, exit status",
                  (r.stdout, r.stderr, r.returncode) == (f"module={mod}.py argv=['7', '--x', 'a b']\n", "err\n", 5),
                  (r.stdout, r.stderr, r.returncode))
        r = run([pr, "gate", "--help"])
        check("--help after a verb goes to the module", r.stdout == "module=pr_gate.py argv=['--help']\n", r.stdout)

        print("fabric-pr — the verb list")
        listing = f"usage: fabric-pr <verb> [args…]\nverbs: {LIST}\n"
        for argv in ([], ["help"], ["--help"]):
            r = run([pr, *argv])
            check(f"{argv or 'no verb'} lists the verbs, exit 0", (r.stdout, r.stderr, r.returncode) == (listing, "", 0),
                  (r.stdout, r.stderr, r.returncode))
        for bad in ("bogus", "Gate", "pr-gate", "gate.sh", "", "-x"):
            r = run([pr, bad])
            check(f"unknown verb {bad!r}: exit 2, named, list on stderr, nothing on stdout",
                  (r.stdout, r.returncode) == ("", 2) and r.stderr == f"fabric-pr: unknown verb '{bad}'; verbs: {LIST}\n",
                  (r.stdout, r.stderr, r.returncode))

        print("fabric-pr — the entry point")
        link = f"{tmp}/on-path"
        os.makedirs(link)
        os.symlink(pr, f"{link}/fabric-pr")
        r = run([f"{link}/fabric-pr", "sessions", "1"])
        check("found through a symlink on PATH", r.stdout == "module=pr_sessions.py argv=['1']\n", (r.stdout, r.stderr))
        r = run([pr, "gate"], {"AGENT_FABRIC_PYTHON": f"{tmp}/absent"})
        check("no pinned Python: exit 127 with the install command, even for a verb",
              r.returncode == 127 and "pinned Python is not installed" in r.stderr and "python_pin.py install" in r.stderr
              and r.stdout == "", (r.stdout, r.stderr, r.returncode))
        for b in ("fabric-pr", "fabric-query"):
            r = subprocess.run(["/bin/bash", f"{fake}/bin/{b}", "gate"], capture_output=True, text=True, timeout=60,
                               env={"PATH": "/nonexistent", "AGENT_FABRIC_PYTHON": sys.executable})
            check(f"{b} without readlink/dirname on PATH: 127 naming the checkout, not a file under /",
                  r.returncode == 127 and f"{b}: cannot locate the checkout" in r.stderr and "//" not in r.stderr,
                  (r.stderr, r.returncode))
        r = run([pr, "bogus"], {"AGENT_FABRIC_PYTHON": f"{tmp}/absent"})
        check("an unknown verb is 2 before Python is looked for", r.returncode == 2, r.returncode)
        r = run([pr, "gate"], {"AGENT_FABRIC_ROOT": "/elsewhere"})
        check("the environment reaches the module as it was (AGENT_FABRIC_ROOT is not set for it)",
              r.stdout.startswith("module=pr_gate.py"), r.stdout)

        print("fabric-query — reaches its module")
        r = run([f"{fake}/bin/fabric-query", "adr", "ADR-054", "x y"], {"FAKE_RC": "3"})
        check("module, argv, streams, exit status", (r.stdout, r.stderr, r.returncode)
              == ("module=query.py argv=['adr', 'ADR-054', 'x y']\n", "err\n", 3), (r.stdout, r.stderr, r.returncode))
        r = run([f"{fake}/bin/fabric-query", "roles"], {"AGENT_FABRIC_PYTHON": f"{tmp}/absent"})
        check("no pinned Python: exit 127 naming fabric-query", r.returncode == 127 and r.stderr.startswith("fabric-query: "),
              (r.stderr, r.returncode))

    print("fabric-pr — against the old shim, the real modules")
    for verb, (_, old) in VERBS.items():
        new = run([f"{ROOT}/bin/fabric-pr", verb, "--help"])
        was = run([f"{ROOT}/runtime/github/{old}.sh", "--help"])
        # ADR-040 §5 rule 7 step 3: the shim says it is deprecated on stderr and is otherwise the verb.
        check(f"{verb} --help is {old}.sh --help, byte for byte, same status; the shim adds one stderr line",
              (new.stdout, DEPRECATED.format(verb) + new.stderr, new.returncode) == (was.stdout, was.stderr, was.returncode)
              and new.returncode in (0, 2) and new.stdout + new.stderr != "", (new.returncode, was.returncode, new.stderr[:200]))
    new = run([f"{ROOT}/bin/fabric-query", "--help"])
    was = run([f"{ROOT}/tools/fabric/query.sh", "--help"])
    check("fabric-query --help is query.sh --help", (new.stdout, new.stderr, new.returncode)
          == (was.stdout, was.stderr, was.returncode) and new.stdout + new.stderr != "", (new.returncode, was.returncode))

    print("the in-checkout callers default to this checkout's fabric-pr")
    sys.path.insert(0, f"{ROOT}/tools/fabric/github")
    import arm
    import pr_gate
    for name in ("AGENT_FABRIC_PR_REVIEW_STATUS", "AGENT_FABRIC_PR_GATE"):
        os.environ.pop(name, None)
    check("pr_gate reads the review with `fabric-pr review-status`",
          pr_gate.review_reader() == [f"{ROOT}/bin/fabric-pr", "review-status"], pr_gate.review_reader())
    check("arm reads the gate with `fabric-pr gate`",
          arm.fabric_pr("AGENT_FABRIC_PR_GATE", "gate") == [f"{ROOT}/bin/fabric-pr", "gate"])
    check("arm reads the review with `fabric-pr review-status`",
          arm.fabric_pr("AGENT_FABRIC_PR_REVIEW_STATUS", "review-status") == [f"{ROOT}/bin/fabric-pr", "review-status"])
    for name in ("AGENT_FABRIC_CTL", "AGENT_FABRIC_GZCOORD_INBOX"):
        os.environ.pop(name, None)
    check("arm's other readers are their own program alone, with no fabric-pr verb in front",
          arm.program("AGENT_FABRIC_CTL", "/d/fabric-ctl") == ["/d/fabric-ctl"]
          and arm.program("AGENT_FABRIC_GZCOORD_INBOX", "/d/gzcoord-inbox") == ["/d/gzcoord-inbox"])
    # The call sites, where F1 broke: verify_waiver with no override set.
    import json
    heads: list[list[str]] = []
    waiver = {"addressed": True, "type": "DECISION", "sender": "h/other",
              "metadata": {"MESSAGE-ID": "m", "TO": "h/me", "FROM": "h/other", "WAIVES": "o/r#1@abcdef01"}}

    def fake_reader(head: list[str], args: list[str], timeout: int = 600) -> tuple[int, str]:
        heads.append(head)
        return (0, json.dumps(waiver)) if len(heads) == 1 else (2, "")

    real_reader, real_role = arm.run_reader, arm.waiver_role_checked
    arm.run_reader, arm.waiver_role_checked = fake_reader, lambda role: role or ""
    try:
        try:
            arm.verify_waiver("w", "1", "o/r", "abcdef0123", "h/me", "any-role", lambda msg: Exception(msg))
        except Exception:
            pass  # the presence read answers nothing; only the heads it was asked with matter
    finally:
        arm.run_reader, arm.waiver_role_checked = real_reader, real_role
    check("verify_waiver reads the relay with gzcoord-inbox alone and the presence with fabric-ctl alone",
          heads == [[f"{ROOT}/bin/gzcoord-inbox"], [f"{ROOT}/bin/fabric-ctl"]], heads)
    os.environ["AGENT_FABRIC_CTL"] = "/x/ctl"
    check("...and an override replaces the default", arm.program("AGENT_FABRIC_CTL", "/d/fabric-ctl") == ["/x/ctl"])
    os.environ["AGENT_FABRIC_PR_GATE"] = os.environ["AGENT_FABRIC_PR_REVIEW_STATUS"] = "/x/mock"
    check("an override is one program, as before",
          pr_gate.review_reader() == ["/x/mock"] and arm.fabric_pr("AGENT_FABRIC_PR_GATE", "gate") == ["/x/mock"])

    with tempfile.TemporaryDirectory(prefix="test_fabric_pr.reader.") as tmp:
        reader = f"{tmp}/fabric-pr"
        with open(reader, "w") as fh:
            fh.write('#!/bin/sh\n[ "$*" = "review-status 5" ] && echo "  head reviewed?: yes"\n')
        os.chmod(reader, 0o755)
        check("pr_gate runs the reader's whole head (program and verb) before the number",
              pr_gate.review_of_head([reader, "review-status"], 5) == "head reviewed",
              pr_gate.review_of_head([reader, "review-status"], 5))

    print("pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
