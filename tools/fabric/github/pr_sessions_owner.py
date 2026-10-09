"""tools/fabric/github/pr_sessions_owner.py — whose a pull request is: a
branch to the session or the role that owns it, this session's own
identity, and the /lastDate cutoff. Split out of pr_sessions.py,
unchanged; the rules and their reasons are in the docstrings below."""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from github import local  # noqa: E402
from github.pr_reply import BOT_OWNER_ROLE, branch_names_a_session  # noqa: E402

UNATTRIBUTED = "(unconventional)"


# BOT ROWS HAVE AN OWNER TOO — a ROLE, not a session. A Dependabot pull
# request belongs to devex-tooling (architect-cto decision, 2026-09-14):
# its review findings are answered by whichever session holds that role,
# and a group that fails to land is triaged by it. Before this map every
# bot row was "(unconventional)", outside every scope by construction, and
# 28 of the 31 unreachable rows were Dependabot — findings on them were
# routed to nobody. The deny-list of automation vendors (pr_reply.AUTOMATION,
# the one set both tools read) still says "not a session"; this map says
# whose the row is instead. A bot not listed stays unattributed, visibly.
BOT_OWNER = {vendor: "role:" + role for vendor, role in BOT_OWNER_ROLE.items()}


def conventional(branch: str) -> bool:
    """STRUCTURAL, not an allow-list of type words. CLAUDE.md specifies
    <host>/<clone>/<type>/<short-desc> and puts no vocabulary on <type>.
    The predicate used to require one of thirteen conventional-commit
    words, so any branch typed outside that set — `spike-3/`, `hotfix/`,
    `stage-4/` — was classified unconventional, given the session
    "(unconventional)", and then SILENTLY DROPPED by the default session
    scope: the command whose whole job is surfacing outstanding work
    quietly answering "none". Deliberately NO test on <type>: it required
    thirteen words once, then a lowercase shape; both guess at an
    open-ended set. pr-reply shares this predicate to decide whether it
    may WRITE to a PR, and there a wrong "not a session" means posting to
    a PR owned by another session — so the two agree on the SPECIFIED
    shape and nothing more.

    "Follows the convention" is the WHOLE shape, not just "has enough
    slashes": counting segments alone reported
    `dependabot/nuget/apps/backend_dotnet/…` as a session called
    "dependabot/nuget", and the footer then told you that apparent owner
    was a parallel session to stay out of the way of. The separator is a
    DENY-list of automation vendors, not an allow-list of type words, and
    the asymmetry is the point: the set of bots that open PRs on a
    repository is small, known, and changes rarely, while the set of
    legitimate <type> words is open-ended — and every omission from an
    allow-list silently deletes real work from this listing."""
    return branch_names_a_session(branch)


def session_of(branch: str) -> str:
    """The session the prefix names, or the ROLE a bot row maps to; a wrong
    owner is worse than a visible unknown, so anything else is
    "(unconventional)" rather than silently mis-attributed. The OWNER of a
    row and its session are one string."""
    p = branch.split("/")
    if conventional(branch):
        return p[0] + "/" + p[1]
    return BOT_OWNER.get(p[0]) or UNATTRIBUTED


def work_of(branch: str) -> str:
    return "/".join(branch.split("/")[2:]) if conventional(branch) else branch


class Me:
    """Who this session is, for the marker: the prefix of this agent,
    host/login, or — while older branches last — the prefix that named this
    working copy, or the role a bot row maps to."""

    def __init__(self, me: str, legacy: str, role: str):
        self.me, self.legacy, self.role = me, legacy, role

    def owns(self, owner: str) -> bool:
        return (owner == self.me or (self.legacy != "" and owner == self.legacy)
                or (self.role != "" and owner == "role:" + self.role))


def cutoff_for(spec: str, now: datetime | None = None) -> str | None:
    """<N>d / <N>h / <N>m to an ISO instant, or None when it is not that
    shape. A bare number is REFUSED rather than assumed to be days: guessing
    the unit on a time filter silently changes which PRs you are looking
    at. A span the calendar cannot hold is an OverflowError, as `date`
    failed on it."""
    m = re.fullmatch(r"([1-9][0-9]*)([dhm])", spec)
    if not m:
        return None
    unit = {"d": "days", "h": "hours", "m": "minutes"}[m.group(2)]
    at = (now or datetime.now(timezone.utc)) - timedelta(**{unit: int(m.group(1))})
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sh(cmd: list[str]) -> tuple[int, str]:
    """(exit status, stdout) of a command; 127 and nothing when it is not
    there, as a shell says."""
    return local.probe(cmd)


def who_am_i() -> tuple[str, str, str]:
    """(me, me_legacy, role): this session — the AGENT (the Linux login, as
    agent-fabric resolves it) on this host, which is what newer branch
    prefixes carry — or ("", "", "") outside a clone. Older branches carry
    the working-copy name in the second segment; me_legacy lets the default
    "mine" filter still find them while they last."""
    root = local.toplevel()
    if not root:
        return "", "", ""
    fabric = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    ident = os.path.join(fabric, "runtime", "identity.py")
    rc, agent = _sh([sys.executable, ident])
    if rc != 0:
        agent += _sh(["id", "-un"])[1]
    host = _sh(["hostname", "-s"])[1].rstrip("\n")
    me = f"{host}/{agent.rstrip(chr(10))}"
    # A working copy named after its repository (~/projects/<repo>) is every
    # login's default clone since the per-login clones were renamed, so its
    # name is no session's: taken for one, it made the pre-rename clone's
    # branches "mine" in every session (a managed project's review). Only a
    # clone with a name of its own carries a legacy prefix.
    remote = local.remote_url(root)
    repo_name = re.sub(r".*[/:]", "", re.sub(r"\.git$", "", remote))
    wc_name = os.path.basename(root)
    legacy = "" if repo_name and wc_name.lower() == repo_name.lower() else f"{host}/{wc_name}"
    # The ROLE this session holds (its runtime binding), because some rows
    # are owned by a role rather than by a session: a Dependabot pull request
    # is devex-tooling's, whichever login holds that role today. No binding,
    # no role — those rows are then nobody's here.
    role = _sh([sys.executable, ident, "--role"])[1].rstrip("\n")
    return me, legacy, role
