#!/usr/bin/env python3
"""A store's entry writes stay inside the store, and an incoming tree is
judged before it is applied (external review S01): write_confined refuses a
link on the way or at the target and a non-regular target, and writes
nothing outside; _write_entry (the entry path) goes through it; _tree_reason
refuses a link, a gitlink, an executable and a path no store holds, and lets
a store's own layout through. Non-secret bytes and scratch directories only;
no gpg (the sealing is replaced by a stub). Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
from secretstore import core, entries, trust  # noqa: E402
from secretstore.core import StoreError  # noqa: E402

AID = "0194a000-0000-7000-8000-000000000001"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    def refused(fn, *a) -> str:
        try:
            fn(*a)
        except StoreError as e:
            return str(e)
        return ""

    with tempfile.TemporaryDirectory(prefix="store-confinement.") as tmp:
        store, outside = os.path.join(tmp, "store"), os.path.join(tmp, "outside")
        os.makedirs(store)
        os.makedirs(outside)

        p = core.write_confined(store, "env/A.gpg", b"one")
        check("control: a plain write lands, 0600, no tmp left",
              open(p, "rb").read() == b"one" and os.stat(p).st_mode & 0o777 == 0o600
              and sorted(os.listdir(os.path.join(store, "env"))) == ["A.gpg"], os.listdir(store))
        core.write_confined(store, "env/A.gpg", b"two")
        check("…replaced whole", open(p, "rb").read() == b"two")

        os.symlink(outside, os.path.join(store, "linked"))
        why = refused(core.write_confined, store, "linked/B.gpg", b"x")
        check("a link as a directory on the way: refused, nothing written outside",
              "link or not a directory" in why and os.listdir(outside) == [], (why, os.listdir(outside)))
        os.symlink(os.path.join(outside, "victim"), os.path.join(store, "env", "C.gpg"))
        why = refused(core.write_confined, store, "env/C.gpg", b"x")
        check("a link as the target: refused, nothing written through it",
              "not a regular file" in why and os.listdir(outside) == [], (why, os.listdir(outside)))
        os.mkdir(os.path.join(store, "env", "D.gpg"))
        check("a directory as the target: refused",
              "not a regular file" in refused(core.write_confined, store, "env/D.gpg", b"x"))
        os.symlink(os.path.join(outside, "stale"), os.path.join(store, "env", ".E.gpg.tmp"))
        core.write_confined(store, "env/E.gpg", b"e")
        check("a planted tmp link is replaced, never written through",
              open(os.path.join(store, "env", "E.gpg"), "rb").read() == b"e" and os.listdir(outside) == [],
              os.listdir(outside))
        check("a path with .. is no path of the store",
              "not a path inside" in refused(core.write_confined, store, "env/../../x", b"x") and os.listdir(outside) == [])

        # The entry path itself, with sealing stubbed.
        real = entries.gpg
        entries.gpg = lambda *a, **k: SimpleNamespace(stdout=b"sealed")
        entries.git = lambda *a, **k: None
        try:
            fresh = os.path.join(tmp, "fresh")
            os.makedirs(fresh)
            entries._write_entry(fresh, "NAME", b"v", [])
            check("control: _write_entry seals into env/NAME.gpg",
                  open(os.path.join(fresh, "env", "NAME.gpg"), "rb").read() == b"sealed")
            hostile = os.path.join(tmp, "hostile")
            os.makedirs(hostile)
            os.symlink(outside, os.path.join(hostile, "env"))
            why = refused(entries._write_entry, hostile, "NAME", b"v", [])
            check("env a link (as a fetched tree could carry it): refused, nothing written outside",
                  bool(why) and os.listdir(outside) == [], (why, os.listdir(outside)))
        finally:
            entries.gpg = real

        # The incoming tree.
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

        def g(*a: str, inp: bytes | None = None) -> str:
            return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t",
                                   "-c", "commit.gpgsign=false", *a], env=env, input=inp, check=True,
                                  capture_output=True).stdout.decode().strip()
        g("init", "-q", "-b", "main")

        def commit(files: dict[str, str | None], msg: str, mode: str = "100644") -> str:
            for rel, content in files.items():
                path = os.path.join(repo, rel)
                if content is None:
                    g("rm", "-q", "--", rel)
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as fh:
                    fh.write(content)
                g("add", "--", rel)
                if mode != "100644":
                    g("update-index", "--chmod=+x", "--", rel)
            g("commit", "-q", "--allow-empty", "-m", msg)
            return g("rev-parse", "HEAD")

        base = commit({".gpg-id": "F\n", ".agent-id": AID + "\n", "env/OK.gpg": "x"}, "base")
        check("a store's own layout from the root passes", trust._tree_reason(repo, None, base) is None)
        good = commit({"env/NEW.gpg": "x", f"state/{AID}.meta": "m", f"recovery/{AID}.recipient": "r",
                       "settings/roles/dev/p.json": "{}"}, "good")
        check("…and what a store adds since its base", trust._tree_reason(repo, base, good) is None,
              trust._tree_reason(repo, base, good))
        gone = commit({"env/OK.gpg": None}, "delete")
        check("…a deletion of an entry", trust._tree_reason(repo, base, gone) is None)

        def bad(label: str, tip: str, needle: str) -> None:
            why = trust._tree_reason(repo, base, tip) or ""
            check(label, needle in why, why)

        g("checkout", "-q", "-b", "evil", base)
        link = g("hash-object", "-w", "--stdin", inp=b"/etc") 
        g("update-index", "--add", "--cacheinfo", f"120000,{link},env/LINK.gpg")
        g("commit", "-q", "-m", "link")
        bad("a symlink under env/: refused", g("rev-parse", "HEAD"), "mode 120000")
        g("checkout", "-q", "-f", "-B", "evil", base)
        g("update-index", "--add", "--cacheinfo", f"160000,{base},env/SUB.gpg")
        g("commit", "-q", "-m", "gitlink")
        bad("a gitlink: refused", g("rev-parse", "HEAD"), "mode 160000")
        g("checkout", "-q", "-f", "-B", "evil", base)
        bad("an executable entry: refused", commit({"env/X.gpg": "x"}, "exec", mode="100755"), "mode 100755")
        g("checkout", "-q", "-f", "-B", "evil", base)
        bad("a file outside the layout: refused", commit({"hooks/post": "x"}, "stray"), "'hooks/post'")
        g("checkout", "-q", "-f", "-B", "evil", base)
        bad("a lower-case entry name: refused", commit({"env/lower.gpg": "x"}, "name"), "'env/lower.gpg'")
        g("checkout", "-q", "-f", "-B", "evil", base)
        bad("a path outside the layout reached through a .. part: refused", commit({"settings/../x": "x"}, "dots"), "'x'")
        g("checkout", "-q", "-f", "-B", "evil", base)
        link2 = g("hash-object", "-w", "--stdin", inp=b"../..")
        g("update-index", "--add", "--cacheinfo", f"120000,{link2},settings/up")
        g("commit", "-q", "-m", "settings link")
        bad("a link under settings/: refused", g("rev-parse", "HEAD"), "mode 120000")

        # The wiring: _verify_incoming refuses a signed-but-bad tree. The
        # signature step is stubbed (test_store_signing proves it with real
        # keys); what is under test is that the tree is judged after it.
        import contextlib
        saved = {n: getattr(trust, n) for n in ("trusted_base", "writers", "_keyring", "_unsigned_reason",
                                                "_record_refusal", "own_agent_id")}
        trust.trusted_base = lambda store: base
        trust.writers = lambda *a, **k: {}
        trust._keyring = lambda keys: contextlib.nullcontext(({}, {}))
        trust._unsigned_reason = lambda *a, **k: None
        trust.own_agent_id = lambda store: AID
        recorded: list = []
        trust._record_refusal = lambda store, commit, reason: recorded.append(reason)
        try:
            g("checkout", "-q", "-f", "-B", "local", base)
            check("control: a signed commit with a store's layout is accepted",
                  trust._verify_incoming(repo, good, AID) == good)
            g("checkout", "-q", "-f", "-B", "evil", base)
            hostile = commit({"hooks/post": "x"}, "stray")
            g("checkout", "-q", "-f", "-B", "local", base)   # HEAD is the store's own, behind the tip
            why = refused(trust._verify_incoming, repo, hostile, AID)
            check("a signed commit with a path no store holds: refused, nothing applied, recorded",
                  "nothing applied" in why and len(recorded) == 1 and "hooks/post" in recorded[0], (why, recorded))
        finally:
            for n, v in saved.items():
                setattr(trust, n, v)

    print("test_store_confinement: " + ("OK" if not fails else f"FAILED — {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
