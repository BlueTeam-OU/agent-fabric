#!/usr/bin/env python3
"""tools/fabric/provisioning/persist_host_settings.py — make the host settings the fabric needs, from the committed source of
their value, and make them come back after a reboot the way this platform needs. Root, via sudo, on the host; idempotent; run by
`bin/fabric-host <host> persist` after persist_accounts.py (the same rule, for the lease directory, is that step's).

    persist_host_settings.py

Two settings: the reserved ports, and the firewall's admission of the roster's range (below).

The reserved ports: net.ipv4.ip_local_reserved_ports must cover the roster's port_range
(the carrier's roster, carrier_install.ROSTER_REL, the only source: agent-fabric ADR-064 rules 1 and 2). An outgoing connection takes any port of the
ephemeral range as its source, and a carrier daemon cannot bind a port one took (EADDRINUSE); `fabric-ctl <login> <carrier>-start`
refuses a host whose setting does not cover the range.

Now: a live value that does not cover the range gets the range ADDED to it — a reservation someone else made is kept — and is read
back; a value that still does not cover it is a failure. A value that cannot be read or parsed is not added to (what it holds is
unknown, and writing would drop it), and is a failure.

Across a reboot: where the root does not persist (host_platform: persists_across_reboot False, a Qubes AppVM) the boot script
$AGENT_FABRIC_RC_LOCAL_D/agent-fabric-<carrier>.rc, 0755, which at boot ADDS the range to whatever the value is then; where it
does, /etc/sysctl.d/90-agent-fabric-<carrier>.conf. Each is generated from the range, rewritten only when its content or mode
differs, replaced whole (a temporary file and a rename), so a crash leaves the previous file or the new one. The other platform's
file is left alone. The sysctl.d file carries the live value with the range added, because the last file for the key wins at boot: one sorting
after ours wins over it, so whoever adds another reservation there must list the range too, and a reservation made
only after this step ran is in the file once the step runs again. A value that cannot be read gets no such file.

The firewall (agent-fabric ADR-064 rule 1, A 2026-11-27): this host's entry in the hosts registry (roots.hosts_registry, found
as the roster is: the tree this file is in, AGENT_FABRIC_HOSTS_REGISTRY first; the entry's id is the short hostname,
identity.current_host) says who the carrier's wildcard listeners may be reached by.
  neither the address nor the admit field (gzcoord.carrier.roster ADDRESS_KEY, ADMIT_KEY)   nothing to admit: one line, no
                              firewall-cmd run
  admit "any"                 the roster's port_range, TCP, as a port in the firewalld zone of the interface the default route
                              (<proc>/net/route) uses
  admit <ip|cidr>             the same range as a rich rule limited to that source (IPv4; a CIDR with host bits is refused)
Each is made live and permanent, only where it is not already (already admitted: one line, no write), then read back; a read-back
that disagrees is a failure. Never wider than the field: "any" is never added for an address. An address without
an admit, a value that is none of these, or an entry that cannot be found is a failure, not "nothing to admit".
Only firewalld is driven. A host whose firewalld is not running, whose firewall-cmd is absent or fails, or that has nftables or
iptables only, is a FAILURE with nothing changed: its profiles listen on the wildcard and its firewall state is unknown. An
admission an earlier, different range made is not removed by this step.

CONTRACT
  argv    none; any is a usage line on stderr, exit 2
  env     AGENT_FABRIC_PROC_ROOT (/proc), AGENT_FABRIC_RC_LOCAL_D (/rw/config/rc.local.d),
          AGENT_FABRIC_SYSCTL_D (/etc/sysctl.d), AGENT_FABRIC_PLATFORM (host_platform), AGENT_FABRIC_HOSTS_REGISTRY, PATH
          (firewall-cmd; the only variable a child gets besides LC_ALL=C)
  stdout  one line per setting: what was found and what was done
  stderr  every failure, as `persist-host-settings: <why>`
  exit    0 done (also: already so); 1 the roster or the live value cannot be read, the value is not covered after the write,
          the firewall cannot be read or set or does not read back as admitted, or the boot file cannot be installed — a failed install IS counted, it is the whole point of the step (unlike
          persist_accounts' boot script); 2 usage
"""
from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from control import carrier_install  # noqa: E402
from gzcoord.carrier import CARRIER_NAME, roster  # noqa: E402
from provisioning import host_platform  # noqa: E402
import roots  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "runtime"))
import identity  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
KEY = "net.ipv4.ip_local_reserved_ports"
# <carrier> is gzcoord.carrier.CARRIER_NAME; the owner's hand copy of the boot script has this name, so the install replaces it.
RC_NAME = f"agent-fabric-{CARRIER_NAME}.rc"
SYSCTL_NAME = f"90-agent-fabric-{CARRIER_NAME}.conf"
FIREWALL_TIMEOUT_S = 30
DEFAULT_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


def _say(text: str) -> None:
    print(f"persist-host-settings: {text}", file=sys.stderr)


def _text(spans: list[tuple[int, int]]) -> str:
    """The kernel's text for these spans, merged: overlapping or adjacent ones are one."""
    merged: list[list[int]] = []
    for lo, hi in sorted(spans):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return ",".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in merged)


def rc_script(low: int, high: int) -> str:
    return f"""#!/bin/sh
# agent-fabric: reserve the carrier roster's ports ({low}-{high}) away from outgoing connections, after every boot.
#
# Generated by tools/fabric/provisioning/persist_host_settings.py from the carrier roster's port_range
# (agent-fabric ADR-064 rule 1); `fabric-host <host> persist` rewrites it when the roster's range changes. A Qubes AppVM's
# /etc is volatile, so a sysctl.d file would not survive: /rw/config/rc.local.d does. The range is ADDED to whatever the value
# is at this point of the boot, never written over it.
f=/proc/sys/net/ipv4/ip_local_reserved_ports
cur=$(cat "$f") || exit 1
exec sysctl -w "{KEY}=${{cur:+$cur,}}{low}-{high}"
"""


def sysctl_conf(spans: list[tuple[int, int]]) -> str:
    """The whole value, not the range alone: systemd-sysctl applies the files in lexical order and the last one for a key wins, so
    a file of the range alone would drop what an earlier file reserved (the live value, which they made, is in `spans`)."""
    return (f"# agent-fabric: reserve the carrier roster's ports away from outgoing connections (agent-fabric ADR-064 rule 1).\n"
            f"# Generated by tools/fabric/provisioning/persist_host_settings.py from the carrier roster and the value live at the time.\n"
            f"{KEY} = {_text(spans)}\n")


def _install(path: str, content: str, mode: int) -> bool:
    """The file with this content and mode, replaced whole; True when it had to be written."""
    try:
        with open(path, encoding="utf-8") as fh:
            if fh.read() == content and (os.stat(path).st_mode & 0o7777) == mode:
                return False
    except (OSError, UnicodeDecodeError):
        pass
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".install-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def _write_live(proc_root: str, text: str) -> None:
    with open(os.path.join(proc_root, carrier_install.RESERVED_PORTS_REL), "w", encoding="ascii") as fh:
        fh.write(text)


def _reserve(env: Mapping[str, str], low: int, high: int) -> int:
    proc_root = env.get("AGENT_FABRIC_PROC_ROOT") or "/proc"
    rcd = env.get("AGENT_FABRIC_RC_LOCAL_D") or "/rw/config/rc.local.d"
    sysctl_d = env.get("AGENT_FABRIC_SYSCTL_D") or "/etc/sysctl.d"
    prof = host_platform.profile(host_platform.detect(env))
    rc = 0
    final: list[tuple[int, int]] | None = None     # the live value once it covers the range
    try:
        spans = carrier_install.read_reserved_ports(proc_root)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        _say(f"the live {KEY} cannot be read ({e}); not written over")
        spans = None
        rc = 1
    if spans is not None:
        if carrier_install.ports_covered(spans, low, high):
            print(f"{KEY}: {low}-{high} already covered")
            final = spans
        else:
            try:
                _write_live(proc_root, _text([*spans, (low, high)]))
                after = carrier_install.read_reserved_ports(proc_root)
            except (OSError, UnicodeDecodeError, ValueError) as e:
                _say(f"{KEY} could not be set and read back ({e})")
                after = None
            if after is not None and carrier_install.ports_covered(after, low, high):
                print(f"{KEY}: {low}-{high} added, now {_text(after)}")
                final = after
            else:
                if after is not None:
                    _say(f"{KEY} does not cover {low}-{high} after the write")
                rc = 1
    if prof.persists_across_reboot:
        if final is None:
            _say(f"{os.path.join(sysctl_d, SYSCTL_NAME)} not installed: the value it would carry is not known")
            return 1
        path, content, mode = os.path.join(sysctl_d, SYSCTL_NAME), sysctl_conf(final), 0o644
    else:
        path, content, mode = os.path.join(rcd, RC_NAME), rc_script(low, high), 0o755
    try:
        wrote = _install(path, content, mode)
        print(f"{path}: {'written' if wrote else 'already as it should be'}")
    except OSError as e:
        _say(f"{path} could not be installed ({e}); the setting would not survive a reboot")
        rc = 1
    return rc


class FirewallError(Exception):
    pass


def _fw(env: Mapping[str, str], *args: str, ok: tuple[int, ...] = (0,)) -> tuple[int, str]:
    """firewall-cmd with an argument list, a bound and a minimal environment. (exit status, stdout), the status one of `ok`;
    absent, hung or any other status is a FirewallError, so a query's "no" (status 1) is never confused with a failed run."""
    try:
        r = subprocess.run(["firewall-cmd", *args], env={"PATH": env.get("PATH") or DEFAULT_PATH, "LC_ALL": "C"},
                           capture_output=True, text=True, timeout=FIREWALL_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        raise FirewallError("firewall-cmd is not installed: only firewalld is driven (a host with nftables or iptables only is "
                            "refused, nothing changed)") from None
    except subprocess.TimeoutExpired:
        raise FirewallError(f"firewall-cmd {' '.join(args)} did not answer in {FIREWALL_TIMEOUT_S} s") from None
    except OSError as e:
        raise FirewallError(f"firewall-cmd cannot be run ({e})") from None
    if r.returncode not in ok:
        detail = (r.stderr or r.stdout).strip().splitlines()
        raise FirewallError(f"firewall-cmd {' '.join(args)} exited {r.returncode}" + (f": {detail[0]}" if detail else ""))
    return r.returncode, r.stdout.strip()


def default_route_interface(proc_root: str) -> str:
    """The interface of the default route with the lowest metric, from <proc>/net/route. Absent or unparseable is an error: the
    zone to open is then unknown."""
    path = os.path.join(proc_root, "net", "route")
    try:
        with open(path, encoding="ascii") as fh:
            rows = [line.split() for line in fh.read().splitlines()[1:] if line.strip()]
        best = [(int(r[6]), r[0]) for r in rows if r[1] == "00000000" and r[7] == "00000000" and int(r[3], 16) & 1]
    except (OSError, UnicodeDecodeError, ValueError, IndexError) as e:
        raise FirewallError(f"the default route cannot be read from {path} ({e.__class__.__name__}): the zone to open is unknown") from None
    if not best:
        raise FirewallError(f"{path} has no default route: the zone to open is unknown")
    return min(best)[1]


def _zone(env: Mapping[str, str], proc_root: str) -> str:
    iface = default_route_interface(proc_root)
    _, zone = _fw(env, f"--get-zone-of-interface={iface}")
    if zone in ("", "no zone"):
        # An interface no zone claims is in the default zone, which is where firewalld applies its traffic.
        _, zone = _fw(env, "--get-default-zone")
    if not zone or " " in zone:
        raise FirewallError(f"the zone of {iface} is not known (firewall-cmd said {zone!r})")
    return zone


def _admission(admit: object, low: int, high: int) -> tuple[str, str]:
    """(firewall-cmd option suffix, the value): `port` or `rich-rule`, from the entry's admit field."""
    ports = str(low) if low == high else f"{low}-{high}"
    if admit == "any":
        return "port", f"{ports}/tcp"
    if isinstance(admit, str):
        try:
            net = ipaddress.IPv4Network(admit, strict=True)
        except ValueError:
            net = None
        if net is not None:
            return "rich-rule", f'rule family="ipv4" source address="{admit}" port port="{ports}" protocol="tcp" accept'
    raise FirewallError(f"{roster.ADMIT_KEY} {admit!r} is neither \"any\" nor an IPv4 address or CIDR without host bits")


def host_entry(env: Mapping[str, str], root: str, host: str) -> Mapping[str, object]:
    path = roots.hosts_registry(environ=env, engine=root)
    try:
        with open(path, encoding="utf-8") as fh:
            entry = json.load(fh)["hosts"][host]
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as e:
        raise FirewallError(f"the entry of host {host} in the hosts registry {path} cannot be read ({e.__class__.__name__}): "
                            "whether this host admits anyone is unknown") from None
    if not isinstance(entry, dict):
        raise FirewallError(f"the entry of host {host} in {path} is not an object")
    return entry


def _admit(env: Mapping[str, str], root: str, low: int, high: int) -> int:
    proc_root = env.get("AGENT_FABRIC_PROC_ROOT") or "/proc"
    try:
        entry = host_entry(env, root, identity.current_host())
        admit, address = entry.get(roster.ADMIT_KEY), entry.get(roster.ADDRESS_KEY)
        if admit is None and address is None:
            print(f"firewall: neither {roster.ADDRESS_KEY} nor {roster.ADMIT_KEY}: nothing to admit")
            return 0
        if admit is None:
            raise FirewallError(f"{roster.ADDRESS_KEY} is set and {roster.ADMIT_KEY} is not: the profiles listen on the wildcard and "
                                "nobody is said to be admitted")
        kind, value = _admission(admit, low, high)
        _fw(env, "--state")        # 252 and every other status: firewalld is not running, which is a failure
        zone = _zone(env, proc_root)
        have = {perm: _fw(env, *(["--permanent"] if perm else []), f"--zone={zone}", f"--query-{kind}={value}", ok=(0, 1))[0] == 0
                for perm in (False, True)}
        if all(have.values()):
            print(f"firewall: {value} already admitted in zone {zone}, live and permanent")
            return 0
        for perm, there in have.items():
            if not there:
                _fw(env, *(["--permanent"] if perm else []), f"--zone={zone}", f"--add-{kind}={value}")
        for perm in (False, True):
            if _fw(env, *(["--permanent"] if perm else []), f"--zone={zone}", f"--query-{kind}={value}", ok=(0, 1))[0] != 0:
                raise FirewallError(f"{value} is not admitted in zone {zone} {'permanently' if perm else 'live'} after the write")
        print(f"firewall: {value} admitted in zone {zone}, live and permanent (from {admit})")
        return 0
    except FirewallError as e:
        _say(f"firewall: {e}")
        return 1


def run(environ: Mapping[str, str] | None = None, root: str = ROOT) -> int:
    """Both settings always run: a host whose ports cannot be reserved still gets its firewall admission, and the reverse."""
    env = os.environ if environ is None else environ
    try:
        low, high = carrier_install.roster_port_range(root)
    except carrier_install.InstallError as e:
        _say(str(e))
        return 1
    return max(_reserve(env, low, high), _admit(env, root, low, high))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        _say("usage: persist_host_settings.py (no arguments)")
        return 2
    return run()


if __name__ == "__main__":
    sys.exit(main())
