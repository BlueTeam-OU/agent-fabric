"""tools/fabric/control/gateway.py — the gateway's binary on this account:
`gateway-install`, a signed ACTION that puts the release the fabric pins in
~/.local/bin under the binary's own name, and `gateway`, the read that says
what is there (the gateway's ADR-014 rules 11, 17-19; the coordinator's
answers of 2026-10-10 to the shape proposed in seq 98283). The binary's name
is the last component of the pin's member, so no project's name is written
into this generic file.

THE PIN is runtime/gateway.json in this checkout (shape of runtime/python.json):
releases.<version>.<arch> holds the asset url, the tarball's name, its
SHA-256, the one member to extract and what that binary reports. The digest is
the reviewed one, never fetched from the artifact's own origin: a checksum
beside the artifact is changed by whoever changes the artifact.

THE ARGUMENTS are a closed set, {"version": "<digits.digits.digits>"}, and the
version must be a key of the pin. Nothing in a request names a url, a digest
or a path.

THE SEQUENCE, for one account, as that login and with no root:
  1. a lock for the account (a second install at once is refused, not queued);
  2. the installed binary is the pinned release already (the marker below says
     so and the file still has the digest the marker recorded): "current",
     nothing downloaded, nothing touched;
  3. download the pinned url with the account's GH_TOKEN, which the asset
     endpoint needs (the repository is internal), into a temporary file beside
     the target; size and time bounded; the token goes in a request header only
     — never argv, never a log, never the reply — and is dropped on the redirect
     to the storage host;
  4. the SHA-256 of what arrived must equal the pin's BEFORE anything is
     extracted or executed; a mismatch deletes the file and installs nothing;
  5. the one pinned member is read out of the tarball (no other member is
     looked at, and no path from the archive is used) into a temporary file in
     the target's directory, mode 0755;
  6. that file is run with `--version --json` and must report what the pin says
     it reports; a binary that cannot say who it is is "failed", not "installed";
  7. os.replace onto the target. A running gateway keeps the inode it started
     from and is never stopped (ADR-014 rule 19); the next launch uses the new
     file;
  8. the marker (<state>/gateway.json: version, artifact digest, binary digest)
     is written whole, by rename.

THE REPLY, data["gateway-install"]: status "installed" | "current" | "refused" |
"failed"; version; sha256 (the verified artifact digest, the pin's); installed_sha256
(the digest of the file now at the path); path; contract (the runtime-contract
version the binary reported); reason on a refusal or a failure. A refusal is a
request the action will not take (bad arguments, a version the pin lacks, an
architecture it has no build for); a failure is an install that was tried or
could not start (no token, the network, a digest that differs, a binary that
disagrees with the pin).

THE READ, data["gateway"]: status "ok" | "absent" | "unreadable"; path;
installed_sha256; version and contract, as the installed binary reports them
under `--version --json`; release_sha256, the artifact digest the marker
recorded when it agrees with the file. Unknown stays unknown: a binary that
will not report is "unreadable", with the reason, never a guessed version.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from control.ops import util
from control.upgrade import VERSION_RE

BIN_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
PIN_REL = os.path.join("runtime", "gateway.json")
MARKER = "gateway.json"
LOCK = "gateway-install.lock"
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 240       # the whole download; each socket read is bounded too
READ_TIMEOUT_S = 30
VERSION_TIMEOUT_S = 10
GATEWAY_INSTALL_BUDGET_S = DOWNLOAD_TIMEOUT_S + 2 * VERSION_TIMEOUT_S + 40   # what fabric-ctl waits for a reply
SHA256 = re.compile(r"[0-9a-f]{64}")
ARCHES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}


class PinError(Exception):
    """The reviewed pin cannot be used: said as one line, never a default."""


def bin_path(home: str, name: str) -> str:
    return os.path.join(home, ".local", "bin", name)


def bin_name(build: dict) -> str:
    return build["member"].rsplit("/", 1)[-1]


def load_pin(root: str) -> dict:
    """runtime/gateway.json, checked for the shape the action relies on."""
    path = os.path.join(root, PIN_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            pin = json.load(fh)
    except OSError as e:
        raise PinError(f"the gateway pin {PIN_REL} cannot be read ({errno.errorcode.get(e.errno or 0) or e})") from None
    except ValueError:
        raise PinError(f"the gateway pin {PIN_REL} is not JSON") from None
    problem = pin_problem(pin)
    if problem:
        raise PinError(f"the gateway pin {PIN_REL} {problem}")
    return pin


def pin_problem(pin: Any) -> str | None:
    """None for a pin of the shape runtime/gateway.json documents, else what is
    wrong: tests/test_control_gateway.py holds the committed pin to it."""
    if not isinstance(pin, dict) or pin.get("version") != 1:
        return "is not version 1"
    releases = pin.get("releases")
    if not isinstance(releases, dict) or not releases:
        return "names no releases"
    names = set()
    for version, builds in releases.items():
        if not (isinstance(version, str) and VERSION_RE.fullmatch(version)):
            return f"names the release {version!r}, not digits.digits.digits"
        if not isinstance(builds, dict) or not builds:
            return f"has no build for {version}"
        for arch, b in builds.items():
            where = f"{version}/{arch}"
            if arch not in ARCHES.values():
                return f"names the architecture {arch!r} at {version}"
            if not isinstance(b, dict):
                return f"{where} is not an object"
            if not (isinstance(b.get("url"), str) and b["url"].startswith("https://")):
                return f"{where} has no https url"
            if not (isinstance(b.get("name"), str) and b["name"].endswith(".tar.gz") and "/" not in b["name"]):
                return f"{where} has no tarball name"
            if not (isinstance(b.get("sha256"), str) and SHA256.fullmatch(b["sha256"])):
                return f"{where} has no sha256 of 64 lowercase hex digits"
            member = b.get("member")
            if not (isinstance(member, str) and member and not member.startswith("/") and ".." not in member.split("/")
                    and "/" in member and BIN_NAME_RE.fullmatch(member.rsplit("/", 1)[-1])):
                return f"{where} names no member of the form <directory>/<binary name>"
            names.add(member.rsplit("/", 1)[-1])
            reports = b.get("reports")
            if not (isinstance(reports, dict) and isinstance(reports.get("gateway_version"), str)
                    and isinstance(reports.get("runtime_contract"), int) and not isinstance(reports.get("runtime_contract"), bool)):
                return f"{where} says nothing of what the binary reports"
            if reports["gateway_version"] != version:
                return f"{where} reports a gateway_version other than {version}"
    if len(names) != 1:
        return f"names more than one binary ({', '.join(sorted(names))})"
    return None


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_marker(state: str) -> dict | None:
    d = util.read_json(os.path.join(state, MARKER))
    return d if isinstance(d, dict) else None


def write_marker(state: str, marker: dict) -> None:
    os.makedirs(state, mode=0o700, exist_ok=True)
    tmp = os.path.join(state, f".{MARKER}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(marker, indent=2) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, os.path.join(state, MARKER))


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """urllib forwards every header, Authorization included, to the redirect
    target. The asset endpoint redirects to storage, which has no business with
    the token (and a pre-signed url refuses one): it goes to the first host only."""

    allow_http = False   # a test's local server only

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not (newurl.startswith("https://") or self.allow_http):
            raise urllib.error.URLError(f"the download redirected to a non-https address ({code})")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            for k in list(new.headers):
                if k.lower() == "authorization":
                    del new.headers[k]
            for k in list(new.unredirected_hdrs):
                if k.lower() == "authorization":
                    del new.unredirected_hdrs[k]
        return new


def download(url: str, token: str, dest: str, max_bytes: int = MAX_ARTIFACT_BYTES, deadline_s: float = DOWNLOAD_TIMEOUT_S,
             read_timeout_s: float = READ_TIMEOUT_S) -> tuple[int, str]:
    """Stream url to dest (0600), counting bytes and hashing as they arrive.
    Returns (bytes, sha256). Raises OSError/URLError/ValueError, the first line
    of which is safe to say: the token is in a header and never in a message."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/octet-stream",
                                               "User-Agent": "fabric-gateway-install", "X-GitHub-Api-Version": "2022-11-28"})
    opener = urllib.request.build_opener(_DropAuthOnRedirect)
    started = time.monotonic()
    h = hashlib.sha256()
    n = 0
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as out, opener.open(req, timeout=read_timeout_s) as resp:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            if n > max_bytes:
                raise ValueError(f"the download is larger than {max_bytes} bytes")
            if time.monotonic() - started > deadline_s:
                raise TimeoutError(f"the download did not finish within {int(deadline_s)} s")
            h.update(chunk)
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())
    return n, h.hexdigest()


def version_report(path: str, run: Callable[..., Any] = subprocess.run, timeout_s: float = VERSION_TIMEOUT_S) -> dict:
    """What the binary says of itself under `--version --json`: a JSON object, or
    ValueError/OSError/SubprocessError for the caller to word. It runs with a
    minimal environment: nothing of the session's, the token least of all."""
    r = run([path, "--version", "--json"], capture_output=True, text=True, timeout=timeout_s, check=True,
            stdin=subprocess.DEVNULL, cwd="/", env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})
    doc = json.loads(r.stdout)
    if not isinstance(doc, dict):
        raise ValueError("--version --json printed no object")
    return doc


def _reports_match(doc: dict, reports: dict) -> str | None:
    for k, want in reports.items():
        if doc.get(k) != want:
            return f"{k}: the binary says {json.dumps(doc.get(k))}, the pin says {json.dumps(want)}"
    return None


def _refused(reason: str) -> dict:
    return {"status": "refused", "reason": reason}


def _failed(version: str, b: dict, reason: str) -> dict:
    return {"status": "failed", "version": version, "sha256": b["sha256"], "reason": reason}


def _arch(machine: str | None = None) -> str | None:
    return ARCHES.get((machine or platform.machine()).lower())


def gateway_install(request: Any, root: str | None = None, home: str | None = None, state: str | None = None,
                    fetch: Callable[..., tuple[int, str]] = download, run: Callable[..., Any] = subprocess.run,
                    token: Callable[[str], str | None] | None = None, machine: str | None = None) -> dict:
    a = request.get("args") if isinstance(request, dict) else None
    if not (isinstance(a, dict) and list(a) == ["version"] and isinstance(a["version"], str) and VERSION_RE.fullmatch(a["version"])):
        return _refused("gateway-install takes one argument, a version")
    version = a["version"]
    root = _code_root() if root is None else root
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    try:
        pin = load_pin(root)
    except PinError as e:
        return {"status": "failed", "reason": str(e)}
    builds = pin["releases"].get(version)
    if builds is None:
        return _refused(f"version {version} is not in the reviewed pin (it has {', '.join(sorted(pin['releases']))})")
    arch = _arch(machine)
    b = builds.get(arch) if arch else None
    if b is None:
        return _refused(f"the reviewed pin has no {version} build for {arch or machine or platform.machine()}")
    target = bin_path(home, bin_name(b))
    os.makedirs(state, mode=0o700, exist_ok=True)
    lock_fd = os.open(os.path.join(state, LOCK), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return _refused("another gateway-install is running on this account")
        return _install(version, b, target, state, home, fetch, run, token)
    finally:
        os.close(lock_fd)


def _install(version: str, b: dict, target: str, state: str, home: str, fetch: Callable[..., tuple[int, str]],
             run: Callable[..., Any], token: Callable[[str], str | None] | None) -> dict:
    marker = read_marker(state)
    if (marker and marker.get("version") == version and marker.get("sha256") == b["sha256"]
            and isinstance(marker.get("installed_sha256"), str) and os.path.isfile(target)
            and file_sha256(target) == marker["installed_sha256"]):
        return {"status": "current", "version": version, "sha256": b["sha256"], "installed_sha256": marker["installed_sha256"],
                "path": target, "contract": b["reports"]["runtime_contract"]}
    if token is None:
        from gzcoord.inbox_parts.tokens import synced_var
        token = lambda name: synced_var(name, home)   # noqa: E731
    tok = token("GH_TOKEN")
    if not tok:
        return _failed(version, b, "no GH_TOKEN is synced for this account (fabric-secrets sync): the release asset needs one")
    bindir = os.path.dirname(target)
    work = os.path.join(state, "gateway-install")
    os.makedirs(bindir, exist_ok=True)
    os.makedirs(work, mode=0o700, exist_ok=True)
    artifact = os.path.join(work, f"{b['name']}.{os.getpid()}.part")
    new = os.path.join(bindir, f".{os.path.basename(target)}.new-{os.getpid()}")
    try:
        try:
            _, digest = fetch(b["url"], tok, artifact)
        except urllib.error.HTTPError as e:
            return _failed(version, b, f"the download answered HTTP {e.code}")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            return _failed(version, b, f"the download failed ({_why(e, tok)})")
        if digest != b["sha256"]:
            return _failed(version, b, f"sha256 mismatch: the pin says {b['sha256']}, the download is {digest}; nothing was installed")
        try:
            _extract_member(artifact, b["member"], new)
        except (tarfile.TarError, OSError, KeyError, ValueError) as e:
            return _failed(version, b, f"the pinned member could not be extracted ({_why(e, tok)})")
        os.chmod(new, 0o755)
        try:
            doc = version_report(new, run)
        except subprocess.TimeoutExpired:
            return _failed(version, b, f"the new binary did not answer --version --json within {VERSION_TIMEOUT_S} s")
        except subprocess.CalledProcessError as e:
            return _failed(version, b, f"the new binary's --version --json exited {e.returncode}")
        except (OSError, ValueError) as e:
            return _failed(version, b, f"the new binary could not report its version ({_why(e, tok)})")
        bad = _reports_match(doc, b["reports"])
        if bad:
            return _failed(version, b, f"the new binary disagrees with the pin ({bad})")
        installed = file_sha256(new)
        os.replace(new, target)
        _fsync_dir(bindir)
        write_marker(state, {"version": version, "sha256": b["sha256"], "installed_sha256": installed, "path": target,
                             "reports": b["reports"]})
        return {"status": "installed", "version": version, "sha256": b["sha256"], "installed_sha256": installed, "path": target,
                "contract": b["reports"]["runtime_contract"]}
    finally:
        for p in (artifact, new):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"gateway-install: could not remove {p} ({errno.errorcode.get(e.errno or 0) or e})", file=sys.stderr)


def _why(e: BaseException, secret: str) -> str:
    """One line for a reply, without the token whatever the library put in it."""
    text = str(getattr(e, "reason", None) or e).split("\n")[0][:160]
    return text.replace(secret, "<token>") or type(e).__name__


def _extract_member(tar_path: str, member: str, dest: str) -> None:
    """Exactly the pinned member, as a regular file, streamed to dest (0600 until
    the caller sets the mode): no other entry is read and the archive picks no path."""
    with tarfile.open(tar_path, "r:gz") as tf:
        info = tf.getmember(member)
        if not info.isreg():
            raise ValueError(f"{member} is not a regular file")
        if info.size > MAX_MEMBER_BYTES:
            raise ValueError(f"{member} is larger than {MAX_MEMBER_BYTES} bytes")
        src = tf.extractfile(info)
        if src is None:
            raise ValueError(f"{member} has no content")
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with src, os.fdopen(fd, "wb") as out:
            remaining = info.size
            while remaining:
                chunk = src.read(min(1 << 20, remaining))
                if not chunk:
                    raise ValueError(f"{member} ended before its {info.size} bytes")
                out.write(chunk)
                remaining -= len(chunk)
            out.flush()
            os.fsync(out.fileno())


def _fsync_dir(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _code_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))


def gateway(home: str | None = None, state: str | None = None, run: Callable[..., Any] = subprocess.run,
            root: str | None = None) -> dict:
    """What is installed on this account, from the file and what it reports."""
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    marker = read_marker(state)
    recorded = marker.get("path") if marker else None
    if isinstance(recorded, str) and os.path.dirname(recorded) == os.path.join(home, ".local", "bin"):
        path = recorded
    else:
        try:
            pin = load_pin(_code_root() if root is None else root)
        except PinError as e:
            return {"status": "unreadable", "reason": str(e)}
        path = bin_path(home, bin_name(next(iter(next(iter(pin["releases"].values())).values()))))
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return {"status": "absent", "path": path}
    except OSError as e:
        return {"status": "unreadable", "path": path, "reason": f"{errno.errorcode.get(e.errno or 0) or e}"}
    if not stat.S_ISREG(st.st_mode) or not st.st_mode & 0o111:
        return {"status": "unreadable", "path": path, "reason": "not an executable file"}
    try:
        digest = file_sha256(path)
    except OSError as e:
        return {"status": "unreadable", "path": path, "reason": f"{errno.errorcode.get(e.errno or 0) or e}"}
    try:
        doc = version_report(path, run)
    except subprocess.TimeoutExpired:
        return {"status": "unreadable", "path": path, "installed_sha256": digest, "reason": f"no answer to --version --json within {VERSION_TIMEOUT_S} s"}
    except subprocess.CalledProcessError as e:
        return {"status": "unreadable", "path": path, "installed_sha256": digest, "reason": f"--version --json exited {e.returncode}"}
    except (OSError, ValueError) as e:
        return {"status": "unreadable", "path": path, "installed_sha256": digest, "reason": f"--version --json: {str(e).split(chr(10))[0][:120]}"}
    out = {"status": "ok", "path": path, "installed_sha256": digest, "version": doc.get("gateway_version"),
           "contract": doc.get("runtime_contract")}
    if marker and marker.get("installed_sha256") == digest and isinstance(marker.get("sha256"), str):
        out["release_sha256"] = marker["sha256"]
    return out
