#!/usr/bin/env python3
"""tools/fabric/fabric_writes.py: a person's version of a file the fabric
replaces is kept every time it differs from the fabric's last write, under a
name of its own, with its mode; the fabric's own unmarked files are never
backed up; the record lives where runtime/identity.py puts the account's
state (review of #86)."""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "runtime"))


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="test_fabric_writes.")
    saved = {k: os.environ.get(k) for k in ("AGENT_FABRIC_STATE_DIR", "XDG_STATE_HOME", "HOME")}
    try:
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state")
        os.environ["HOME"] = os.path.join(tmp, "home")
        import fabric_writes as fw
        import identity
        check("the record lives in runtime/identity.py's agent state directory",
              fw.state_dir() == identity.agent_state_dir(), (fw.state_dir(), identity.agent_state_dir()))
        del os.environ["AGENT_FABRIC_STATE_DIR"]
        os.environ["XDG_STATE_HOME"] = os.path.join(tmp, "xdg")
        check("…and without the override, under XDG_STATE_HOME as identity has it",
              fw.state_dir() == identity.agent_state_dir(), (fw.state_dir(), identity.agent_state_dir()))
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state")

        d = os.path.join(tmp, "ws")
        os.makedirs(d)
        dest = os.path.join(d, "CLAUDE.md")
        base = dest + fw.SUFFIX

        def write(content: bytes) -> None:
            """What bootstrap's put() does around the write."""
            fw.keep_person_version(dest)
            with open(dest, "wb") as f:
                f.write(content)
            fw.record(dest, content)

        def person(content: bytes, mode: int = 0o600) -> None:
            with open(dest, "wb") as f:
                f.write(content)
            os.chmod(dest, mode)

        check("nothing to keep when there is no file", fw.keep_person_version(dest) is None)
        person(b"person v1\n")
        write(b"fabric one\n")
        check("a person's first version is kept as .before-agent-fabric",
              open(base, "rb").read() == b"person v1\n")
        check("…with the person's mode, not 0644", stat.S_IMODE(os.stat(base).st_mode) == 0o600,
              oct(stat.S_IMODE(os.stat(base).st_mode)))
        write(b"fabric two\n")
        check("the fabric's own unmarked file changing is never backed up",
              not os.path.exists(base + ".1"), sorted(os.listdir(d)))
        person(b"person v2\n")
        write(b"fabric three\n")
        check("a person's LATER edit is kept too, under the next free name, the first backup untouched",
              open(base + ".1", "rb").read() == b"person v2\n" and open(base, "rb").read() == b"person v1\n",
              sorted(os.listdir(d)))
        person(b"person v1\n")
        write(b"fabric four\n")
        check("a version a backup already holds is not kept twice", not os.path.exists(base + ".2"), sorted(os.listdir(d)))
        person(b"has the agent-fabric marker\n")
        write(b"fabric five\n")
        check("a file carrying the marker is the fabric's: not kept", not os.path.exists(base + ".2"))

        os.remove(base)
        person(b"person v3\n")
        write(b"fabric six\n")
        check("a free base name is used before a new number",
              open(base, "rb").read() == b"person v3\n" and not os.path.exists(base + ".2"), sorted(os.listdir(d)))

        shutil.rmtree(os.path.join(tmp, "state"))
        with open(dest, "wb") as f:
            f.write(b"fabric six\n")
        check("a lost record costs at most one backup, never a lost file",
              fw.keep_person_version(dest) is not None)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for root, dirs, _ in os.walk(tmp):
            for x in dirs:
                os.chmod(os.path.join(root, x), 0o700)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
