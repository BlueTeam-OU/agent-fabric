"""tools/fabric/control/usage_resets.py — agentd records each account's weekly usage reset in the coordinator's store.

Owner 2026-10-24: an account's weekly reset (weekday, UTC hour, the next reset time) is account metadata.

Contract
  input   the rows of one accounts read (ops.accounts(): {"accounts": [{slug, status, limits: [{kind, resets_at, …}]}]}),
          read by agentd's keeper from the observer sign-ins.
  reads   settings/accounts/<slug>.json of the store, on the remote's head (account_observe._locked).
  writes  ONE key, "usage_resets", in that slug's file, every other byte kept (account_observe.set_key); a file that
          does not exist is created with "account" and "usage_resets" only. All changed files go in one settings-put
          commit; a file whose value is already what the read says is not touched, so a four-hourly read makes a commit
          once a week, not six a day.
  value   {"weekly": {"weekday": "thursday", "time_utc": "12:00", "next": "<the read's resets_at>"}}. The weekday and
          hour are the minute nearest the report's 15:59:59 end (account_observe.weekly_reset); "next" is the report's text.
  unknown a row that is not ok, or whose weekly_all meter carries no parseable reset, leaves the field as it was: unknown
          is not a reset of nothing. A file the key cannot be spliced into is refused by name and left alone.
  failure never raised into the keeper: a store that is missing, moved, or refused is one stderr line, the reads go on.
  secrets none held: the rows are the sign-ins' reports, whose figures carry no token.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any, Callable, Mapping

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import control.account_observe as observe  # noqa: E402

KEY = "usage_resets"
WEEKLY_KIND = "weekly_all"


def weekly_of(row: Mapping[str, Any]) -> dict | None:
    """The row's weekly reset, or None where the row gives none."""
    if row.get("status") != "ok" or not isinstance(row.get("slug"), str):
        return None
    for lim in row.get("limits") if isinstance(row.get("limits"), list) else []:
        if isinstance(lim, dict) and lim.get("kind") == WEEKLY_KIND:
            at = lim.get("resets_at")
            reset = observe.weekly_reset({"resets_at": at}) if isinstance(at, str) else None
            return None if reset is None else {**reset, "next": at}
    return None


def wanted(rows: Any) -> dict[str, dict]:
    """slug → the value of usage_resets, for the rows that carry a reset. A slug twice keeps the first row's."""
    out: dict[str, dict] = {}
    for row in rows.get("accounts") if isinstance(rows, dict) and isinstance(rows.get("accounts"), list) else []:
        w = weekly_of(row) if isinstance(row, dict) else None
        if w is not None and observe.usage.ACCOUNT_SLUG.fullmatch(row["slug"]):
            out.setdefault(row["slug"], {"weekly": w})
    return out


def _current(text: str | None) -> Any:
    try:
        v = json.loads(text) if text is not None else None
    except (ValueError, RecursionError):
        return None   # set_key refuses the file by name; here only "not equal"
    return v.get(KEY) if isinstance(v, dict) else None


def _push_ahead() -> None:
    from secretstore.core import store_dir
    from secretstore.entries import _push_if_ahead
    _push_if_ahead(store_dir())


def record(rows: Any, *, path_of: Callable[[str], str] = observe.account_path, put: Callable[..., dict] = observe.store_put,
           locked: Callable[[], Any] = observe._locked, push_ahead: Callable[[], None] = lambda: _push_ahead(),
           say: Callable[[str], None] = lambda m: print(m, file=sys.stderr, flush=True)) -> dict[str, str]:
    """Write what `rows` say; returns slug → "created" | "updated" | "unchanged" | "refused: why". Never raises."""
    want = wanted(rows)
    if not want:
        return {}
    result: dict[str, str] = {}
    try:
        with locked() as head, tempfile.TemporaryDirectory(prefix="usage-resets-") as tree:
            os.makedirs(os.path.join(tree, "accounts"), mode=0o700)
            for slug, value in sorted(want.items()):
                try:
                    text = observe.read_text(path_of(slug))
                    if _current(text) == value:
                        result[slug] = "unchanged"
                        continue
                    body = json.dumps({"account": slug, KEY: value}, indent=2, ensure_ascii=False, allow_nan=False) + "\n" \
                        if text is None else observe.set_key(text, KEY, value)
                except observe.FileRefused as e:
                    result[slug] = f"refused: {e}"
                    continue
                with open(os.path.join(tree, "accounts", f"{slug}.json"), "w", encoding="utf-8") as fh:
                    fh.write(body)
                result[slug] = "created" if text is None else "updated"
            if any(v in ("created", "updated") for v in result.values()):
                put(tree, expect_head=head)
            else:
                push_ahead()   # a commit an earlier failed push left is not "unchanged" for the remote
    except Exception as e:  # noqa: BLE001 — a store refusal is one line; the keeper's reads go on
        text = str(e)[:160]
        say(f"agentd: usage resets: the store refused or failed: {text}" + ("" if "nothing written" in text else " (a commit may be made but not pushed)"))
        return {}
    for slug, what in sorted(result.items()):
        if what.startswith("refused"):
            say(f"agentd: usage resets: {slug}: {what}")
    return result
