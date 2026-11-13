"""tools/fabric/provisioning/carrier_step.py — steps 7c-7e of a new-agent run: a new
login's way onto the channel without the relay (agent-fabric ADR-064; the
relay-free cutover's W14).

  7c  the pinned carrier release installed, as the account (account_carrier.py install)
  7d  the account's roster row: valid already (a re-run after the coordinator
      countersigned it) or written out for the coordinator and the run left open
  7e  the account's control agent and carrier units started (account_carrier.py start)

What the relay used to do for a new account — move its inbox cursor to the
channel's newest message (relay_catchup.py) and import its history through
the relay at bootstrap — is nothing here: a carrier delivers what arrives
after it starts, so there is no backlog to skip and nothing to read through
a relay that may be stopped. (Steps 7c-7e and 5 read no relay, and the tests pin that; bootstrap's journal import,
step 7, still does, best effort: it says one "!" line without one.)

THE ROW is the one step that is not the account's to finish: the account mints
its key and signs its own row (`gzcoord-carrier roster-row`), and the
coordinator picks the port and countersigns it (`roster-admit`, ADR-064 rule 2).
This module never signs for the coordinator. It writes the row where the
operator can read it (on the host the account is placed on, which it names), says the command, and the run ends with
status 3 (open) after everything else ran: the re-run, once the roster on origin/main holds the row, finds it valid
and starts the units. Status 3 is "open" for either cause: the row, or no user manager yet to start the units in
(`loginctl enable-linger`); the re-run starts them in both. `roster-row` itself refuses (exit 2) until the account's
key is on origin/main, which a first run of a new login has not got yet (step 5 only says to commit it): that
too is open, with the refusal's own words, never a failed run.

Each function returns the lines that leave the run open, [] when done; a step
that fails dies (steps are idempotent, a re-run converges).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess

import roots

OPEN_EXIT = 3        # the worker's and new-agent's status for "every step ran; something is left for another login or a re-run"
UNIT = "agent-fabric-agentd"
ROW_DIR_MODE = 0o755
ROW_MODE = 0o644      # the row holds a public PeerId and signatures; the coordinator's login must read it


def _tail(text: str | None, n: int = 5) -> list[str]:
    return [ln for ln in (text or "").splitlines() if ln.strip()][-n:]


def uid_of(login: str) -> int:   # -1: unknown
    """Through getent, as the worker finds the home: the account may live in a directory the Python pwd module reads
    differently from the tools the rest of the run asks. A login getent does not know is a refusal at the caller, not a guess."""
    got = subprocess.run(["getent", "passwd", login], capture_output=True, text=True, timeout=30, check=False)
    fields = got.stdout.strip().split(":")
    if got.returncode != 0 or len(fields) < 3 or not fields[2].isdigit():
        return -1
    return int(fields[2])


def manager_env(w) -> list[str]:
    """The account's user manager, which `sudo -u` + `env -i` does not reach: the same variables a login session has."""
    # AGENT_FABRIC_RUN_USER: where the host keeps user runtime directories, a test's own tree instead of /run/user.
    uid = uid_of(w.a.login)
    if uid < 0:
        w.die(f"step failed: the uid of {w.a.login} could not be read (getent passwd); nothing after it ran")
    run = f"{w.env.get('AGENT_FABRIC_RUN_USER') or '/run/user'}/{uid}"
    return [f"XDG_RUNTIME_DIR={run}", f"DBUS_SESSION_BUS_ADDRESS=unix:path={run}/bus"]


def host_name() -> str:
    return socket.gethostname().split(".")[0]


def install(w, env: list[str] | None = None) -> None:
    script = roots.account_clone(w.home, "tools", "fabric", "provisioning", "account_carrier.py")
    if w.a.dry:
        w.say(f"would: as {w.a.login}: account_carrier.py install")
        return
    # The account's user manager is reached, so a release replaced under running units restarts them, as when agentd
    # runs the same install; without it the units are invisible, run on the old programs, and 7e finds them replaced.
    got = w.as_login([w.py, "-I", script, "install"], env=env, login_shell=False)
    if got.returncode != 0:
        for ln in _tail(got.stdout):
            w.say(f"   {ln}")
        w.die(f"step failed: the carrier release for {w.a.login} (account_carrier.py install); nothing after it ran")
    w.say("7c. carrier release " + ("already installed" if '"status": "current"' in (got.stdout or "") else "installed"))


def row_file(w) -> str:
    base = w.env.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "agent-fabric", "new-agent", f"roster-row-{w.a.login}.json")


def roster_row(w) -> list[str]:
    """7d. The account's row valid in its own clone's roster (render-config refuses otherwise), or the row written out."""
    login = w.a.login
    carrier = roots.account_clone(w.home, "bin", "gzcoord-carrier")
    if w.a.dry:
        w.say(f"would: as {login}: gzcoord-carrier render-config (is its roster row valid?), else roster-row")
        return []
    if w.as_login([carrier, "render-config"], login_shell=False).returncode == 0:
        w.say("7d. roster row valid")
        return []
    got = w.as_login([carrier, "roster-row"], login_shell=False, stderr=subprocess.PIPE)   # stdout is the JSON
    if got.returncode == 2:
        # The carrier's own refusal, in its words (usually: the account's key is not on origin/main yet, and step 5 only
        # said to commit it): the run is left open with the order that fixes it, not failed, since every step after
        # this one is independent of it. Any other status is a crash or an unreachable command, which stays a failure.
        why = _tail(got.stderr, 1)
        return [f"gzcoord-carrier roster-row refused for {login}: {why[0] if why else 'no reason given'}; once identities/keys/ "
                "is merged to origin/main, re-run this command, which writes the row for the coordinator; the carrier is not started"]
    try:
        row = json.loads(got.stdout) if got.returncode == 0 else None
    except ValueError:
        row = None
    if not isinstance(row, dict):
        for ln in _tail(got.stderr):
            w.say(f"   {ln}")
        w.die(f"step failed: gzcoord-carrier roster-row as {login} (exit {got.returncode}); nothing after it ran")
    path = row_file(w)
    os.makedirs(os.path.dirname(path), mode=ROW_DIR_MODE, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, ROW_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(row, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.chmod(path, ROW_MODE)
    w.say(f"7d. roster row of {login} written to {path} on {host_name()}")
    return [f"roster row of {login} needs the coordinator's countersignature: the row is {path} on {host_name()}; as fabric-coordinator, "
            f"gzcoord-carrier roster-admit {path} --port <free port in the roster's range>, merge the roster, "
            "then re-run this command; the carrier is not started"]


def start(w, env: list[str] | None = None) -> list[str]:
    """7e. The control agent and the carrier's two units, in the account's user manager."""
    login = w.a.login
    if w.a.dry:
        w.say(f"would: as {login}: systemctl --user enable --now {UNIT}; account_carrier.py start")
        return []
    env = env or manager_env(w)
    run_dir = env[0].split("=", 1)[1]
    if not w.sudo_test("-S", f"{run_dir}/bus"):
        return [f"{login} has no user manager at {run_dir}/bus (loginctl enable-linger {login}): the control agent and the "
                "carrier are installed, not started"]
    got = w.as_login(["systemctl", "--user", "enable", "--now", UNIT + ".service"], env=env, login_shell=False)
    if got.returncode != 0:
        for ln in _tail(got.stdout):
            w.say(f"   {ln}")
        w.die(f"step failed: systemctl --user enable --now {UNIT} as {login}; nothing after it ran")
    script = roots.account_clone(w.home, "tools", "fabric", "provisioning", "account_carrier.py")
    got = w.as_login([w.py, "-I", script, "start"], env=env, login_shell=False)
    if got.returncode != 0:
        for ln in _tail(got.stdout):
            w.say(f"   {ln}")
        w.die(f"step failed: the carrier's units for {login} (account_carrier.py start); nothing after it ran")
    w.say(f"7e. {UNIT} and the carrier's units started")
    return []


def carrier_steps(w) -> list[str]:
    env = None if w.a.dry else manager_env(w)       # a dry run asks no host
    install(w, env)
    open_ = roster_row(w)
    return open_ or start(w, env)
