# The control plane, read back — 2026-09-17

`docs/control-plane.md` rests on three read-backs of things outside the
fabric (the relay, the platform, shadow-utils) and one end-to-end run.
Measured on `develop-qzapp` (Qubes AppVM, Fedora template), as login
`user`, relay claude-code-bridge at `127.0.0.1:8765`.

## The relay's `since_id` (source, `server.py` `_read_channel_rows`)

- `/api/messages?channel&limit=N` without `since_id` returns the newest
  N rows, ascending. With `since_id`, the rows after that id; an id the
  channel does not hold returns `warning: "since_id_not_found"` and an
  empty page rather than everything.
- `/api/wait` takes the same `since_id` and long-polls up to 55 s. No
  consumer id is needed on either, and nothing is acked, so the daemon
  keeps no cursor file: it primes from the newest record and waits after
  it. Decides: no replay at restart, no per-daemon state on the relay.
- `sender` is whatever the client posts. Decides: the fence keys on the
  record's `from`, and signing is the next commit.

## Persistence on this host

- Read from inside the VM (`/proc/mounts`, the qubes persistence marker): `/rw` and `/home` persist,
  `/etc` and `/var/lib` do not (`rw-only`); the fifteen accounts existed
  only in the volatile `/etc/passwd`; `Linger=no` on all, `/rw/bind-dirs`
  unused. The VM had never been rebooted since the first account.
- `/rw/config/rc.local.d/*.rc` files are *executed* by `qubes-misc-post`
  after logind — the existing `tmp-size.rc` is the precedent — so the
  boot script is bash with a shebang, not a sourced fragment.
- shadow-utils writes `passwd+` and `rename(2)`s it over `passwd`; a
  bind-mounted single file makes the target a mountpoint and the rename
  fails with EBUSY. Decides: a snapshot re-added at boot, never bind-dirs.
- After `sudo bin/fabric-host develop-qzapp persist`: fifteen logins in
  `/rw/config/agent-fabric/accounts/{passwd,shadow,group,gshadow,subuid,subgid}`
  (0600), the rc file in place, `loginctl show-user <l> -p Linger` = yes
  for each, `/run/user/<uid>` present for each (the user manager starts
  on enable-linger, without a login). `tmp-size.rc` carries `size=3G`.
- A reboot of the AppVM is the owner's call and has not been done; what
  it must show is `getent passwd` listing the fifteen and `fabric-ctl
  all ping` answered within five seconds.

## End to end

- `bootstrap.sh` as `user`: the unit written, `daemon-reload`, `enable
  --now` → `active (running)` under
  `user@1000.service/app.slice/agent-fabric-agentd.service`, 29 MB.
- `fabric-ctl user ping`: one row, 9 ms, wall 0.37 s.
- Every other placement, through `fabric-host run --as <login>`: `git
  pull --ff-only`, then `bootstrap.sh` with `XDG_RUNTIME_DIR` set (the
  executor's environment is empty) → fourteen `active`.
- `fabric-ctl all ping`: fifteen rows `ok` in one poll (679 ms is the
  first read after the 500 ms interval, not fifteen latencies), wall
  1.04 s, exit 0. `fabric-ctl all status`: fifteen rows; the two Claude
  accounts and their windows agree with `bin/fabric-usage` to the
  percent (13 % / 86 % on one, 18 % / 18 % on the other); the four
  accounts with no credentials file say `no-credentials`; every fabric
  head `c785ade`, none dirty; every role as bound.
- `GZCOORD_CHANNEL=fabric:control node inbox.mjs` → exit 2, "is a
  control channel … never a session's inbox or outbox"; the watch on
  `gzapp:gzcoord` saw no control record.
- A `keys` reply names the four keys by presence and fingerprint; the
  reply text contains no value (asserted in the suite against fixture
  secrets, and read by eye here).

## After the blind review (4c416c3, 5b353fb)

- `fabric-host develop-qzapp persist` again: `members` holds fifteen
  lines (`<login>:flutterdev,otscache`, the operator's with `qubes` too),
  the installed boot script now equals the checkout's (`cmp`).
- Every account pulled and re-bootstrapped (the unit changed: PATH) →
  fifteen `active`; `fabric-ctl all status` fifteen rows on head
  `5b353fb`; the daemon's journal names its operator set at start and
  the request it answered. `--timeout 20s` refused, exit 2.

## Not measured

Signing (next commit); a second host; the reboot.
