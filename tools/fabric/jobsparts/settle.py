"""tools/fabric/jobsparts/settle.py — the evidence `switch` asks of the job being left (ADR-037 rule 10, step 1).
A part of tools/fabric/jobs.py, whose docstring is the contract.

settle() returns what it checked and every thing that failed, so the refusal names all of them at once. A check that
cannot be told (gh, git or the journal did not answer) is a failure too, said as such: unknown is never settled."""
from __future__ import annotations

import calendar
import json
import os
import re
import time
from fabric_jobs import blockers as bl
from fabric_jobs import vcs
from fabric_jobs.base import FABRIC_ROOT, MESSAGE_ID, _load, identity

_REPO = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+"
PR_FULL = re.compile(rf"(?<![\w/.-])({_REPO})#([1-9][0-9]{{0,8}})\b", re.ASCII)
PR_URL = re.compile(rf"github\.com/({_REPO})/pull/([1-9][0-9]{{0,8}})", re.ASCII)
PR_BARE = re.compile(r"(?:\bPR\s*#?|(?<![\w/.-])#)([1-9][0-9]{0,8})\b", re.ASCII | re.IGNORECASE)
REPLY = re.compile(rf"\breply:({MESSAGE_ID.pattern})", re.ASCII)
SHA = re.compile(r"(?<![0-9a-zA-Z])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}(?![0-9a-zA-Z])", re.ASCII)
# What a blocked job's free text must say to count as an owner's decision (rule 10: the one blocker no tool can check).
OWNER_DECISION = re.compile(r"\s*(?:owner(?:'s)?\s+decision|owner:|the owner(?:'s)?\s+decision)", re.IGNORECASE)
EVIDENCE_FORMS = "a pull request (owner/repo#N, #N or its URL), a commit sha, or reply:<MESSAGE-ID>"


def artifacts_of(job: dict, repo: str | None) -> dict[str, list]:
    """What the job's artifacts name: {"prs": [(repo, n)], "shas": [...], "replies": [...]}. A bare #N is in the job's own repository."""
    prs: list[tuple[str, str]] = []
    shas: list[str] = []
    replies: list[str] = []
    for art in job.get("artifacts") or []:
        text = str(art)
        for m in REPLY.finditer(text):
            replies.append(m.group(1).lower())
        stripped = MESSAGE_ID.sub(" ", text)
        found = [(m.group(1), m.group(2)) for m in PR_URL.finditer(stripped)]
        found += [(m.group(1), m.group(2)) for m in PR_FULL.finditer(stripped)]
        taken = {n for _, n in found}
        if repo:
            found += [(repo, m.group(1)) for m in PR_BARE.finditer(PR_URL.sub(" ", stripped)) if m.group(1) not in taken]
        prs += found
        shas += [m.group(0) for m in SHA.finditer(PR_URL.sub(" ", stripped))]
    return {"prs": list(dict.fromkeys(prs)), "shas": list(dict.fromkeys(shas)), "replies": list(dict.fromkeys(replies))}


def _journal():
    episodic = _load("fabric_episodic", os.path.join(FABRIC_ROOT, "tools", "fabric", "episodic.py"))
    path = episodic.db_path()
    if not os.path.exists(path):
        return None
    return episodic.open_readonly(path)


def replied(message_id: str) -> bool | str:
    """True when this login's journal holds a REPLY of its own to `message_id`; False when not; a string saying why it could not be told."""
    try:
        conn = _journal()
        if conn is None:
            return False
        try:
            return conn.execute("SELECT 1 FROM episodes WHERE direction='outbound' AND type='REPLY' AND lower(in_reply_to)=? LIMIT 1",
                                (message_id,)).fetchone() is not None
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — an unreadable journal is "could not tell", never a traceback
        return f"journal: {e}"[:160]


def owed_replies(since: float | None) -> list[dict] | str:
    """The REQUESTs and QUESTIONs addressed to this login with REPLY-EXPECTED: yes, received at or after `since` (epoch seconds;
    None: all), that have no REPLY from it, oldest first: [{"id", "type", "from", "subject"}]; a string saying why the
    journal could not be read. Scoped to the job (the owner's reading, 2026-10-14): an old message of another subject does not
    hold every switch hostage."""
    me = f"{identity.current_host()}/{identity.current_agent()}"
    try:
        conn = _journal()
        if conn is None:
            return []
        try:
            answered = {str(r[0]).lower() for r in conn.execute(
                "SELECT in_reply_to FROM episodes WHERE direction='outbound' AND type='REPLY' AND in_reply_to IS NOT NULL")}
            rows = conn.execute("SELECT message_id, type, sender, metadata_json, happened_at FROM episodes WHERE direction='inbound' "
                                "AND type IN ('REQUEST', 'QUESTION') AND message_id IS NOT NULL ORDER BY happened_at, rowid").fetchall()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        return f"journal: {e}"[:160]
    owed = []
    for mid, kind, sender, meta_json, happened in rows:
        try:
            meta = json.loads(meta_json)
            at = calendar.timegm(time.strptime(str(happened), "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, OverflowError):
            owed.append({"id": mid, "type": kind, "from": sender, "subject": "(its record could not be read)"})
            continue
        if since is not None and at < since:
            continue
        if not isinstance(meta, dict) or str(meta.get("REPLY-EXPECTED", "")).strip().lower() != "yes":
            continue
        if me not in re.split(r"[\s,]+", str(meta.get("TO", ""))) or str(mid).lower() in answered:
            continue
        owed.append({"id": mid, "type": kind, "from": sender, "subject": str(meta.get("SUBJECT", ""))[:70]})
    return owed


def started_at(job: dict) -> float | None:
    """When the job last became active, as epoch seconds; its creation when it never did."""
    stamps = [e.get("at") for e in job.get("log") or [] if e.get("state") == "active"] or [job.get("created")]
    try:
        return calendar.timegm(time.strptime(str(stamps[-1]), "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return None


def memory_dirs(candidates: list[str]) -> list[str]:
    layout = _load("fabric_layout", os.path.join(FABRIC_ROOT, "tools", "fabric", "layout.py"))
    return [d for d in dict.fromkeys(layout.default_memory_dir(c) for c in candidates if c) if os.path.isdir(d)]


def memory_changed(job: dict, candidates: list[str]) -> str | None:
    """None when a memory file changed since the job started; otherwise the problem."""
    dirs = memory_dirs(candidates)
    if not dirs:
        return "no memory directory was found for this job's working copy; write what the job taught you as a memory"
    since = started_at(job)
    if since is None:
        return f"{job['id']} has no readable start time, so memory changes cannot be dated"
    newest = 0.0
    for d in dirs:
        try:
            for name in os.listdir(d):
                newest = max(newest, os.stat(os.path.join(d, name)).st_mtime)
        except OSError as e:
            return f"the memory directory {d} could not be read ({e.strerror or e})"
    if newest <= since:
        return (f"your memory directory has not changed during {job['id']}: write what it taught you "
                "(one fact per file, with a roles_class) before leaving it")
    return None


def _landed(job: dict, found: dict, problems: list[str]) -> list[str]:
    """The artifacts that show the work on the default branch, for `done`: merged PRs, commits on origin's default branch, replies."""
    landed, opened = [], []
    wc = job.get("working_copy")
    for repo, number in found["prs"]:
        try:
            state = str(vcs.gh.pr_view(int(number), ["state"], repo=repo).get("state") or "")
        except (vcs.gh.GhError, ValueError) as e:
            problems.append(f"could not tell whether {repo}#{number} is merged ({getattr(e, 'reason', e)})")
            continue
        (landed if state == "MERGED" else opened if state == "OPEN" else []).append(f"{repo}#{number} {state.lower()}")
    if found["shas"] and wc:
        try:
            default = vcs.default_branch(wc)
            vcs.fetch(wc)
            for sha in found["shas"]:
                if vcs.question(wc, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}") and vcs.question(wc, "merge-base", "--is-ancestor", sha, f"origin/{default}"):
                    landed.append(f"{sha[:12]} on origin/{default}")
        except vcs.VcsError as e:
            problems.append(f"could not tell whether a commit is on the default branch ({e})")
    landed += _replies(found, problems)
    if opened:
        problems.append(f"{', '.join(opened)} is still open: the job is delivered, not done (fabric-jobs deliver)")
    return landed


def _replies(found: dict, problems: list[str]) -> list[str]:
    out = []
    for mid in found["replies"]:
        said = replied(mid)
        if said is True:
            out.append(f"reply {mid[:8]} sent")
        elif said is False:
            problems.append(f"reply:{mid} is not in this login's journal as sent")
        else:
            problems.append(f"could not tell whether reply:{mid} was sent ({said})")
    return out


def _delivered(job: dict, found: dict, problems: list[str]) -> list[str]:
    opened, merged = [], []
    for repo, number in found["prs"]:
        try:
            state = str(vcs.gh.pr_view(int(number), ["state"], repo=repo).get("state") or "")
        except (vcs.gh.GhError, ValueError) as e:
            problems.append(f"could not tell whether {repo}#{number} is open ({getattr(e, 'reason', e)})")
            continue
        (opened if state == "OPEN" else merged if state == "MERGED" else []).append(f"{repo}#{number}")
    replies = _replies(found, problems)
    if merged and not opened:
        problems.append(f"{', '.join(merged)} is merged: the job is done, not delivered (fabric-jobs done)")
    return [f"{p} open" for p in opened] + replies


def _pushed(job: dict, problems: list[str]) -> list[str]:
    branch, where = job.get("branch"), job.get("worktree") or job.get("working_copy")
    if not branch or not where:
        problems.append("a paused job names the branch holding its work: pause it from that branch's checkout "
                        f"(fabric-jobs pause {job['id']} \"<why>\")")
        return []
    try:
        tip = vcs.remote_tip(where, branch)
        if tip is None:
            problems.append(f"branch {branch} is not on origin: push it, so the paused work survives this checkout")
            return []
        vcs.fetch(where)
        local = vcs.text(where, "rev-parse", f"refs/heads/{branch}")
        if not vcs.question(where, "merge-base", "--is-ancestor", local, f"refs/remotes/origin/{branch}"):
            problems.append(f"branch {branch} has commits origin does not: push it")
            return []
    except vcs.VcsError as e:
        problems.append(f"could not tell whether branch {branch} is pushed ({e})")
        return []
    return [f"branch {branch} pushed"]


def _blocker(job: dict, problems: list[str]) -> list[str]:
    specs = bl.specs_of(job)
    on = str(job.get("blocked_on") or "")
    if specs:
        cache = bl.refresh(specs, check=True)
        if bl.cleared_flag(job, cache) is True:
            problems.append(f"every blocker of {job['id']} has cleared ({', '.join(specs)}): it is not blocked; start it, or deliver or finish it")
            return []
        return [f"blocked on {', '.join(specs)}"]
    if OWNER_DECISION.match(on):
        return [f"blocked on {on[:80]}"]
    problems.append(f"{job['id']} is blocked on free text: name what it waits on with --on pr:<owner/repo>#<n>, request:<message-id> "
                    "or job:<login>/j<n> (or --on-request), or state the owner's decision as \"owner: <what is awaited>\"")
    return []


def settle(job: dict, places: list[str], session_start: float | None = None) -> tuple[list[str], list[str]]:
    """(the evidence found, the problems) for leaving `job` in the state it is in. `places` are the working copies whose
    state and memory count: the job's own and the one this command runs in."""
    problems: list[str] = []
    state = job["state"]
    # From the job's start, or this session's, whichever is earlier: a message that arrived while it worked is owed.
    starts = [t for t in (started_at(job), session_start) if t is not None]
    duty_since = min(starts) if starts else None
    repo = None
    if job.get("working_copy"):
        try:
            repo = vcs.gh.this_repo(job["working_copy"])
        except vcs.gh.GhError:
            repo = None
    found = artifacts_of(job, repo)
    if state == "done":
        evidence = _landed(job, found, problems)
        if not evidence and not problems:
            problems.append(f"done needs evidence it landed: deliver {EVIDENCE_FORMS} that is merged or on the default branch")
    elif state == "delivered":
        evidence = _delivered(job, found, problems)
        if not evidence and not problems:
            problems.append(f"delivered needs an artifact that is open: fabric-jobs deliver {job['id']} {EVIDENCE_FORMS}")
    elif state == "blocked":
        evidence = _blocker(job, problems)
    elif state == "paused":
        evidence = _pushed(job, problems)
    elif state == "dropped":
        evidence = [f"dropped: {job['reason']}"] if str(job.get("reason") or "").strip() else []
        if not evidence:
            problems.append("a dropped job needs a reason: fabric-jobs drop <id> \"<why>\"")
    else:
        evidence = []
        problems.append(f"{job['id']} is {state}: settle it first (done, delivered, blocked, paused or dropped)")
    for place in places:
        if not os.path.isdir(place):
            continue        # a worktree swept after its job landed has nothing uncommitted; a directory that exists and cannot be read is still unknown
        try:
            lines = vcs.dirty(place)
        except vcs.VcsError as e:
            problems.append(f"could not tell whether {place} has uncommitted changes ({e})")
            continue
        if lines:
            problems.append(f"{place} has uncommitted changes ({lines[0].strip()[:60]}{', …' if len(lines) > 1 else ''}): commit them")
    owed = owed_replies(duty_since)
    if isinstance(owed, str):
        problems.append(f"could not tell whether every reply you owe was sent ({owed})")
    else:
        for m in owed:
            problems.append(f"unanswered, REPLY-EXPECTED: yes, from {m['from']}: {m['subject']} ({m['id']}); answer it with gzcoord-send")
    why = memory_changed(job, places)
    if why:
        problems.append(why)
    if not problems:
        evidence += ["working copy clean", "replies answered", "memory written"]
    return evidence, problems
