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
  3. the account waits for its turn on the host's download lease (one
     download at a time across the host's accounts; a refused turn is a
     failure, not a bypass), then the archive is downloaded with the account's GH_TOKEN (the repository is
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
  7. the units of the roster's profile that are running are noted and the
     programs install.sh will replace are kept (ADR-064 rule 14); then
     `<root>/install.sh` runs with no argument, in a minimal environment
     (programs into ~/.local/bin, the two user-unit templates into the
     user's systemd directory; it enables nothing and touches no profile);
  8. each program the archive carries in bin/ must now be in ~/.local/bin
     byte for byte, the two unit templates must be there, and every program
     in `reports` is run from ~/.local/bin and must print its value again;
  9. exactly the units that were running are restarted and checked: each
     active (twice, a poll apart), the daemon's process running the installed file, every program the pin reports printing its value, the
     carrier answering `gzcoord-carrier status` when its client runs. With no
     unit running there is nothing to restart and the check is the version
     alone, which the reply says. A check that fails, or any failure after
     install.sh began, puts the kept programs back, restarts the same units
     again, checks again and replies failed with both results;
 10. the marker (<state>/<carrier>-install.json) is written whole, by rename,
     only after the check passed;
 11. the temporary directory is removed however the install ends, and one a
     killed install left is removed at the start of the next.

THE REPLY, data["<carrier>-install"]: status "installed" | "current" |
"refused" | "failed"; version; sha256 (the verified archive digest, the pin's);
programs (name -> digest of the file now in ~/.local/bin); reason on a refusal
or a failure. A refusal is a request the action will not take (an argument,
an architecture the pin has no build for); a failure is an install that was
tried or could not start. A failure leaves the account on its previous
programs (`restored`: true), except where the restoring itself failed
(`restored`: false, the reason says which program), or where only the marker
could not be written. `units` on an install: the units that were running and the
check's result; `checks` on a failure that had restarted them: [the first
check, the check after restoring].

THE READ, data["<carrier>"]: status "ok" | "absent" | "unreadable"; version
and reports, as the installed programs print them under --version; programs
(name -> digest); release_sha256 (the marker's, when every digest still
agrees); pinned (whether what is installed prints what the pin says); units
(whether each template is in the user's systemd directory). A program that
will not report makes the status "unreadable" with the reason, never a guessed
version. channel: the check of step 9 looked at once, now: "ok" | "off" (a unit
runs and fails it) | "not-running" | "unknown" (it could not be made), with the
units' states and a reason, so that an account off the channel is seen.

THE START (`<carrier>-start`, no arguments; agent-fabric ADR-064 rule 11: starting an account's units is the dual
run's switch) writes the profile's config.yaml and brings the roster's profile up as two units of the user manager:
  1. the account's lock, the install's (a start, a stop and an install never run at once on one account);
  2. refused, nothing touched, unless the account lingers (its units would die with its last session), the programs
     in ~/.local/bin print what the pin says and both unit templates are in the user's systemd directory;
  3. `gzcoord-carrier render-config --write` of the installed release writes
     $XDG_CONFIG_HOME/<carrier>/profiles/<profile>/config.yaml (atomic, 0600); the carrier refuses it when this
     agent has no valid roster row, and that refusal is the action's (a row is a fact of the roster, not of this
     account). With both units already running the file is left alone: a running daemon read the old one, and
     re-rendering on a roster change is another operation;
  4. `systemctl --user enable --now` the daemon unit, then the client unit;
  5. rule 14's check through channel_check, polled: both units active, the daemon's process the installed
     program, every program the pin reports printing its value, the carrier answering `status`;
  6. a unit that did not come up, or a check that failed, disables --now both and the reply says so (the relay
     carries alone, rule 11).
THE STOP (`<carrier>-stop`, no arguments) disables --now the client then the daemon and replies stopped only once the
manager says neither runs. It leaves config.yaml and the programs where they are.

THE REPLIES, data["<carrier>-start"]: status "started" | "refused" | "failed"; units (unit -> state), check (what the
channel check said) and `already_running` when nothing was changed; on a failure `stopped` (whether both units are
inactive now) and `checks`; reason on a refusal or a failure. data["<carrier>-stop"]: "stopped" | "failed", units.

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
import time
import urllib.error
import zlib
from typing import Any, Callable

from gzcoord.carrier import CARRIER_LABEL, CARRIER_NAME
from control.gateway import ARCHES, SHA256, PinError, _arch, _fsync_dir, _why, download, file_sha256
from control.ops import util
from control.upgrade import LEASE_HELD, VERSION_RE, LeaseRefused, hold_lease

PIN_REL = os.path.join("runtime", CARRIER_NAME, "release.json")
INSTALL_OP = f"{CARRIER_NAME}-install"
START_OP = f"{CARRIER_NAME}-start"
STOP_OP = f"{CARRIER_NAME}-stop"
# One lock for the three: an install restarts the units a start brings up and a stop takes down.
LOCK_BUSY = f"another {INSTALL_OP}, {START_OP} or {STOP_OP} is running on this account"
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
# One download at a time per HOST, across its accounts: `fabric-ctl all <carrier>-install` made 28 accounts fetch the
# 117 MB archive at once on 2026-10-25 and every one hit its DOWNLOAD_TIMEOUT_S where each alone took well under it.
# The host lease (bin/fabric-lease, ADR-010) queues them as `upgrade claude` does; it is held from before the fetch
# until the archive is extracted, never through the restart, which costs the account and not the link. The wait is
# the number of accounts (30 on develop-qzapp) at about 40 s a turn.
DOWNLOAD_LEASE = f"{CARRIER_NAME}-download"
LEASE_WAIT_S = 1200
LEASE_GRACE_S = 60
SYSTEMCTL_TIMEOUT_S = 10
CHECK_POLLS = 5                # the channel check looks this many times, POLL_S apart, before it says the unit did not come back
POLL_S = 2
STATUS_TIMEOUT_S = 10
# What one channel check may take at most, for the two units: CHECK_POLLS state queries each with a POLL_S pause between,
# the daemon's MainPID, its --version, and CHECK_POLLS asks of the carrier's status with the same pauses.
CHECK_BUDGET_S = (2 * (CHECK_POLLS * SYSTEMCTL_TIMEOUT_S + (CHECK_POLLS - 1) * POLL_S) + SYSTEMCTL_TIMEOUT_S + VERSION_TIMEOUT_S
                  + CHECK_POLLS * STATUS_TIMEOUT_S + (CHECK_POLLS - 1) * POLL_S)
# An install asks the units' states before, then twice (the install, the restore) restarts both and checks.
CARRIER_INSTALL_BUDGET_S = (LEASE_WAIT_S + LEASE_GRACE_S + DOWNLOAD_TIMEOUT_S + EXTRACT_BUDGET_S + INSTALL_SH_TIMEOUT_S + 8 * VERSION_TIMEOUT_S + 40
                            + 2 * SYSTEMCTL_TIMEOUT_S + 2 * (2 * SYSTEMCTL_TIMEOUT_S + CHECK_BUDGET_S))
# A start: the linger question, the programs' versions, the config render, two `enable --now`, one channel check, and on a
# failure two `disable --now` and the states.
LOGINCTL_TIMEOUT_S = 10
RENDER_TIMEOUT_S = 30
CARRIER_START_BUDGET_S = (LOGINCTL_TIMEOUT_S + 2 * VERSION_TIMEOUT_S + RENDER_TIMEOUT_S + 2 * SYSTEMCTL_TIMEOUT_S + 2 * SYSTEMCTL_TIMEOUT_S
                          + CHECK_BUDGET_S + 2 * SYSTEMCTL_TIMEOUT_S + 2 * (CHECK_POLLS * SYSTEMCTL_TIMEOUT_S + (CHECK_POLLS - 1) * POLL_S) + 20)
CARRIER_STOP_BUDGET_S = 2 * SYSTEMCTL_TIMEOUT_S + 2 * (CHECK_POLLS * SYSTEMCTL_TIMEOUT_S + (CHECK_POLLS - 1) * POLL_S) + 20
# The read: the installed programs' versions, the units' states, and one look of the check (which asks the states and the
# daemon's version again).
CARRIER_READ_BUDGET_S = (2 * VERSION_TIMEOUT_S + 2 * SYSTEMCTL_TIMEOUT_S
                         + 2 * SYSTEMCTL_TIMEOUT_S + SYSTEMCTL_TIMEOUT_S + VERSION_TIMEOUT_S + STATUS_TIMEOUT_S + 10)
# The only variables of the session install.sh and the programs see besides HOME and PATH: where the
# user's systemd manager and configuration are. The token and the rest of the session never reach them.
PROC_ROOT = "/proc"      # a test points it at a directory of its own
ROSTER_REL = os.path.join("runtime", CARRIER_NAME, "roster.json")
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
            for (judged, parts), info in zip(members, tf):
                if info.name != judged.name or info.size != judged.size or info.type != judged.type:
                    raise InstallError("the archive changed between its check and its extraction")
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


# --- the channel (agent-fabric ADR-064 §5 rule 14) ----------------------------------------------------------------
# An install replaces the programs under a running daemon and carrier; if the new ones do not come back, the agent is
# off the channel and nobody is told. So the units that were running are restarted and checked, and a check that
# fails puts the previous programs back.

DAEMON_PROGRAM = "transport-daemon"
RUNNING = ("active", "activating", "reloading")


class ChannelUnknown(Exception):
    """The user manager did not answer in time: whether a unit runs is not known, which is not 'not running'."""


def roster_profile(root: str) -> str:
    """The profile the units are templated on, from the committed roster; InstallError if it cannot be read."""
    try:
        with open(os.path.join(root, ROSTER_REL), encoding="utf-8") as fh:
            profile = json.load(fh).get("profile")
    except (OSError, ValueError, AttributeError) as e:
        raise InstallError(f"the {CARRIER_LABEL} roster {ROSTER_REL} cannot be read ({_oneline(e)})") from None
    if not (isinstance(profile, str) and NAME_RE.fullmatch(profile)):
        raise InstallError(f"the {CARRIER_LABEL} roster {ROSTER_REL} has no profile name")
    return profile


def unit_names(profile: str) -> tuple[str, str]:
    """(daemon, client)."""
    return (f"{CARRIER_NAME}-daemon@{profile}.service", f"{CARRIER_NAME}-client@{profile}.service")


def unit_state(unit: str, run: Callable[..., Any], home: str) -> str | None:
    """The unit's ActiveState, or None when no user manager answers (no systemctl, no session bus: the account has
    no unit running, as install.sh itself takes it). A manager that does not answer in time raises ChannelUnknown."""
    return show_property(unit, "ActiveState", run, home)


def show_property(unit: str, prop: str, run: Callable[..., Any], home: str) -> str | None:
    try:
        r = run(["systemctl", "--user", "show", f"--property={prop}", "--value", unit], capture_output=True, encoding="utf-8", errors="replace",
                timeout=SYSTEMCTL_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
    except subprocess.TimeoutExpired:
        raise ChannelUnknown(f"the user manager did not answer within {SYSTEMCTL_TIMEOUT_S} s") from None
    except OSError:
        return None
    return (r.stdout or "").strip() or None if r.returncode == 0 else None


def running_units(profile: str, run: Callable[..., Any], home: str) -> tuple[dict[str, str | None], list[str]]:
    """(state of each unit, the units that run, daemon first)."""
    states = {u: unit_state(u, run, home) for u in unit_names(profile)}
    return states, [u for u, st in states.items() if st in RUNNING]


def daemon_process_problem(daemon: str, bindir: str, run: Callable[..., Any], home: str) -> str | None:
    """None when the daemon unit's process runs the program installed now; else why not. install.sh renames over the
    old file, so `--version` of the file on disk is the new one even when the restart never happened: the process's own
    /proc/<pid>/exe is what tells, and a replaced file reads as "<path> (deleted)"."""
    pid_text = show_property(daemon, "MainPID", run, home)
    if not (pid_text and pid_text.isdigit() and int(pid_text) > 0):
        return f"{daemon} has no main process"
    try:
        exe = os.readlink(os.path.join(PROC_ROOT, pid_text, "exe"))
    except OSError as e:
        return f"the process of {daemon} ({pid_text}) cannot be inspected ({errno.errorcode.get(e.errno or 0) or e})"
    if exe.endswith(" (deleted)"):
        return f"{daemon} still runs a program that has been replaced ({exe})"
    want = os.path.realpath(os.path.join(bindir, DAEMON_PROGRAM))
    if exe != want:
        return f"{daemon} runs {exe}, not the installed {want}"
    return None


def restart_units(units: list[str], run: Callable[..., Any], home: str) -> str | None:
    """None when each unit was asked to restart and the manager took it; else why not."""
    for u in units:
        try:
            r = run(["systemctl", "--user", "restart", u], capture_output=True, encoding="utf-8", errors="replace", timeout=SYSTEMCTL_TIMEOUT_S, check=False,
                    stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
        except subprocess.TimeoutExpired:
            return f"restarting {u} did not finish within {SYSTEMCTL_TIMEOUT_S} s"
        except OSError as e:
            return f"restarting {u} could not be run ({_oneline(e)})"
        if r.returncode != 0:
            return f"restarting {u} exited {r.returncode}"
    return None


def channel_check(profile: str, running: list[str], build: dict, root: str, run: Callable[..., Any], home: str,
                  sleep: Callable[[float], None], polls: int = CHECK_POLLS, pinned: bool = True) -> dict:
    """The check of the units in `running`: each active (and still active one poll later, so a crash loop is not
    mistaken for a start), the daemon's process running the installed file, every program the pin reports printing its
    value, and the carrier answering `status` when its
    client unit runs. `pinned` False (the check after a restore) leaves the version out: the programs put back are
    the account's own, which the pin says nothing of. {"status": "passed" | "failed" | "not-running", "reason"?, "units": {unit: state}}."""
    daemon, client = unit_names(profile)
    if not running:
        return {"status": "not-running", "units": {}}
    seen: dict[str, str | None] = {}

    def failed(reason: str, unknown: bool = False) -> dict:
        return {"status": "failed", "reason": reason, "units": seen, **({"unknown": True} if unknown else {})}

    for u in running:
        streak = 0
        for i in range(polls):
            if i:
                sleep(POLL_S)
            try:
                st = unit_state(u, run, home)
            except ChannelUnknown as e:
                return failed(str(e), unknown=True)
            seen[u] = st
            streak = streak + 1 if st == "active" else 0
            if streak >= (2 if polls > 1 else 1):
                break
        else:
            return failed(f"{u} is {seen[u] or 'not answering'} after {polls} look(s)")
    if daemon in running:
        try:
            bad = daemon_process_problem(daemon, bin_dir(home), run, home)
        except ChannelUnknown as e:
            return failed(str(e), unknown=True)
        if bad:
            return failed(bad)
    if pinned:
        bad = check_reports(bin_dir(home), build["reports"], run, home)     # every program the pin reports, not the daemon alone
        if bad:
            return failed(bad)
    if client in running:
        for i in range(polls):
            if i:
                sleep(POLL_S)
            try:
                r = run([os.path.join(root, "bin", "gzcoord-carrier"), "status"], capture_output=True, encoding="utf-8", errors="replace",
                        timeout=STATUS_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
            except subprocess.TimeoutExpired:
                reason = f"gzcoord-carrier status did not answer within {STATUS_TIMEOUT_S} s"
            except OSError as e:
                return failed(f"gzcoord-carrier status could not be run ({_oneline(e)})")
            else:
                if r.returncode == 0:
                    break
                reason = f"gzcoord-carrier status exited {r.returncode}: the carrier does not answer"
        else:
            return failed(reason)
    return {"status": "passed", "units": seen}


def _channel_text(c: dict) -> str:
    return "passed" if c["status"] == "passed" else c.get("reason") or c["status"]


class _Undo:
    """The programs the install is about to replace, kept so a failure puts them back."""

    def __init__(self, bindir: str, keep: str, names: list[str]) -> None:
        self.bindir, self.keep = bindir, keep
        self.before: dict[str, tuple[str, str | None]] = {}
        os.makedirs(keep, mode=0o700, exist_ok=True)
        for n in names:
            path = os.path.join(bindir, n)
            if os.path.islink(path):
                self.before[n] = ("link", os.readlink(path))
            elif os.path.lexists(path):
                shutil.copy2(path, os.path.join(keep, n))
                self.before[n] = ("file", None)
            else:
                self.before[n] = ("absent", None)

    def restore(self) -> str | None:
        """None when every program is as it was; else every one that could not be put back. It does not stop at the first:
        the others are still worth restoring."""
        problems = []
        for n, (kind, target) in self.before.items():
            path = os.path.join(self.bindir, n)
            tmp = os.path.join(self.bindir, f".{n}.restore")
            try:
                if os.path.lexists(tmp):      # a killed restore's
                    os.unlink(tmp)
                if kind == "absent":
                    if os.path.lexists(path):
                        os.unlink(path)
                elif kind == "link":
                    assert target is not None
                    os.symlink(target, tmp)
                    os.replace(tmp, path)
                else:
                    shutil.copy2(os.path.join(self.keep, n), tmp)
                    os.replace(tmp, path)
            except OSError as e:
                problems.append(f"{n} ({errno.errorcode.get(e.errno or 0) or e})")
        return ", ".join(problems) or None


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
                       token: Callable[[str], str | None] | None = None, machine: str | None = None,
                    sleep: Callable[[float], None] = time.sleep, lease: Callable[..., Any] = hold_lease) -> dict:
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
            return _refused(LOCK_BUSY)
        return _install(version, pin["releases"][version], build, state, home, root, fetch, run, token, sleep, lease)
    finally:
        os.close(lock_fd)


def _install(version: str, release: dict, build: dict, state: str, home: str, root: str, fetch: Callable[..., tuple[int, str]],
             run: Callable[..., Any], token: Callable[[str], str | None] | None, sleep: Callable[[float], None],
             lease: Callable[..., Any]) -> dict:
    bindir = bin_dir(home)
    work = os.path.join(state, WORK)
    # Under the lock nothing else is writing here: whatever is left is a killed install's, and it is removed before
    # any answer, "current" included.
    shutil.rmtree(work, ignore_errors=True)
    marker = read_marker(state)
    recorded = _marker_programs(marker)
    if (marker and recorded and marker.get("version") == version and marker.get("sha256") == build["sha256"]
            and set(build["reports"]) <= set(recorded) and _digests_match(bindir, recorded)):
        return {"status": "current", "version": version, "sha256": build["sha256"], "programs": recorded}
    try:
        profile = roster_profile(root)
    except InstallError as e:
        return _failed(version, str(e))
    if token is None:
        from gzcoord.inbox_parts.tokens import synced_var
        token = lambda name: synced_var(name, home)   # noqa: E731
    tok = token("GH_TOKEN")
    if not tok:
        return _failed(version, "no GH_TOKEN is synced for this account (fabric-secrets sync): the release asset needs one")
    tree_dir = os.path.join(work, "tree")
    try:
        os.makedirs(tree_dir, mode=0o700)
    except OSError as e:
        return _failed(version, f"the install directories cannot be prepared ({_why(e, tok)})")
    try:
        # Refused, not bypassed: fetching unqueued is what failed 28 accounts at once.
        try:
            turn = lease(root, wait_s=LEASE_WAIT_S, name=DOWNLOAD_LEASE)
        except LeaseRefused as e:
            # e.reason is fabric-lease's one-word code; e.line is the sentence that says what to do.
            return _failed(version, f"the host's download lease stayed held for {LEASE_WAIT_S} s; nothing was fetched — run it again"
                           if e.code == LEASE_HELD else
                           f"the host's download queue is unavailable ({e.line[:160]}); nothing was fetched")
        try:
            tree = fetch_and_unpack(build, tok, tree_dir, fetch)
        except InstallError as e:
            return _failed(version, str(e))
        finally:
            turn.release()
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
            _, running = running_units(profile, run, home)
        except ChannelUnknown as e:
            return _failed(version, f"whether the {CARRIER_LABEL} units run is not known ({e}); nothing was installed")
        try:
            undo = _Undo(bindir, os.path.join(work, "previous"), sorted(programs))
        except OSError as e:
            return _failed(version, f"the programs now installed could not be kept ({_why(e, tok)}); nothing was installed")

        def roll_back(reason: str, first: dict | None = None, restarted: bool = False) -> dict:
            """Failure after install.sh began: the previous programs back, the units that were restarted restarted
            again and checked, and a reply that says every result."""
            out = _failed(version, reason)
            left = undo.restore()
            if left:
                # The kept copies are the only ones: they leave the work directory, which is removed, for a place a person can read.
                # A name of its own each time: a retry whose restore also fails must not replace the copies of the first,
                # which are the only true previous programs.
                kept = os.path.join(state, f"{INSTALL_OP}-previous.{time.time_ns()}")
                try:
                    shutil.move(undo.keep, kept)
                    where = f"; the previous programs are kept in {kept}"
                except OSError:
                    where = "; the previous programs could not be kept"
                out["reason"] += f"; the previous programs could not all be restored ({left}){where}"
                out["restored"] = False
                if first:
                    out["checks"] = [first]
                return out
            out["restored"] = True
            out["reason"] += "; the previous programs are back"
            if restarted:
                again = restart_units(running, run, home)
                second = ({"status": "failed", "reason": again, "units": {}} if again
                          else channel_check(profile, running, build, root, run, home, sleep, pinned=False))
                out["reason"] += f"; restarted again, check: {_channel_text(second)}"
                out["checks"] = [first, second]
            return out

        try:
            r = run([os.path.join(tree, "install.sh")], capture_output=True, encoding="utf-8", errors="replace", timeout=INSTALL_SH_TIMEOUT_S, check=False,
                    stdin=subprocess.DEVNULL, cwd=tree, env=child_env(home))
        except subprocess.TimeoutExpired:
            return roll_back(f"install.sh did not finish within {INSTALL_SH_TIMEOUT_S} s")
        except OSError as e:
            return roll_back(f"install.sh could not be run ({_why(e, tok)})")
        if r.returncode != 0:
            lines = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            return roll_back(f"install.sh exited {r.returncode}" + (f": {_why(Exception(lines[-1]), tok)}" if lines else ""))
        landed = _landed(bindir, home, programs)
        if landed:
            return roll_back(landed)
        bad = check_reports(bindir, build["reports"], run, home)
        if bad:
            return roll_back(f"the installed programs disagree with the pin ({bad})")
        restart_failed = restart_units(running, run, home) if running else None
        check = ({"status": "failed", "reason": restart_failed, "units": {}} if restart_failed
                 else channel_check(profile, running, build, root, run, home, sleep))
        if check["status"] == "failed":
            return roll_back(f"the {CARRIER_LABEL} channel did not come back on the new programs ({_channel_text(check)})", check, True)
        try:
            _write_marker(state, {"version": version, "tag": release["tag"], "sha256": build["sha256"], "size": build["size"],
                                  "programs": programs, "bin_dir": bindir, "reports": build["reports"]})
        except OSError as e:
            return _failed(version, f"the programs are in place but could not be recorded ({_why(e, tok)}); a retry installs them again")
        return {"status": "installed", "version": version, "sha256": build["sha256"], "programs": programs,
                "units": {"running_before": running, "check": "passed" if running else "not run: no unit was running"}}
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


# --- start and stop ------------------------------------------------------------------------------------------------

STOPPED = ("inactive", "failed")     # `failed` is a unit that ended badly: it does not run, which is all a stop asks


def _lock(state: str) -> tuple[int | None, dict | None]:
    """(fd holding the account's lock, None), or (None, the reply that says why not)."""
    try:
        os.makedirs(state, mode=0o700, exist_ok=True)
        fd = os.open(os.path.join(state, LOCK), os.O_WRONLY | os.O_CREAT, 0o600)
    except OSError as e:
        return None, {"status": "failed", "reason": f"the state directory cannot be prepared ({errno.errorcode.get(e.errno or 0) or e})"}
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None, _refused(LOCK_BUSY)
    return fd, None


def config_path(home: str, profile: str, environ: Any = None) -> str:
    cfg = (os.environ if environ is None else environ).get("XDG_CONFIG_HOME")
    return os.path.join(cfg if cfg else os.path.join(home, ".config"), CARRIER_NAME, "profiles", profile, "config.yaml")


def linger_problem(login: str, run: Callable[..., Any], home: str) -> str | None:
    """None when the login lingers; else why not. A loginctl that does not answer is not 'no linger' and not 'lingers':
    the reason says it could not be asked."""
    try:
        r = run(["loginctl", "show-user", login, "--property=Linger", "--value"], capture_output=True, encoding="utf-8", errors="replace",
                timeout=LOGINCTL_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
    except subprocess.TimeoutExpired:
        return f"whether {login} lingers could not be asked: loginctl did not answer within {LOGINCTL_TIMEOUT_S} s"
    except OSError as e:
        return f"whether {login} lingers could not be asked: loginctl could not be run ({_oneline(e)})"
    answer = (r.stdout or "").strip()
    if r.returncode == 0 and answer == "yes":
        return None
    if r.returncode == 0 and answer == "no":
        return f"{login} has no linger (loginctl enable-linger {login}): units started now would die with its last session"
    return f"whether {login} lingers could not be read (loginctl exited {r.returncode}, answered {answer[:40]!r})"


def _systemctl(verb: list[str], run: Callable[..., Any], home: str) -> str | None:
    """None when `systemctl --user <verb>` exited 0; else one line of why."""
    shown = " ".join(verb)
    try:
        r = run(["systemctl", "--user", *verb], capture_output=True, encoding="utf-8", errors="replace", timeout=SYSTEMCTL_TIMEOUT_S, check=False,
                stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
    except subprocess.TimeoutExpired:
        return f"systemctl --user {shown} did not finish within {SYSTEMCTL_TIMEOUT_S} s"
    except OSError as e:
        return f"systemctl --user {shown} could not be run ({_oneline(e)})"
    if r.returncode != 0:
        lines = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
        return f"systemctl --user {shown} exited {r.returncode}" + (f": {lines[-1][:120]}" if lines else "")
    return None


def _disable_now(units: list[str], run: Callable[..., Any], home: str) -> str | None:
    """Each unit asked to disable --now (all of them, whatever the first answered); None when every one was taken."""
    problems = [p for p in (_systemctl(["disable", "--now", u], run, home) for u in units) if p]
    return "; ".join(problems) or None


def _settled(units: list[str], run: Callable[..., Any], home: str, sleep: Callable[[float], None]) -> tuple[dict[str, str | None], str | None]:
    """(each unit's state, None) once none runs, polled; else (the last states, why not). An unanswered manager is a reason."""
    seen: dict[str, str | None] = {}
    for i in range(CHECK_POLLS):
        if i:
            sleep(POLL_S)
        try:
            seen = {u: unit_state(u, run, home) for u in units}
        except ChannelUnknown as e:
            return seen, str(e)
        if None in seen.values():
            return seen, "the user manager does not answer"
        if all(st in STOPPED for st in seen.values()):
            return seen, None
    return seen, ", ".join(f"{u} is {st}" for u, st in seen.items() if st not in STOPPED)


def _login() -> str:
    import pwd
    return pwd.getpwuid(os.getuid()).pw_name


def carrier_start(request: Any, root: str | None = None, home: str | None = None, state: str | None = None,
                  run: Callable[..., Any] = subprocess.run, machine: str | None = None,
                  sleep: Callable[[float], None] = time.sleep, login: str | None = None) -> dict:
    a = request.get("args") if isinstance(request, dict) else None
    if not (a is None or a == {}):
        return _refused(f"{START_OP} takes no argument: it starts the units of the roster's profile")
    root = _code_root() if root is None else root
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    login = _login() if login is None else login
    try:
        _, build = pinned_build(load_pin(root), machine)
    except PinError as e:
        return _failed(None, str(e))
    except InstallError as e:
        return _refused(str(e))
    try:
        profile = roster_profile(root)
    except InstallError as e:
        return _failed(None, str(e))
    fd, reply = _lock(state)
    if fd is None:
        return reply or _refused(LOCK_BUSY)
    try:
        return _start(build, profile, root, home, run, sleep, login)
    finally:
        os.close(fd)


def _start(build: dict, profile: str, root: str, home: str, run: Callable[..., Any], sleep: Callable[[float], None], login: str) -> dict:
    daemon, client = unit_names(profile)
    both = [daemon, client]
    bad = linger_problem(login, run, home)
    if bad:
        return _refused(bad)
    bad = check_reports(bin_dir(home), build["reports"], run, home)
    if bad:
        return _refused(f"the installed programs are not the pin's ({bad}); run {INSTALL_OP} first")
    for unit in UNITS:
        if not os.path.isfile(os.path.join(unit_dir(home), unit)):
            return _refused(f"{unit} is not in {unit_dir(home)}; run {INSTALL_OP} first")
    try:
        _, running = running_units(profile, run, home)
    except ChannelUnknown as e:
        return _failed(None, f"whether the {CARRIER_LABEL} units run is not known ({e}); nothing was started")
    already = len(running) == len(both)
    if not already:
        path = config_path(home, profile)
        try:
            r = run([os.path.join(root, "bin", "gzcoord-carrier"), "render-config", "--write", path], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=RENDER_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL, cwd="/", env=child_env(home))
        except subprocess.TimeoutExpired:
            return _failed(None, f"gzcoord-carrier render-config did not finish within {RENDER_TIMEOUT_S} s; nothing was started")
        except OSError as e:
            return _failed(None, f"gzcoord-carrier render-config could not be run ({_oneline(e)}); nothing was started")
        if r.returncode != 0:
            lines = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
            why = (lines[-1][:200] if lines else f"exit {r.returncode}")
            # Exit 2 is the carrier declining (no valid roster row for this agent, ...): a refusal. Any other is a render that broke.
            out = _refused if r.returncode == 2 else (lambda reason: _failed(None, reason))
            return out(f"gzcoord-carrier render-config: {why}; nothing was started")
        problem = None
        for u in both:
            problem = _systemctl(["enable", "--now", u], run, home)
            if problem:
                break
    else:
        problem = None
    check = ({"status": "failed", "reason": problem, "units": {}} if problem
             else channel_check(profile, both, build, root, run, home, sleep))
    if check["status"] == "passed":
        out: dict = {"status": "started", "units": check["units"], "check": "passed"}
        if already:
            out["already_running"] = True
        return out
    # The relay carries alone (rule 11): whatever came up is taken down, and the reply says whether that worked.
    out = _failed(None, f"the {CARRIER_LABEL} units did not come up ({_channel_text(check)})")
    left = _disable_now(both, run, home)
    states, still = _settled(both, run, home, sleep)
    out["units"] = states
    out["checks"] = [check]
    out["stopped"] = not left and not still
    out["reason"] += ("; both units are stopped" if out["stopped"]
                      else f"; stopping them failed ({left or still}): the units may still run")
    return out


def carrier_stop(request: Any, root: str | None = None, home: str | None = None, state: str | None = None,
                 run: Callable[..., Any] = subprocess.run, sleep: Callable[[float], None] = time.sleep) -> dict:
    a = request.get("args") if isinstance(request, dict) else None
    if not (a is None or a == {}):
        return _refused(f"{STOP_OP} takes no argument: it stops the units of the roster's profile")
    root = _code_root() if root is None else root
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    try:
        profile = roster_profile(root)
    except InstallError as e:
        return _failed(None, str(e))
    fd, reply = _lock(state)
    if fd is None:
        return reply or _refused(LOCK_BUSY)
    try:
        daemon, client = unit_names(profile)
        left = _disable_now([client, daemon], run, home)       # the client first: it talks to the daemon
        states, still = _settled([daemon, client], run, home, sleep)
        if left or still:
            return {"status": "failed", "units": states, "reason": f"the units are not both stopped ({left or still})"}
        return {"status": "stopped", "units": states}
    finally:
        os.close(fd)


# --- the read ----------------------------------------------------------------------------------------------------

def installed(home: str | None = None, state: str | None = None, run: Callable[..., Any] = subprocess.run,
              root: str | None = None) -> dict:
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    bindir = bin_dir(home)
    units = {u: os.path.isfile(os.path.join(unit_dir(home), u)) for u in UNITS}
    marker = read_marker(state)
    recorded = _marker_programs(marker)
    root = _code_root() if root is None else root
    wanted: dict | None = None
    build: dict | None = None
    try:
        _, build = pinned_build(load_pin(root))
        wanted = build["reports"]
    except (PinError, InstallError):
        pass
    names = sorted(recorded) if recorded else sorted(wanted) if wanted else []
    marker_reports = marker.get("reports") if marker else None
    reporting = set(wanted) if wanted else set(marker_reports) if isinstance(marker_reports, dict) else set()
    reporting &= set(names)
    if not reporting:
        return {"status": "unreadable", "units": units, "reason": "neither the pin nor the marker names a program that reports a version"}
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
    out["channel"] = read_channel(root, build, run, home)
    return out


def read_channel(root: str, build: dict | None, run: Callable[..., Any], home: str) -> dict:
    """The same check an install ends with, run now and looking once: {"status": "ok" | "off" | "not-running" | "unknown",
    "units": {unit: state}, "reason"?}. Off is a unit that runs and fails the check; unknown is a check that could not be made."""
    try:
        profile = roster_profile(root)
        states, running = running_units(profile, run, home)
    except InstallError as e:
        return {"status": "unknown", "reason": str(e)}
    except ChannelUnknown as e:
        return {"status": "unknown", "reason": str(e)}
    if not running:
        return {"status": "not-running", "units": states}
    if build is None:
        return {"status": "unknown", "units": states, "reason": "the pin cannot be read, so the daemon's version cannot be compared"}
    c = channel_check(profile, running, build, root, run, home, time.sleep, polls=1)
    if c["status"] == "passed":
        return {"status": "ok", "units": states}
    if c.get("unknown"):
        return {"status": "unknown", "units": states, "reason": _channel_text(c)}
    return {"status": "off", "units": states, "reason": _channel_text(c)}


def _code_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
