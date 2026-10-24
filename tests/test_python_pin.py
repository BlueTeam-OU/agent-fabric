#!/usr/bin/env python3
"""tools/fabric/python_pin.py with fake archives in a scratch prefix: the
pinned build installed and linked, an archive that is not the pinned one
refused with nothing changed, a hostile archive refused, an upgrade
moving the link, and a re-run changing nothing; a pinned wheel checked and
handed to the build's own pip offline, a wheel that is not the pinned one
refused, a build whose wheel is not the pinned version rebuilt, and a
pinned import that fails refused."""
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


# The fake interpreter answers python_pin's probe and its pip: a pip run
# records its arguments and "installs" each wheel by writing the
# distribution line the probe prints, NAME VERSION read from the wheel's
# file name; a probe that asks to import "missing" fails as Python would.
FAKE = """#!/bin/sh
d=$(dirname "$(readlink -f "$0")")/..
if [ "$2" = "-m" ] && [ "$3" = "pip" ]; then
  echo "$@" > "$d/pip-args"
  echo "PIP_INDEX_URL=${PIP_INDEX_URL-unset} PIP_CONFIG_FILE=${PIP_CONFIG_FILE-unset}" > "$d/pip-env"
  for a; do case "$a" in *failpip*) echo "ERROR: the wheel would not install" >&2; exit 1;; esac; done
  for a; do case "$a" in *.whl) basename "$a" | awk -F- '{print $1, $2}' >> "$d/dists";; esac; done
  exit 0
fi
echo {version}
cat "$d/dists" 2>/dev/null
for a; do [ "$a" = import:missing ] && echo "ModuleNotFoundError: No module named 'missing'" >&2 && exit 1; done
exit 0
"""


def archive(version: str, *, escape: str | None = None) -> bytes:
    """A tar.gz shaped like python-build-standalone's install_only: python/bin/python3."""
    script = FAKE.replace("{version}", version).encode()
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

        # Wheels: the build gets them before it is renamed into place.
        blobs["wheel"], blobs["wheel2"] = b"a wheel\n", b"the next wheel\n"
        wurl = "https://files.example/x/brotli-1.2.1-cp314-cp314-manylinux_2_17_x86_64.whl"
        w2url = "https://files.example/x/brotli-1.2.2-cp314-cp314-manylinux_2_17_x86_64.whl"
        blobs[wurl], blobs[w2url] = blobs["wheel"], blobs["wheel2"]

        def wpin(version: str, url: str, wversion: str, sha: str | None = None, imports=("brotli",)) -> dict:
            q = pin(version, "good")
            q["builds"]["x86_64"]["wheels"] = [{"name": "brotli", "version": wversion, "url": url,
                                                "sha256": sha or hashlib.sha256(blobs[url]).hexdigest()}]
            return q | {"imports": list(imports)}

        wprefix, wlink = os.path.join(tmp, "w", "lib"), os.path.join(tmp, "w", "fabric-python")
        q = wpin("3.13.15", wurl, "1.2.1")
        pp.install(p, wprefix, wlink, machine="x86_64", fetch=fetch)
        problem = pp.check(q, wprefix, wlink, "x86_64")
        check("a build of the pinned version that lacks the pinned wheel is not the pinned build",
              problem is not None and "brotli absent, not the pinned 1.2.1" in problem, problem)
        fetched.clear()
        os.environ["PIP_INDEX_URL"] = "https://index.example/simple"
        try:
            line = pp.install(q, wprefix, wlink, machine="x86_64", fetch=fetch)
        finally:
            del os.environ["PIP_INDEX_URL"]
        with open(os.path.join(pp.target(q, wprefix), "pip-args")) as fh:
            args = fh.read().split()
        with open(os.path.join(pp.target(q, wprefix), "pip-env")) as fh:
            pip_env = fh.read().split()
        check("a pinned wheel is fetched, checked and installed by the build's own pip, offline",
              wurl in fetched and pp.check(q, wprefix, wlink, "x86_64") is None
              and {"--no-index", "--no-deps", "-I"} <= set(args)
              and any(a.endswith("/brotli-1.2.1-cp314-cp314-manylinux_2_17_x86_64.whl") for a in args), (line, args))
        check("…with nothing of the caller's pip settings: no index from the environment, a null config",
              pip_env == ["PIP_INDEX_URL=unset", f"PIP_CONFIG_FILE={os.devnull}"], pip_env)

        bad = wpin("3.13.15", w2url, "1.2.2", sha="0" * 64)
        try:
            pp.install(bad, wprefix, wlink, machine="x86_64", fetch=fetch)
            check("a wheel that is not the pinned one is refused", False)
        except pp.PinError as e:
            check("a wheel that is not the pinned one is refused", "wheel sha256" in str(e) and "not the pinned" in str(e), e)
        check("…and the build in place stands, with its wheel", pp.check(q, wprefix, wlink, "x86_64") is None)

        q2 = wpin("3.13.15", w2url, "1.2.2")
        problem = pp.check(q2, wprefix, wlink, "x86_64")
        check("a build whose wheel is not the pinned version is not the pinned build",
              problem is not None and "brotli 1.2.1, not the pinned 1.2.2" in problem, problem)
        pp.install(q2, wprefix, wlink, machine="x86_64", fetch=fetch)
        check("…and install rebuilds it with the pinned wheel", pp.check(q2, wprefix, wlink, "x86_64") is None)

        # The same version and release with another wheel rebuilds the build
        # the link reaches, in its place: a failure must leave it standing.
        furl = "https://files.example/x/brotli-1.2.3-failpip-manylinux_2_17_x86_64.whl"
        blobs[furl] = b"a wheel pip refuses\n"
        try:
            pp.install(wpin("3.13.15", furl, "1.2.3"), wprefix, wlink, machine="x86_64", fetch=fetch)
            check("a wheel pip cannot install is refused", False)
        except pp.PinError as e:
            check("a wheel pip cannot install is refused, with pip's last line",
                  "pip could not install brotli" in str(e) and "would not install" in str(e), e)
        check("…and the build the link reaches stands, with its wheel", pp.check(q2, wprefix, wlink, "x86_64") is None)
        real_rename = os.rename

        def rename_refusing_the_new_build(src: str, dst: str) -> None:
            if src.endswith(os.sep + "python") and ".python-pin-" in src:
                # An interrupt, not only an OSError: Ctrl-C between the renames.
                raise KeyboardInterrupt("rename refused (test)")
            real_rename(src, dst)
        pp.os.rename = rename_refusing_the_new_build
        try:
            pp.install(q, wprefix, wlink, machine="x86_64", fetch=fetch)
            check("a failed swap into place is refused", False)
        except KeyboardInterrupt as e:
            check("a swap into place interrupted puts the previous build back where the link reaches it",
                  "rename refused" in str(e) and pp.check(q2, wprefix, wlink, "x86_64") is None, e)
        finally:
            pp.os.rename = real_rename

        def rename_interrupted_after_moving_aside(src: str, dst: str) -> None:
            real_rename(src, dst)
            if dst.endswith(os.sep + "old") and ".python-pin-" in dst:
                # The first rename done, the interrupt right after it.
                raise KeyboardInterrupt("interrupted after moving aside (test)")
        pp.os.rename = rename_interrupted_after_moving_aside
        try:
            pp.install(q, wprefix, wlink, machine="x86_64", fetch=fetch)
            check("an interrupt after the move aside is refused", False)
        except KeyboardInterrupt as e:
            check("an interrupt right after the move aside puts the previous build back",
                  "after moving aside" in str(e) and pp.check(q2, wprefix, wlink, "x86_64") is None, e)
        finally:
            pp.os.rename = real_rename

        try:
            pp.install(wpin("3.13.16", wurl, "1.2.1", imports=("missing",)) | {"builds": {"x86_64": {
                "url": "next", "sha256": hashlib.sha256(blobs["next"]).hexdigest(), "wheels": []}}},
                wprefix, wlink, machine="x86_64", fetch=fetch)
            check("a build that cannot import a pinned module is refused", False)
        except pp.PinError as e:
            check("a build that cannot import a pinned module is refused, naming it",
                  "cannot import" in str(e) and "missing" in str(e) and pp.check(q2, wprefix, wlink, "x86_64") is None, e)

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
