"""tools/fabric/provisioning/host_steps.py — what the worker's steps 0-4 must
decide (ADR-040 Wave 5; carried from tools/fabric/new_agent_worker.py): the
host's name and whether the account exists, the audit of the host's tools,
the claude version the installer is given, the subordinate id range, and the
GitHub host keys an account lacks. The step-runner (worker.py) asks these and
does the rest as argument lists."""
from __future__ import annotations

import json
import subprocess
import sys

from provisioning import bounded
from provisioning.worker_args import TARGET, VERSION, Exit

def host_check(login: str) -> str:
    """The host names itself; the coordinator compares this with the
    registry id it reached the host as, and never stamps a host it is not
    on. `hostname -s` and getent as commands, as the bash ran them."""
    name = bounded.run_bounded(["hostname", "-s"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       timeout=bounded.READBACK_TIMEOUT_S).stdout.decode("utf-8", "surrogateescape")
    present = bounded.run_bounded(["getent", "passwd", login], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          timeout=bounded.READBACK_TIMEOUT_S).returncode == 0
    return name + ("account: present\n" if present else "account: absent\n")


def audit(platform_id: str, persists: str, hint: str, n_tools: str, packages: list[str]) -> str:
    """Step 0, the host: what the fabric's host contract (platform/detect.sh:
    FABRIC_HOST_TOOLS) finds missing, as the packages that hold it — what
    its hooks, scripts and provisioning call; the package each comes from,
    and where a package persists, is the platform profile's. A Qubes AppVM
    keeps only /home and /usr/local across a reboot, so there a package is
    the TemplateVM's. A project's extra needs are its own host-check."""
    pkgs = " ".join(packages)
    if not packages:
        return f"new-agent: 0. {platform_id}: host tools present ({n_tools}, the fabric's contract)\n"
    try:
        persists_on = int(persists or "0") != 0   # bash's (( … )): a number, empty as 0
    except ValueError:
        persists_on = False
    if persists_on:
        return f"new-agent: 0. {platform_id}: this host lacks {pkgs}: {hint} {pkgs}\n"
    return (f"new-agent: 0. {platform_id}: this AppVM lacks {pkgs} — a package does not survive a reboot here;\n"
            f"new-agent:    {hint} {pkgs}   (then restart this AppVM)\n")


def claude_want(root: str, target: str) -> str:
    """The version the installer is given. claude: the vendor's installer,
    as the account, on the version the fleet pins
    (runtime/claude-code/harness.json — what `fabric-ctl … upgrade claude`
    brings every account to), so a new account starts where the others
    are; --claude overrides it (a version, stable or latest), and with no
    pin readable it is the vendor's latest. The pin reaches as_login's
    eval: a pin that is not a version is refused, and a pin that cannot be
    read is said, never silently turned into latest."""
    try:
        with open(f"{root}/runtime/claude-code/harness.json", encoding="utf-8") as fh:
            pinned = str(json.load(fh).get("claude") or "")
    except (OSError, ValueError, AttributeError):
        pinned = ""
    if pinned and not VERSION.fullmatch(pinned):
        raise Exit(1, f"new-agent: runtime/claude-code/harness.json pins claude '{pinned}', which is not a version; "
                      "nothing installed")
    if not target and not pinned:
        print("new-agent:    claude: no readable pin in runtime/claude-code/harness.json — the vendor's latest instead",
              file=sys.stderr)
    want = target or pinned or "latest"
    if not TARGET.fullmatch(want):
        raise Exit(1, f"new-agent: claude target '{want}' is not stable, latest or a version; nothing installed")
    return want


def subids(login: str, etc: str) -> str:
    """A subordinate uid AND gid range, or rootless podman can unpack no
    image and every Testcontainers suite fails on the login: useradd
    allocates one by default (login.defs SUB_UID_COUNT), but an account
    made another way has none — architect-cto-01 was that account, found
    2026-09-19 with 2716 fixture failures. The next free block above every
    range in the files (SUB_UID_MIN when they are empty), the same block
    for both."""
    def lines(name: str) -> list[str]:
        try:
            with open(f"{etc}/{name}", encoding="utf-8", errors="surrogateescape") as fh:
                return fh.read().splitlines()
        except OSError:
            return []
    uid, gid = lines("subuid"), lines("subgid")
    mine = [ln for ln in uid if ln.startswith(f"{login}:")]
    if mine and any(ln.startswith(f"{login}:") for ln in gid):
        return "have " + mine[0].split(":", 1)[1] + "\n"
    defs = {}
    for ln in lines("login.defs"):
        f = ln.split()
        if len(f) >= 2 and f[0] in ("SUB_UID_MIN", "SUB_UID_COUNT"):
            defs.setdefault(f[0], f[1])
    start = int(defs.get("SUB_UID_MIN") or 524288)
    count = int(defs.get("SUB_UID_COUNT") or 65536)
    for ln in uid + gid:
        f = ln.split(":")
        try:
            start = max(start, int(f[1]) + int(f[2]))
        except (IndexError, ValueError):
            pass
    return f"alloc {start}-{start + count - 1}\n"


def missing_keys(keys_file: str, known_hosts: str) -> str:
    """From the committed copy of GitHub's PUBLISHED keys (github-host-keys,
    api.github.com/meta, fingerprints checked against docs.github.com when
    the file was written — docs/live-checks/2026-09-16-github-host-keys.md),
    never ssh-keyscan: a scan trusts whatever answers on the network the
    bootstrap is about to use (review, 2026-09-16). Every key line the
    account does not hold yet, as a whole line; a changed key at GitHub is
    a change to the committed file, reviewed like any other."""
    have = set(known_hosts.splitlines())
    with open(keys_file, encoding="utf-8") as fh:
        return "".join(f"{ln}\n" for ln in fh.read().splitlines() if ln and ln not in have)
