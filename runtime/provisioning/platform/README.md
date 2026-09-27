# `runtime/provisioning/platform/` — what differs per platform, in one file each

The provisioning worker (`new-agent-worker.sh`) sources
`platform/<id>.sh` after reading `/etc/os-release` (`ID`, and
`QUBES_*`/`/usr/share/qubes` for an AppVM); everything that is a
distribution's or a deployment's choice lives there, and nothing else in
the worker names one:

| function / variable | what it says |
|---|---|
| `PLATFORM_ID` | the id the host registry uses (`fedora-qubes`, `fedora`, `debian`, `debian-qubes`) |
| `PKG_INSTALL_HINT` | the command a person runs to install packages, where they persist (a Qubes AppVM: in the TemplateVM) |
| `pkg_for <tool>` | the package that provides a tool of the fabric's contract |
| `PERSISTS_ACROSS_REBOOT` | whether a package installed on this machine is still there after a reboot (no, on a Qubes AppVM) |
| `GLOBAL_BASHRC` | the system bashrc a login shell sources (`/etc/bashrc` on Fedora, `/etc/bash.bashrc` on Debian) |
| `SUDO_GROUP_NOTE` | how sudo is granted to the operator here (the `qubes` group on Qubes; `sudo` on Debian) |

**The fabric's host contract** — the commands its hooks, scripts and
provisioning call, whatever the platform:
`bash sudo ssh getent pgrep timeout flock stat sha256sum cmp useradd
usermod shred install curl python3 node npm git gh jq gpg` (`usermod
--add-subuids` needs shadow-utils 4.9 or later: Fedora 35+, Debian 12+) (`cmp` is
what bootstrap's idempotence rests on; a Fedora container without
diffutils rewrote every file on every run — the smoke job's first find). `pkg_for` maps each
to its package; the CI smoke jobs install that list from the map on a
Fedora and a Debian container and run the suites, so the map is proven
by being used.

A project's extra needs (a container runtime, an image tool, a signing
wrapper) are the project's own `integration/provisioning/host-check.sh`.

## A Qubes AppVM: what lives where, and what a reboot must show

An AppVM's root volume is a volatile copy of its TemplateVM; only
`/home`, `/rw` and `/usr/local` survive a reboot. The fabric therefore
keeps three things in three places, and **nothing about the accounts is
ever done in the TemplateVM**:

| where | what | how it gets there |
|---|---|---|
| the TemplateVM | packages only: the host contract above (`node`, `git`, `gh`, `jq`, `python3`, `gpg`, …) | a person, once (`PKG_INSTALL_HINT`); the worker's host audit names a missing one |
| `/rw/config/agent-fabric/accounts/` | the account records — one line per login from `passwd shadow group gshadow subuid subgid`, and `members` (the login's supplementary groups); root, 0600 | `persist-accounts.sh`, run by the worker at every account's creation and by `bin/fabric-host <host> persist` for all placements |
| `/rw/config/rc.local.d/` | `agent-fabric-accounts.rc` (re-adds the records at boot, restores the memberships, enables linger, makes the lease directory `/run/lock/agent-fabric` — `docs/resources.md`) and `tmp-size.rc` (`/tmp` size) | `persist-accounts.sh` installs and refreshes the first; the second is the operator's |
| `/etc/tmpfiles.d/agent-fabric.conf` (persistent platforms only) | the lease directory `/run/lock/agent-fabric` for the next boot — on a Qubes AppVM the boot script above makes it instead | `persist-accounts.sh` installs it from `platform/agent-fabric.tmpfiles.conf` |
| `/home/<login>` | everything else: the account's tools (`~/.local`), its checkouts, its unit (`~/.config/systemd/user/`), its secrets | the worker, `bootstrap.sh`, `fabric-secrets sync` |

Creating the logins in the TemplateVM instead would work — the boot
script skips a login that is already present — but it is not the
design: the template would carry every account's uid and shadow line
into every AppVM built from it, and become a second source of truth for
what `persist-accounts.sh` owns. Why bind-dirs is not used either: a
bound `/etc/passwd` is a mountpoint, and shadow-utils' `rename(2)` over
it fails with EBUSY, breaking every later `useradd`
(`docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md`).

After a reboot of the AppVM, from the coordinator's checkout:

```sh
getent passwd | grep -c agent-fabric        # every placed account is back
loginctl show-user <login> -p Linger        # Linger=yes: its user manager, and the control agent, run without a login
bin/fabric-ctl all ping                     # every account answers within seconds (docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md)
```

The first reboot on `develop-qzapp` is recorded, when it happens, in
`docs/live-checks/2026-09-17-control-plane.md`.
