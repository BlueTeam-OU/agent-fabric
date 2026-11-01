# 2026-11-01 — the roster's reserved ports, made to survive a reboot by `fabric-host <host> persist`

Run by fabric-coordinator (user@develop-qzapp, job j469) on develop-qzapp, the control plane at c7b41a90 (main, with #449). The question: does the provisioning step #449 added (`tools/fabric/provisioning/persist_host_settings.py`, run by `bin/fabric-host <host> persist`) take over the reservation of the carrier roster's `port_range` (agent-fabric ADR-064 §5 rule 1) on a Qubes AppVM, where it was lost once already?

## Why it was asked

develop-qzapp is a Qubes AppVM, rw-only (`qubesdb-read /qubes-vm-persistence`): only `/rw`, `/home` and `/usr/local` survive a reboot, and `/etc` comes back from the template. The owner reserved 47100-47199 on 2026-10-26 in `/etc/sysctl.d/90-interweave-roster-ports.conf` (the rule 1 amendment of that day). After the reboot of 2026-10-30 05:08Z the value was empty and the file was gone: the boot-enabled InterWeave units came up anyway (systemd does not check it), but `fabric-ctl all interweave-start` refused all 30 accounts. The owner restored it by hand the same day as `/rw/config/rc.local.d/agent-fabric-interweave.rc`, 65 bytes: `sysctl -w net.ipv4.ip_local_reserved_ports=47100-47199`, which writes over any other reservation.

## What was measured

| step | result |
|---|---|
| before: `fabric-ctl user interweave --json`, `reserved_ports` | `{"range": [47100, 47199], "status": "covered"}` (the hand copy's work) |
| `fabric-host develop-qzapp persist`, first run | exit 0; `net.ipv4.ip_local_reserved_ports: 47100-47199 already covered`, `/rw/config/rc.local.d/agent-fabric-interweave.rc: written`; the account step printed nothing |
| the boot script after it | root, 0755, 681 bytes, generated: reads `/proc/sys/net/ipv4/ip_local_reserved_ports` and runs `sysctl -w` with the range appended to what it read |
| live value after it | `47100-47199` |
| `/etc/sysctl.d/` after it | no `90-agent-fabric-interweave.conf` (the AppVM path writes only the boot script, as the module says) |
| `fabric-host develop-qzapp persist`, second run | exit 0; `already covered`, the script `already as it should be`; its mtime unchanged (18:29:01 +0100) |
| control: the installed script with `f` pointed at a scratch file and `sysctl -w` replaced by `echo`, starting from an empty value | `net.ipv4.ip_local_reserved_ports=47100-47199` |
| control: the same, starting from `8080` | `net.ipv4.ip_local_reserved_ports=8080,47100-47199` (the other reservation is kept, which the hand copy did not do) |

## What it decides

On this host the reservation is now provisioning's: the boot script is generated from the roster, replaced the owner's hand copy under the same name, and is idempotent. The fix for a `reserved_ports` that reads `not-covered` or `unreadable`, and for a start refused for it, is `fabric-host <host> persist`, which is what both now name. ADR-064 rule 1 says so (A 2026-11-01).

## Not verified

- A reboot. The script was run with a stubbed `sysctl`, not by `rc.local` at boot; the next reboot of develop-qzapp is the check, read with `fabric-ctl all interweave` (`reserved_ports` covered on every account before any `interweave-start`).
- The persistent-host path (`/etc/sysctl.d/90-agent-fabric-interweave.conf`): no persistent host is placed; the suite covers it.
- The `not-covered` read and the refusal live: clearing the live value would have left the roster's ports open to outgoing connections for the length of the check; `tests/test_control_carrier_install.py` covers both.
