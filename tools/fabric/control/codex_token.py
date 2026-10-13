"""tools/fabric/control/codex_token.py — the coordinator's half of the Codex review's ChatGPT sign-in
(agent-fabric ADR-053 rule 8). The sign-in the engine runs on is the coordinator's, in ~/.codex-chatgpt; its refresh
token never leaves that home. Every other login gets the access token and the account id, and nothing else.

  fabric-accounts codex-token <login…|all> [--no-sync] [--force] [--refresh] [--home DIR]
        reads the sign-in (chatgpt_signin.read_signin: three values kept), writes ONLY the access token and the
        account id into each login's store (`fabric-secrets store codex-assign`, which holds the values inside its own
        process: none is in argv, a row, a log or a message), then each login applies it through its own daemon
        (`fabric-ctl <logins> secrets-sync`, a signed action; --no-sync leaves that to the login's next sync).
        --refresh refreshes the sign-in first when it has under 72 hours left. Human logins are refused: a human
        runs no review (ADR-044).

  the tick (`start`, agentd, on the host operator's account like the account switch): every TICK_S, and first
        FIRST_TICK_S after the daemon starts, when the sign-in has under REFRESH_BELOW_S left it is refreshed
        (`CODEX_HOME=<home> codex exec` once, ADR-053 rule 8 and review_gateway.py's header) and distributed to
        every placed agent; a fresh one is handed out again at the first tick and then once a day, and at the next tick
        after a distribution that did not reach every login (`codex-assign` answers "unchanged" for a login that has
        it, so a login placed later takes it within a day). A sign-in that is not there is not this account's business
        and is said once a day; a refresh that did not advance the expiry is said and nothing is distributed.

Exit: 0 done, 1 a login, the refresh or the sync failed, 2 usage or a refused request. Prints no token: a row names
a login, a status and the token's 12-hex fingerprint and expiry.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence

HERE = os.path.dirname(os.path.realpath(__file__))
FABRIC = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
import chatgpt_signin  # noqa: E402

DEFAULT_HOME = ".codex-chatgpt"
REFRESH_BELOW_S = 72 * 3600
CODEX_MIN_LIFE_S = 3600        # secretstore/accounts.py's floor: a token with less is not distributed
TICK_S = 6 * 3600
FIRST_TICK_S = 300
REFRESH_TIMEOUT_S = 300
STORE_TIMEOUT_S = 900
CTL_TIMEOUT_S = 1800
SAY_ABSENT_EVERY_S = 24 * 3600
# A fresh sign-in is still handed out again this often: `codex-assign` answers "unchanged" for a login that has it, so
# a login placed later, or one that missed the last distribution, takes it within a day.
CATCH_UP_EVERY_S = 24 * 3600
USAGE = ("usage: fabric-accounts codex-token <login…|all> [--no-sync] [--force] [--refresh] [--home DIR]")
PROMPT = "Reply with the single word ok."


def signin_home(env: dict[str, str], flag: str | None = None) -> str:
    return os.path.abspath(os.path.expanduser(flag)) if flag else os.path.join(env.get("HOME") or os.path.expanduser("~"), DEFAULT_HOME)


def codex_binary(env: dict[str, str]) -> str | None:
    return env.get("AGENT_FABRIC_CODEX_BIN") or shutil.which("codex", path=env.get("PATH"))


def life(home: str, now: float | None = None) -> tuple[float | None, str | None]:
    """(seconds of life left in the sign-in's access token, why it cannot be read): one of the two is None."""
    try:
        _access, _account, exp = chatgpt_signin.read_signin(home)
    except chatgpt_signin.Refused as e:
        return None, str(e)
    return exp - (time.time() if now is None else now), None


def refresh(home: str, env: dict[str, str], run: Callable[..., Any] = subprocess.run) -> str | None:
    """Run Codex once in the sign-in's home, which renews the tokens as a side effect; None when it ran, else why not.
    A minimal environment (the sign-in's home, the path, nothing of the session), an argument list, a timeout and a
    scratch directory to run in; the output is not kept, since a failing Codex may print what it read."""
    binary = codex_binary(env)
    if not binary:
        return "no `codex` on PATH (AGENT_FABRIC_CODEX_BIN names one); the sign-in cannot be refreshed here"
    clean = {"CODEX_HOME": home, "HOME": env.get("HOME") or os.path.expanduser("~"), "PATH": env.get("PATH") or "/usr/bin:/bin",
             "LANG": "C.UTF-8"}
    with tempfile.TemporaryDirectory(prefix="codex-refresh.") as scratch:
        try:
            r = run([binary, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", PROMPT], cwd=scratch, env=clean,
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=REFRESH_TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            return f"`codex exec` did not finish within {REFRESH_TIMEOUT_S} s"
        except OSError as e:
            return f"`codex exec` could not run ({e.strerror or e})"
    return None if r.returncode == 0 else f"`codex exec` exited {r.returncode}"


def _store_assign(logins: Sequence[str], home: str, force: bool, run: Callable[..., Any], root: str) -> list[dict]:
    cmd = [os.path.join(root, "bin", "fabric-secrets"), "store", "codex-assign", *logins, "--home", home, "--json", *(["--force"] if force else [])]
    try:
        r = run(cmd, capture_output=True, timeout=STORE_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [{"login": lg, "status": "failed", "reason": f"fabric-secrets: {type(e).__name__}"} for lg in logins]
    try:
        rows = json.loads(r.stdout.decode("utf-8", "replace"))
        if isinstance(rows, list) and all(isinstance(x, dict) for x in rows):
            return rows
    except ValueError:
        pass
    # A refusal before any row (no sign-in, a token with too little life): the last line says why, and never a value.
    why = (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["fabric-secrets store codex-assign failed"])[-1][:200]
    return [{"login": lg, "status": "failed", "reason": why} for lg in logins]


def distribute(logins: Sequence[str], home: str, *, force: bool = False, sync: bool = True, root: str,
               env: dict[str, str], run: Callable[..., Any] = subprocess.run, spawn: Callable[..., Any] = subprocess.run,
               say: Callable[[str], None] = lambda m: print(m, file=sys.stderr), out: Callable[[str], None] = print) -> int:
    """The store half, then the sync half; 0 when every login was reached and applied it."""
    rows = _store_assign(logins, home, force, run, root)
    for r in rows:
        out(f"{r['login']:<22} {r['status']}{('  ' + str(r['reason'])) if r.get('reason') else ''}"
            f"{('  token ' + r['token_sha256_12']) if r.get('token_sha256_12') else ''}")
    bad = any(r.get("status") not in ("written", "unchanged") for r in rows)
    reached = [r["login"] for r in rows if r.get("status") in ("written", "unchanged")]
    if not sync or not reached:
        if not sync and any(r.get("status") == "written" for r in rows):
            say("fabric-accounts: --no-sync: each changed login applies it at its next fabric-secrets sync")
        return 1 if bad else 0
    # The unchanged ones too: the store says nothing of what the account last synced.
    cmd = [os.path.join(root, "bin", "fabric-ctl"), *reached, "secrets-sync"]
    try:
        r = spawn(cmd, env=env, timeout=CTL_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        say(f"fabric-accounts: fabric-ctl secrets-sync: {type(e).__name__}")
        return 1
    return 1 if bad or r.returncode != 0 else 0


def main(argv: Sequence[str], *, env: dict[str, str], root: str, agents: Callable[[], tuple[list[str], list[str]]],
         run: Callable[..., Any] = subprocess.run, spawn: Callable[..., Any] = subprocess.run,
         say: Callable[[str], None] = lambda m: print(m, file=sys.stderr), out: Callable[[str], None] = print) -> int:
    """`fabric-accounts codex-token …` (argv after the verb). `agents()` gives (placed agent logins, human logins)."""
    args = list(argv)
    flags = {"--no-sync": False, "--force": False, "--refresh": False}
    home_flag = None
    rest: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in flags:
            flags[a] = True
        elif a == "--home" and i + 1 < len(args):
            home_flag = args[i + 1]
            i += 1
        elif a.startswith("-"):
            say(USAGE)
            return 2
        else:
            rest.append(a)
        i += 1
    if not rest:
        say(USAGE)
        return 2
    placed, humans = agents()
    logins = placed if rest == ["all"] else rest
    h = [lg for lg in logins if lg in humans]
    if h:
        say(f"fabric-accounts: a human login runs no review (ADR-044): {', '.join(h)}")
        return 2
    unknown = [lg for lg in logins if lg not in placed]
    if unknown:
        say(f"fabric-accounts: not a placed account (runtime/hosts/registry.json): {', '.join(unknown)}")
        return 2
    home = signin_home(env, home_flag)
    if flags["--refresh"]:
        left, why = life(home)
        if left is not None and left < REFRESH_BELOW_S:
            problem = refresh(home, env, run)
            if problem:
                say(f"fabric-accounts: {problem}")
                return 1
            after, why = life(home)
            if after is None or after <= left:
                say("fabric-accounts: the refresh did not advance the sign-in's expiry; nothing distributed")
                return 1
    return distribute(logins, home, force=flags["--force"], sync=not flags["--no-sync"], root=root, env=env, run=run,
                      spawn=spawn, say=say, out=out)


class Tick:
    """The refresh-and-distribute timer's body, one object so a test holds its clock, its Codex and its distribution."""

    def __init__(self, *, env: dict[str, str], root: str, agents: Callable[[], list[str]], log: Callable[[str], None],
                 run: Callable[..., Any] = subprocess.run, spawn: Callable[..., Any] = subprocess.run,
                 clock: Callable[[], float] = time.time):
        self.env, self.root, self.agents, self.log, self.run, self.spawn, self.clock = env, root, agents, log, run, spawn, clock
        self.absent_said = 0.0
        self.distributed_at = 0.0
        self.pending = False       # the last distribution did not reach every login

    def __call__(self) -> str:
        """What this tick did, as one word, for a test: absent, fresh, refused, unchanged-expiry, distributed, failed.
        A fresh sign-in is handed out again at the first tick and then once a day (CATCH_UP_EVERY_S), and at the next
        tick after a distribution that did not reach every login."""
        home = signin_home(self.env)
        left, why = life(home, self.clock())
        if left is None:
            if self.clock() - self.absent_said >= SAY_ABSENT_EVERY_S:
                self.absent_said = self.clock()
                self.log(f"agentd: codex sign-in: {why}")
            return "absent"
        due = self.pending or self.clock() - self.distributed_at >= CATCH_UP_EVERY_S
        if left >= REFRESH_BELOW_S:
            return self.hand_out("handed again to") if due else "fresh"
        problem = refresh(home, self.env, self.run)
        if problem:
            self.log(f"agentd: codex sign-in has {int(left // 3600)} h left and could not be refreshed: {problem}")
            return self.stale_hand_out(due, left, "refused")
        after, why = life(home, self.clock())
        if after is None or after <= left:
            self.log("agentd: codex sign-in: the refresh did not advance the expiry; nothing new to distribute")
            return self.stale_hand_out(due, left, "unchanged-expiry")
        return self.hand_out(f"refreshed ({int(after // 3600)} h) and handed to")

    def stale_hand_out(self, due: bool, left: float, outcome: str) -> str:
        """The refresh gave nothing new, but a login that missed the last distribution (or was placed since) still gets
        the sign-in there is, while it has enough life for a review (the store's own floor); the tick's word stays
        the refresh's."""
        if due and left >= CODEX_MIN_LIFE_S:
            self.hand_out("handed again, unrefreshed, to")
        return outcome

    def hand_out(self, what: str) -> str:
        """Distribute the sign-in to every placed agent; a failure leaves `pending` for the next tick."""
        home = signin_home(self.env)
        logins = self.agents()
        self.distributed_at = self.clock()     # an attempt: the daily catch-up counts from it, a failure retries by `pending`
        if distribute(logins, home, root=self.root, env=self.env, run=self.run, spawn=self.spawn,
                      say=lambda m: self.log(f"agentd: {m}"), out=lambda m: None) != 0:
            self.pending = True
            self.log("agentd: codex sign-in: not every login took it, tried again at the next tick (fabric-accounts codex-token all says which)")
            return "failed"
        self.pending = False
        self.log(f"agentd: codex sign-in {what} {len(logins)} login(s)")
        return "distributed"


def start(ticker: Callable[..., Any], log: Callable[[str], None], *, agents: Callable[[], list[str]],
          env: dict[str, str] | None = None, root: str | None = None) -> None:
    """agentd's timer, on the host operator's account."""
    tick = Tick(env=dict(os.environ) if env is None else env, root=root or os.environ.get("AGENT_FABRIC_ROOT") or FABRIC,
                agents=agents, log=log)
    ticker("codex sign-in", tick, TICK_S, first_s=FIRST_TICK_S).start()
