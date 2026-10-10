"""tools/fabric/provisioning/store_step.py — step 5, the account's key and store,
and the Claude account's token (ADR-038, ADR-031): the template read before an
account is made, the store filled by the PARENT, the token assigned, the login's
kind read from the hosts registry (carried from tools/fabric/new_agent.py)."""
from __future__ import annotations

import collections
import json
import sys

from provisioning import config as cfg
from provisioning.new_agent_args import FINGERPRINT, die, say
from provisioning.steps import Steps


def claude_template(s: Steps, slug: str) -> str:
    """The fingerprint of the template's token in this login's store, or a
    refusal: an unknown slug, a template with no token, and a store that
    did not answer are all refused here, before any account is made — the
    same refusals as fabric-accounts assign (tools/fabric/control/accounts.py)."""
    rc, out = s.capture([cfg.SECRETS, "store", "templates", "--json"])
    try:
        rows = json.loads(out) if rc == 0 else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        s.tail(3)
        die(f"this login's Claude account templates could not be read (fabric-secrets store templates, exit {rc}); "
            "nothing made")
    t = next((r for r in rows if isinstance(r, dict) and r.get("account") == slug), None)
    if t is None:
        die(f"'{slug}' is not a template in this store (fabric-accounts templates); nothing made")
    fp = t.get("token_sha256_12")
    if fp is None:
        die(f"template {slug} holds no CLAUDE_CODE_OAUTH_TOKEN yet; nothing made")
    if not isinstance(fp, str) or not FINGERPRINT.fullmatch(fp):
        die(f"template {slug}: the store answered a fingerprint that is not one ({fp!r}); nothing made")
    return fp


def login_kind(reg: dict, login: str, path: str) -> str:
    """The login's kind (ADR-044 rule 1): `kinds` names a human; a login it
    does not name is an agent. A kinds that is not a table, or a kind that
    is neither, is refused: the run would make the wrong pieces."""
    kinds = reg.get("kinds") or {}
    kind = kinds.get(login, "agent") if isinstance(kinds, dict) else None
    if kind not in ("agent", "human"):
        die(f"{path}: the kind of {login} cannot be read (kinds is a table of agent or human); nothing made")
    return kind


# The one shared name a human's work needs: its reads of the state stream
# and its messages (ADR-044 rule 3). provision share's allowlist holds it.
HUMAN_SHARED = "CLAUDE_BRIDGE_AUTH_TOKEN"


# A human has no projects to name its channel; the fleet's channel is the
# control plane's (projects/agent-fabric/integration/gzcoord).
HUMAN_CHANNEL_PROJECT = "agent-fabric"


def secrets_step(s: Steps, login: str, host: str, projects: list[str], slug: str, fp: str, *,
                 human: bool = False) -> None:
    if s.capture([sys.executable, cfg.STORE, "export-key"])[0] != 0:
        die("this login has no store of its own, so it cannot be a parent: store-enroll.sh --self first; nothing after "
            "it ran")
    if s.indented([cfg.STORE_ENROLL, login, "--host", host, "--born-now"])[0] != 0:
        die(f"step failed: store-enroll.sh {login}; nothing after it ran")

    def provision(label: str, *args: str) -> list:
        """One line per run, statuses only; the rows, [] when unreadable."""
        rc, rows = s.capture([cfg.SECRETS, "provision", *args])
        if rc != 0:
            s.tail(3)
            die(f"step failed: fabric-secrets provision {' '.join(args)}; nothing after it ran")
        try:
            parsed = json.loads(rows)
            counts = collections.Counter(r["status"] for r in parsed)
            summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "nothing to do"
        except (ValueError, TypeError, KeyError):
            parsed, summary = [], ""
        say(f"   {label}: {summary}")
        return parsed if isinstance(parsed, list) else []
    provision("identity", "identity", login, "--host", host)
    if human:
        # The one name is the human's whole use of its store: a row that is
        # not written or present (the parent lacks it, or no row) stops here.
        rows = provision("relay credential", "share", login, "--name", HUMAN_SHARED)
        if not any(isinstance(r, dict) and r.get("name") == HUMAN_SHARED and r.get("status") in ("written", "present")
                   for r in rows):
            die(f"step failed: {HUMAN_SHARED} did not reach {login}'s store (above); nothing after it ran")
        projects = [HUMAN_CHANNEL_PROJECT]
    else:
        provision("shared names", "share", login)
        provision("OpenRouter key", "issue-key", "openrouter", login)
        provision("OpenAI key", "issue-key", "openai", login)
    if slug:
        assign(s, login, slug, fp)
    as_account = [cfg.HX, host, "--as", login, "--"]
    # The filled store reaches the account as a bundle: its SSH key is in
    # it, so it could not pull it (store-enroll's first contact). Then
    # synced as the account, from its own checkout, without a pull: 2 is
    # "applied, names missing", said by the verification in finish; 1 and
    # 3 are a store the account cannot read or one naming someone else.
    bundled, taken = s.indented([sys.executable, cfg.STORE, "child-bundle", login],
                                [*as_account, "projects/agent-fabric/bin/fabric-secrets", "store", "take-bundle"])
    if bundled != 0 or taken != 0:
        die(f"step failed: its store did not reach {login} as a bundle; nothing after it ran")
    rc = s.indented([*as_account, "projects/agent-fabric/bin/fabric-secrets", "sync", "--quiet", "--no-pull"])[0]
    if rc not in (0, 2):
        die(f"step failed: fabric-secrets sync as {login} (exit {rc}); nothing after it ran")
    # Its GZCoord cursor at the channel's newest message: a consumer the
    # relay has never seen reads from the first message it holds, and
    # everything before the account existed is someone else's history.
    # Not fatal: an account whose cursor stayed behind still works, it only
    # reads old traffic once.
    if s.indented([*as_account, "python3", "projects/agent-fabric/tools/fabric/relay_catchup.py", *projects])[0] != 0:
        say("   its inbox cursor was not moved (above); its first session reads the channel's backlog")
    say("5. its key made and certified, its store filled and synced; commit identities/keys/, then write its recovery "
        "copy and back up:")
    say(f"     fabric-host {host} run --as {login} -- projects/agent-fabric/bin/fabric-secrets store recovery-copy")
    say("     fabric-secrets store backup")


def assign(s: Steps, login: str, slug: str, fp: str) -> None:
    """The template's token into the child's store, by fabric-accounts'
    own writer, before the bundle carries the store to the account: its
    first sync applies it. assign prints every row and exits 1 when one
    failed; a row other than this login's, or none, is no answer."""
    rc, out = s.capture([cfg.SECRETS, "store", "assign", slug, login, "--json"])
    try:
        rows = json.loads(out)
    except ValueError:
        rows = None
    row = rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else {}
    if rc != 0 or row.get("status") not in ("written", "unchanged") or row.get("login") != login:
        s.tail(3)
        why = f": {row['reason']}" if isinstance(row.get("reason"), str) else f" (exit {rc})"
        die(f"step failed: fabric-secrets store assign {slug} {login}{why}; nothing after it ran")
    # The template is read twice, here and before the account was made; one
    # replaced in between is not the account the run checked.
    if row.get("token_sha256_12") != fp:
        die(f"step failed: fabric-secrets store assign {slug} {login} wrote token {row.get('token_sha256_12')}, not the "
            f"{fp} checked at the start (the template changed); nothing after it ran")
    say(f"   Claude account: {slug}, {row['status']} (token {fp})")
