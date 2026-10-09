"""tools/fabric/control/ops — what a control agent can say about its own
account, as pure extractors: each takes its inputs (a home, a fetch, a
run) so a test runs them against a scratch home and a fake relay, and
each returns only fixed, whitelisted keys — never a value from a secret.
The fingerprints are the one place a secret is read: hashed in place,
twelve hex digits of its sha256, enough to tell two keys apart and
nothing else (the CEO, 2026-09-17: "the username it logs in with, or
the api key hash").

The port of runtime/control/ops.mjs and ops/*.mjs (ADR-040 Wave 8). The
replies are frozen with the wire: the same op names, the same keys in the
same order, the same statuses; a mixed fleet answers both ways. Where the
port differs, it is listed here:
  - A directory's entries are taken in sorted order where the Node took
    readdir's (memory rows, transcripts, leases, du's arguments): ties
    and rows come out the same on every run.
  - accounts: a read lock holding no positive pid is stale (the Node
    signalled pid 0, its own process group, and kept the account busy).
  - usage: no proxy, and a redirect is a failed read (urllib would carry
    the token to wherever a redirect names).
  - memory: a harvest that failed with nothing on stderr says why
    (a timeout, a missing interpreter), where the Node said "".
  - Every subprocess has a timeout, presence's pgrep included.

A section that cannot be read says so inline ({status: ...}) rather than
raising: a reply always arrives, and its gaps are named.

The extractors are synchronous; collect() runs a request's sections in
threads, as the Node ran them under one Promise.all.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping

from . import util  # noqa: F401 — first: it puts tools/fabric on sys.path
from .identity import identity, fabric, session, presence  # noqa: F401
from .usage import (USAGE_URL, MESSAGES_URL, PROBE_MODEL, usage, windows_from_headers, ACCOUNTS_TIMEOUT_MS,  # noqa: F401
                    ACCOUNT_SLUG, accounts_dir, take_read_lock, account_slugs, claude_bin, parse_usage_report,
                    read_account, accounts, TOKEN_RATIOS, TOKENS_DAYS, equivalent, tokens)
from .keys import KEY_NAMES, keys, STORE_ROW, store_refusal, SIGNING_ROW, signing_secret  # noqa: F401
from .host import host, DISK_TIMEOUT_MS, DISK_MAX_BUFFER, DISK_TOP, disk  # noqa: F401
from .activity import (script_counts, langid_cmd, languages, recall_kind, recall, notes_dir, script,  # noqa: F401
                       WORKER_TYPE, worker_transcripts, source_locale, SOURCE_TAG)
from .memory import MEMORY_PART_BYTES, memory_slug, memory_dirs, memory  # noqa: F401

OPS = ["ping", "identity", "usage", "keys", "fabric", "session", "script", "recall", "tokens", "memory", "host", "disk",
       "accounts", "upgrade", "secrets-sync", "status", "presence", "jobs", "jobs-add", "tools", "local", "local-prune",
       "secrets-selftest", "pool-add", "pool-list", "pool-claim"]

# Answered for any placed account, not only an operator: whether a session
# is running is what every sender needs before it writes to one, and it
# names nothing a relay reader could not already infer (the owner,
# 2026-09-25: presence moves from HELLO/GOODBYE, now retired, to the
# control plane). And a role's pool (pool, ADR-037 rule 9): every placed
# agent lists its role's pool and claims from it, for itself.
PUBLIC_OPS = ["presence", "pool-list", "pool-claim"]


def _jobs(ctx: Mapping[str, Any]) -> Any:
    from control.jobs import jobs   # python-dev-01's port; until it lands the section says it failed
    return jobs(home=ctx.get("home"), root=ctx.get("root"), **(ctx.get("jobs_opts") or {}))


def _tools(ctx: Mapping[str, Any]) -> Any:
    from control.tools import tools
    return tools(**(ctx.get("tools_opts") or {}))


def _local(ctx: Mapping[str, Any]) -> Any:
    from control.local import local
    return local(home=ctx.get("home"), root=ctx.get("root"))


def _host(ctx: Mapping[str, Any]) -> Any:
    # The machine now, and the pressure this daemon sampled up to now (pressure.py).
    from control.pressure import memory_pressure
    return {**host(**(ctx.get("host_opts") or {})), "memory_pressure": memory_pressure(**(ctx.get("pressure_opts") or {}))}


def _keys(ctx: Mapping[str, Any]) -> Any:
    run = ctx.get("run")
    return [*keys(ctx.get("home")), signing_secret(**({"run": run} if run else {})),
            store_refusal(ctx.get("home"), ctx.get("store_dir"))]


def _run_kw(ctx: Mapping[str, Any]) -> dict:
    return {"run": ctx["run"]} if ctx.get("run") else {}


# Each section and how a request's context reaches it. `who` unset is
# whoami() per request, so a rebind shows.
SECTIONS: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    "identity": lambda c: identity(c.get("home"), c.get("who")),
    "usage": lambda c: c["usage_cached"]() if c.get("usage_cached") else usage(c.get("home"), **({"fetch": c["fetch"]} if c.get("fetch") else {})),
    "keys": _keys,
    "fabric": lambda c: fabric(c.get("root"), **_run_kw(c)),
    "session": lambda c: session(c.get("uid"), **_run_kw(c)),
    "presence": lambda c: presence(**(c.get("presence_opts") or {})),
    "script": lambda c: script(c.get("home"), source=source_locale(c.get("who"), root=c.get("root"))),
    "recall": lambda c: recall(c.get("home")),
    "tokens": lambda c: tokens(c.get("home"), **({"days": c["days"]} if c.get("days") else {})),
    "memory": lambda c: memory(c.get("home"), all=True, **({"run": c["run_bounded"]} if c.get("run_bounded") else {})),
    "host": _host,
    # One scan per daemon however many ask at once (the daemon's disk keeper).
    "disk": lambda c: c["disk_cached"]() if c.get("disk_cached") else disk(c.get("home"), **(c.get("disk_opts") or {})),
    "local": _local,
    "jobs": _jobs,
    "tools": _tools,
    "accounts": lambda c: c["accounts_cached"]() if c.get("accounts_cached") else accounts(c.get("home"), **(c.get("accounts_opts") or {})),
}


def _wants(op: str) -> list[str]:
    if op == "status":
        return ["identity", "usage", "keys", "fabric", "session"]
    if op == "tokens":
        return ["identity", "tokens"]
    return [op]


def collect(op: str, ctx: Mapping[str, Any] | None = None) -> dict:
    """Everything, for `status`; the sections a request names, otherwise.
    An op that names no section answers {}. The reply's keys follow the
    request's order, as the Node's did when every section answered at once."""
    ctx = ctx or {}
    names = [n for n in _wants(op) if n in SECTIONS]

    def guard(name: str) -> Any:
        try:
            return SECTIONS[name](ctx)
        except Exception as e:  # noqa: BLE001 — a section that raised is said as one, never the whole reply
            return {"status": "failed", "error": str(e)[:200]}
    if not names:
        return {}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        results = list(pool.map(guard, names))
    return dict(zip(names, results))
