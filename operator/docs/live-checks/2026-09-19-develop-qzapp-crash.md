# 2026-09-19 — develop-qzapp died under two backend suites

Read back from inside the VM after its reboot, by the coordinator's
login; what it decides is `docs/resources.md` and `bin/fabric-lease`.

## What was measured

- **Boot:** 09:12:57 CEST (`/proc/stat btime`). The last file written
  before it: 09:12:30. The VM died in that window.
- **The crashed boot's journal is gone.** `/var/log/journal` is on the
  AppVM's volatile root; `journalctl --list-boots` shows the template's
  boots and this one only. The proof of the OOM, if any, is in dom0:
  `/var/log/xen/console/guest-develop-qzapp.log`, `/var/log/qubes/qmemman.log`.
- **Disk: not it.** `/rw` (xvdb, 295 G) had 41 G free; mounted clean on
  this boot, no journal recovery; `tune2fs` state `clean`.
- **Memory ceiling:** `qvm-prefs` says `maxmem 32000, memory 16000`;
  the guest's own `xenstore memory/static-max` says 18,803,768 kB ≈
  18.3 GB, and `xl list` shows the domain holding 18,326 MB — at that
  ceiling, not the 32 GB the prefs intend. Thirteen minutes after boot
  `free` showed 8.6 GiB total: the balloon grows on demand, in steps.
- **The five minutes before** (session transcripts, local time):
  - 09:08:01 `db-admin`: `dotnet build` of `Gzapp.DriverApi.Tests`, then its run.
  - 09:08:40 `backend-dev-02`: `make backend-test FILTER=AdServingTests`.
  - 09:11–09:12:30: **~166,000 files written** — 116k in
    `backend-dev-02`'s podman volume, 50k in `db-admin`'s: two
    Testcontainers postgres instances materialising a schema per test
    class, concurrently. Then nothing.
  - `flutter-dev-01` idle since 08:58 (a Monitor and a `git status`);
    `flutter-dev-02` no session. Not involved.
- **Load at the time:** five Claude sessions, two `dotnet` build/test
  trees (MSBuild nodes, compiler servers, xunit hosts), two write-hot
  postgres containers, six vCPUs, at most 18.3 GB and likely less.

## What it decides

1. Two accounts must not start the same host-bound heavy job at once:
   a host lease at the call site (`bin/fabric-lease`, the directory
   made at boot), with a memory floor for the balloon lag.
2. The 18.3 GB ceiling is a dom0 matter (the clamp at domain creation,
   or a `maxmem` raised after the last cold start): a full
   `qvm-shutdown`/`qvm-start` with the host able to reserve it, then
   re-read `static-max`. Raising `memory` toward what a suite burst
   needs also shortens the balloon's lag.
3. The per-account quota (`MemoryHigh` on the user slice) is the next
   layer, not this one: the lease serialises two accounts and does
   nothing about one.
4. A dedicated "test runner" role was considered and declined: it
   changes who runs the suite, not how many run at once, and adds a
   handoff to every run.

## The lease, read back live (10:25 CEST, same day)

`persist-accounts.sh user` made `/run/lock/agent-fabric` (1777, root)
for this boot and refreshed the boot script under `/rw/config`. Then,
with a world-readable copy of `bin/fabric-lease` (each account reads
the fabric from its own checkout, and the coordinator's home is 0700):

- `user` held `backend-test` for four seconds.
- `db-admin`, through the host executor: `--who` → `held: user 376293
  2026-09-19T08:26:39Z backend-test`; a plain call → refused, exit 75,
  the same record; `--wait 10` → `acquired-by db-admin` once `user`
  finished, and the file now reads `db-admin 376420 … backend-test`
  while still owned by `user`.

The first attempt failed with `Permission denied` opening the file:
`fs.protected_regular` (1 here — systemd's default, `/usr/lib/sysctl.d/50-default.conf`; some distributions set 2; the mechanism needs only ≥ 1) refuses an `O_CREAT` open of another login's
file in a sticky world-writable directory, and bash's `<>` and `>`
always carry `O_CREAT`. The tool now locks a read-only descriptor and
writes the record with `dd conv=nocreat`. The suite cannot reproduce
this (one uid); this read-back is the proof.
