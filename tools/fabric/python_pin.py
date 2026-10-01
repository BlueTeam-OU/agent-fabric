#!/usr/bin/env python3
"""tools/fabric/python_pin.py — the one Python the fleet runs (agent-fabric
ADR-040), pinned in runtime/python.json and installed once per host.

    python_pin.py check              is this host's fabric-python the pinned build?
    python_pin.py install            (root) make it so; idempotent
    python_pin.py path               the interpreter the shims run, for this host

Run by the host's own /usr/bin/python3, which the host contract already
requires (platform/detect.sh): the installer cannot need the Python it
installs. Standard library only.

The build lands in /usr/local/lib/agent-fabric/python-<version>+<release>/
(on a Qubes AppVM, /usr/local is one of the two trees that survive a
reboot) and /usr/local/bin/fabric-python points at its interpreter. The
archive is checked against the sha256 the pin carries before anything is
extracted; the extraction goes to a directory beside the target and is
renamed into place, so a failure leaves the previous build and link as
they were. Every file is readable by every account: each runs it.

exit 0 present (check) or installed; 1 absent, wrong or failed, said in one
line; 2 usage.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIN = os.path.join(FABRIC, "runtime", "python.json")
# The overrides are for a non-root reader (a test, fabric-status's check);
# as root the installer writes only the fixed paths, whatever `sudo -E`
# carried in (review of #77).
_AS_ROOT = os.geteuid() == 0
PREFIX = "/usr/local/lib/agent-fabric" if _AS_ROOT else os.environ.get("AGENT_FABRIC_PYTHON_PREFIX", "/usr/local/lib/agent-fabric")
LINK = "/usr/local/bin/fabric-python" if _AS_ROOT else os.environ.get("AGENT_FABRIC_PYTHON_LINK", "/usr/local/bin/fabric-python")


class PinError(Exception):
    """The whole answer, in one line."""


def pin(path: str = PIN) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        return {"python": doc["python"], "release": doc["release"], "builds": doc["builds"]}
    except (OSError, ValueError, KeyError) as e:
        raise PinError(f"runtime/python.json unreadable: {e}") from None


def target(p: dict, prefix: str = PREFIX) -> str:
    return os.path.join(prefix, f"python-{p['python']}+{p['release']}")


def version_of(interpreter: str) -> str | None:
    try:
        r = subprocess.run([interpreter, "-I", "-c", "import platform; print(platform.python_version())"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def check(p: dict, prefix: str = PREFIX, link: str = LINK) -> str | None:
    """None when the link reaches the pinned build and it runs as that
    version; otherwise what is wrong."""
    want = os.path.join(target(p, prefix), "bin", "python3")
    if not os.path.lexists(link):
        return f"{link} is absent"
    if os.path.realpath(link) != os.path.realpath(want):
        return f"{link} points at {os.path.realpath(link)}, not the pinned {want}"
    got = version_of(link)
    if got != p["python"]:
        return f"{link} runs {got or 'nothing'}, not {p['python']}"
    return None


def _download(url: str, dest: str) -> None:
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(p: dict, prefix: str = PREFIX, link: str = LINK, machine: str | None = None,
            fetch=_download) -> str:
    """Make the link reach the pinned build; what was done, in one line."""
    if check(p, prefix, link) is None:
        return f"{link}: Python {p['python']} ({p['release']}) already in place"
    arch = machine or platform.machine()
    build = p["builds"].get(arch)
    if not build:
        raise PinError(f"no pinned build for {arch} (runtime/python.json has {', '.join(sorted(p['builds']))})")
    dest = target(p, prefix)
    os.makedirs(prefix, mode=0o755, exist_ok=True)
    if not version_of(os.path.join(dest, "bin", "python3")) == p["python"]:
        with tempfile.TemporaryDirectory(dir=prefix, prefix=".python-pin-") as tmp:
            archive = os.path.join(tmp, "python.tar.gz")
            fetch(build["url"], archive)
            got = _sha256(archive)
            if got != build["sha256"]:
                raise PinError(f"the archive's sha256 is {got}, not the pinned {build['sha256']}; nothing installed")
            out = os.path.join(tmp, "x")
            with tarfile.open(archive) as tf:
                # The data filter refuses absolute paths, .. and links that
                # leave the tree: a pinned hash makes a hostile archive
                # unlikely, not impossible to have been pinned.
                tf.extractall(out, filter="data")
            built = os.path.join(out, "python")
            if version_of(os.path.join(built, "bin", "python3")) != p["python"]:
                raise PinError(f"the extracted interpreter is not Python {p['python']}; nothing installed")
            for d, dirs, files in os.walk(built):
                os.chmod(d, 0o755)
                for name in files:
                    path = os.path.join(d, name)
                    if not os.path.islink(path):
                        os.chmod(path, os.stat(path).st_mode | 0o444)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            os.rename(built, dest)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    tmp_link = f"{link}.new"
    if os.path.lexists(tmp_link):
        os.unlink(tmp_link)
    os.symlink(os.path.join(dest, "bin", "python3"), tmp_link)
    os.replace(tmp_link, link)
    problem = check(p, prefix, link)
    if problem:
        raise PinError(f"installed, but {problem}")
    return f"{link}: Python {p['python']} ({p['release']}) installed at {dest}"


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("check", "install", "path"):
        print("usage: python_pin.py check|install|path", file=sys.stderr)
        return 2
    try:
        p = pin()
        if argv[0] == "path":
            print(LINK)
            return 0
        if argv[0] == "check":
            problem = check(p)
            print(f"fabric-python: {problem}" if problem else f"fabric-python: Python {p['python']} ({p['release']})")
            return 1 if problem else 0
        if os.geteuid() != 0:
            raise PinError(f"install writes {PREFIX} and {LINK}: run it as root "
                           f"(sudo /usr/bin/python3 {os.path.abspath(__file__)} install)")
        print(install(p))
        return 0
    except (PinError, OSError, tarfile.TarError) as e:
        print(f"python_pin: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
