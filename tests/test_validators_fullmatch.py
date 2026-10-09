#!/usr/bin/env python3
"""A validator that decides on a whole value refuses it with a trailing
newline. `$` matches before one, so `^...$` with .match accepted "name\\n"
(found in resume.py, then in a scan of the tree); .fullmatch does not. One
case per whole-value site, each with its positive control. Sites that read
a line from `split("\\n")` or a stripped string cannot carry a newline and
have no case."""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
import secret_run  # noqa: E402
import secret_store  # noqa: E402
from secretstore import accounts, backup, core, entries, mirrors, trust  # noqa: E402

AID = "01a11d49-960f-7f91-a7a7-8e640fb7394c"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:300]}"))
        fails += not good

    def refuses(call, needle: str) -> tuple[bool, object]:
        try:
            call()
        except (core.StoreError, secret_run.Refused) as e:
            return needle in str(e), str(e)
        except Exception as e:   # the old code ran on into the store: a failure of this case, not a crash of the suite
            return False, repr(e)
        return False, "no refusal"

    check("gh: --repo a/b is explicit, so not scoped", gh._scoped(["pr", "view", "--repo", "a/b"]) is False)
    check("gh: --repo 'a/b\\n' names no repository", gh._scoped(["pr", "view", "--repo", "a/b\n"]) is True)
    check("gh: repo view a/b is explicit", gh._scoped(["repo", "view", "a/b"]) is False)
    check("gh: repo view 'a/b\\n' is not", gh._scoped(["repo", "view", "a/b\n"]) is True)
    url = "https://github.com/a/b/pull/1"
    check("gh: pr view <url> is explicit", gh._scoped(["pr", "view", url]) is False)
    check("gh: pr view '<url>\\n' is not", gh._scoped(["pr", "view", url + "\n"]) is True)

    check("accounts: a slug is accepted", accounts._slug_name("acct-1").endswith("ACCT_1"), accounts._slug_name("acct-1"))
    ok, why = refuses(lambda: accounts._slug_name("acct-1\n"), "is not an account slug")
    check("accounts: 'acct-1\\n' is not a slug", ok, why)

    entries._check_name("DB_PASS")
    ok, why = refuses(lambda: entries._check_name("DB_PASS\n"), "is not a secret name")
    check("entries: a secret name with '\\n' is refused (the add path's _write_entry)", ok, why)
    ok, why = refuses(lambda: entries._write_entry("/nonexistent", "DB_PASS\n", b"v", []), "is not a secret name")
    check("entries: _write_entry refuses it before touching the store", ok, why)

    ok, why = refuses(lambda: secret_run.parse(["A_B\n", "--", "true"]), "is not a secret name")
    check("secret_run: a name with '\\n' is refused", ok, why)
    check("secret_run: its control parses", secret_run.parse(["A_B", "--", "true"])[0] == ["A_B"])

    saved = secret_store.reserved
    secret_store.reserved = lambda name: "someone"
    try:
        ok, why = refuses(lambda: secret_store._own_or_managed("A_B", False, "set"), "is managed by someone")
        check("secret_store: a managed name is refused (control)", ok, why)
        check("secret_store: 'A_B\\n' is no name here: left to the write path, which refuses it",
              secret_store._own_or_managed("A_B\n", False, "set") is None)
    finally:
        secret_store.reserved = saved

    ok, why = refuses(lambda: mirrors.resolve(AID + "\n", {}), "is neither a login nor an agent id")
    check("mirrors.resolve: an id with '\\n' is neither", ok, why)
    ok, why = refuses(lambda: mirrors.resolve("alice\n", {}), "is neither a login nor an agent id")
    check("mirrors.resolve: a login with '\\n' is neither", ok, why)
    try:
        mirrors.resolve("alice", {})
        why = "no refusal"
    except core.StoreError as e:
        why = str(e)
    check("mirrors.resolve: 'alice' is a login (control: refused for another reason)",
          "neither" not in why and bool(why), why)
    ok, why = refuses(lambda: mirrors.seed_child(AID + "\n", "r", "t"), "is not an agent id")
    check("mirrors.seed_child: an id with '\\n' is refused", ok, why)

    env = {k: os.environ.get(k) for k in ("HOME", "AGENT_FABRIC_SECRET_STORE")}
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HOME"] = os.path.join(tmp, "home")
        os.environ["AGENT_FABRIC_SECRET_STORE"] = os.path.join(tmp, "store")
        try:
            ok, why = refuses(lambda: entries.init(agent_id=AID + "\n"), "no agent id")
            check("entries.init: an agent id with '\\n' is no agent id", ok, why)

            os.makedirs(os.path.join(tmp, "store", "env"))
            for n in ("A_B.gpg", "C_D\n.gpg"):
                open(os.path.join(tmp, "store", "env", n), "w").close()
            check("entries.names: the file 'C_D\\n.gpg' is no secret", entries.names() == ["A_B"], entries.names())

            kids = core.children_dir()
            for n in (AID, "01a11d49-960f-7f91-a7a7-8e640fb7394d\n"):
                os.makedirs(os.path.join(kids, n, ".git"))
            open(os.path.join(tmp, "store", ".agent-id"), "w").write(AID + "\n")
            check("backup._stores: a mirror directory named with '\\n' is not held",
                  sorted(backup._stores()) == sorted([AID]), sorted(backup._stores()))
            check("trust._mirror_ids: nor is it a mirror", trust._mirror_ids() == [AID], trust._mirror_ids())
            open(os.path.join(kids, AID[:-1] + "e\n.refusal.json"), "w").close()
            check("trust._mirror_ids(kept): '<id>\\n.refusal.json' keeps nothing",
                  trust._mirror_ids(kept=True) == [AID], trust._mirror_ids(kept=True))
        finally:
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    print(f"{'FAILED' if fails else 'passed'}: {fails} failing")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
