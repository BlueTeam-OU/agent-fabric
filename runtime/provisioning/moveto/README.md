# `moveto`

Open a shell as another role account, in that account's **workspace** —
`~/projects`, the directory a session is launched from — with the window
title set to the session.

```
moveto architect-cto-01        # shell as that account, in ~/projects
moveto architect-cto-01 <clone>  # …in a named clone under it instead
moveto --list                  # accounts with a clone or the agent-fabric checkout
moveto <account> --list        # that account's clones
moveto <account> --print       # resolve only — print path and title, spawn nothing
moveto <account> [<clone>] --resume  # …and bring its last session back first (fabric-resume)
moveto <account> [<clone>] --wait    # "<account> - Enter to activate"; Enter does --resume
moveto <account> [<clone>] --watch   # …and show its status first (fabric-watch), until q
```

`exit` returns to the shell you came from.

`--wait`, `--resume` and `--watch` are Fleet Deck's three pane modes
(`docs/fleet-deck/tab-states.md`) and exclude one another: two of them
together exit 1. Each reaches `enter` as its fixed last argument, where the
deck reads it. `--wait` prints its one line **before** the refresh below,
so the refresh is as fresh as the Enter; Enter then does exactly
`--resume`, and input that ends first leaves a plain shell, said.
`fabric-resume` refuses (exit 3, one line) while any session is alive on
the account, or while another activation's launcher holds its
`resume.lock`, so an Enter never starts a second session. `--watch` runs
`fabric-watch`, read-only, after the refresh; `q` returns to the account's
shell.

Entering refreshes the account, best effort, before the shell opens: the
fabric checkout is fast-forwarded (`git -C ~/projects/agent-fabric pull
--ff-only origin main` — it is read-only for the account, so it can only be
behind), `bootstrap.sh` re-runs from it (hooks, agent files, skills, workspace
settings; idempotent), and `fabric-secrets sync --quiet` pulls the account's
own store into `~/.config/agent-fabric/secrets.env` so a rotated value
arrives too. Each step is capped (30/30/20 s); offline, what is there stands
and only a problem prints a line.

This is **host tooling, not part of the product.** It is installed to
`/usr/local` and is not delivered by a `git clone`; this directory is the
source, and `install.sh` is how it gets there.

## Install

```sh
sudo runtime/provisioning/moveto/install.sh
```

These land: `/usr/local/bin/moveto` (a shim since ADR-040 Wave 5), the
work it runs, `/usr/local/share/moveto/moveto.py`, on the fleet's pinned
Python, `/usr/local/share/moveto/enter`, `/usr/local/share/moveto/rc`, the
tab completion, and a manifest of what was installed,
`/usr/local/share/moveto/installed.sha256`. The copy under `/usr/local`
can drift from this directory, and `bin/fabric-status` says so on every
call — `moveto       drift: behind the repository: share/moveto/enter …`
when this directory moved on and the installer was not re-run, `edited
in place since install` when a copy differs from the manifest; `in sync`
otherwise (`tools/fabric/hosttools.py` is the check). Re-run the
installer after any change here.

## What it assumes

**The destination is the workspace, not a clone.** `~/projects` is where
`bootstrap.sh` writes the account's `CLAUDE.md` and hooks and where `claude`
is started; the session-start hook records whichever clone the session then
enters. Every account's clones are named after their projects, so a
clone named on the command line is the only way into one. An account with no
`~/projects` at all is reported as not provisioned rather than dropping you
in `$HOME`, because landing somewhere unexpected is worse than being told;
an empty `~/projects` is enterable (bootstrap may still have to run there).

**It goes one way.** On the Fedora/Qubes deployment (verified there,
2026-09-14) `sudo` is granted through the `qubes` group, and the role
accounts are not in it; on Debian it is the `sudo` group's, with the same
shape (`runtime/provisioning/platform/`). Either way an account that has
sudo can become a role account, and a role account can become nothing. `exit` is the way back,
which is why nothing here tries to be a two-way switch.

## What it gives you, and what it does not

On Fedora/Qubes `sudo` runs its PAM session stack — `/etc/pam.d/sudo`
includes `system-auth`, which carries `pam_systemd` — so a `moveto` shell
gets its own `/run/user/<uid>`, which is what rootless containers need.
Verified there by watching the directory appear for an account that had
none (2026-09-14); on Debian the stack is `common-session` and the same
result is expected but has not been read back on a live host. (`-H` only sets `HOME`; it
is not what creates the session.) What it does **not** give
you is persistence: that directory is removed when the account's last session
ends, so anything expected to outlive the shell needs
`sudo loginctl enable-linger <account>`, which
the deployment's provisioning runbook does when standing an
account up.

That document is the other half of this one: it covers creating a role account
and moving a session into it; this covers getting into one afterwards.

## The title

The title is the **role instance** — the account name — because that is what
names a session. The one exception is an account holding several clones, where
its own name cannot tell two sessions apart and the clone name is used instead;
once every session has its own account, that branch never fires.

Qubes prefixes window titles with the VM name, so the result reads like
`[develop-qzapp] architect-cto-01`. That prefix is the GUI daemon's, not ours.

## Three things that are easy to get wrong here

Each of these was a live defect during development, and each is invisible when
you get it wrong — which is why they are written down rather than left to the
code.

**`bash -c '…"$1"…' _ "$dir"` under `sudo -i` loses the path.** Two things
combine: `-c` consumes its first following argument as `$0`, and `sudo -i`
concatenates the command and its arguments into one string for the login shell
(`man sudo`), escaping everything except alphanumerics, underscores, hyphens
and — note — `$`. The original form hit both, and `cd` failed with `null
directory`. `enter` is a plain command with real arguments now, which is the
shape that works; the `$`-not-escaped part is the footgun worth remembering if
anything ever goes back through `-i`. Login processing (`PATH` from
`/etc/profile` and `~/.bash_profile`) comes from `-l` in `enter`'s own shebang.

**The entering shell is a file, not an inline `bash -lc '...'`.** The inline
form put the whole script — 156 characters of it — on the process command line,
and a terminal that titles from the running command showed *that* instead of
the session name.

**`PROMPT_COMMAND` already has a title write in it.** On Fedora `/etc/bashrc` rewrites
the title as `user@host:cwd` at every prompt, so a one-shot title is
overwritten within a second — `enter` sets the title before the first prompt
*and* `rc` re-sets it at each one.

On Fedora that variable is an **array** (Debian's `/etc/bash.bashrc` sets
no title write, and `rc` falls back to it when there is no `/etc/bashrc`):
`/etc/bashrc` does `declare -a
PROMPT_COMMAND` and sets element 0, then vte.sh and the systemd OSC-context
hook append further elements. A string append therefore reads and writes
element 0 only — it neither disturbs those hooks (a plain clobber would not
have either) nor runs after them. Ours lands inside element 0 and runs *before*
elements 1..n, which is harmless only because vte.sh deliberately leaves the
title alone in the array case. A `~/.bashrc` appending its own title hook as a
later element would win.

OSC 1 (tab) and OSC 2 (window) are set explicitly rather than OSC 0, which
means "both" and is honoured inconsistently.

## Tests

```sh
fabric-python tests/test_moveto_cli.py
```

Covers the resolution matrix through `--print`, which runs the whole resolution
path and stops before the exec. `getent` and `sudo` are mocked on `PATH`, so the
suite needs neither root nor the real accounts.

The fixture set includes an account whose single clone is named *differently*
from the account. That one exists because without it a mutant that always titles
by clone basename passes every other assertion — under the template layout the
account name and the clone name are the same string, so nothing can tell the two
rules apart. Both that mutation and "silently pick the first clone" were checked
to fail the suite.

## Tab completion

`install.sh` also installs `completion.bash` where bash-completion loads
it on first use (`<prefix>/share/bash-completion/completions/moveto`):
`moveto <TAB>` proposes the accounts the host registry places on this
host, read from the fabric checkout in the operator's workspace with no
sudo; `moveto <account> <TAB>` proposes that account's clones through
`moveto <account> --list`, plus `--print` and `--list`. When the
registry cannot be read the first word falls back to `moveto --list`.
The file is in the drift manifest like the other three.
