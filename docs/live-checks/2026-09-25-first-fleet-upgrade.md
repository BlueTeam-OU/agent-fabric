# 2026-09-25 — the first signed fleet upgrade, read back

> GOODBYE from the launcher was retired later the same day (presence replaced HELLO and GOODBYE); the measurement stands.
`fabric-ctl … upgrade claude` (PR #34) with the operator key registered
(PR #35), on develop-qzapp, sixteen accounts, the pin at 2.1.282.

## The key

Before the registry change was committed: the private half synced into the
operator's `secrets.env` signed a probe request that the registry's public
half verified — the pair matches. Neither half was printed.

## One account first

`fabric-ctl db-admin upgrade claude`: `upgraded 2.1.281 → 2.1.282`, session
`none`; the account's `actions-seen.json` held the operator's timestamp;
no restart marker (no session). Signature, ledger, install and verify all
worked on the real daemon.

## The whole fleet at once — nine failures

`fabric-ctl all upgrade claude`: 3 `current` (the operator's own account,
db-admin, and devex-tooling — which had a live session, was already at the
pin, and was left alone), 4 `upgraded`, **9 `failed`** with `claude install
2.1.282: Command failed: <argv>`. The same install run by hand as one of
the failed accounts succeeded; `fabric-ctl <login> upgrade claude` for the
failed accounts one at a time succeeded for every one. The request to `*`
makes every daemon on the host install at the same moment — some ~240 MB
download and unpack each — and most of them failed; the reason shown was
execFile's first line, so the actual error never surfaced. `fabric-ctl`
exited 0.

What this decided (PR #36): installs queue on the host lease
(`fabric-lease claude-install --wait 480`); the reported reason is the
command's last line; a failed action makes the run exit 1. (Its review
moved the queue ahead of the stop and the wait to 900 s:
`docs/fleet-upgrade.md` is the current procedure.)

Read back after finishing one at a time: `fabric-ctl all upgrade claude` →
16 × `current`.

## Background auto-update was on

Two accounts had moved to 2.1.282 on their own before the run: the
operator's (at 21:02 on 2026-09-24) and devex-tooling. Both carried
`autoUpdates: false` in `~/.claude.json`. Read from the 2.1.282 binary:

```
if (DISABLE_UPDATES) … ; if (truthy(process.env.DISABLE_AUTOUPDATER)) …
if (cfg.autoUpdates === false && (cfg.installMethod !== "native" || cfg.autoUpdatesProtectedForNative !== true)) → disabled
```

On a native install with `autoUpdatesProtectedForNative: true` (the
operator's), `autoUpdates: false` does not disable anything. Since PR #34
bootstrap writes `env.DISABLE_AUTOUPDATER=1` into every login's user
settings; read back on all sixteen after the 2026-09-25 distribution.

## Where the restart marker lives

The daemon (systemd user unit) and the launcher (login shell) resolve the
fabric state root the same way only if neither sees a different
`XDG_STATE_HOME`. Measured on all sixteen accounts: unset in a login shell
(`bash -lc`) and absent from `systemctl --user show-environment`.

## Not yet read back

A restart: no session was stopped in this run (none was running where an
install happened). The first upgrade that meets a running session should
confirm the SessionEnd hook ran, the session resumed with `--resume`, and —
on the broker path, where `claude` is `ori`'s child — that the launcher
reached its GOODBYE.
