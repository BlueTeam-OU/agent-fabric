"""tools/fabric/control/account_observe.py — what each Claude account tells the fabric about itself, written into the
coordinator's account files (`fabric-accounts observe [--write]`; docs/live-checks/2026-10-24-account-metadata-from-api.md).

Contract
  who     run by the coordinator: its store holds the templates (CLAUDE_ACCOUNT_<SLUG>) and the owner's account files
          (settings/accounts/<slug>.json).
  reads   for every template, one inference probe on its setup-token (ops/usage.py probe_account: both windows,
          the organization and workspace ids, the overage state); and, where an observer sign-in exists under
          <state>/accounts/<slug>/, its oauthAccount and its /usage report (ops/usage.py read_account).
  writes  ONE key, "observed", in that slug's file; every other byte of the file is kept (the key is spliced into the
          text, the file is not re-serialised). A file that does not exist is created with "account" and "observed"
          only. All files go in one settings-put commit. Without --write nothing is written and the verb prints what
          it would set.
  observed  read_at, status ("ok", or "read-failed" / "no-token" with "error" — a failed read carries no figures,
          unknown is not 0); organization_id, workspace_id; five_hour and seven_day {utilization, resets_at, status};
          weekly_reset {weekday, time_utc} from seven_day; overage {status, disabled_reason}. From a sign-in only:
          organization_type, rate_limit_tier, billing_type, subscription_created_at, extra_usage_enabled and
          model_weekly [{model, percent, resets_at}]; a sign-in whose /usage did not read is {"signin": {status, error}}.
          A figure a source did not give is null.
  exit    0 every template read ok and every file written (or, dry, would be); 1 a read failed or a file was
          refused (a failed read is still written under --write); 2 usage.
  secrets a token is held in a variable and put in one header (ops/usage.py); every error text that reaches the
          output is scrubbed of every token this run holds.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import control.ops.usage  # noqa: E402,F401
import control.ops.util  # noqa: E402,F401

# The package re-exports a function named `usage` and one named `util`'s members; the modules are taken by name.
usage, util = sys.modules["control.ops.usage"], sys.modules["control.ops.util"]

USAGE = "usage: fabric-accounts observe [--write]"
KEY = "observed"
TEMPLATE_PREFIX = "CLAUDE_ACCOUNT_"
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def weekly_reset(seven_day: Mapping[str, Any] | None) -> dict | None:
    """The weekday and UTC time of the weekly window's end. The /usage report
    ends its windows at 15:59:59, the headers at 16:00:00: the minute nearest."""
    at = util.date_parse_ms((seven_day or {}).get("resets_at"))
    if at is None:
        return None
    minute = int(round(at / 60000))
    day, rem = divmod(minute, 1440)
    return {"weekday": _DAYS[(day + 3) % 7], "time_utc": f"{rem // 60:02d}:{rem % 60:02d}"}   # day 0 of the epoch was a Thursday


def _window(w: Mapping[str, Any] | None) -> dict | None:
    if not w:
        return None
    return {"utilization": w.get("utilization"), "resets_at": w.get("resets_at"), "status": w.get("status")}


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) and v else None


def signin_profile(directory: str) -> dict:
    """The sign-in's account facts, from its .claude.json; None where absent or not of the field's type."""
    p = util.read_json(os.path.join(directory, ".claude.json"))
    acct = p.get("oauthAccount") if isinstance(p, dict) else None
    acct = acct if isinstance(acct, dict) else {}
    extra = acct.get("hasExtraUsageEnabled")
    return {"organization_type": _str(acct.get("organizationType")), "rate_limit_tier": _str(acct.get("organizationRateLimitTier")),
            "billing_type": _str(acct.get("billingType")), "subscription_created_at": _str(acct.get("subscriptionCreatedAt")),
            "extra_usage_enabled": extra if isinstance(extra, bool) else None}


def build_observed(slug: str, token: str | None, directory: str, *, probe: Callable[..., dict], read_signin: Callable[..., dict],
                   now: Callable[[], float]) -> dict:
    out: dict[str, Any] = {"read_at": util.iso_ms(now())}
    if not token:
        out.update(status="no-token", error="the template holds no CLAUDE_CODE_OAUTH_TOKEN")
    else:
        p = probe(token)
        if p.get("status") != "ok":
            out.update(status="read-failed", error=f"the inference probe gave no reading{' (HTTP ' + str(p['http']) + ')' if p.get('http') else ''}")
        else:
            out.update(status="ok", organization_id=p.get("organization_id"), workspace_id=p.get("workspace_id"),
                       five_hour=_window(p.get("five_hour")), seven_day=_window(p.get("seven_day")),
                       weekly_reset=weekly_reset(p.get("seven_day")),
                       overage=p.get("overage") or {"status": None, "disabled_reason": None})
    if os.path.exists(os.path.join(directory, ".credentials.json")):
        out.update(signin_profile(directory))
        r = read_signin(directory)
        if r.get("status") == "ok":
            out["model_weekly"] = [{"model": lim.get("model"), "percent": lim.get("percent"), "resets_at": lim.get("resets_at")}
                                   for lim in r.get("limits") or [] if lim.get("kind") == "weekly_scoped"]
        else:
            out["signin"] = {"status": r.get("status"), "error": r.get("error")}
    return out


# ── the file: one key spliced in, the rest untouched ───────────────────────────────────────────

class FileRefused(Exception):
    """The existing file cannot take the key without being rewritten; the message names why, never a value."""


def _no_constant(name: str) -> Any:
    raise ValueError(name)


_DECODER = json.JSONDecoder(parse_constant=_no_constant)
_WS = " \t\r\n"


def set_key(text: str, key: str, value: Any) -> str:
    """`text` (a JSON object) with `key` set to `value`, every other byte as it was."""
    def skip(i: int) -> int:
        while i < len(text) and text[i] in _WS:
            i += 1
        return i

    try:
        i = skip(0)
        if i >= len(text) or text[i] != "{":
            raise FileRefused("not a JSON object")
        open_at, i = i, skip(i + 1)
        members: list[tuple[str, int, int]] = []   # key, start of value, end of value
        first_key_at = i
        while i < len(text) and text[i] != "}":
            if members:
                if text[i] != ",":
                    raise FileRefused("not valid JSON")
                i = skip(i + 1)
            k, i = _DECODER.raw_decode(text, i)
            i = skip(i)
            if not isinstance(k, str) or i >= len(text) or text[i] != ":":
                raise FileRefused("not valid JSON")
            vs = skip(i + 1)
            _, ve = _DECODER.raw_decode(text, vs)
            members.append((k, vs, ve))
            i = skip(ve)
        if i >= len(text) or text[i:].strip(_WS) != "}":
            raise FileRefused("not valid JSON")
    except ValueError:
        raise FileRefused("not valid JSON") from None
    same = [m for m in members if m[0] == key]
    if len(same) > 1:
        raise FileRefused(f"the key {key!r} is there twice")
    gap = text[open_at + 1:first_key_at]
    pretty = "\n" in gap or not members
    indent = gap[gap.rindex("\n") + 1:] if "\n" in gap else "  "
    body = json.dumps(value, ensure_ascii=False, **({"indent": indent or "  "} if pretty else {}))
    body = body.replace("\n", "\n" + indent) if pretty else body
    if same:
        _, vs, ve = same[0]
        return text[:vs] + body + text[ve:]
    member = f"{json.dumps(key)}: {body}"
    if not members:
        return text[:open_at + 1] + "\n" + indent + member + "\n" + text[i:]
    end = members[-1][2]
    return text[:end] + "," + ("\n" + indent if pretty else " ") + member + text[end:]


def new_file(slug: str, value: Any) -> str:
    return json.dumps({"account": slug, KEY: value}, indent=2, ensure_ascii=False) + "\n"


# ── the store ───────────────────────────────────────────────────────────────────────────────

def store_tokens() -> dict[str, str | None]:
    """Every template by slug, its token or None. In-process; decrypts the template entries and nothing else."""
    from secretstore import entries
    named = [n for n in entries.names() if n.startswith(TEMPLATE_PREFIX)]
    vals = entries.values(only=named)
    return {n[len(TEMPLATE_PREFIX):].lower().replace("_", "-"): vals.get(n) or None for n in named}


def account_path(slug: str) -> str:
    from secretstore.core import store_dir
    return os.path.join(store_dir(), "settings", "accounts", f"{slug}.json")


def read_text(path: str) -> str | None:
    """The file's text; None if absent. Never through a link (settings-put refuses one too)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError as e:
        raise FileRefused(e.strerror or "unreadable") from None
    with os.fdopen(fd, "rb") as fh:
        try:
            return fh.read().decode("utf-8")
        except UnicodeDecodeError:
            raise FileRefused("not UTF-8") from None


def store_put(tree: str) -> dict:
    from secretstore.settings import settings_put
    return settings_put(tree)


def _locked() -> Any:
    from secretstore.core import store_dir
    from secretstore.entries import _before_write
    from secretstore.lock import write_lock
    @contextlib.contextmanager
    def cm():
        s = store_dir()
        with write_lock(s):
            _before_write(s)   # the files are read on the remote's head: whole-file replacement must not lose a newer edit
            yield
    return cm()


def scrub(v: Any, secrets: Sequence[str]) -> Any:
    if isinstance(v, str):
        for s in secrets:
            v = v.replace(s, "[token]")
        return v
    if isinstance(v, dict):
        return {k: scrub(x, secrets) for k, x in v.items()}
    if isinstance(v, list):
        return [scrub(x, secrets) for x in v]
    return v


def main(argv: Sequence[str] | None = None, *, home: str | None = None, env: Mapping[str, str] | None = None,
         tokens: Callable[[], dict[str, str | None]] = store_tokens, path_of: Callable[[str], str] = account_path,
         put: Callable[[str], dict] = store_put, locked: Callable[[], Any] = _locked,
         probe: Callable[..., dict] = usage.probe_account, read_signin: Callable[..., dict] = usage.read_account,
         now: Callable[[], float] = lambda: time.time() * 1000,
         say: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--write"]):
        say(USAGE)
        return 2
    write = bool(argv)
    home = os.path.expanduser("~") if home is None else home
    directory = usage.accounts_dir(home, env)
    try:
        held = tokens()
    except Exception as e:  # noqa: BLE001 — the store's errors are its own one-liners; a value is never in them
        say(f"fabric-accounts: the templates could not be read: {str(e)[:160]}")
        return 1
    if not held:
        say("fabric-accounts: no template in this store (fabric-secrets store template-set <slug>)")
        return 1
    secrets = [t for t in held.values() if t]
    failed = False
    observed: dict[str, dict] = {}
    for slug in sorted(held):
        o = build_observed(slug, held[slug], os.path.join(directory, slug), probe=probe,
                           read_signin=lambda d: read_signin(d, home=home), now=now)
        observed[slug] = scrub(o, secrets)
        failed = failed or o["status"] != "ok"
    texts: dict[str, str | None] = {}
    result: dict[str, str] = {}

    def render(slug: str) -> str:
        t = texts[slug]
        return new_file(slug, observed[slug]) if t is None else set_key(t, KEY, observed[slug])

    def gather() -> None:
        nonlocal failed
        for slug in observed:
            try:
                texts[slug] = read_text(path_of(slug))
                render(slug)
                result[slug] = "create" if texts[slug] is None else "update"
            except FileRefused as e:
                result[slug] = f"refused: {e}"
                failed = True

    if not write:
        gather()
        for slug in observed:
            print(f"{slug}: {observed[slug]['status']}; would {result[slug]} {path_of(slug)}" if not result[slug].startswith("refused")
                  else f"{slug}: {result[slug]}")
            print(json.dumps({KEY: observed[slug]}, indent=2, ensure_ascii=False))
        return 1 if failed else 0
    try:
        with locked(), tempfile.TemporaryDirectory(prefix="observe-") as tree:
            gather()
            os.makedirs(os.path.join(tree, "accounts"), mode=0o700)
            for slug in observed:
                if result[slug].startswith("refused"):
                    continue
                with open(os.path.join(tree, "accounts", f"{slug}.json"), "w", encoding="utf-8") as fh:
                    fh.write(render(slug))
            r = put(tree) if any(not v.startswith("refused") for v in result.values()) else {"changed": False}
    except Exception as e:  # noqa: BLE001 — a store refusal is a line, nothing was written
        say(f"fabric-accounts: nothing written: {str(scrub(str(e), secrets))[:200]}")
        return 1
    for slug in observed:
        print(f"{slug}: {observed[slug]['status']}; {result[slug]}{'' if result[slug].startswith('refused') else 'd'}")
    print(f"settings: {'committed ' + str(r.get('commit')) if r.get('changed') else 'unchanged'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
