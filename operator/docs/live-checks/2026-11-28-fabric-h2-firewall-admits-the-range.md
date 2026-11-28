# 2026-11-28 — fabric-h2's firewall admits the InterWeave range, made by persist's host-settings step

**Decides:** `persist_host_settings.py` on main (5e5eb53bc, #721;
ADR-064 rule 1, A 2026-11-27) opens the roster's whole range
47100-47199/tcp in fabric-h2's firewalld zone, live and permanent. It does
so from the registry's `interweave_admit: "any"`, and a source outside
the provider's network then reaches a listener in the range. The
range-versus-profiles question is not reopened. #597 and ADR-064's
2026-11-14 and 2026-11-27 amendments chose the whole range. This closes
the 2026-11-27 check's open point (`2026-11-27-fabric-h2-public-forward.md`,
"What follows"). It does not by itself let a roster row name fabric-h2:
j860's SPIKE-004 limits come first.

**Who, from where:** fabric-coordinator (`user` on develop-qzapp), as on
11-27. This host leaves through 2.35.202.83, so the probe takes the
public path with no hairpin. fabric-h2 was reached with
`fabric-host fabric-h2 run`, as `op`.

## The door refused

`fabric-host fabric-h2 persist` answered `no placements on fabric-h2`
(exit 2) and ran neither step. Its placement check comes before both
steps, while only `persist_accounts.py` needs placements. The host
settings were therefore made by running the exact line persist would
run for its second step:

    fabric-host fabric-h2 run -- sudo -n /usr/local/bin/fabric-python -I @fabric/tools/fabric/provisioning/persist_host_settings.py

That refusal is a defect, and its fix is sent to python-dev (j1127).
Before the run, op's checkout (`~/projects/agent-fabric`, the registry's
`fabric`) was 1476 commits behind. It was fast-forwarded to 5e5eb53bc.
The checkout's `runtime/python.json` (3.14.9+20261021) is the build
installed there.

## Measured

1. **Before.** Zone `public` (default, ens18, the default route's
   interface), services cockpit, dhcpv6-client and ssh. No ports were
   open, live or permanent. `ip_local_reserved_ports` was empty, and
   nothing listened on 471xx.
2. **The step.** Output, exit 0:
   - `ip_local_reserved_ports: 47100-47199 added, now 47100-47199`
   - `/etc/sysctl.d/90-agent-fabric-interweave.conf: written`
   - `firewall: 47100-47199/tcp admitted in zone public, live and permanent (from any)`

   A second run printed "already covered", "already as it should be"
   and "already admitted", with exit 0. `--list-ports` and
   `--permanent --list-ports` both read `47100-47199/tcp`.
3. **From outside** (07:03Z), with a one-shot listener on fabric-h2 at
   0.0.0.0:47150 and at 0.0.0.0:47200:

   | port | 11-27, before | 11-28, after |
   |---|---|---|
   | 47150 (listener) | — | connected in 0.14 s and read `fabric-h2 probe 47150`; the listener logged `accepted from 2.35.202.83` |
   | 47100 (no listener) | `EHOSTUNREACH` 0.07 s | `ECONNREFUSED` 0.07 s |
   | 47199 (no listener) | `EHOSTUNREACH` 0.08 s | `ECONNREFUSED` 0.07 s |
   | 47200 (listener, outside the range) | — | timeout, 10 s |
   | 22 (control, not forwarded) | timeout, 10 s | timeout, 10 s |

   At both ends of the range, the firewall's reject became the kernel's
   reset for a port nobody holds, so the firewall now passes the whole
   range. The listeners exited by themselves (60 s bound), and afterwards
   nothing listened on 471xx or 472xx.

## Not measured

- **Survival across a reboot.** The permanent zone and the sysctl.d file
  are written; fabric-h2 was not rebooted.
- **Why 47200 is refused.** The provider's forward covers the range, so
  the timeout cannot separate the VM's firewall from the provider not
  forwarding the port. The firewall's own answer is the port list above.
- UDP, and any InterWeave daemon. This was a TCP connect only.
- `persist_accounts.py`. No account is placed on fabric-h2.
