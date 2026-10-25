"""tools/fabric/control/carrier_install.py — the carrier's transport on this account (<carrier> is gzcoord.carrier.CARRIER_NAME):
`<carrier>-install`, a signed ACTION that installs the release the fabric
pins, with the archive's own install.sh (agent-fabric ADR-064 §5 rule 4,
never a checkout build), and `<carrier>`, the read that says what is there.
The shape is gateway.py's (`gateway-install` / `gateway`); the parts that
are the same are imported from it.

THE PIN is runtime/<carrier>/release.json in this checkout: `current` names
the release every account installs, releases.<version>.<arch> holds the
asset url, the archive's name, size and SHA-256, the directory the archive
unpacks into (`root`) and what each program must print under `--version`
(`reports`). The size and digest are the reviewed ones, never fetched from
the artifact's own origin.

THE REQUEST has no arguments: the release is the pin's `current`, and
nothing in a request names a url, a digest, a size or a path.

THE SEQUENCE, for one account, as that login and with no root:
  1. a lock for the account (a second install at once is refused, not queued);
  2. "current", nothing downloaded and nothing touched, when the marker names
     this release and every program it lists is in ~/.local/bin with the
     digest the marker recorded;
  3. the archive is downloaded with the account's GH_TOKEN (the repository is
     internal): into the install's own temporary directory, the token in a
     header only and dropped on the redirect to storage;
  4. its size AND its SHA-256 must equal the pin's before anything is
     extracted or run;
  5. it is extracted into that directory, member by member, after every
     member has been judged: one outside `root`, absolute, with "..", twice,
     or anything but a file or a directory (a link, a device) refuses the
     whole archive;
  6. every program in `reports` is run from the extracted tree with --version
     and must print exactly its value: a build that does not say who it is
     installs nothing;
  7. `<root>/install.sh` runs with no argument, in a minimal environment
     (programs into ~/.local/bin, the two user-unit templates into the
     user's systemd directory; it enables nothing and touches no profile);
  8. each program the archive carries in bin/ must now be in ~/.local/bin
     byte for byte, the two unit templates must be there, and every program
     in `reports` is run from ~/.local/bin and must print its value again;
  9. the marker (<state>/<carrier>-install.json) is written whole, by rename;
 10. the temporary directory is removed however the install ends, and one a
     killed install left is removed at the start of the next.

THE REPLY, data["<carrier>-install"]: status "installed" | "current" |
"refused" | "failed"; version; sha256 (the verified archive digest, the pin's);
programs (name -> digest of the file now in ~/.local/bin); reason on a refusal
or a failure. A refusal is a request the action will not take (an argument,
an architecture the pin has no build for); a failure is an install that was
tried or could not start. A failure at step 6 or before leaves the account as
it was; one after step 7 may leave the programs install.sh copied, which the
next run replaces: the marker is written only after step 8.

THE READ, data["<carrier>"]: status "ok" | "absent" | "unreadable"; version
and reports, as the installed programs print them under --version; programs
(name -> digest); release_sha256 (the marker's, when every digest still
agrees); pinned (whether what is installed prints what the pin says); units
(whether each template is in the user's systemd directory). A program that
will not report makes the status "unreadable" with the reason, never a guessed
version.

fetch_and_unpack is the part of steps 3-5 another tool needs without an
install (the two-account live check): it downloads, verifies and extracts into
a directory it is given and runs nothing.
"""
from __future__ import annotations

import errno
import fcntl
import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.error
import zlib
from typing import Any, Callable

from gzcoord.carrier import CARRIER_LABEL, CARRIER_NAME
from control.gateway import ARCHES, SHA256, PinError, _arch, _fsync_dir, _why, download, file_sha256
from control.ops import util
from control.upgrade import VERSION_RE

PIN_REL = os.path.join("runtime", CARRIER_NAME, "release.json")
INSTALL_OP = f"{CARRIER_NAME}-install"
MARKER = f"{INSTALL_OP}.json"
LOCK = f"{INSTALL_OP}.lock"
WORK = INSTALL_OP
UNITS = (f"{CARRIER_NAME}-daemon@.service", f"{CARRIER_NAME}-client@.service")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
DOWNLOAD_TIMEOUT_S = 600       # the whole download; the archive is 117 MB and the link has stalled for 30 s
READ_TIMEOUT_S = 60
EXTRACT_BUDGET_S = 120         # what the extraction of ~480 MB of programs is allowed for in the reply's budget
INSTALL_SH_TIMEOUT_S = 120
VERSION_TIMEOUT_S = 10
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 1000
CARRIER_INSTALL_BUDGET_S = DOWNLOAD_TIMEOUT_S + EXTRACT_BUDGET_S + INSTALL_SH_TIMEOUT_S + 8 * VERSION_TIMEOUT_S + 40
# The only variables of the session install.sh and the programs see besides HOME and PATH: where the
# user's systemd manager and configuration are. The token and the rest of the session never reach them.
PASS_ENV = ("XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "DBUS_SESSION_BUS_ADDRESS")


class InstallError(Exception):
    """One line for a reply: what failed, never the token."""


def pin_problem(pin: Any) -> str | None:
    """None for a pin of the shape runtime/<carrier>/release.json documents, else what is wrong."""
    if not isinstance(pin, dict) or pin.get("version") != 1:
        return "is not version 1"
    releases = pin.get("releases")
    current = pin.get("current")
    if not isinstance(releases, dict) or not releases:
        return "names no releases"
    if not (isinstance(current, str) and VERSION_RE.fullmatch(current) and current in releases):
        return "has a current that is not one of its releases"
    for version, rel in releases.items():
        if not (isinstance(version, str) and VERSION_RE.fullmatch(version)):
            return f"names the release {version!r}, not digits.digits.digits"
        if not isinstance(rel, dict):
            return f"{version} is not an object"
        if not (isinstance(rel.get("tag"), str) and rel["tag"] == f"v{version}"):
            return f"{version} has a tag other than v{version}"
        if not (isinstance(rel.get("commit"), str) and COMMIT_RE.fullmatch(rel["commit"])):
            return f"{version} has no commit of 40 lowercase hex digits"
        builds = [k for k in rel if k in ARCHES.values()]
        if not builds:
            return f"{version} has no build"
        for arch in builds:
            where = f"{version}/{arch}"
            b = rel[arch]
            if not isinstance(b, dict):
                return f"{where} is not an object"
            if not (isinstance(b.get("url"), str) and b["url"].startswith("https://")):
                return f"{where} has no https url"
            if not (isinstance(b.get("name"), str) and b["name"].endswith(".tar.gz") and "/" not in b["name"]):
                return f"{where} has no tarball name"
            size = b.get("size")
            if not (isinstance(size, int) and not isinstance(size, bool) and size > 0):
                return f"{where} has no size"
            if not (isinstance(b.get("sha256"), str) and SHA256.fullmatch(b["sha256"])):
                return f"{where} has no sha256 of 64 lowercase hex digits"
            if not (isinstance(b.get("root"), str) and NAME_RE.fullmatch(b["root"]) and b["root"] not in (".", "..")):
                return f"{where} has no root directory name"
            reports = b.get("reports")
            if not (isinstance(reports, dict) and reports
                    and all(isinstance(k, str) and NAME_RE.fullmatch(k) and isinstance(v, str) and v for k, v in reports.items())):
                return f"{where} says nothing of what the programs print"
    return None


def load_pin(root: str) -> dict:
    path = os.path.join(root, PIN_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            pin = json.load(fh)
    except OSError as e:
        raise PinError(f"the {CARRIER_LABEL} pin {PIN_REL} cannot be read ({errno.errorcode.get(e.errno or 0) or e})") from None
    except ValueError:
        raise PinError(f"the {CARRIER_LABEL} pin {PIN_REL} is not JSON") from None
    problem = pin_problem(pin)
    if problem:
        raise PinError(f"the {CARRIER_LABEL} pin {PIN_REL} {problem}")
    return pin


def pinned_build(pin: dict, machine: str | None = None) -> tuple[str, dict]:
    """(version, build) of the pin's current release for this machine's architecture; InstallError if it has none."""
    version = pin["current"]
    arch = _arch(machine)
    build = pin["releases"][version].get(arch) if arch else None
    if build is None:
        raise InstallError(f"the reviewed pin has no {version} build for {arch or machine or os.uname().machine}")
    return version, build


def _oneline(e: BaseException) -> str:
    """One line of an error that carries no secret (nothing here has a token in hand)."""
    return (str(getattr(e, "reason", None) or e).split("\n")[0][:160]) or type(e).__name__


def bin_dir(home: str) -> str:
    return os.path.join(home, ".local", "bin")


def unit_dir(home: str, environ: Any = None) -> str:
    cfg = (os.environ if environ is None else environ).get("XDG_CONFIG_HOME")
    return os.path.join(cfg if cfg else os.path.join(home, ".config"), "systemd", "user")


def child_env(home: str) -> dict[str, str]:
    env = {"HOME": home, "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
    env.update({k: os.environ[k] for k in PASS_ENV if os.environ.get(k)})
    return env


# --- the archive -------------------------------------------------------------------------------------------------

def _judge_members(tf: tarfile.TarFile, root: str) -> list[tuple[tarfile.TarInfo, tuple[str, ...]]]:
    """Every member, judged before the first byte is written: (info, path components) in archive order."""
    out: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
    seen: set[tuple[str, ...]] = set()
    total = 0
    for info in tf:
        if len(out) >= MAX_MEMBERS:
            raise InstallError(f"the archive has more than {MAX_MEMBERS} members")
        name = info.name
        if "\0" in name or name.startswith("/"):
            raise InstallError(f"the archive has a member that is absolute or not a name: {name[:60]!r}")
        parts = tuple(p for p in name.split("/") if p not in ("", "."))
        if ".." in parts:
            raise InstallError(f"the archive has a member with '..': {name[:60]!r}")
        if not parts or parts[0] != root:
            raise InstallError(f"the archive has a member outside {root}: {name[:60]!r}")
        if not (info.isreg() or info.isdir()):
            raise InstallError(f"the archive has a member that is not a file or a directory (a link or a device): {name[:60]!r}")
        if parts in seen:
            raise InstallError(f"the archive has {name[:60]!r} twice")
        seen.add(parts)
        if info.isreg():
            total += info.size
            if total > MAX_UNPACKED_BYTES:
                raise InstallError(f"the archive unpacks to more than {MAX_UNPACKED_BYTES} bytes")
        out.append((info, parts))
    if (root,) not in seen:
        raise InstallError(f"the archive has no {root} directory")
    return out


def unpack(archive: str, root: str, dest: str) -> str:
    """Extract archive into dest (fetch_and_unpack made sure it was empty), only what lies under `root`; returns dest/root. Files get
    0755 when the archive marked them executable and 0644 otherwise, whatever the umask; no link is ever made,
    so nothing written can lead outside dest."""
    try:
        with tarfile.open(archive, "r:gz") as tf:
            members = _judge_members(tf, root)
        with tarfile.open(archive, "r:gz") as tf:
            for info in tf:
                parts = tuple(p for p in info.name.split("/") if p not in ("", "."))
                target = os.path.join(dest, *parts)
                if info.isdir():
                    os.makedirs(target, mode=0o755, exist_ok=True)
                    os.chmod(target, 0o755)
                    continue
                os.makedirs(os.path.dirname(target), mode=0o755, exist_ok=True)
                src = tf.extractfile(info)
                if src is None:
                    raise InstallError(f"{info.name[:60]!r} has no content")
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with src, os.fdopen(fd, "wb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                    os.fchmod(out.fileno(), 0o755 if info.mode & 0o111 else 0o644)
    except InstallError:
        raise
    except (tarfile.TarError, OSError, EOFError, zlib.error, ValueError) as e:
        raise InstallError(f"the archive could not be extracted ({_oneline(e)})") from None
    return os.path.join(dest, root)


def fetch_and_unpack(build: dict, token: str, dest: str, fetch: Callable[..., tuple[int, str]] = download) -> str:
    """Download build["url"] with token, refuse unless its size AND sha256 equal the pin's, extract into the empty
    directory dest and return dest/<root>, which holds bin/ and install.sh. Runs nothing, reads no environment and
    touches no home. InstallError, one line with the token out of it, for every failure."""
    if not os.path.isdir(dest):
        raise InstallError("the extraction directory does not exist")
    if os.listdir(dest):
        raise InstallError("the extraction directory is not empty")
    part = os.path.join(dest, ".archive.part")
    try:
        try:
            # One byte past the pin's size is a size mismatch already: the bound stops a stream that never ends.
            got, digest = fetch(build["url"], token, part, max_bytes=build["size"] + 1,
                                deadline_s=DOWNLOAD_TIMEOUT_S, read_timeout_s=READ_TIMEOUT_S)
        except urllib.error.HTTPError as e:
            raise InstallError(f"the download answered HTTP {e.code}") from None
        except (urllib.error.URLError, OSError, ValueError, TimeoutError, http.client.HTTPException) as e:
            raise InstallError(f"the download failed ({_why(e, token)})") from None
        if got != build["size"]:
            raise InstallError(f"size mismatch: the pin says {build['size']} bytes, the download is {got}; nothing was installed")
        if digest != build["sha256"]:
            raise InstallError(f"sha256 mismatch: the pin says {build['sha256']}, the download is {digest}; nothing was installed")
        return unpack_checked(part, build, dest)
    finally:
        try:
            os.unlink(part)
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"{INSTALL_OP}: could not remove {part} ({errno.errorcode.get(e.errno or 0) or e})", file=sys.stderr)


def unpack_checked(archive: str, build: dict, dest: str) -> str:
    tree = unpack(archive, build["root"], dest)
    installer = os.path.join(tree, "install.sh")
    try:
        st = os.lstat(installer)
        programs = os.lstat(os.path.join(tree, "bin"))
    except OSError:
        raise InstallError("the archive has no install.sh and bin/ under its root") from None
    if not (stat.S_ISREG(st.st_mode) and st.st_mode & 0o100 and stat.S_ISDIR(programs.st_mode)):
        raise InstallError("the archive's install.sh is not an executable file, or its bin is not a directory")
    return tree


# --- the programs ------------------------------------------------------------------------------------------------

def tree_programs(tree: str) -> dict[str, str]:
    """name -> sha256 of each regular file in the extracted bin/."""
    d = os.path.join(tree, "bin")
    return {n: file_sha256(os.path.join(d, n)) for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))}


def version_line(path: str, run: Callable[..., Any], home: str) -> str:
    """What the program prints under --version, one trailing newline taken off and nothing else."""
    r = run([path, "--version"], capture_output=True, text=True, timeout=VERSION_TIMEOUT_S, check=True,
            stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
    out = r.stdout
    return out[:-1] if out.endswith("\n") else out


def check_reports(directory: str, reports: dict, run: Callable[..., Any], home: str) -> str | None:
    """None when each program in reports, run from directory, prints exactly its value; else why not."""
    for name, want in reports.items():
        path = os.path.join(directory, name)
        try:
            got = version_line(path, run, home)
        except subprocess.TimeoutExpired:
            return f"{name} did not answer --version within {VERSION_TIMEOUT_S} s"
        except subprocess.CalledProcessError as e:
            return f"{name} --version exited {e.returncode}"
        except (OSError, ValueError) as e:
            return f"{name} --version could not be run ({_oneline(e)})"
        if got != want:
            return f"{name} --version prints {json.dumps(got[:80])}, the pin says {json.dumps(want)}"
    return None


def _write_marker(state: str, marker: dict) -> None:
    os.makedirs(state, mode=0o700, exist_ok=True)
    tmp = os.path.join(state, f".{MARKER}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(marker, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, os.path.join(state, MARKER))
        _fsync_dir(state)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_marker(state: str) -> dict | None:
    d = util.read_json(os.path.join(state, MARKER))
    return d if isinstance(d, dict) else None


def _marker_programs(marker: dict | None) -> dict[str, str] | None:
    p = marker.get("programs") if marker else None
    if isinstance(p, dict) and p and all(isinstance(k, str) and NAME_RE.fullmatch(k) and isinstance(v, str) and SHA256.fullmatch(v)
                                         for k, v in p.items()):
        return p
    return None


def _digests_match(directory: str, programs: dict[str, str]) -> bool:
    """A file this account cannot read is not shown to be the release: the install goes on and replaces it."""
    for name, digest in programs.items():
        path = os.path.join(directory, name)
        try:
            if not (os.path.isfile(path) and file_sha256(path) == digest):
                return False
        except OSError:
            return False
    return True


def _refused(reason: str) -> dict:
    return {"status": "refused", "reason": reason}


def _failed(version: str | None, reason: str) -> dict:
    # No digest: `sha256` in a reply is the one that was verified, and a failure before the check verified nothing.
    out: dict = {"status": "failed", "reason": reason}
    if version:
        out["version"] = version
    return out


def carrier_install(request: Any, root: str | None = None, home: str | None = None, state: str | None = None,
                       fetch: Callable[..., tuple[int, str]] = download, run: Callable[..., Any] = subprocess.run,
                       token: Callable[[str], str | None] | None = None, machine: str | None = None) -> dict:
    a = request.get("args") if isinstance(request, dict) else None
    if not (a is None or a == {}):
        return _refused(f"{INSTALL_OP} takes no argument: it installs the release the reviewed pin names")
    root = _code_root() if root is None else root
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    try:
        pin = load_pin(root)
        version, build = pinned_build(pin, machine)
    except PinError as e:
        return _failed(None, str(e))
    except InstallError as e:
        return _refused(str(e))
    try:
        os.makedirs(state, mode=0o700, exist_ok=True)
        lock_fd = os.open(os.path.join(state, LOCK), os.O_WRONLY | os.O_CREAT, 0o600)
    except OSError as e:
        return _failed(version, f"the state directory cannot be prepared ({errno.errorcode.get(e.errno or 0) or e})")
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return _refused(f"another {INSTALL_OP} is running on this account")
        return _install(version, pin["releases"][version], build, state, home, fetch, run, token)
    finally:
        os.close(lock_fd)


def _install(version: str, release: dict, build: dict, state: str, home: str, fetch: Callable[..., tuple[int, str]],
             run: Callable[..., Any], token: Callable[[str], str | None] | None) -> dict:
    bindir = bin_dir(home)
    marker = read_marker(state)
    recorded = _marker_programs(marker)
    if (marker and recorded and marker.get("version") == version and marker.get("sha256") == build["sha256"]
            and set(build["reports"]) <= set(recorded) and _digests_match(bindir, recorded)):
        return {"status": "current", "version": version, "sha256": build["sha256"], "programs": recorded}
    if token is None:
        from gzcoord.inbox_parts.tokens import synced_var
        token = lambda name: synced_var(name, home)   # noqa: E731
    tok = token("GH_TOKEN")
    if not tok:
        return _failed(version, "no GH_TOKEN is synced for this account (fabric-secrets sync): the release asset needs one")
    work = os.path.join(state, WORK)
    tree_dir = os.path.join(work, "tree")
    try:
        # Under the lock nothing else is writing here: whatever is left is a killed install's.
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(tree_dir, mode=0o700)
    except OSError as e:
        return _failed(version, f"the install directories cannot be prepared ({_why(e, tok)})")
    try:
        try:
            tree = fetch_and_unpack(build, tok, tree_dir, fetch)
        except InstallError as e:
            return _failed(version, str(e))
        try:
            programs = tree_programs(tree)
        except OSError as e:
            return _failed(version, f"the archive's programs could not be read ({_why(e, tok)})")
        missing = sorted(set(build["reports"]) - set(programs))
        if missing:
            return _failed(version, f"the archive has no bin/{missing[0]}, which the pin expects")
        bad = check_reports(os.path.join(tree, "bin"), build["reports"], run, home)
        if bad:
            return _failed(version, f"the archive's programs disagree with the pin ({bad}); nothing was installed")
        try:
            r = run([os.path.join(tree, "install.sh")], capture_output=True, text=True, timeout=INSTALL_SH_TIMEOUT_S, check=False,
                    stdin=subprocess.DEVNULL, cwd=tree, env=child_env(home))
        except subprocess.TimeoutExpired:
            return _failed(version, f"install.sh did not finish within {INSTALL_SH_TIMEOUT_S} s")
        except OSError as e:
            return _failed(version, f"install.sh could not be run ({_why(e, tok)})")
        if r.returncode != 0:
            lines = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            return _failed(version, f"install.sh exited {r.returncode}" + (f": {_why(Exception(lines[-1]), tok)}" if lines else ""))
        landed = _landed(bindir, home, programs)
        if landed:
            return _failed(version, landed)
        bad = check_reports(bindir, build["reports"], run, home)
        if bad:
            return _failed(version, f"the installed programs disagree with the pin ({bad}); the next install replaces them")
        try:
            _write_marker(state, {"version": version, "tag": release["tag"], "sha256": build["sha256"], "size": build["size"],
                                  "programs": programs, "bin_dir": bindir, "reports": build["reports"]})
        except OSError as e:
            return _failed(version, f"the programs are in place but could not be recorded ({_why(e, tok)}); a retry installs them again")
        return {"status": "installed", "version": version, "sha256": build["sha256"], "programs": programs}
    finally:
        try:
            shutil.rmtree(work)
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"{INSTALL_OP}: could not remove {work} ({errno.errorcode.get(e.errno or 0) or e})", file=sys.stderr)


def _landed(bindir: str, home: str, programs: dict[str, str]) -> str | None:
    """None when install.sh put every program of the archive in bindir byte for byte and both templates in the
    unit directory; else the first thing that is not there."""
    for name, digest in programs.items():
        path = os.path.join(bindir, name)
        try:
            if os.path.islink(path) or file_sha256(path) != digest:
                return f"install.sh finished but {name} in {bindir} is not the archive's"
        except OSError:
            return f"install.sh finished but {name} is not in {bindir}"
    for unit in UNITS:
        if not os.path.isfile(os.path.join(unit_dir(home), unit)):
            return f"install.sh finished but {unit} is not in {unit_dir(home)}"
    return None


# --- the read ----------------------------------------------------------------------------------------------------

def installed(home: str | None = None, state: str | None = None, run: Callable[..., Any] = subprocess.run,
              root: str | None = None) -> dict:
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    bindir = bin_dir(home)
    units = {u: os.path.isfile(os.path.join(unit_dir(home), u)) for u in UNITS}
    marker = read_marker(state)
    recorded = _marker_programs(marker)
    wanted: dict | None = None
    try:
        _, build = pinned_build(load_pin(_code_root() if root is None else root))
        wanted = build["reports"]
    except (PinError, InstallError):
        pass
    names = sorted(recorded) if recorded else sorted(wanted) if wanted else []
    marker_reports = marker.get("reports") if marker else None
    reporting = set(wanted) if wanted else set(marker_reports) if isinstance(marker_reports, dict) else set()
    reporting &= set(names)
    if not reporting:
        return {"status": "unreadable", "units": units, "reason": "neither the pin nor the marker names a program that reports a version"}
    if not names:
        return {"status": "unreadable", "units": units, "reason": "neither the marker nor the pin names a program"}
    present = [n for n in names if os.path.lexists(os.path.join(bindir, n))]
    if not present:
        return {"status": "absent", "units": units}
    digests: dict[str, str] = {}
    lines: dict[str, str] = {}
    for n in names:
        path = os.path.join(bindir, n)
        try:
            if not (os.path.isfile(path) and os.stat(path).st_mode & 0o111):
                return {"status": "unreadable", "units": units, "reason": f"{n} in {bindir} is not an executable file"}
            digests[n] = file_sha256(path)
            # Only the programs the pin says report a version are run: the others (a desktop program, a launcher)
            # have no --version contract, and one that exits 1 would make the whole read "unreadable".
            if n in reporting:
                lines[n] = version_line(path, run, home)
        except subprocess.TimeoutExpired:
            return {"status": "unreadable", "units": units, "reason": f"{n} did not answer --version within {VERSION_TIMEOUT_S} s"}
        except subprocess.CalledProcessError as e:
            return {"status": "unreadable", "units": units, "reason": f"{n} --version exited {e.returncode}"}
        except FileNotFoundError:
            return {"status": "unreadable", "units": units, "reason": f"{n} is not in {bindir}"}
        except (OSError, ValueError) as e:
            return {"status": "unreadable", "units": units, "reason": f"{n} --version: {_oneline(e)}"}
    versions = {m.group(1) for m in (re.search(r"(\d+\.\d+\.\d+)", ln) for ln in lines.values()) if m}
    if len(versions) != 1 or any(not re.search(r"\d+\.\d+\.\d+", ln) for ln in lines.values()):
        return {"status": "unreadable", "units": units, "programs": digests, "reports": lines,
                "reason": "the programs do not print one version"}
    out: dict = {"status": "ok", "version": versions.pop(), "reports": lines, "programs": digests, "units": units}
    if marker and recorded and all(digests.get(n) == d for n, d in recorded.items()) and isinstance(marker.get("sha256"), str):
        out["release_sha256"] = marker["sha256"]
    if wanted is not None:
        out["pinned"] = all(lines.get(n) == v for n, v in wanted.items())
    return out


def _code_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
