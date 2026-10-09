"""tools/fabric/control/ops/usage.py — the Claude account's usage windows, the Claude accounts this login observes, and the tokens its own sessions spent.
A part of the ops package, whose __init__.py is the contract every
extractor here keeps."""
from __future__ import annotations

import errno
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from . import util
from gzcoord import gzmsg, jsvalues as js  # noqa: E402 — util puts tools/fabric on sys.path
from gzcoord.inbox_parts.tokens import synced_var  # noqa: E402

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
HTTP_TIMEOUT_S = 15

# A login on a template runs on its setup-token, which cannot read the
# usage endpoint (HTTP 403, user:inference only) — but every inference
# reply carries the account's windows in anthropic-ratelimit-unified-*
# headers (docs/live-checks/2026-10-08-usage-from-inference-headers.md).
# So the windows are read from one reply: the smallest model, one output
# token, against the account's own allowance. The model is a pinned id,
# not routing's: the probe must answer the same way whatever a class rides.
PROBE_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class Response:
    """What an HTTP exchange answered: any status, 3xx and 4xx included.
    headers are looked up lower-cased."""
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status <= 299


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_a, **_k):  # noqa: ANN002 — the stdlib's signature
        return None   # a 3xx is then an answer that is not 2xx


# The token goes to api.anthropic.com and nowhere else: urllib, unlike the
# Node's fetch, would go through http_proxy/https_proxy from the
# environment and follow a redirect with the Authorization header to
# whatever host it names. A redirect is a failed read here.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def http_fetch(url: str, method: str = "GET", headers: Mapping[str, str] | None = None, body: bytes | None = None,
               timeout: float = HTTP_TIMEOUT_S) -> Response:
    """One exchange. Raises OSError (URLError, a timeout) when there is no
    answer, and ValueError for a header http.client refuses — a value with
    a line break; neither message is ever put in a reply, since the
    header's would quote the token."""
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        with e:
            return Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read())


Fetch = Callable[..., Response]


def windows_from_headers(get: Callable[[str], Any]) -> dict:
    """The headers give a fraction and epoch seconds; the windows are reported
    as the usage endpoint reports them, a percentage and an ISO time."""
    def num(h: str) -> float:
        # Number(null) is 0: an absent header must stay absent, never a reading of 0%.
        v = get(h)
        return js.number(v) if isinstance(v, str) and gzmsg.js_trim(v) != "" else float("nan")

    def finite(x: float) -> bool:
        return x == x and x not in (float("inf"), float("-inf"))

    def win(k: str) -> dict | None:
        u = num(f"anthropic-ratelimit-unified-{k}-utilization")
        r = num(f"anthropic-ratelimit-unified-{k}-reset")
        status = get(f"anthropic-ratelimit-unified-{k}-status")
        if not finite(u) and not finite(r):
            return None
        out: dict[str, Any] = {"utilization": util.whole(util.js_round(u * 1000) / 10) if finite(u) else None,
                               "resets_at": util.iso_ms(r * 1000) if finite(r) and r > 0 else None}
        if isinstance(status, str) and re.fullmatch(r"[a-z_]{1,32}", status):
            out["status"] = status
        return out
    return {"five_hour": win("5h"), "seven_day": win("7d")}


def _from_inference(tok: str, fetch: Fetch, url: str) -> dict:
    try:
        r = fetch(url, method="POST", timeout=HTTP_TIMEOUT_S,
                  headers={"Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20",
                           "anthropic-version": "2023-06-01", "content-type": "application/json"},
                  body=json.dumps({"model": PROBE_MODEL, "max_tokens": 1,
                                   "messages": [{"role": "user", "content": "."}]}, separators=(",", ":")).encode())
    except (OSError, ValueError):
        return {"status": "read-failed", "via": "setup-token"}
    # A full window answers 429 and still names its windows: that is a reading.
    w = windows_from_headers(lambda k: r.headers.get(k))
    if not w["five_hour"] and not w["seven_day"]:
        return {"status": "read-failed", "via": "setup-token", "http": r.status}
    return {"status": "ok", "via": "setup-token", **w, "subscription": None}


def usage(home: str | None = None, fetch: Fetch = http_fetch, url: str = USAGE_URL, messages_url: str = MESSAGES_URL) -> dict:
    """The five-hour and seven-day windows, read with the account's own OAuth
    token, which goes into one header and nowhere else."""
    home = os.path.expanduser("~") if home is None else home
    setup = synced_var("CLAUDE_CODE_OAUTH_TOKEN", home)
    if setup:
        return _from_inference(setup, fetch, messages_url)
    creds = util.read_json(os.path.join(home, ".claude", ".credentials.json"))
    oauth = js.get(creds, "claudeAiOauth")
    tok = js.get(oauth, "accessToken")
    if not util.truthy(tok):
        return {"status": "no-credentials"}
    try:
        r = fetch(url, headers={"Authorization": f"Bearer {js.string(tok)}", "anthropic-beta": "oauth-2025-04-20"},
                  timeout=HTTP_TIMEOUT_S)
    except (OSError, ValueError):
        return {"status": "read-failed"}
    if not r.ok:
        return {"status": "read-failed", "http": r.status}
    try:
        u = json.loads(r.body)
    except ValueError:
        return {"status": "unreadable"}

    def win(w: Any) -> dict | None:
        if not isinstance(w, (dict, list)):
            return None
        return {"utilization": None if js.nullish(js.get(w, "utilization")) else w["utilization"],
                "resets_at": None if js.nullish(js.get(w, "resets_at")) else w["resets_at"]}
    sub = js.get(oauth, "subscriptionType")
    return {"status": "ok", "five_hour": win(js.get(u, "five_hour")), "seven_day": win(js.get(u, "seven_day")),
            "subscription": None if js.nullish(sub) else sub}


# THE CLAUDE ACCOUNTS this login observes: one Claude Code config
# directory per Claude account under accounts_dir(), each signed in once
# with /login and held by this observer alone — a refresh token has one
# holder, or the first refresh signs the others out. The fleet's working
# sessions run on each account's one-year setup-token, which is
# `user:inference` only: the usage endpoint refuses it, and usage() above
# reads its five-hour and seven-day windows from the headers of an
# inference call it pays for. A sign-in here reads the account's whole
# report, the per-model weekly meter included, with no model call
# (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md).
#
# The read is the harness's own `/usage`, run headless: no model call
# (0 turns, $0), and it renews an expired 8-hour sign-in the official way
# — measured 2026-09-24 on 2.1.281 (docs/live-checks/2026-09-24-claude-
# accounts.md). Reimplementing the OAuth refresh here was the rejected
# alternative: it would present Claude Code's client id without being
# Claude Code. `claude auth status` is not a keep-alive: it starts a
# refresh, exits, and leaves a lock the next run trips on until the
# harness calls it stale (60 s).
STALE_EMPTY_S = 5
ACCOUNTS_TIMEOUT_MS = 120000

ACCOUNTS_MAX_BYTES = 4 * 1024 * 1024

ACCOUNT_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


def accounts_dir(home: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """Under the login's fabric state root, the same one runtime/identity.py
    resolves: AGENT_FABRIC_STATE_DIR when set, else the XDG default."""
    home = os.path.expanduser("~") if home is None else home
    env = os.environ if env is None else env
    if env.get("AGENT_FABRIC_STATE_DIR"):
        root = os.path.abspath(env["AGENT_FABRIC_STATE_DIR"])
    else:
        root = os.path.join(env.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state"), "agent-fabric")
    return os.path.join(root, "accounts")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True   # another login's process: alive
    except (OSError, OverflowError):
        return False
    return True


def take_read_lock(directory: str, pid: int | None = None) -> Callable[[], None] | None:
    """One reader per account across PROCESSES, not only inside the daemon: a
    person's `fabric-accounts read` beside the keeper would start a second
    harness on the same config directory, and the loser fails on the
    refresh lock. The lock is created complete — the pid written to a file
    of our own, then linked into place, EEXIST being the busy answer — so a
    held lock is never empty and a second reader cannot mistake a holder
    between create and write for a crash. A holder that is gone (a killed
    read) does not keep the account. A lock naming no positive pid is stale
    only once it is older than STALE_EMPTY_S: the Node wrote its lock in two
    steps, so a Node daemon beside this one can be between them. (The Node
    signalled pid 0 — its own process group — for an empty file and kept the
    account busy for good.) Raises OSError for a failure that is not the race."""
    pid = os.getpid() if pid is None else pid
    f = os.path.join(directory, ".fabric-read.lock")
    tmp = f"{f}.{os.getpid()}.{threading.get_ident()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"{pid}\n")
        for _ in range(2):
            try:
                os.link(tmp, f)
            except FileExistsError:
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        text = fh.read().strip()
                    age = time.time() - os.stat(f).st_mtime
                except FileNotFoundError:
                    continue   # released between our attempt and this read: try again; anything else is loud
                holder = int(text) if text.isascii() and text.isdigit() else 0
                if holder > 0:
                    if _alive(holder) and holder != pid:
                        return None
                elif age < STALE_EMPTY_S:
                    return None
                try:
                    os.unlink(f)
                except OSError:
                    pass   # raced
                continue

            def release() -> None:
                # Only a lock that still names us: after a takeover the file is another reader's.
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        if fh.read().strip() != str(pid):
                            return
                    os.unlink(f)
                except OSError:
                    pass   # gone
            return release
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def account_slugs(directory: str) -> list[str]:
    try:
        with os.scandir(directory) as it:
            return sorted(e.name for e in it if e.is_dir(follow_symlinks=False) and ACCOUNT_SLUG.fullmatch(e.name))
    except OSError:
        return []


def claude_bin(home: str | None = None) -> str:
    home = os.path.expanduser("~") if home is None else home
    own = os.path.join(home, ".local", "bin", "claude")
    return own if os.path.exists(own) else "claude"


def parse_usage_report(stdout: str) -> dict:
    """The /usage events, reduced to fixed keys. `limits` are the server's
    meters in its order: session, weekly_all, weekly_scoped (per model)."""
    try:
        events = json.loads(stdout)
    except ValueError:
        return {"status": "unreadable"}
    if not isinstance(events, list):
        return {"status": "unreadable"}
    result = next((e for e in events if js.get(e, "type") == "result"), None)
    holder = next((e for e in events if util.truthy(js.get(e, "usage_report"))), None)
    report = js.get(holder, "usage_report")
    if util.truthy(js.get(result, "is_error")):
        res = js.get(result, "result")
        return {"status": "failed", "error": ("" if js.nullish(res) else js.string(res))[:200]}
    limits = js.get(js.get(report, "rate_limits"), "limits")
    if not isinstance(limits, list):
        return {"status": "no-report"}

    def val(v: Any) -> Any:
        return None if js.nullish(v) else v
    return {"status": "ok", "limits": [
        {"kind": val(js.get(lim, "kind")), "group": val(js.get(lim, "group")),
         "percent": lim["percent"] if isinstance(js.get(lim, "percent"), (int, float)) and not isinstance(lim["percent"], bool) else None,
         "resets_at": val(js.get(lim, "resets_at")),
         "model": val(js.get(js.get(js.get(lim, "scope"), "model"), "display_name"))} for lim in limits]}


def read_account(directory: str, home: str | None = None, run: Callable[..., Any] = util.run_bounded,
                 bin: str | None = None, now: Callable[[], float] = lambda: time.time() * 1000,  # noqa: A002
                 timeout_ms: int = ACCOUNTS_TIMEOUT_MS) -> dict:
    """One account's reading. The child gets an environment built from
    nothing: a token variable inherited from the observer's own session
    (CLAUDE_CODE_OAUTH_TOKEN, ANTHROPIC_API_KEY, a base URL) would outrank
    the account's sign-in and report another account's windows."""
    home = os.path.expanduser("~") if home is None else home
    bin = claude_bin(home) if bin is None else bin  # noqa: A001
    slug = os.path.basename(directory)
    profile = js.get(util.read_json(os.path.join(directory, ".claude.json")), "oauthAccount")
    email, org = js.get(profile, "emailAddress"), js.get(profile, "organizationUuid")
    out: dict[str, Any] = {"slug": slug, "email": None if js.nullish(email) else email,
                           "organization_uuid": None if js.nullish(org) else org, "read_at": util.iso_ms(now())}
    if not os.path.exists(os.path.join(directory, ".credentials.json")):
        return {**out, "status": "not-signed-in"}
    try:
        release = take_read_lock(directory)
    except OSError as e:   # this account's row, not the whole section's
        return {**out, "status": "failed", "error": f"read lock: {errno.errorcode.get(e.errno or 0) or str(e)[:80]}"}
    if not release:
        return {**out, "status": "busy", "error": "another reader holds this account (the daemon, or fabric-accounts read)"}
    # A fixed working directory: the harness records a project per cwd even
    # with --no-session-persistence (an empty one, measured), so a fresh
    # temporary cwd per read would leave one more entry every 4 hours.
    cwd = os.path.join(directory, "work")
    cmd = [bin, "-p", "/usage", "--output-format", "json", "--no-session-persistence"]
    try:
        os.makedirs(cwd, mode=0o700, exist_ok=True)   # inside the try: a failure here must still release the lock
        env = {"HOME": home, "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "CLAUDE_CONFIG_DIR": directory,
               "LANG": "C.UTF-8"}
        r = run(cmd, cwd=cwd, env=env, timeout=timeout_ms / 1000, max_bytes=ACCOUNTS_MAX_BYTES)
        return {**out, **parse_usage_report(util.decode(r.stdout))}
    except (subprocess.SubprocessError, OSError) as e:
        return {**out, "status": "timeout" if isinstance(e, subprocess.TimeoutExpired) else "failed",
                "error": util.node_error(e, cmd)[:200]}
    finally:
        release()


def accounts(home: str | None = None, directory: str | None = None, **opts: Any) -> dict:
    """Every observed account, one at a time: two harness runs on one config
    directory race for its refresh lock."""
    home = os.path.expanduser("~") if home is None else home
    directory = accounts_dir(home) if directory is None else directory
    slugs = account_slugs(directory)
    if not slugs:
        return {"status": "none", "dir": directory}
    return {"status": "ok", "accounts": [read_account(os.path.join(directory, s), home=home, **opts) for s in slugs]}


# THE TOKENS. The usage windows (`usage`) are the Claude account's, one
# number for every login signed into it; which login consumed what is
# nowhere but in each login's own session records, where every assistant
# message carries the model and its usage (input, cache creation, cache
# read, output). Summed here per model over a window, deduplicated by
# request — the harness writes one record per content block, all with
# the same usage — for the session transcripts and the subagent
# transcripts beside them (a dispatched agent spends the same account).
# A file older than the window holds nothing in it; a record is in the
# window by its own timestamp. `equiv` is the sum in input-token
# equivalents at the API's own ratios — cache write 1.25×, cache read
# 0.1×, output 5× — a proxy for what the subscription meter weighs, not
# its figure: the meter's weighting is unpublished, one model tier is
# not priced here against another, and what the same account spends
# outside this host (the web app, a phone) is invisible. Read back
# 2026-09-19: this login's session, 155 requests, 22.5M cache reads,
# 68k output. Counts only; nothing of the text leaves.
TOKEN_RATIOS = {"input": 1, "cache_write": 1.25, "cache_read": 0.1, "output": 5}

TOKENS_DAYS = 7

_COUNTS = ("requests", "input", "cache_write", "cache_read", "output")


def equivalent(u: Mapping[str, float], ratios: Mapping[str, float] = TOKEN_RATIOS) -> int:
    return util.js_round(u["input"] * ratios["input"] + u["cache_write"] * ratios["cache_write"]
                         + u["cache_read"] * ratios["cache_read"] + u["output"] * ratios["output"])


def transcripts(root: str) -> list[tuple[str, str]] | None:
    """Every session transcript under ~/.claude/projects and the subagent
    transcripts beside each, as (path, "session"|"subagent"); None when the
    directory cannot be listed."""
    files: list[tuple[str, str]] = []
    try:
        dirs = sorted(os.listdir(root))
    except OSError:
        return None
    for d in dirs:
        directory = os.path.join(root, d)
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for n in names:
            if n.endswith(".jsonl"):
                files.append((os.path.join(directory, n), "session"))
                continue
            sub = os.path.join(directory, n, "subagents")
            try:
                subs = sorted(os.listdir(sub))
            except OSError:
                continue
            files.extend((os.path.join(sub, a), "subagent") for a in subs if re.fullmatch(r"agent-.*\.jsonl", a))
    return files


def _num0(v: Any) -> float | int:
    n = js.number(v) if not isinstance(v, (dict, list)) else float("nan")
    return util.whole(n) if n == n and n not in (float("inf"), float("-inf")) else 0


def tokens(home: str | None = None, days: float = TOKENS_DAYS, now: float | None = None) -> dict:
    home = os.path.expanduser("~") if home is None else home
    now = time.time() * 1000 if now is None else now
    since = now - days * 86400000
    files = transcripts(os.path.join(home, ".claude", "projects"))
    if files is None:
        return {"status": "no-records", "days": days}
    models: dict[str, dict[str, Any]] = {}
    kinds = {"session": 0, "subagent": 0}
    seen: set[str] = set()
    read = 0
    first: float | None = None
    last: float | None = None
    for f, kind in files:
        try:
            if os.stat(f).st_mtime * 1000 < since:
                continue
            with open(f, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            continue
        read += 1
        for line in body.split("\n"):
            if '"assistant"' not in line or '"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if js.get(d, "type") != "assistant":
                continue
            m = js.get(d, "message")
            u = js.get(m, "usage")
            if not isinstance(u, (dict, list)):
                continue
            ts = util.date_parse_ms(js.get(d, "timestamp"))
            if ts is None or ts < since or ts > now:
                continue
            key = js.coalesce(js.get(d, "requestId"), js.get(m, "id"))
            if not util.truthy(key):
                continue
            key = js.stringify(key)   # a Set holds 1 and "1" apart, as this does
            if key in seen:
                continue
            seen.add(key)
            model = js.get(m, "model")
            if not isinstance(model, str) or model.startswith("<"):
                continue   # <synthetic>: the harness's own, no usage
            t = models.setdefault(model, {k: 0 for k in _COUNTS})
            t["requests"] += 1
            t["input"] += _num0(js.get(u, "input_tokens"))
            t["cache_write"] += _num0(js.get(u, "cache_creation_input_tokens"))
            t["cache_read"] += _num0(js.get(u, "cache_read_input_tokens"))
            t["output"] += _num0(js.get(u, "output_tokens"))
            kinds[kind] += 1
            first = ts if first is None or ts < first else first
            last = ts if last is None or ts > last else last
    if not read or not seen:
        return {"status": "no-records", "days": days}
    # Two paths, two bills: a model id with a vendor prefix (z-ai/glm-5.3,
    # anthropic/claude-opus-5) was served by the broker on the account's
    # OpenRouter key; a bare id (claude-opus-5) by Anthropic directly, on
    # the Claude account's subscription — the one the usage windows meter.
    paths: dict[str, dict[str, Any]] = {"claude": {k: 0 for k in _COUNTS}, "broker": {k: 0 for k in _COUNTS}}
    for model, t in models.items():
        t["equiv"] = equivalent(t)
        t["path"] = "broker" if "/" in model else "claude"
        for k in _COUNTS:
            paths[t["path"]][k] += t[k]
    for t in paths.values():
        t["equiv"] = equivalent(t)
    ordered = dict(sorted(models.items(), key=lambda kv: -kv[1]["equiv"]))
    return {"status": "ok", "days": days, "files": read, "requests": kinds,
            "first": util.iso_ms(first) if first else None, "last": util.iso_ms(last) if last else None,
            "models": ordered, "claude": paths["claude"], "broker": paths["broker"], "ratios": TOKEN_RATIOS}
