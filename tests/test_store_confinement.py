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

        # A two-file write learns of a refusal on the second target before the first is replaced.
        two = os.path.join(tmp, "two")
        os.makedirs(os.path.join(two, "state"))
        os.symlink(os.path.join(outside, "m"), os.path.join(two, "state", "x.meta"))
        why = refused(core.check_confined, two, "state/x.meta")
        check("check_confined: a link as the second target is refused without writing",
              "not a regular file" in why and os.listdir(os.path.join(two, "state")) == ["x.meta"], why)
        check("…control: an absent target and an absent directory pass",
              refused(core.check_confined, two, "state/none.tar.gpg") == "" and refused(core.check_confined, two, "new/x") == "")

        # The entry path itself, with sealing stubbed.
        real, real_git = entries.gpg, entries.git
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
            entries.gpg, entries.git = real, real_git

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

        for name in ("my notes.md", ".editorconfig", "café.md", "notes~", "-x.md"):
            commit({f"settings/roles/dev/{name}": "x"}, "name")
        check("settings names settings_put can commit (spaces, dots, non-ASCII, ~, -) are a store's",
              trust._tree_reason(repo, good, g("rev-parse", "HEAD")) is None,
              trust._tree_reason(repo, good, g("rev-parse", "HEAD")))

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
        # A tree object can name ".." though git add cannot: made with mktree.
        blob = g("hash-object", "-w", "--stdin", inp=b"x")
        inner = g("mktree", inp=f"100644 blob {blob}\t..\n".encode())
        dotted = g("mktree", inp=f"040000 tree {inner}\tsettings\n".encode())
        dotted_c = g("commit-tree", dotted, "-p", base, "-m", "dotdot")
        bad("a tree naming a .. part under settings/: refused by the part, not the regex", dotted_c, "'settings/..'")
        g("checkout", "-q", "-f", "-B", "evil", base)
        link2 = g("hash-object", "-w", "--stdin", inp=b"../..")
        g("update-index", "--add", "--cacheinfo", f"120000,{link2},settings/up")
        g("commit", "-q", "-m", "settings link")
        bad("a link under settings/: refused", g("rev-parse", "HEAD"), "mode 120000")
        g("checkout", "-q", "-f", "-B", "evil", base)
        bad("a .git* name under settings/ is refused, as settings_put refuses it", commit({"settings/.gitmodules": "x"}, "gm"),
            "'settings/.gitmodules'")

        # From the root the WHOLE tree is judged: a bad entry in an early commit the tip does not touch,
        # and a merge tip (which a plain diff-tree shows as nothing).
        g("checkout", "-q", "-f", "--orphan", "rooted")
        g("rm", "-rq", "--cached", ".")
        link3 = g("hash-object", "-w", "--stdin", inp=b"/etc")
        g("update-index", "--add", "--cacheinfo", f"120000,{link3},env/LINK.gpg")
        g("commit", "-q", "-m", "root with a link")
        benign = commit({"env/NEW.gpg": "x"}, "benign on top")
        check("from the root: a link added by an early commit the tip does not touch is found",
              "mode 120000" in (trust._tree_reason(repo, None, benign) or ""), trust._tree_reason(repo, None, benign))
        g("checkout", "-q", "-f", "-B", "side", benign)
        side = commit({"env/SIDE.gpg": "x"}, "side")
        g("checkout", "-q", "-f", "-B", "rooted", benign)
        g("merge", "-q", "--no-ff", "-m", "merge", side)
        merged = g("rev-parse", "HEAD")
        check("from the root: a merge tip is judged on its tree, not shown as nothing",
              "mode 120000" in (trust._tree_reason(repo, None, merged) or ""), trust._tree_reason(repo, None, merged))
        try:
            trust.require_tree(repo, merged)
            required = ""
        except StoreError as e:
            required = str(e)
        check("require_tree (first contact, fresh clone) refuses it, nothing applied", "nothing applied" in required, required)
        g("checkout", "-q", "-f", "-B", "local", base)
        # require_tree records its refusal, and a sha256 store is judged like any other.
        rec: list = []
        real_rec = trust._record_refusal
        trust._record_refusal = lambda store, commit, reason: rec.append((commit, reason))
        try:
            refused(trust.require_tree, repo, "rooted")
        finally:
            trust._record_refusal = real_rec
        check("require_tree records the refusal under the full commit id",
              len(rec) == 1 and len(rec[0][0]) == 40 and "mode 120000" in rec[0][1], rec)
        sha256 = os.path.join(tmp, "sha256")
        os.makedirs(sha256)
        probe = subprocess.run(["git", "-C", sha256, "init", "-q", "--object-format=sha256", "-b", "main"], env=env,
                               capture_output=True)
        if probe.returncode == 0:
            def g2(*a: str) -> str:
                return subprocess.run(["git", "-C", sha256, "-c", "user.name=t", "-c", "user.email=t@t",
                                       "-c", "commit.gpgsign=false", *a], env=env, check=True,
                                      capture_output=True).stdout.decode().strip()
            os.makedirs(os.path.join(sha256, "env"))
            open(os.path.join(sha256, "env", "OK.gpg"), "w").write("x")
            g2("add", "-A")
            g2("commit", "-q", "-m", "one")
            check("a sha256 store: judged from the root, not an unknown-revision error",
                  trust._tree_reason(sha256, None, "HEAD") is None, trust._tree_reason(sha256, None, "HEAD"))
            open(os.path.join(sha256, "stray"), "w").write("x")
            g2("add", "-A")
            g2("commit", "-q", "-m", "two")
            check("…and its stray path is found", "'stray'" in (trust._tree_reason(sha256, None, "HEAD") or ""))
        else:
            check("a sha256 store can be made here", False, probe.stderr)

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
