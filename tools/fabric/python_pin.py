#!/usr/bin/env python3
"""tools/fabric/python_pin.py — the one Python the fleet runs (agent-fabric
ADR-040), pinned in runtime/python.json and installed once per host.

    python_pin.py check              is this host's fabric-python the pinned build?
    python_pin.py install            (root) make it so; idempotent
    python_pin.py path               the interpreter the shims run, for this host

Run by the host's own /usr/bin/python3, which the host contract already
requires (platform/detect.sh): the installer cannot need the Python it
installs. Standard library only.

Each build lands in its own directory,
/usr/local/lib/agent-fabric/python-<version>+<release>~<stamp>/ (on a
Qubes AppVM, /usr/local is one of the two trees that survive a reboot),
and /usr/local/bin/fabric-python points at its interpreter. The archive
is checked against the sha256 the pin carries before anything is
extracted; the extraction goes to a directory beside the target and is
renamed to a name nothing has, so nothing existing is ever renamed away
or overwritten: the one os.replace of the link is the only moment the
fleet's interpreter changes, and a failure or a SIGKILL at any step leaves
the link on a build that runs. A build installed before the stamp existed,
python-<version>+<release> itself, is still a build of its pin. Every file
is readable by every account: each runs it.

ADR-040 rule 1 allows no third-party package, and lint refuses a pinned
wheel: the wheel machinery below stays for the day rule 1 is amended to
allow one. It checks each wheel against its sha256 like the archive and
installs it into the extracted tree by its own pip, offline and without
dependencies, before the rename. Its known limit: a wheel's console
scripts would carry the temporary tree's path in their shebangs, so one
with entry points needs them rewritten after the rename first. The
pin's `imports` are what the build must import, and both are part of
"is this the pinned build", not only the version.

exit 0 present (check) or installed; 1 absent, wrong or failed, said in one
line; 2 usage.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
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
        return {"python": doc["python"], "release": doc["release"], "builds": doc["builds"],
                "imports": doc.get("imports", [])}
    except (OSError, ValueError, KeyError) as e:
        raise PinError(f"runtime/python.json unreadable: {e}") from None


def target(p: dict, prefix: str = PREFIX) -> str:
    """The pin's name stem: the whole directory of a build installed before
    builds were stamped, and what a stamped one's name starts with."""
    return os.path.join(prefix, f"python-{p['python']}+{p['release']}")


def builds_of(p: dict, prefix: str = PREFIX) -> list[str]:
    """Every directory that is, by its name, a build of this pin: the flat
    one and each stamped one. The stamp is fixed-shape hex after "~", so a
    release that merely begins with this one's ("1" and "1.5") is no match."""
    stem = target(p, prefix)
    pattern = re.compile(re.escape(os.path.basename(stem)) + r"~[0-9a-f]{16}", re.ASCII)
    try:
        names = sorted(os.listdir(prefix))
    except FileNotFoundError:
        names = []
    found = [os.path.join(prefix, n) for n in names if pattern.fullmatch(n)]
    return ([stem] if os.path.lexists(stem) else []) + found


def _build_of_link(p: dict, prefix: str, link: str) -> str | None:
    """The build directory the link reaches, when it is a build of this pin."""
    real = os.path.realpath(link)
    build = os.path.dirname(os.path.dirname(real))
    mine = {os.path.realpath(b) for b in builds_of(p, prefix)}
    return build if os.path.basename(real) == "python3" and build in mine else None


def version_of(interpreter: str) -> str | None:
    try:
        r = subprocess.run([interpreter, "-I", "-c", "import platform; print(platform.python_version())"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


# One run answers the version, each pinned wheel's installed version and
# whether every pinned import loads: a line each, the version first.
_PROBE = """import importlib, importlib.metadata as m, platform, sys
print(platform.python_version())
for a in sys.argv[1:]:
    kind, _, name = a.partition(":")
    if kind == "dist":
        try:
            print(name, m.version(name))
        except m.PackageNotFoundError:
            print(name, "absent")
    else:
        importlib.import_module(name)
"""


def _machine_wheels(p: dict, machine: str | None) -> list[dict]:
    return (p["builds"].get(machine or platform.machine()) or {}).get("wheels", [])


def build_problem(interpreter: str, p: dict, machine: str | None = None) -> str | None:
    """None when the interpreter is the pinned version, carries each pinned
    wheel at its pinned version and imports every pinned module."""
    wheels = _machine_wheels(p, machine)
    args = [f"dist:{w['name']}" for w in wheels] + [f"import:{m}" for m in p.get("imports", [])]
    try:
        r = subprocess.run([interpreter, "-I", "-c", _PROBE, *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return f"{interpreter} runs nothing, not {p['python']}"
    lines = r.stdout.splitlines()
    got = lines[0].strip() if lines else ""
    if got != p["python"]:
        return f"{interpreter} runs {got or 'nothing'}, not {p['python']}"
    have = dict(line.split(" ", 1) for line in lines[1:] if " " in line)
    for w in wheels:
        if have.get(w["name"]) != w["version"]:
            return f"{interpreter} has {w['name']} {have.get(w['name'], 'absent')}, not the pinned {w['version']}"
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["exit %d" % r.returncode])[-1]
        return f"{interpreter} cannot import every pinned module ({', '.join(p.get('imports', []))}): {last}"
    return None


def check(p: dict, prefix: str = PREFIX, link: str = LINK, machine: str | None = None) -> str | None:
    """None when the link reaches the pinned build and it runs as that
    version, with its wheels and imports; otherwise what is wrong."""
    if not os.path.lexists(link):
        return f"{link} is absent"
    if _build_of_link(p, prefix, link) is None:
        return f"{link} points at {os.path.realpath(link)}, not a build of the pinned {os.path.basename(target(p, prefix))}"
    return build_problem(link, p, machine)


def _download(url: str, dest: str) -> None:
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _install_wheels(python: str, wheels: list[dict], tmp: str, fetch) -> None:
    """Each wheel fetched under its own file name (pip reads the tags from
    it), checked, then installed by the build's pip: -I and a null config
    so nothing `sudo -E` carried in (PIP_INDEX_URL, a user pip.conf)
    reaches it, --no-index and --no-deps so it installs exactly the checked
    files or fails."""
    paths = []
    for w in wheels:
        path = os.path.join(tmp, os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(w["url"]).path)))
        fetch(w["url"], path)
        got = _sha256(path)
        if got != w["sha256"]:
            raise PinError(f"{w['name']}'s wheel sha256 is {got}, not the pinned {w['sha256']}; nothing installed")
        paths.append(path)
    if not paths:
        return
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON"))}
    env["PIP_CONFIG_FILE"] = os.devnull
    r = subprocess.run([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir",
                        "--disable-pip-version-check", "--no-warn-script-location", "--root-user-action=ignore",
                        *paths], capture_output=True, text=True, timeout=300, env=env)
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["exit %d" % r.returncode])[-1]
        raise PinError(f"pip could not install {', '.join(w['name'] for w in wheels)}: {last}; nothing installed")


def _sweep(p: dict, prefix: str, keep: str) -> None:
    """Remove the other builds of this pin once the link is on `keep` and
    passes. Left until then (not removed before the switch) because a service
    started from the old one still maps its files; swept here rather than
    left for a person because they are the same version and release, which
    nothing can want again. A failure to remove is not the install's: what is
    left is unlinked, fails build_problem or is merely extra, and the next
    run sweeps it. Older pins' directories are not touched. Two installs at
    once are not supported (root, by hand, one host): the later sweep could
    remove the other's build before it links."""
    for b in builds_of(p, prefix):
        if os.path.realpath(b) != os.path.realpath(keep):
            shutil.rmtree(b, ignore_errors=True)


def install(p: dict, prefix: str = PREFIX, link: str = LINK, machine: str | None = None,
            fetch=_download) -> str:
    """Make the link reach the pinned build; what was done, in one line."""
    if check(p, prefix, link, machine) is None:
        _sweep(p, prefix, keep=_build_of_link(p, prefix, link))
        return f"{link}: Python {p['python']} ({p['release']}) already in place"
    arch = machine or platform.machine()
    build = p["builds"].get(arch)
    if not build:
        raise PinError(f"no pinned build for {arch} (runtime/python.json has {', '.join(sorted(p['builds']))})")
    os.makedirs(prefix, mode=0o755, exist_ok=True)
    # A build of this pin that already runs as pinned (the flat one of an
    # earlier layout, or a stamped one a run was cut off after) is linked as
    # it is: nothing is downloaded for a link that only points elsewhere.
    dest = next((b for b in builds_of(p, prefix) if build_problem(os.path.join(b, "bin", "python3"), p, arch) is None), None)
    if dest is None:
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
            _install_wheels(os.path.join(built, "bin", "python3"), build.get("wheels", []), tmp, fetch)
            problem = build_problem(os.path.join(built, "bin", "python3"), p, arch)
            if problem:
                raise PinError(f"the extracted build is not the pinned one: {problem}; nothing installed")
            for d, dirs, files in os.walk(built):
                os.chmod(d, 0o755)
                for name in files:
                    path = os.path.join(d, name)
                    if not os.path.islink(path):
                        os.chmod(path, os.stat(path).st_mode | 0o444)
            # Same version and release with other wheels or imports is a
            # different build in a different directory, never a rename over
            # the one the link and running services use: any interval between
            # two renames would leave the link dangling for every command of
            # the account. A random stamp makes the name one nothing has, and
            # the only thing that ever moves is the link.
            dest = f"{target(p, prefix)}~{os.urandom(8).hex()}"
            os.rename(built, dest)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    tmp_link = f"{link}.new"
    if os.path.lexists(tmp_link):
        os.unlink(tmp_link)
    os.symlink(os.path.join(dest, "bin", "python3"), tmp_link)
    os.replace(tmp_link, link)
    problem = check(p, prefix, link, arch)
    if problem:
        raise PinError(f"installed, but {problem}")
    _sweep(p, prefix, keep=dest)
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
