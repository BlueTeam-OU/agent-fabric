# 2026-09-25 — develop-qzapp died under one account's full stack and an app build

Read back from inside the VM after its reboot, by the coordinator's
login, the same way as `2026-09-19-develop-qzapp-crash.md`. Times are
local (CEST); the session transcripts are UTC, two hours behind.

## What was measured

- **Death and boot.** The last file written anywhere was at 12:26:15;
  the VM booted at 12:26:42 (`/proc/stat btime`). `last -x` has no
  shutdown record for the previous boot: it went down, not off.
- **The crashed boot's journal is gone** again: `/var/log/journal` is on
  the AppVM's volatile root. The proof of an OOM, if there is one, is
  still only in dom0 (`/var/log/qubes/qmemman.log`,
  `/var/log/xen/console/guest-develop-qzapp.log`), which was not read.
- **Memory ceiling: not the clamp of 2026-09-19.** `xenstore
  memory/static-max` now reads 33,554,432 kB (32 GiB); it was 18.3 GB
  then. Right after this boot `free` shows 31 GiB total.
- **The minutes before**, from each account's session transcripts:
  - `flutter-dev-01` had its own full gzapp stack up in podman:
    **20 containers**. Among them OpenTripPlanner, Nominatim,
    Keycloak and its Postgres, the main Postgres, five .NET APIs, a
    tileserver and tiles API, and Prometheus, Grafana, Loki and Tempo.
    At 12:24:16 it started the passenger app,
    `apps/passenger_flutter/scripts/run-linux-mcp.sh`: a Linux desktop
    Flutter build and run. From 12:24:22 it was waiting for the Dart
    VM service, so the build was still going. Prometheus wrote its WAL
    at 12:26:15, the last write on the host.
  - `p2p-network-dev-01`: `cargo test` at 12:23:01 and `cargo clippy`
    at 12:23:45 had both returned by 12:24, since the next command
    started. From 12:24:13 to the end, its subagent ran grep- and
    Python-based doc checks. **Not heavy at the time of death.**
  - `devex-tooling`: `git diff`s and shell guard tests until 12:26:08.
    Light.
  - Every other account: no command in the window.

## What it decides

1. The heavy load at death was one account's full local stack plus a
   desktop app build. The host lease (`bin/fabric-lease`,
   `docs/resources.md`) serialises backend test suites; nothing
   serialises bringing a whole stack up, or bounds it by free memory.
2. Where the stack starts is the managed project's (`gzapp`'s
   Makefile, devex-tooling's lane). Two shapes are open to it: a
   lighter profile for app work, without OpenTripPlanner and
   Nominatim; or bringing the stack up under a host lease with a
   memory floor (`fabric-lease <name> --need-mem <MB>`), as the
   backend suite already does. The finding went to devex-tooling
   over GZCoord.
3. Whether it was memory at all is settled only in dom0: a kernel OOM
   or panic line in the guest console log, or qmemman refusing the
   balloon. Until that is read, "memory" is the likely cause, not the
   measured one.
