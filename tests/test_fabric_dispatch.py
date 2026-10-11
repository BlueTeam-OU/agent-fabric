#!/usr/bin/env python3
"""The dispatch that moved out of bash (ADR-040 Wave 9, batch 1): the verb
tables of fabric-pr (tools/fabric/github/fabric_pr.py), fabric-locale
(tools/fabric/fabric_locale.py) and fabric-secrets (tools/fabric/fabric_secrets.py),
the forwarders that remain at their old paths, and the fake gh the secrets-sync
tests use. The bash tests of fabric-pr and secrets-sync stay the oracle for the
streams and exit codes; this covers the internals and the shape rule."""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "github"))
import fabric_locale  # noqa: E402
import fabric_pr  # noqa: E402
import fabric_secrets  # noqa: E402

FORWARDERS = {"fabric-pr": f"{ROOT}/bin/fabric-pr", "fabric-locale": f"{ROOT}/bin/fabric-locale",
              "fabric-secrets": f"{ROOT}/runtime/provisioning/secrets/fabric-secrets"}
FAKE_GH = f"{ROOT}/tests/fixtures/fake_gh_auth.py"


class Execs:
    """os.execv replaced by a recorder, so a dispatch is read, not run."""

    def __init__(self):
        self.calls = []

    def __enter__(self):
        self.real, os.execv = os.execv, lambda path, argv: self.calls.append((path, argv))
        return self

    def __exit__(self, *_):
        os.execv = self.real


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    print("fabric_pr — the verb table")
    gh = os.path.join(ROOT, "tools", "fabric", "github")
    check("every verb names a module that exists", all(os.path.isfile(f"{gh}/{m}.py") for m in fabric_pr.VERBS.values()), fabric_pr.VERBS)
    check("the verbs are the eleven, in the order the help lists them",
          list(fabric_pr.VERBS) == ["gate", "review-status", "post-review", "reply", "arm", "sessions", "trial-merge", "wait-merged",
                                    "owed-supply", "compliance", "counts"])
    expected = {"gate": "pr_gate", "review-status": "pr_review_status", "post-review": "post_review", "reply": "pr_reply", "arm": "arm",
                "sessions": "pr_sessions", "trial-merge": "trial_merge", "wait-merged": "wait_merged", "owed-supply": "owed_supply",
                "compliance": "pr_compliance", "counts": "pr_counts"}
    check("the table is the bash's, verb for verb", fabric_pr.VERBS == expected, fabric_pr.VERBS)
    for verb, mod in expected.items():
        with Execs() as e:
            fabric_pr.main(["fabric-pr", verb, "7", "--x", "a b"])
        check(f"{verb} execs {mod}.py on this interpreter with the rest of argv",
              e.calls == [(sys.executable, [sys.executable, f"{gh}/{mod}.py", "7", "--x", "a b"])], e.calls)
    out, err = io.StringIO(), io.StringIO()
    out.buffer = io.BytesIO()
    err.buffer = io.BytesIO()
    with redirect_stdout(out), redirect_stderr(err), Execs() as e:
        rc_unknown = fabric_pr.main(["fabric-pr", ""])
        rc_help = fabric_pr.main(["fabric-pr"])
    check("an empty verb is an unknown one (exit 2, stderr), no verb is the help (exit 0, stdout)",
          (rc_unknown, rc_help, e.calls) == (2, 0, [])
          and err.buffer.getvalue().startswith(b"fabric-pr: unknown verb '';") and out.buffer.getvalue().startswith("usage: fabric-pr <verb> [args…]\n".encode()),
          (rc_unknown, rc_help, err.buffer.getvalue()))

    print("fabric_locale — tokens and digest")
    for verb in ("tokens", "digest"):
        with Execs() as e:
            fabric_locale.main(["fabric-locale", verb, "src.md"])
        check(f"{verb} execs lint.py --{verb} with the one path",
              e.calls == [(sys.executable, [sys.executable, fabric_locale.LINT, f"--{verb}", "src.md"])], e.calls)
        for argv in ([], ["a", "b"]):
            err = io.StringIO()
            with redirect_stderr(err), Execs() as e:
                rc = fabric_locale.main(["fabric-locale", verb, *argv])
            check(f"{verb} with {len(argv)} path(s): its own usage, exit 2, nothing run",
                  (rc, err.getvalue(), e.calls) == (2, f"usage: fabric-locale {verb} <source.md>\n", []), (rc, err.getvalue()))
    for argv in ([], [""], ["bogus", "x"], ["Tokens", "x"]):
        err = io.StringIO()
        with redirect_stderr(err), Execs() as e:
            rc = fabric_locale.main(["fabric-locale", *argv])
        check(f"{argv or 'no verb'}: the general usage, exit 2, nothing run",
              (rc, err.getvalue(), e.calls) == (2, "usage: fabric-locale tokens|digest <source.md>\n", []), (rc, err.getvalue()))

    print("fabric_secrets — the verb, else the sync")
    here = os.path.join(ROOT, "tools", "fabric")
    for verb, mod in (("store", "secret_store.py"), ("provision", "store_provision.py"), ("selftest", "secret_selftest.py")):
        check(f"{mod} exists", os.path.isfile(f"{here}/{mod}"))
        with Execs() as e:
            fabric_secrets.main(["fabric-secrets", verb, "a", "--b"])
        check(f"{verb} execs {mod} with the rest of argv, the verb dropped",
              e.calls == [(sys.executable, [sys.executable, f"{here}/{mod}", "a", "--b"])], e.calls)
    for argv in ([], ["sync"], ["status", "--json"], [""], ["Store"], ["bogus", "x"]):
        with Execs() as e:
            fabric_secrets.main(["fabric-secrets", *argv])
        check(f"{argv or 'no argument'}: secrets_sync.py with every argument, the first included",
              e.calls == [(sys.executable, [sys.executable, f"{here}/secrets_sync.py", *argv])], e.calls)

    print("the forwarders — the shape of ADR-040 §5 rule 1")
    for name, path in FORWARDERS.items():
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        code = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        body = "\n".join(code)
        check(f"{name}: at most 12 lines of code ({len(code)})", len(code) <= 12, len(code))
        check(f"{name}: no case, no loop", not re.search(r"(^|[;&|\s])(case|for|while|until|select)\s", body), body)
        check(f"{name}: checks the pin, names the install command, and ends in one exec",
              "python_pin.py install" in body and code[-1].startswith('exec "$py"') and body.count("exec ") == 1, code[-1])
        check(f"{name}: carries no verb", not re.search(r"\b(gate|review-status|tokens|digest|selftest|provision)\b", body.replace(
            "fabric-secrets", "").replace("fabric-pr", "")), body)
    for mod in ("fabric_pr.py", "fabric_locale.py", "fabric_secrets.py"):
        check(f"{mod} states its contract in its header", "THE CONTRACT" in open(next(
            p for p in (f"{gh}/{mod}", f"{here}/{mod}") if os.path.isfile(p)), encoding="utf-8").read())

    print("fabric-locale — the forwarder reaches lint.py, streams and status untouched")
    # A fixture source, not a live identity file: a test never reads the checkout's instance files.
    src_dir = tempfile.TemporaryDirectory(prefix="test_fabric_dispatch.src.")
    source = f"{src_dir.name}/charter.md"
    with open(source, "w", encoding="utf-8") as fh:
        fh.write("---\nname: charter\n---\n# Charter\n\nRun `fabric-status` and read tools/fabric/lint.py before ADR-040.\n")
    env = {"PATH": "/usr/bin:/bin", "AGENT_FABRIC_PYTHON": sys.executable}
    for verb in ("tokens", "digest"):
        via = subprocess.run([FORWARDERS["fabric-locale"], verb, source], capture_output=True, text=True, env=env, timeout=120)
        direct = subprocess.run([sys.executable, f"{here}/lint.py", f"--{verb}", source], capture_output=True, text=True, env=env, timeout=120)
        check(f"{verb}: same stdout, stderr and status as lint.py --{verb}",
              (via.stdout, via.stderr, via.returncode) == (direct.stdout, direct.stderr, direct.returncode) and via.stdout != "",
              (via.stderr[:200], via.returncode, direct.returncode))
    r = subprocess.run([FORWARDERS["fabric-locale"], "bogus"], capture_output=True, text=True, env=env, timeout=60)
    check("an unknown verb: usage on stderr, exit 2", (r.stdout, r.stderr, r.returncode) == ("", "usage: fabric-locale tokens|digest <source.md>\n", 2), r)
    r = subprocess.run([FORWARDERS["fabric-locale"], "tokens", source], capture_output=True, text=True, timeout=60,
                       env={"PATH": "/usr/bin:/bin", "AGENT_FABRIC_PYTHON": "/nonexistent/py"})
    check("no pinned Python: 127 with the install command, before any usage error",
          r.returncode == 127 and "python_pin.py install" in r.stderr and r.stdout == "", (r.returncode, r.stderr))
    r = subprocess.run([FORWARDERS["fabric-locale"]], capture_output=True, text=True, timeout=60,
                       env={"PATH": "/usr/bin:/bin", "AGENT_FABRIC_PYTHON": "/nonexistent/py"})
    check("...also for no verb at all", r.returncode == 127, r.returncode)
    src_dir.cleanup()

    print("fabric-secrets — the forwarder reaches the dispatcher, whichever path it is called by")
    for verb in ("store", "provision", "selftest"):
        r = subprocess.run([FORWARDERS["fabric-secrets"], verb, "--help"], capture_output=True, text=True, env=env, timeout=120)
        mod = {"store": "secret_store.py", "provision": "store_provision.py", "selftest": "secret_selftest.py"}[verb]
        d = subprocess.run([sys.executable, f"{here}/{mod}", "--help"], capture_output=True, text=True, env=env, timeout=120)
        check(f"{verb} --help is {mod} --help, stream for stream",
              (r.stdout, r.stderr, r.returncode) == (d.stdout, d.stderr, d.returncode), (r.stderr[:200], r.returncode, d.returncode))
    with tempfile.TemporaryDirectory(prefix="test_fabric_dispatch.") as tmp:
        link = f"{tmp}/fabric-secrets"
        os.symlink(FORWARDERS["fabric-secrets"], link)
        r = subprocess.run([link, "selftest", "--help"], capture_output=True, text=True, env=env, timeout=120)
        check("found through a symlink", r.returncode in (0, 2) and (r.stdout + r.stderr) != "", (r.returncode, r.stderr[:200]))

    print("fake_gh_auth — the secrets-sync tests' gh")
    with tempfile.TemporaryDirectory(prefix="test_fabric_dispatch.gh.") as tmp:
        base = {"PATH": "/usr/bin:/bin", "HOME": tmp}

        def gh_run(args, stdin="", **extra):
            return subprocess.run([sys.executable, FAKE_GH, *args], input=stdin, capture_output=True, text=True,
                                  env={**base, **extra}, timeout=30)
        check("auth token with no token stored: nothing, exit 1", (gh_run(["auth", "token"]).stdout, gh_run(["auth", "token"]).returncode) == ("", 1))
        r = gh_run(["auth", "login", "--with-token"], "tok-1\n")
        check("auth login stores stdin, exit 0", (r.returncode, r.stdout) == (0, "") and open(f"{tmp}/.config/gh/fake-token").read() == "tok-1\n")
        r = gh_run(["auth", "token"])
        check("auth token prints it back, exit 0", (r.stdout, r.returncode) == ("tok-1\n", 0), r)
        r = gh_run(["auth", "login"], "tok-2\n", FAKE_GH_LOGIN_EXIT="3")
        check("a refused login reads stdin, stores nothing, exits with FAKE_GH_LOGIN_EXIT",
              r.returncode == 3 and open(f"{tmp}/.config/gh/fake-token").read() == "tok-1\n", r.returncode)
        r = gh_run(["auth", "login"], "tok-3\n", FAKE_GH_LOGIN_EXIT="0")
        check("FAKE_GH_LOGIN_EXIT=0 is not a refusal", r.returncode == 0 and open(f"{tmp}/.config/gh/fake-token").read() == "tok-3\n")
        r = gh_run(["pr", "list"])
        check("anything else: unsupported on stderr, exit 2", (r.stdout, r.stderr, r.returncode) == ("", "fake gh: unsupported: pr list\n", 2), r)
        r = gh_run(["auth", "token"], GH_CONFIG_DIR=f"{tmp}/elsewhere")
        check("GH_CONFIG_DIR moves the token file", (r.stdout, r.returncode) == ("", 1))
        empty = f"{tmp}/e"
        os.makedirs(empty)
        open(f"{empty}/fake-token", "w").close()
        check("an empty token file is no token", gh_run(["auth", "token"], GH_CONFIG_DIR=empty).returncode == 1)

    print("pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
