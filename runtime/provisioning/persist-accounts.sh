#!/usr/bin/env bash
# runtime/provisioning/persist-accounts.sh — make the named accounts
# survive this host's reboot, the way this platform needs. Root, via sudo,
# on the host the accounts live on; idempotent; run by new-agent-worker.sh
# after useradd and by `bin/fabric-host <host> persist` for every
# placement (the one-time migration of accounts made before this
# existed, 2026-09-17).
#
#   persist-accounts.sh <login>...
#
# Every platform: `loginctl enable-linger <login>`, so the account's user
# manager — and the control agent under it — runs without a login. On a
# Qubes AppVM (platform/fedora-qubes.sh, PERSISTS_ACROSS_REBOOT=0) the
# account records themselves are volatile too: each login's line from
# /etc/{passwd,shadow,group,gshadow,subuid,subgid} is written into the
# snapshot /rw/config/agent-fabric/accounts/ (root, 0600), replacing an
# older line for the same name — each file swapped into place whole, so a
# crash mid-write leaves the previous snapshot, never a partial one — plus
# the login's supplementary groups (`members`: login:g1,g2, from the live
# /etc/group, so the shared-cache membership the worker grants comes back
# too), and the boot script platform/qubes/agent-fabric-accounts.rc is
# installed under /rw/config/rc.local.d/ and refreshed whenever this
# checkout's copy differs. Nothing on a persistent platform writes a
# snapshot. Secrets: the shadow line carries a hash, never a password; the
# snapshot directory is root's alone.
#
# Also on every platform: the host-wide lease directory the accounts
# share, /run/lock/agent-fabric (bin/fabric-lease, ADR-010) —
# made now, 1777, and made to come back after a reboot: by the boot
# script above on a Qubes AppVM, by a tmpfiles.d entry
# (platform/agent-fabric.tmpfiles.conf -> /etc/tmpfiles.d/) where /etc
# persists.
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
SNAP="${AGENT_FABRIC_ACCOUNTS_SNAPSHOT:-/rw/config/agent-fabric/accounts}"
RCD="${AGENT_FABRIC_RC_LOCAL_D:-/rw/config/rc.local.d}"
ETC="${AGENT_FABRIC_ETC:-/etc}"
LEASES="${AGENT_FABRIC_LEASES:-/run/lock/agent-fabric}"
TMPFILES_D="${AGENT_FABRIC_TMPFILES_D:-/etc/tmpfiles.d}"
LOGINCTL="${AGENT_FABRIC_LOGINCTL:-loginctl}"
[[ $# -ge 1 ]] || { echo "usage: persist-accounts.sh <login>..." >&2; exit 2; }
# shellcheck source=runtime/provisioning/platform/detect.sh
. "$ROOT/runtime/provisioning/platform/detect.sh"
rc=0
# The lease directory, for this boot; and for the next one where /etc persists.
install -d -m 1777 "$LEASES" || { echo "persist-accounts: cannot make the lease directory $LEASES" >&2; rc=1; }
if (( PERSISTS_ACROSS_REBOOT )); then
    src="$ROOT/runtime/provisioning/platform/agent-fabric.tmpfiles.conf"
    if ! cmp -s "$src" "$TMPFILES_D/agent-fabric.conf"; then
        install -d -m 755 "$TMPFILES_D" && install -m 644 "$src" "$TMPFILES_D/agent-fabric.conf" || rc=1
    fi
fi
# One writer at a time: the worker for one login and `fabric-host persist`
# for another both read-modify-write the same snapshot files.
if (( PERSISTS_ACROSS_REBOOT == 0 )); then
    install -d -m 700 "$SNAP" || exit 1
    exec 9>"$SNAP/.lock"; flock -w "${AGENT_FABRIC_LOCK_WAIT:-30}" 9 || { echo "persist-accounts: the snapshot is locked by another writer" >&2; exit 1; }
fi
for login in "$@"; do
    if ! getent passwd "$login" >/dev/null 2>&1 && ! grep -q "^$login:" "$ETC/passwd" 2>/dev/null; then
        echo "persist-accounts: no such account: $login" >&2; rc=1; continue
    fi
    if (( PERSISTS_ACROSS_REBOOT == 0 )); then
        install -d -m 700 "$SNAP" || { rc=1; continue; }
        put_line() {  # put_line <file> <line>: replace-or-append the login's line, atomically
            local f="$1" line="$2" tmp
            tmp="$(mktemp "$SNAP/.$f.XXXXXX")" || return 1
            { [[ -f "$SNAP/$f" ]] && grep -v "^$login:" "$SNAP/$f"; printf '%s\n' "$line"; } > "$tmp"
            chmod 600 "$tmp" && mv -f "$tmp" "$SNAP/$f"
        }
        for f in passwd shadow group gshadow subuid subgid; do
            [[ -f "$ETC/$f" ]] || continue
            line="$(grep "^$login:" "$ETC/$f" | head -1)"
            [[ -n "$line" ]] || continue
            put_line "$f" "$line" || rc=1
        done
        # Supplementary groups: every group whose member list names the
        # login (otscache, for one), as one line: login:g1,g2.
        groups="$(awk -F: -v u="$login" '{ n = split($4, m, ","); for (i = 1; i <= n; i++) if (m[i] == u) print $1 }' "$ETC/group" | paste -sd, -)"
        put_line members "$login:$groups" || rc=1
        src="$ROOT/runtime/provisioning/platform/qubes/agent-fabric-accounts.rc"
        if ! cmp -s "$src" "$RCD/agent-fabric-accounts.rc"; then
            install -d -m 755 "$RCD"
            install -m 755 "$src" "$RCD/agent-fabric-accounts.rc"
        fi
    fi
    "$LOGINCTL" enable-linger "$login" 2>/dev/null || { echo "persist-accounts: enable-linger failed for $login" >&2; rc=1; }
done
exit "$rc"
