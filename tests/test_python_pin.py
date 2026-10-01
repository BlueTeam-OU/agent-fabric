#!/usr/bin/env python3
"""tools/fabric/python_pin.py with fake archives in a scratch prefix: the
pinned build installed and linked, an archive that is not the pinned one
refused with nothing changed, a hostile archive refused, an upgrade
moving the link, and a re-run changing nothing."""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import python_pin as pp  # noqa: E402


def archive(version: str, *, escape: str | None = None) -> bytes:
    """A tar.gz shaped like python-build-standalone's install_only: python/bin/python3."""
    script = f"#!/bin/sh\necho {version}\n".encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data, mode in (("python/bin/python3", script, 0o755), ("python/lib/x.txt", b"x\n", 0o600)):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode = len(data), mode
            tf.addfile(ti, io.BytesIO(data))
        if escape:
            ti = tarfile.TarInfo(escape)
            ti.size = 2
            tf.addfile(ti, io.BytesIO(b"x\n"))
    return buf.getvalue()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        prefix, link = os.path.join(tmp, "lib"), os.path.join(tmp, "bin", "fabric-python")
        # A member that climbs out: extracted under <prefix>/.python-pin-*/x,
        # three levels up is beside <prefix>, outside the temporary
        # directory that would otherwise sweep it away. (An absolute name is
        # no test: the data filter strips its slash and keeps it inside.)
        # Without the filter — 3.12 and 3.13's default — tarfile writes it
        # there; on 3.14 the default is already `data`, so CI's older legs
        # are what catch the argument's removal.
        escaped = os.path.join(tmp, "evil", "escaped.txt")
        blobs = {"good": archive("3.13.15"), "next": archive("3.13.16"),
                 "evil": archive("3.13.15", escape="../../../escaped.txt")}
        fetched: list[str] = []

        def fetch(url: str, dest: str) -> None:
            fetched.append(url)
            with open(dest, "wb") as f:
                f.write(blobs[url])

        def pin(version: str, key: str, sha: str | None = None) -> dict:
            return {"python": version, "release": "20260929",
                    "builds": {"x86_64": {"url": key, "sha256": sha or hashlib.sha256(blobs[key]).hexdigest()}}}

        p = pin("3.13.15", "good")
        check("absent at first", pp.check(p, prefix, link) == f"{link} is absent")
        line = pp.install(p, prefix, link, machine="x86_64", fetch=fetch)
        check("installed: the link runs the pinned version", "installed at" in line and pp.check(p, prefix, link) is None
              and pp.version_of(link) == "3.13.15", line)
        mode = os.stat(os.path.join(pp.target(p, prefix), "lib", "x.txt")).st_mode
        check("…every file readable by every account", mode & 0o444 == 0o444, oct(mode))
        fetched.clear()
        line = pp.install(p, prefix, link, machine="x86_64", fetch=fetch)
        check("a re-run downloads nothing and changes nothing", "already in place" in line and not fetched, line)

        bad = pin("3.13.16", "next", sha="0" * 64)
        try:
            pp.install(bad, prefix, link, machine="x86_64", fetch=fetch)
            check("an archive that is not the pinned one is refused", False)
        except pp.PinError as e:
            check("an archive that is not the pinned one is refused", "not the pinned" in str(e), e)
        check("…and the previous build and link stand", pp.check(p, prefix, link) is None
              and not os.path.exists(pp.target(bad, prefix)))

        try:
            pp.install(pin("3.13.15", "good") | {"builds": {"aarch64": {"url": "good", "sha256": "x"}}},
                       os.path.join(tmp, "other"), os.path.join(tmp, "other-link"), machine="x86_64", fetch=fetch)
            check("a machine with no pinned build is refused", False)
        except pp.PinError as e:
            check("a machine with no pinned build is refused, naming what is pinned", "no pinned build for x86_64" in str(e)
                  and "aarch64" in str(e), e)

        evil_prefix = os.path.join(tmp, "evil", "lib")
        try:
            pp.install(pin("3.13.15", "evil"), evil_prefix, os.path.join(tmp, "evil-link"), machine="x86_64", fetch=fetch)
            check("an archive reaching outside its tree is refused", False)
        except tarfile.FilterError as e:
            check("an archive reaching outside its tree is refused by tarfile's data filter",
                  not os.path.exists(escaped) and not os.path.lexists(os.path.join(tmp, "evil-link")), e)

        nxt = pin("3.13.16", "next")
        line = pp.install(nxt, prefix, link, machine="x86_64", fetch=fetch)
        check("an upgrade moves the link to the new build", pp.check(nxt, prefix, link) is None
              and pp.version_of(link) == "3.13.16", line)
        check("…and the old build stays beside it", os.path.isdir(pp.target(p, prefix)))

    if os.geteuid() != 0:
        r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "python_pin.py"), "install"],
                           capture_output=True, text=True, timeout=60)
        check("install as a non-root login: refused, with the command to run", r.returncode == 1
              and "run it as root" in r.stderr and "sudo /usr/bin/python3" in r.stderr, r.stderr)
    r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "python_pin.py"), "nonsense"],
                       capture_output=True, text=True, timeout=60)
    check("usage: exit 2", r.returncode == 2)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
