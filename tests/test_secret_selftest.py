#!/usr/bin/env python3
"""tools/fabric/secret_selftest.py (`fabric-secrets selftest`): against a
scratch account — keyring, store and fabric of its own, never the real ones
(the keyring outside the scratch HOME, as tests/test_secret_store.py says) —
a pass sets, uses and removes the canary with the real commands and leaves
the store as it was, two signed commits on; no output carries the canary or
its digest; an own entry by the fixed name stops the test before it writes;
and rm runs whatever failed between set and it."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(ROOT, "runtime", "provisioning", "secrets", "fabric-secrets")
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_selftest.py")
STORE_TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
sys.path.insert(0, os.path.dirname(STORE_TOOL))
import secret_store  # noqa: E402 — the id helpers
from instance_fixtures import write_secrets_instance  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home, gnupg, fabric = (os.path.join(tmp, d) for d in ("home", "gnupg", "fabric"))
        store = os.path.join(home, "store")
        os.makedirs(home)
        os.makedirs(gnupg, mode=0o700)
        os.makedirs(os.path.join(fabric, "projects"))
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        write_secrets_instance(fabric)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "GNUPGHOME": gnupg, "LANG": "C.UTF-8",
               "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_SECRET_STORE": store, "AGENT_FABRIC_PYTHON": sys.executable,
               "GIT_CONFIG_GLOBAL": os.path.join(home, ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        run = lambda args, stdin=None, e=env: subprocess.run(args, env=e, input=stdin, capture_output=True,  # noqa: E731
                                                             text=True, timeout=600, cwd=tmp)
        git = lambda *a: run(["git", "-C", store, *a]).stdout.strip()  # noqa: E731
        try:
            aid = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
            p = run([sys.executable, STORE_TOOL, "init", "--agent-id", aid])
            check("a scratch store to test against", p.returncode == 0, p.stderr)
            run([SHIM, "store", "set", "OWN_KEPT"], stdin="kept")
            names0, head0 = run([SHIM, "store", "names", "--json"]).stdout, git("rev-parse", "HEAD")

            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("selftest passes: precondition, set, run, rm, absent, each ok",
                  p.returncode == 0 and r.get("status") == "pass"
                  and [(s["step"], s["ok"]) for s in r.get("steps", [])]
                  == [("precondition", True), ("set", True), ("run", True), ("rm", True), ("absent", True)], p.stdout + p.stderr)
            check("…the store as it was found", run([SHIM, "store", "names", "--json"]).stdout == names0)
            me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
            check("…two signed commits on: set and rm of the canary's name",
                  git("log", "--format=%s", f"{head0}..HEAD").splitlines()
                  == [f"agent {me}: rm AF_SELFTEST_CANARY", f"agent {me}: set AF_SELFTEST_CANARY"]
                  and set(git("log", "--format=%G?", f"{head0}..HEAD").split()) <= {"G", "U"},
                  git("log", "--format=%s %G?", f"{head0}..HEAD"))
            # The canary was a token_urlsafe(32), and its digest 64 hex: no
            # output holds a run of either shape.
            blob = p.stdout + p.stderr
            check("…and no output holds a canary- or digest-shaped value",
                  not re.search(r"[A-Za-z0-9_-]{40,}", blob), blob)
            p = run([SHIM, "selftest"])
            check("the text form says each step and the verdict", p.returncode == 0
                  and "fabric-secrets selftest: pass" in p.stdout and "run           ok" in p.stdout, p.stdout + p.stderr)

            run([SHIM, "store", "set", "AF_SELFTEST_CANARY"], stdin="an agent's own value")
            head1 = git("rev-parse", "HEAD")
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("an own entry by the fixed name: fail at the precondition, nothing written or removed",
                  p.returncode == 1 and r.get("status") == "fail" and len(r.get("steps", [])) == 1
                  and r["steps"][0]["step"] == "precondition" and "in the store already" in r["steps"][0]["reason"]
                  and git("rev-parse", "HEAD") == head1, p.stdout + p.stderr)
            run([SHIM, "store", "rm", "AF_SELFTEST_CANARY"])
            p = run([SHIM, "selftest", "--json"], e={**env, "AGENT_FABRIC_ROOT": os.path.join(tmp, "no-fabric")})
            r = json.loads(p.stdout or "{}")
            check("a registry that cannot be read: fail at the precondition",
                  p.returncode == 1 and r.get("steps", [{}])[0].get("reason", "").startswith(os.path.join(tmp, "no-fabric")),
                  p.stdout + p.stderr)
            p = run([SHIM, "selftest", "--bogus"])
            check("an unknown argument is usage: exit 2", p.returncode == 2 and "usage" in p.stderr, p.stderr)

            # A leftover (the own-secrets review, R3; the coordinator's rule
            # D): the store gets a remote whose receive refuses (set's push
            # fails, its commit kept) and whose second upload-pack fails
            # (rm's fetch fails after set's succeeded). The canary stays
            # committed; the run says so and fails; the next run, the remote
            # back, removes it first and passes.
            bare = os.path.join(tmp, "remote.git")
            run(["git", "init", "-q", "--bare", "-b", "main", bare])
            git("remote", "add", "origin", bare)
            run(["git", "-C", store, "push", "-q", "origin", "HEAD:main"])
            hook = os.path.join(bare, "hooks", "pre-receive")
            served = os.path.join(tmp, "served-once")

            def break_remote() -> None:
                with open(hook, "w", encoding="utf-8") as fh:
                    fh.write("#!/bin/sh\nexit 1\n")
                os.chmod(hook, 0o755)
                pack = os.path.join(tmp, "upload-pack-once")
                with open(pack, "w", encoding="utf-8") as fh:
                    fh.write(f"#!/bin/sh\n[ -e '{served}' ] && exit 1\ntouch '{served}'\nexec git-upload-pack \"$@\"\n")
                os.chmod(pack, 0o755)
                git("config", "remote.origin.uploadpack", pack)

            def mend_remote() -> None:
                os.remove(hook)
                git("config", "--unset", "remote.origin.uploadpack")
                if os.path.exists(served):
                    os.remove(served)

            mark = os.path.join(store, ".git", "agent-fabric-selftest-leftover")
            break_remote()
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            steps = {s["step"]: s for s in r.get("steps", [])}
            check("set's push and rm's fetch both fail: fail, and the report says the canary is still committed and "
                  "that the next selftest removes it",
                  p.returncode == 1 and r.get("status") == "fail" and not steps.get("set", {}).get("ok", True)
                  and "the next selftest removes it" in steps.get("rm", {}).get("reason", "")
                  and "AF_SELFTEST_CANARY" in run([SHIM, "store", "names", "--json"]).stdout and os.path.exists(mark),
                  p.stdout + p.stderr)
            mend_remote()
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("…the next run, the remote back: the leftover removed first, then a pass, and nothing left",
                  p.returncode == 0 and [(s["step"], s["ok"]) for s in r.get("steps", [])]
                  == [("leftover", True), ("precondition", True), ("set", True), ("run", True), ("rm", True), ("absent", True)]
                  and run([SHIM, "store", "names", "--json"]).stdout == names0 and not os.path.exists(mark),
                  p.stdout + p.stderr)
            break_remote()
            run([SHIM, "selftest", "--json"])
            mend_remote()
            run([SHIM, "store", "set", "AF_SELFTEST_CANARY"], stdin="the agent's own, after the leftover")
            head1 = git("rev-parse", "HEAD")
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("…but an agent's own write to the name after the leftover makes it the agent's: refused, untouched",
                  p.returncode == 1 and [s["step"] for s in r.get("steps", [])] == ["precondition"]
                  and "in the store already" in r["steps"][0]["reason"] and git("rev-parse", "HEAD") == head1,
                  p.stdout + p.stderr)
            run([SHIM, "store", "rm", "AF_SELFTEST_CANARY"])
            # …and a commit with the selftest's subject that this store's key
            # did not sign is no leftover either, even named in the record.
            env_dir = os.path.join(store, "env")
            shutil.copy(os.path.join(env_dir, "OWN_KEPT.gpg"), os.path.join(env_dir, "AF_SELFTEST_CANARY.gpg"))
            git("add", "env/AF_SELFTEST_CANARY.gpg")
            run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit",
                 "-q", "-m", f"agent {me}: set AF_SELFTEST_CANARY"])
            unsigned = git("rev-parse", "HEAD")
            check("…(that commit is there, unsigned, under the selftest's subject)",
                  git("log", "-1", "--format=%G? %s") == f"N agent {me}: set AF_SELFTEST_CANARY", git("log", "-1", "--format=%G? %s"))
            with open(mark, "w", encoding="utf-8") as fh:
                fh.write(unsigned + "\n")
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("…nor is an unsigned commit with the selftest's subject, named in the record: refused, untouched",
                  p.returncode == 1 and [s["step"] for s in r.get("steps", [])] == ["precondition"]
                  and git("rev-parse", "HEAD") == unsigned, p.stdout + p.stderr)
            git("reset", "-q", "--hard", "HEAD~1")
            os.remove(mark)
            # …nor a signed commit under another subject, named in the record.
            run([SHIM, "store", "set", "AF_SELFTEST_CANARY"], stdin="own")
            signing = run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                           "from secretstore.keys import _signing_args; print('\\n'.join(_signing_args()))",
                           os.path.dirname(STORE_TOOL)]).stdout.split("\n")
            amended = run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", *[a for a in signing if a],
                           "commit", "-q", "--amend", "-m",
                           f"agent {me}: put AF_SELFTEST_CANARY"])
            check("…(the amended commit is signed, under the other subject)",
                  git("log", "-1", "--format=%G? %s") in (f"G agent {me}: put AF_SELFTEST_CANARY",
                                                          f"U agent {me}: put AF_SELFTEST_CANARY"),
                  f"{git('log', '-1', '--format=%G? %s')} {signing} {amended.stderr}")
            other = git("rev-parse", "HEAD")
            with open(mark, "w", encoding="utf-8") as fh:
                fh.write(other + "\n")
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("…nor a signed commit under another subject, named in the record: refused, untouched",
                  p.returncode == 1 and [s["step"] for s in r.get("steps", [])] == ["precondition"]
                  and git("rev-parse", "HEAD") == other, p.stdout + p.stderr)
            os.remove(mark)
            # The amended commit replaced one the remote holds: back to the
            # remote's, then removed, so what follows starts from a clean store.
            git("reset", "-q", "--hard", "origin/main")
            cleaned = run([SHIM, "store", "rm", "AF_SELFTEST_CANARY"])
            check("…(and removed again, the store clean)", cleaned.returncode == 0, cleaned.stdout + cleaned.stderr)
            # …nor one with the selftest's subject, signed by another key this
            # keyring holds (a good signature, not the store's key).
            run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", "other <other@test.invalid>", "ed25519", "sign", "never"])
            other_fpr = next(l.split(":")[9] for l in run(["gpg", "--with-colons", "--list-keys", "other@test.invalid"]).stdout.splitlines()
                             if l.startswith("fpr:"))
            shutil.copy(os.path.join(env_dir, "OWN_KEPT.gpg"), os.path.join(env_dir, "AF_SELFTEST_CANARY.gpg"))
            git("add", "env/AF_SELFTEST_CANARY.gpg")
            run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", f"user.signingkey={other_fpr}",
                 "-c", "gpg.program=gpg", "commit", "-q", "-S", "-m", f"agent {me}: set AF_SELFTEST_CANARY"])
            foreign = git("rev-parse", "HEAD")
            check("…(that commit is there, with a good signature by the other key)",
                  git("-c", "gpg.program=gpg", "log", "-1", "--format=%G? %GF") in (f"G {other_fpr}", f"U {other_fpr}"),
                  git("-c", "gpg.program=gpg", "log", "-1", "--format=%G? %GF"))
            with open(mark, "w", encoding="utf-8") as fh:
                fh.write(foreign + "\n")
            p = run([SHIM, "selftest", "--json"])
            r = json.loads(p.stdout or "{}")
            check("…nor one signed by another key in the keyring, named in the record: refused, untouched",
                  p.returncode == 1 and [s["step"] for s in r.get("steps", [])] == ["precondition"]
                  and git("rev-parse", "HEAD") == foreign, p.stdout + p.stderr)
            git("reset", "-q", "--hard", "HEAD~1")
            os.remove(mark)
            # With git on PATH and gpg not, git answers N for the selftest's
            # own signed set: no answer, never "not a leftover".
            own_set = run([SHIM, "store", "set", "AF_SELFTEST_CANARY"], stdin="signed by the store")
            gitonly = os.path.join(tmp, "git-only")
            os.makedirs(gitonly, exist_ok=True)
            if not os.path.exists(os.path.join(gitonly, "git")):
                os.symlink(shutil.which("git"), os.path.join(gitonly, "git"))
            probe_last = ("import sys; sys.path.insert(0, sys.argv[1]); import secret_selftest as t\n"
                          "try: print(t._last_set_by_me(sys.argv[2]))\n"
                          "except t.StoreError as e: print('StoreError', e)")
            seen_ok = run([sys.executable, "-c", probe_last, os.path.dirname(TOOL), store])
            seen_nogpg = run([sys.executable, "-c", probe_last, os.path.dirname(TOOL), store],
                             e={**env, "PATH": gitonly})
            check("…a signed set read with no gpg to start is no answer (and, with gpg, the commit itself)",
                  own_set.returncode == 0 and seen_ok.stdout.strip() == git("rev-parse", "HEAD")
                  and seen_nogpg.stdout.startswith("StoreError"),
                  own_set.stderr + seen_ok.stdout + seen_ok.stderr + seen_nogpg.stdout + seen_nogpg.stderr)
            cleaned = run([SHIM, "store", "rm", "AF_SELFTEST_CANARY"])
            check("…(and removed again)", cleaned.returncode == 0, cleaned.stdout + cleaned.stderr)
        finally:
            subprocess.run(["gpgconf", "--homedir", gnupg, "--kill", "all"], capture_output=True, timeout=30)

    # In process, the commands replaced: whatever fails after set, rm runs.
    spec = importlib.util.spec_from_file_location("secret_selftest", TOOL)
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    st.reserved = lambda name, root: None
    real_cmd = st._cmd
    # The store is the fakes': no leftover is read or recorded in a real one,
    # and a path that reaches for one fails here, loudly (review of #110).
    st._remember_leftover = lambda: False
    st._own_leftover = lambda: None
    st._forget_leftover = lambda: None

    def no_real_store():
        raise AssertionError("the in-process cases reached for a real store")
    st.store_dir = no_real_store

    # The leftover's rm is held to the recorded commit (--expect-last), so a
    # write that lands between the check and the rm is not removed.
    leftover_sha = "f" * 40
    seen_rm: list[list[str]] = []

    def held_once(args, stdin=None):
        if args[-2:] == ["names", "--json"]:
            return 0, '["AF_SELFTEST_CANARY"]' if not seen_rm else "[]", ""
        if "rm" in args and "--expect-last" in args:
            seen_rm.append(args)
            return 0, "AF_SELFTEST_CANARY: removed\n", ""
        return 0, "", ""
    st._own_leftover, st._cmd = (lambda: leftover_sha), held_once
    st.selftest()
    check("the leftover's rm names the recorded commit (--expect-last)",
          seen_rm and seen_rm[0][-2:] == ["--expect-last", leftover_sha], seen_rm)
    st._cmd = real_cmd
    st._own_leftover = lambda: None


    # A timeout ends the command's whole group (the own-secrets review, R3):
    # the shim's python and the git it runs, not only the direct child. A
    # grandchild that ignores SIGTERM is killed after the grace.
    import time
    with tempfile.TemporaryDirectory() as gtmp:
        bounds = st.STEP_TIMEOUT_S, st.STOP_GRACE_S
        st.STEP_TIMEOUT_S, st.STOP_GRACE_S = 1, 1
        for trap, what in (("", "a grandchild"), ("trap '' TERM; ", "a grandchild that ignores SIGTERM")):
            pidfile = os.path.join(gtmp, "pid")
            t0 = time.monotonic()
            got = st._cmd(["bash", "-c", f"{trap}(trap '' TERM; exec sleep 60) & echo $! > {pidfile}; wait"
                           if trap else f"sleep 60 & echo $! > {pidfile}; wait"])
            took = time.monotonic() - t0
            pid = int(open(pidfile).read())
            gone = False
            for _ in range(50):
                # Gone, or a zombie: dead, and left unreaped where PID 1 does
                # not reap orphans (the platform-smoke containers on #110).
                try:
                    with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
                        state = fh.read().rsplit(")", 1)[1].split()[0]
                except (FileNotFoundError, ProcessLookupError):
                    state = "gone"
                if state in ("gone", "Z", "X"):
                    gone = True
                    break
                time.sleep(0.1)
            check(f"a command that runs out: 124, and {what} it started is ended with it", got[0] == 124 and gone
                  and took < 20, f"{got} gone={gone} took={took:.1f}")
            if not gone:
                os.kill(pid, 9)
        st.STEP_TIMEOUT_S, st.STOP_GRACE_S = bounds
    calls: list[list[str]] = []

    def fake(args, stdin=None):
        calls.append(args)
        if args[-2:] == ["names", "--json"]:
            return 0, "[]", ""
        if "set" in args:
            return 0, "AF_SELFTEST_CANARY: set\n", ""
        if args[0] == st.SECRET_RUN and "pass" not in args:
            return 3, "", ""
        if "rm" in args:
            return 0, "AF_SELFTEST_CANARY: removed\n", ""
        return 2, "", "fabric-secret-run: AF_SELFTEST_CANARY: absent from this login's store"
    st._cmd = fake
    r = st.selftest()
    check("a run that fails is reported, and rm still runs after it",
          r["status"] == "fail" and [(s["step"], s["ok"]) for s in r["steps"]]
          == [("precondition", True), ("set", True), ("run", False), ("rm", True), ("absent", True)]
          and "another value" in r["steps"][2]["reason"], r)
    calls.clear()
    st._cmd = lambda args, stdin=None: (calls.append(args), fake(args, stdin) if "set" not in args
                                        else (1, "", "fabric-secrets store: could not push"))[1]
    r = st.selftest()
    check("a set that fails skips run, and rm is still asked",
          [s["step"] for s in r["steps"]] == ["precondition", "set", "rm", "absent"]
          and any("rm" in c for c in calls) and r["steps"][1]["reason"] == "store set exited 1", r)
    probe = lambda value, given: subprocess.run(  # noqa: E731
        [sys.executable, "-I", "-c", st.PROBE], input=given, text=True, capture_output=True, timeout=60,
        env={"PATH": os.environ.get("PATH", ""), **({st.NAME: value} if value is not None else {})}).returncode
    import hashlib
    d = hashlib.sha256(b"v1").hexdigest()
    check("the probe: 0 for the value whose digest it is given, 3 for another, 3 for none",
          (probe("v1", d), probe("v2", d), probe(None, d)) == (0, 3, 3))
    seen: list[str] = []
    st._cmd = lambda args, stdin=None: (seen.append(stdin or ""), fake(args, stdin) if "set" not in args
                                        else (1, "", f"a broken set that echoed {stdin}"))[1]
    r = st.selftest()
    canary = next(x for x in seen if x)
    check("a set whose stderr echoed the canary: the reason is its exit, no output relayed (#108, CodeQL 48/49)",
          canary not in json.dumps(r) and "echoed" not in json.dumps(r) and r["steps"][1]["reason"] == "store set exited 1", r)
    for rc, why in ((124, f"store set: no answer within {st.STEP_TIMEOUT_S} s"), (127, "store set: could not be started")):
        st._cmd = lambda args, stdin=None, rc=rc: fake(args, stdin) if "set" not in args else (rc, "", f"echo {stdin}")
        r = st.selftest()
        check(f"…exit {rc}: said in words", r["steps"][1]["reason"] == why, r)
    st._cmd = lambda args, stdin=None: fake(args, stdin) if "set" not in args else (0, f"echoed {stdin}\n", "")
    r = st.selftest()
    check("…a set that exits 0 with another answer: fixed text, not its output",
          r["steps"][1]["reason"] == "store set did not answer 'AF_SELFTEST_CANARY: set'" and "echoed" not in json.dumps(r), r)
    st._cmd = lambda args, stdin=None: (2, "", "fabric-secret-run: refused for another reason") \
        if args[0] == st.SECRET_RUN and "pass" in args else fake(args, stdin)
    r = st.selftest()
    check("…an absent check refused otherwise: fixed text, not its stderr",
          r["steps"][-1]["reason"] == "fabric-secret-run refused the removed name, not as absent"
          and "another reason" not in json.dumps(r), r)
    # A git or gpg that gives no answer is no answer, never "not a leftover"
    # (review of #110, 2): a StoreError, which the run reports as such.
    def git_answering(answers):
        def fake_git(store, *args, check=True):
            for key, (rc, out) in answers.items():
                if key in args:
                    if check and rc:
                        raise st.StoreError(f"git {args[0]}: exit {rc}")
                    return subprocess.CompletedProcess(args, rc, out.encode(), b"")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        return fake_git
    saved_git, saved_login = st.git, st.login
    st.login = lambda: "me"
    try:
        for answers, what in (({"ls-files": (128, "")}, "ls-files exiting 128"),
                              ({"--format=%H %s": (0, "abc agent me: set AF_SELFTEST_CANARY"), "--format=%G?": (0, "E")},
                               "a signature gpg could not check (E)"),
                              ({"--format=%H %s": (0, "abc agent me: set AF_SELFTEST_CANARY"), "--format=%G?": (0, "G"),
                                "verify-commit": (1, "")}, "verify-commit failing on a good %G?"),
                              ({"--format=%H %s": (0, "abc agent me: set AF_SELFTEST_CANARY"), "--format=%G?": (0, "N"),
                                "cat-file": (0, "tree t\nauthor a\ngpgsig -----BEGIN PGP SIGNATURE-----\n\nmessage")},
                               "N on a commit that carries a signature (gpg not started)")):
            st.git = git_answering(answers)
            try:
                got = st._last_set_by_me("/nowhere")
                check(f"…{what}: no answer, a StoreError", False, f"answered {got!r}")
            except st.StoreError:
                check(f"…{what}: no answer, a StoreError", True)
        st.git = git_answering({"--format=%H %s": (0, "abc agent me: set AF_SELFTEST_CANARY"), "--format=%G?": (0, "N"),
                                "cat-file": (0, "tree t\nauthor a\n\nmessage")})
        check("…while N on a commit with no signature is a plain no", st._last_set_by_me("/nowhere") is None)
    finally:
        st.git, st.login = saved_git, saved_login
    rm_fails = lambda args, stdin=None: (1, "", "") if "rm" in args else fake(args, stdin)  # noqa: E731
    def unreadable():
        raise st.StoreError("git ls-files exited 128")
    st._remember_leftover = unreadable
    st._cmd = rm_fails
    r = st.selftest()
    check("…and an rm that failed with no answer about the canary says so, and fails",
          r["status"] == "fail" and "whether the canary is still committed could not be read"
          in next(s for s in r["steps"] if s["step"] == "rm")["reason"], r)
    # Each command waits for the store's lock less than its own bound.
    env_seen = real_cmd(["sh", "-c", "printf %s \"$AGENT_FABRIC_STORE_LOCK_WAIT_S\""])
    check("a command is told to wait for the store's write lock under its own bound",
          env_seen[0] == 0 and env_seen[1] == str(st.LOCK_WAIT_S) and st.LOCK_WAIT_S < st.STEP_TIMEOUT_S, env_seen)
    # The bound is counted from the code, not written down: each _cmd in
    # selftest(), and each _names (one command each), against the limit
    # control/selftest.py sets (review of #110, re-review 2).
    import ast
    tree = ast.parse(open(TOOL, encoding="utf-8").read())
    body = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "selftest")
    commands = sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("_cmd", "_names")
                   for n in ast.walk(body))
    limit_ms = int(re.search(r"^SELFTEST_TIMEOUT_MS = (\d+)$", open(os.path.join(ROOT, "tools", "fabric", "control", "selftest.py"),
                                                                   encoding="utf-8").read(), re.M).group(1))
    worst = commands * (st.STEP_TIMEOUT_S + st.STOP_GRACE_S + 2 * st.REAP_S)
    check(f"…and the selftest's {commands} commands, each with its grace, fit the control agent's limit "
          f"({worst} s < {limit_ms // 1000} s)", worst < limit_ms / 1000, (commands, worst, limit_ms))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
