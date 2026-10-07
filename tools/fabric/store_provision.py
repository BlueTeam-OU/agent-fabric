#!/usr/bin/env python3
"""tools/fabric/store_provision.py — a parent fills its children's stores
(ADR-038): what enroll.sh did in Doppler, done with `put`, so no value is
ever read back from a child and none reaches a terminal. Run by the
fabric-coordinator login, the parent, behind `fabric-secrets provision`.

    fabric-secrets provision identity <login> --host <host-id> [--replace]
        AGENT_LOGIN and AGENT_HOST, the names sync checks the store against
    fabric-secrets provision share <login…|all> [--name NAME]... [--replace]
        the parent's own value of each shared name into each child's store
        where the child lacks it; --replace writes it anyway (a rotation:
        `fabric-secrets store set --managed NAME` first, then this, then
        `fabric-ctl all secrets-sync`)
    fabric-secrets provision issue-key openrouter|openai <login…> [--replace]
        a key of the login's own, minted with the parent's provisioning key
        (OPENROUTER_PROVISIONING_KEY) or admin key (OPENAI_ADMIN_KEY, and
        OPENAI_PROJECT_ID with several projects) from the parent's store,
        straight into the child's; a child that holds one is left alone
        unless --replace, since a key is minted, never read back

Output: one JSON row per login and name — status written, present,
skipped or failed — never a value. Exit 1 when a row failed.

SHARED NAMES are an allowlist. enroll.sh fill-from copied every name the
source held except a denylist, and handed a fresh account the power to
mint keys for every other when the coordinator's provisioning key was
not on the list (brand-comms-01, 2026-09-15). --name selects among the
listed names and nothing else: a refusal list is the shape that failed,
and a login's own key named by mistake would put the parent's in every
child (review of #69, F2). A new shared name is a change to this list.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import secret_store as ss  # noqa: E402

SHARED_NAMES = ["GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN",
                "GIT_USER_NAME", "GIT_USER_EMAIL", "GIT_SIGNING_KEY", "GIT_GPG_PROGRAM",
                "SSH_PRIVATE_KEY", "SSH_PUBLIC_KEY"]
KEY_NAMES = {"openrouter": "OPENROUTER_API_KEY", "openai": "OPENAI_API_KEY"}
TIMEOUT_S = 30


def placed_logins() -> list[str]:
    reg = os.environ.get("AGENT_FABRIC_HOSTS_REGISTRY") or os.path.join(ss.FABRIC_ROOT, "runtime", "hosts", "registry.json")
    return sorted((json.load(open(reg, encoding="utf-8")).get("placement") or {}))


def child_names(who: str) -> tuple[str, str, list[str]]:
    """(login, agent id, the names the child's store holds): entry names
    are file names, readable in the parent's mirror; values are not."""
    aid, rec = ss.resolve(who)
    mirror = os.path.join(ss.children_dir(), aid)
    if not os.path.isdir(mirror):
        raise ss.StoreError(f"no mirror of {rec.get('login') or who}'s store ({mirror}): store-enroll.sh {rec.get('login') or who} first")
    ss.pull(mirror)
    return rec.get("login") or who, aid, ss.names(mirror)


def identity(who: str, host: str, *, replace: bool = False) -> list[dict]:
    """A parent cannot read what it put, and GPG encrypts at random, so a
    put is never "unchanged": a name the child holds is left alone unless
    --replace (a login renamed, an account moved to another host)."""
    login, aid, have = child_names(who)
    rows = []
    for name, value in (("AGENT_LOGIN", login), ("AGENT_HOST", host)):
        if name in have and not replace:
            rows.append({"login": login, "name": name, "status": "present"})
            continue
        ss.put(aid, name, value.encode(), exact=True)
        rows.append({"login": login, "name": name, "status": "written"})
    return rows


def share(logins: list[str], names: list[str] | None = None, *, replace: bool = False) -> list[dict]:
    names = names or SHARED_NAMES
    bad = [n for n in names if n not in SHARED_NAMES]
    if bad:
        raise ss.StoreError(f"not a shared name: {', '.join(bad)} (store_provision.SHARED_NAMES; a login's own "
                            "value is put with `fabric-secrets store put`)")
    ss.pull()
    own = ss.values()
    rows = []
    for who in logins:
        try:
            login, aid, have = child_names(who)
        except ss.StoreError as e:
            rows.append({"login": who, "status": "failed", "reason": str(e)[:160]})
            continue
        for name in names:
            if name not in own:
                rows.append({"login": login, "name": name, "status": "skipped", "reason": "not in the parent's store"})
            elif name in have and not replace:
                rows.append({"login": login, "name": name, "status": "present"})
            else:
                try:
                    ss.put(aid, name, own[name].encode(), exact=True)
                    rows.append({"login": login, "name": name, "status": "written"})
                except ss.StoreError as e:
                    rows.append({"login": login, "name": name, "status": "failed", "reason": str(e)[:160]})
    return rows


def _http(method: str, url: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise ss.StoreError(f"{method} {url.split('/v1/', 1)[-1]} refused ({e.code}): {e.read()[:160].decode(errors='replace')}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise ss.StoreError(f"{method} {url.split('/v1/', 1)[-1]}: {getattr(e, 'reason', e)}")
    return json.loads(raw) if raw.strip() else {}


def _mint_openrouter(login: str, own: dict[str, str]):
    """A key named after the login, as the fleet's keys are; with the
    handle that deletes it again if the put fails, so a key never exists
    under a login's name that nothing records (review, 2026-09-16)."""
    prov = own.get("OPENROUTER_PROVISIONING_KEY")
    if not prov:
        raise ss.StoreError("OPENROUTER_PROVISIONING_KEY is not in the parent's store")
    base = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    body = _http("POST", f"{base}/keys", prov, {"name": login})
    key = body.get("key") or (body.get("data") or {}).get("key")
    if not key:
        raise ss.StoreError("OpenRouter returned no key")
    h = (body.get("data") or {}).get("hash") or ""

    def undo() -> bool:
        if not h:
            return False
        _http("DELETE", f"{base}/keys/{h}", prov)
        return True
    return key, undo


def _mint_openai(login: str, own: dict[str, str]):
    """A service account agent-fabric-<login> in the organisation's project:
    the only way to mint a project key programmatically, and the key is
    returned once — so one already there under this name (or the bare
    login, an earlier spelling) is replaced, never reused."""
    adm = own.get("OPENAI_ADMIN_KEY")
    if not adm:
        raise ss.StoreError("OPENAI_ADMIN_KEY is not in the parent's store")
    base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    pid = own.get("OPENAI_PROJECT_ID")
    if not pid:
        projs = [p for p in _http("GET", f"{base}/organization/projects?limit=50", adm).get("data", []) if p.get("status") == "active"]
        if len(projs) != 1:
            raise ss.StoreError(f"{len(projs)} active OpenAI projects; set OPENAI_PROJECT_ID in the parent's store")
        pid = projs[0]["id"]
    name = f"agent-fabric-{login}"
    existing = {s["name"]: s["id"] for s in _http("GET", f"{base}/organization/projects/{pid}/service_accounts?limit=100", adm).get("data", [])}
    for old in (name, login):
        if old in existing:
            _http("DELETE", f"{base}/organization/projects/{pid}/service_accounts/{existing[old]}", adm)
    sa = _http("POST", f"{base}/organization/projects/{pid}/service_accounts", adm, {"name": name})
    key = (sa.get("api_key") or {}).get("value")
    if not key:
        raise ss.StoreError("OpenAI returned no key with the service account")

    def undo() -> bool:
        if not sa.get("id"):
            return False
        _http("DELETE", f"{base}/organization/projects/{pid}/service_accounts/{sa['id']}", adm)
        return True
    return key, undo


def issue_key(service: str, logins: list[str], *, replace: bool = False) -> list[dict]:
    entry = KEY_NAMES[service]
    mint = _mint_openrouter if service == "openrouter" else _mint_openai
    ss.pull()
    own = ss.values()
    rows = []
    for who in logins:
        try:
            login, aid, have = child_names(who)
        except ss.StoreError as e:
            rows.append({"login": who, "status": "failed", "reason": str(e)[:160]})
            continue
        if entry in have and not replace:
            rows.append({"login": login, "name": entry, "status": "present"})
            continue
        try:
            key, undo = mint(login, own)
        except ss.StoreError as e:
            rows.append({"login": login, "name": entry, "status": "failed", "reason": str(e)[:160]})
            continue
        try:
            ss.put(aid, entry, key.encode(), exact=True)
            rows.append({"login": login, "name": entry, "status": "written"})
        except Exception as e:  # noqa: BLE001 — whatever stopped the put, the minted key must not outlive it unrecorded
            try:
                why = ("the key just minted was deleted again; re-run" if undo()
                       else f"the key just minted was NOT deleted (no handle for it): one for {login} exists that nothing records — delete it in the dashboard")
            except Exception:  # noqa: BLE001
                why = f"AND the minted key could not be deleted: one for {login} exists that nothing records — delete it in the dashboard"
            rows.append({"login": login, "name": entry, "status": "failed", "reason": f"{str(e)[:120]}; {why}"})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets provision", description="a parent fills its children's stores (ADR-038)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("identity")
    i.add_argument("login")
    i.add_argument("--host", required=True)
    i.add_argument("--replace", action="store_true")
    s = sub.add_parser("share")
    s.add_argument("logins", nargs="+")
    s.add_argument("--name", action="append", dest="names")
    s.add_argument("--replace", action="store_true")
    k = sub.add_parser("issue-key")
    k.add_argument("service", choices=sorted(KEY_NAMES))
    k.add_argument("logins", nargs="+")
    k.add_argument("--replace", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "identity":
            rows = identity(args.login, args.host, replace=args.replace)
        else:
            # `all` is every child: the parent holds its own store, not a mirror of it.
            logins = [l for l in placed_logins() if l != ss.login()] if args.logins == ["all"] else args.logins
            if args.cmd == "share":
                rows = share(logins, args.names, replace=args.replace)
            else:
                rows = issue_key(args.service, logins, replace=args.replace)
    except ss.StoreError as e:
        print(f"fabric-secrets provision: {e}", file=sys.stderr)
        return 1
    print(json.dumps(rows, indent=2))
    return 1 if any(r["status"] == "failed" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
