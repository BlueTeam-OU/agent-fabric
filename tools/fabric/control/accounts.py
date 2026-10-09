"""tools/fabric/control/accounts.py — the Claude accounts this login observes
(ops `accounts`; ADR-031). Run as the observing login, in practice the
coordinator's. The port of runtime/control/accounts.mjs (ADR-040 Wave 8). Run from tools/fabric as
`python3 -m control.accounts`, which bin/fabric-accounts will run at the
cutover; until then the shim still runs the Node.

  fabric-accounts login <account>   sign one Claude account in, once: opens the harness
                                    in that account's own config directory; /login in the
                                    browser AS THAT ACCOUNT, then /exit. A real terminal.
  fabric-accounts list              each observed account: signed in, email, sign-in expiry
  fabric-accounts read              read every account's windows now (the harness's /usage)
  fabric-accounts assign <login…|all> <account> [--no-restart] [--no-sync] [--force]
                                    which Claude account those logins run on: the template's token,
                                    from the coordinator's store (ADR-038), written into each
                                    login's store; then `fabric-ctl <logins> secrets-sync
                                    --expect <template's fingerprint> --restart` — every account
                                    applies it, proves it, and resumes a running session on it
  fabric-accounts templates         each template's token fingerprint in the coordinator's store,
                                    to name the account behind a login's `setup-token <sha>`
                                    (fabric-ctl, fabric-status)

Prints no token: a sign-in is described by its email, its expiry and whether
a refresh token is held — never by a value.

Exit: 0 done, 1 a row, account or step failed, 2 usage or a refused request.
`placements` is control/ctl.py's (python-dev-03): rows with `login` and `kind`
("agent" or "human"), reached through ctl() so this module imports without it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any, Callable, Sequence

from control.ops import util
from control.ops.usage import ACCOUNT_SLUG, account_slugs, accounts, accounts_dir, claude_bin, take_read_lock

USAGE = """usage: fabric-accounts login <account> | list | read | templates | assign <login…|all> <account> [--no-restart] [--no-sync] [--force]
  <account>: lowercase letters, digits and hyphens — the account's email with @ and . as -,
             e.g. claude-pzhuy-8alias-com (the template's name: CLAUDE_ACCOUNT_<ACCOUNT> in the
             coordinator's store)"""

# assign: four git round trips a login.
STORE_TIMEOUT_S = 900
# fabric-ctl waits for each account's signed action, a restart's stop included.
CTL_TIMEOUT_S = 1800
_CODE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
_SCRUBBED = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")


def fabric_root(env: dict[str, str] | None = None) -> str:
    return (os.environ if env is None else env).get("AGENT_FABRIC_ROOT") or _CODE_ROOT


def ctl() -> Any:
    from control import ctl as module   # python-dev-03's port
    return module


def _js_number(v: Any) -> float:
    """Number(v) for what a credentials file can hold; nan where the Node read NaN."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except OverflowError:
            return float("inf") if v > 0 else float("-inf")   # an integer past a double, as JSON.parse read it
    if isinstance(v, str):
        try:
            return float(v.strip()) if v.strip() else 0.0
        except ValueError:
            return float("nan")
    return float("nan")


def describe(directory: str, now_ms: float | None = None) -> dict:
    """What a config directory holds, in words: no token leaves this function."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    creds = util.read_json(os.path.join(directory, ".credentials.json"))
    oauth = creds.get("claudeAiOauth") if isinstance(creds, dict) else None
    oauth = oauth if isinstance(oauth, dict) else {}
    claude = util.read_json(os.path.join(directory, ".claude.json"))
    profile = claude.get("oauthAccount") if isinstance(claude, dict) else None
    profile = profile if isinstance(profile, dict) else {}
    exp = _js_number(oauth["expiresAt"]) if "expiresAt" in oauth else float("nan")
    finite = exp == exp and exp not in (float("inf"), float("-inf"))
    try:
        expires_at = util.iso_ms(exp) if finite else None
    except (ValueError, OverflowError, OSError):
        expires_at = None   # a date past what a Date holds: unknown, not a crash
    return {
        "slug": os.path.basename(directory),
        "email": profile.get("emailAddress"),
        "signed_in": util.truthy(oauth.get("accessToken")),
        "refresh_token": util.truthy(oauth.get("refreshToken")),
        "expires_at": expires_at,
        "expired": (exp <= now_ms) if expires_at is not None else None,
    }


def list_lines(directory: str, now_ms: float | None = None) -> list[str]:
    slugs = account_slugs(directory)
    if not slugs:
        return [f"no Claude account observed under {directory} — fabric-accounts login <account>"]
    lines = []
    for s in slugs:
        d = describe(os.path.join(directory, s), now_ms)
        if not d["signed_in"]:
            state = "not signed in"
        elif not d["refresh_token"]:
            state = "signed in, NO refresh token (will lapse)"
        elif d["expired"]:
            state = f"sign-in lapsed at {d['expires_at']} (the next read renews it)"
        else:
            state = f"signed in until {d['expires_at']}"
        lines.append(f"{s:<34} {(d['email'] or '-'):<34} {state}")
    return lines


# The templates live in the coordinator's store, as CLAUDE_ACCOUNT_<SLUG>
# entries, and an assignment is the coordinator writing the token into each
# login's store (it cannot read it back): fabric-secrets store templates and
# assign, which keep every value inside that process (ADR-038, ADR-031).
def _store(args: list[str], run: Callable[..., Any], root: str) -> Any:
    r = run([os.path.join(root, "bin", "fabric-secrets"), "store", *args, "--json"],
            capture_output=True, timeout=STORE_TIMEOUT_S, check=True, stdin=subprocess.DEVNULL)
    return util.loads(util.decode(r.stdout))


def store_templates(run: Callable[..., Any] = subprocess.run, root: str | None = None) -> list[dict]:
    return _store(["templates"], run, root or fabric_root())


def store_assign(logins: Sequence[str], account: str, run: Callable[..., Any] = subprocess.run,
                 force: bool = False, root: str | None = None) -> list[dict]:
    try:
        return _store(["assign", account, *logins, *(["--force"] if force else [])], run, root or fabric_root())
    except subprocess.CalledProcessError as e:
        # assign exits 1 when a row failed and still prints every row.
        try:
            return util.loads(util.decode(e.stdout))
        except ValueError:
            reason = (util.decode(e.stderr).strip().split("\n") or [""])[-1][:160]
            return [{"login": login, "status": "failed", "reason": reason} for login in logins]
    except (OSError, subprocess.TimeoutExpired) as e:
        return [{"login": login, "status": "failed", "reason": util.node_error(e, ["fabric-secrets"])[:160]} for login in logins]


def _say(msg: str) -> None:
    print(msg, file=sys.stderr)


def main(argv: Sequence[str] | None = None, *, home: str | None = None, env: dict[str, str] | None = None,
         stdin_tty: bool | None = None, spawn: Callable[..., Any] = subprocess.run,
         read: Callable[..., dict] = accounts, run: Callable[..., Any] = subprocess.run,
         registry: Any = None, placements: Callable[[Any], list[dict]] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    home = os.path.expanduser("~") if home is None else home
    env = dict(os.environ) if env is None else env
    stdin_tty = sys.stdin.isatty() if stdin_tty is None else stdin_tty
    cmd = argv[0] if argv else None
    arg = argv[1] if len(argv) > 1 else None
    directory = accounts_dir(home, env)
    root = fabric_root(env)
    if cmd == "list" and len(argv) == 1:
        print("\n".join(list_lines(directory)))
        return 0
    if cmd == "assign":
        flags = ("--no-sync", "--no-restart", "--force")
        no_sync, no_restart, force = (f in argv for f in flags)
        rest = [a for a in argv[1:] if a not in flags]
        if len(rest) < 2:
            _say(USAGE)
            return 2
        account, who = rest[-1], rest[:-1]
        # A human login has no Claude account (ADR-044 §5 rule 2): never assigned one.
        everyone = (placements or ctl().placements)(registry)
        placed = [p["login"] for p in everyone if p["kind"] == "agent"]
        logins = placed if who == ["all"] else who
        humans = [lg for lg in logins if any(p["login"] == lg and p["kind"] == "human" for p in everyone)]
        if humans:
            _say(f"fabric-accounts: a human login has no Claude account (ADR-044): {', '.join(humans)}")
            return 2
        unknown = [lg for lg in logins if lg not in placed]
        if unknown:
            _say(f"fabric-accounts: not a placed account (runtime/hosts/registry.json): {', '.join(unknown)}")
            return 2
        # No way back to a login's own /login: the launcher refuses a session
        # without a template's long-lived token (runtime/openrouter/launch).
        t = next((x for x in store_templates(run, root) if x["account"] == account), None)
        if t is None:
            hint = " — a login runs only on a template's token; assign it another account" if account in ("own", "none") else ""
            _say(f"fabric-accounts: {json.dumps(account)} is not a template in this store (fabric-accounts templates){hint}")
            return 2
        if not t.get("token_sha256_12"):
            _say(f"fabric-accounts: template {account} holds no CLAUDE_CODE_OAUTH_TOKEN yet; nothing written")
            return 2
        rows = store_assign(logins, account, run, force, root)
        for r in rows:
            reason = f"  {r['reason']}" if r.get("reason") else ""
            print(f"{r['login']:<22} {str(r.get('from') if r.get('from') is not None else '-'):<30} → "
                  f"{str(r.get('to') if r.get('to') is not None else '-'):<30} {r['status']}{reason}")
        bad = any(r["status"] not in ("written", "unchanged") for r in rows)
        changed = [r["login"] for r in rows if r["status"] == "written"]
        reached = [r["login"] for r in rows if r["status"] in ("written", "unchanged")]
        if no_sync or not reached:
            if changed:
                _say("fabric-accounts: --no-sync — each changed login applies it at its next fabric-secrets sync")
            return 1 if bad else 0
        # Every named login applies it now through its own daemon (a signed
        # action) — the unchanged ones too, since the store says nothing of what
        # the account last synced — and proves it against the template's
        # fingerprint; a running session is resumed on it.
        cmd_ = [os.path.join(root, "bin", "fabric-ctl"), *reached, "secrets-sync", "--expect", t["token_sha256_12"],
                *([] if no_restart else ["--restart"])]
        try:
            r = spawn(cmd_, env=env, timeout=CTL_TIMEOUT_S, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            _say(f"fabric-accounts: {util.node_error(e, cmd_)}")
            return 1
        return 1 if bad or r.returncode != 0 else 0
    if cmd == "templates" and len(argv) == 1:
        ts = store_templates(run, root)
        if not ts:
            print("no template in this store (fabric-secrets store template-set <slug>)")
            return 1
        for x in ts:
            print(f"{x['account']:<34} {'setup-token ' + x['token_sha256_12'] if x.get('token_sha256_12') else 'no CLAUDE_CODE_OAUTH_TOKEN'}")
        return 0 if all(x.get("token_sha256_12") for x in ts) else 1
    if cmd == "read" and len(argv) == 1:
        r = read(home, directory=directory)
        if r["status"] == "none":
            print("\n".join(list_lines(directory)))
            return 1
        for a in r["accounts"]:
            m = "; ".join(f"{lim['kind']} {lim['percent'] if lim.get('percent') is not None else '-'}%"
                          f"{' (' + lim['model'] + ')' if lim.get('model') else ''} resets {str(lim.get('resets_at') or '-')[:16]}"
                          for lim in (a.get("limits") or []))
            print(f"{(a.get('email') or a['slug']):<34} {a['status']}{'  ' + m if m else ''}{'  ' + a['error'] if a.get('error') else ''}")
        return 0 if all(a["status"] == "ok" for a in r["accounts"]) else 1
    if cmd == "login" and len(argv) == 2:
        assert arg is not None
        if not ACCOUNT_SLUG.fullmatch(arg):
            _say(f"fabric-accounts: {json.dumps(arg)} is not an account name\n{USAGE}")
            return 2
        if not stdin_tty:
            _say("fabric-accounts: login opens the harness for /login in a browser — run it in a real terminal, not through a tool or `!`")
            return 2
        target = os.path.join(directory, arg)
        os.makedirs(target, mode=0o700, exist_ok=True)
        os.chmod(target, 0o700)
        # The same lock the reads take: a keeper read overlapping a /login would
        # be two harnesses on one config directory.
        release = take_read_lock(target)
        if release is None:
            _say(f"fabric-accounts: {arg} is being read right now (the daemon's keeper); try again in a minute")
            return 1
        _say(f"fabric-accounts: {arg} — in the harness that opens now: /login, approve in the browser SIGNED IN AS THAT ACCOUNT, then /exit")
        # The same clean environment the reads use: an inherited token would
        # make the harness think it is already signed in, as someone else.
        clean = {k: v for k, v in env.items() if k not in _SCRUBBED}
        try:
            # No timeout: a person is typing in this harness, and /exit ends it.
            r = spawn([claude_bin(home)], cwd=target, env={**clean, "CLAUDE_CONFIG_DIR": target}, check=False)
        finally:
            release()
        d = describe(target)
        if d["signed_in"]:
            tail = "" if d["refresh_token"] else " — but with no refresh token; it will lapse"
            _say(f"fabric-accounts: {arg} signed in as {d['email'] or '(email not yet recorded)'}{tail}")
        else:
            _say(f"fabric-accounts: {arg} is not signed in (no /login completed)")
        return 0 if d["signed_in"] and r.returncode == 0 else 1
    _say(USAGE)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — a person gets the one line the Node printed, not a traceback
        _say(f"fabric-accounts: {e}")
        sys.exit(1)
