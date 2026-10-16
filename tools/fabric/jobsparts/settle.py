"""tools/fabric/jobsparts/settle.py — the evidence `switch` asks of the job being left (ADR-037 rule 10, step 1).
A part of tools/fabric/jobs.py, whose docstring is the contract.

settle() returns what it checked and every thing that failed, so the refusal names all of them at once. A check that
cannot be told (gh, git or the journal did not answer) is a failure too, said as such: unknown is never settled."""
from __future__ import annotations

import calendar
import glob
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
# Any 7-40 hex word: an abbreviated sha can be all digits (one in 27 at seven characters) or all letters. A word that is no commit here
# is "not evidence" when probed, never a failure, so the loose reading costs a probe.
SHA = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])", re.ASCII)
# What a blocked job's free text must say to count as an owner's decision (rule 10: the one blocker no tool can check).
OWNER_DECISION = re.compile(r"\s*(?:owner(?:'s)?\s+decision|owner:|the owner(?:'s)?\s+decision)", re.IGNORECASE)
EVIDENCE_FORMS = "a pull request (owner/repo#N, #N or its URL), a commit sha, a branch on origin or reply:<MESSAGE-ID> (the reply's id or the id it answers)"
# A branch artifact is a ref name (or origin/<ref>) holding a slash. The pattern keeps a leading dash out of git's argv; whether a
# candidate is a branch at all is asked of git, so a path or a repo name that matches is no evidence and no failure.
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)+", re.ASCII)


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


def branches_of(job: dict) -> list[str]:
    """The ref names the job's artifacts hold (origin/<ref> without the prefix): candidates until git knows them."""
    names = []
    for art in job.get("artifacts") or []:
        bare = PR_URL.sub(" ", PR_FULL.sub(" ", MESSAGE_ID.sub(" ", str(art))))
        for word in bare.split():
            m = BRANCH.fullmatch(word.strip(".,;:()[]'\""))
            if m:
                names.append(m.group(0)[len("origin/"):] if m.group(0).startswith("origin/") else m.group(0))
    return list(dict.fromkeys(names))


def _branch_tips(job: dict, problems: list[str]) -> tuple[str | None, list[tuple[str, str]]]:
    """(the default branch, [(branch, tip)]) for the branch artifacts that are branches on origin now (asked of the remote, so a
    branch deleted there is none although its tracking ref lingers); (None, []) when there are none or git could not tell
    (said in `problems`). The default branch itself and origin/HEAD are no contributor branch: a job's note that it was "merged into origin/main" is no evidence of its work."""
    wc = job.get("working_copy")
    names = branches_of(job)
    if not names or not wc:
        return None, []
    try:
        vcs.fetch(wc)
        default = vcs.default_branch(wc)
        tips = []
        for name in names:
            if name in (default, "HEAD"):       # HEAD also fails remote_tip below; named so the intent does not hang on that
                continue        # by name, not by tip: a branch fast-forwarded into the default branch shares its tip and is still a branch
            r = vcs.run(wc, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}^{{commit}}", check=False)
            if r.returncode not in (0, 1):
                problems.append(f"could not tell whether {name} is a branch on origin (git rev-parse: exit {r.returncode})")
            elif r.returncode == 0 and vcs.remote_tip(wc, name) == r.stdout.strip():
                tips.append((name, r.stdout.strip()))
        return default, tips
    except vcs.VcsError as e:
        problems.append(f"could not tell whether a branch artifact is on origin ({e})")
        return None, []


def _journal():
    episodic = _load("fabric_episodic", os.path.join(FABRIC_ROOT, "tools", "fabric", "episodic.py"))
    path = episodic.db_path()
    if not os.path.exists(path):
        return None
    return episodic.open_readonly(path)


# An answer is a message this login sent and the carrier accepted (a failed or still pending one never reached the peer) that names
# what it answers: an empty IN-REPLY-TO names nothing, and SQLite does not count '' as NULL.
_ANSWERS = "direction='outbound' AND state='accepted' AND trim(coalesce(in_reply_to, '')) <> ''"


def replied(message_id: str) -> bool | str:
    """True when this login's journal holds a message of its own, accepted by the carrier, of any type but with a non-empty IN-REPLY-TO (a DECISION answers a REQUEST as a REPLY does), that answers `message_id` or is `message_id` (gzcoord-send prints only the
    reply's own id, so a holder cannot be asked for the answered one); False when not; a string saying why it could not be told.
    Both are UUIDv7s and only this login's accepted outbound rows with an IN-REPLY-TO are read, so neither reading can name another message."""
    try:
        conn = _journal()
        if conn is None:
            return False
        try:
            return conn.execute(f"SELECT 1 FROM episodes WHERE {_ANSWERS} "
                                "AND (lower(in_reply_to)=? OR lower(message_id)=?) LIMIT 1", (message_id, message_id)).fetchone() is not None
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 — an unreadable journal is "could not tell", never a traceback
        return f"journal: {e}"[:160]


def owed_replies(since: float | None) -> list[dict] | str:
    """The REQUESTs and QUESTIONs addressed to this login with REPLY-EXPECTED: yes, received at or after `since` (epoch seconds;
    None: all), that have no answer from it (any accepted outbound message whose IN-REPLY-TO names them, whatever its type), oldest first: [{"id", "type", "from", "subject"}]; a string saying why the
    journal could not be read. Scoped to the job (the owner's reading, 2026-10-14): an old message of another subject does not
    hold every switch hostage."""
    me = f"{identity.current_host()}/{identity.current_agent()}"
    try:
        conn = _journal()
        if conn is None:
            return []
        try:
            answered = {str(r[0]).lower() for r in conn.execute(
                f"SELECT in_reply_to FROM episodes WHERE {_ANSWERS}")}
            rows = conn.execute("SELECT message_id, type, sender, metadata_json, recorded_at FROM episodes WHERE direction='inbound' "
                                "AND type IN ('REQUEST', 'QUESTION') AND message_id IS NOT NULL ORDER BY recorded_at, rowid").fetchall()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        return f"journal: {e}"[:160]
    owed = []
    for mid, kind, sender, meta_json, received in rows:
        # Whether it was answered and whether it falls in the window are read from the row itself, so a row whose metadata cannot be
        # read still clears by a reply and by age; only what stays undetermined after them is owed.
        if str(mid).lower() in answered:
            continue
        at = None
        try:
            at = calendar.timegm(time.strptime(str(received), "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, OverflowError):
            pass
        if since is not None and at is not None and at < since:
            continue
        try:
            meta = json.loads(meta_json)
        except ValueError:
            meta = None
        readable = isinstance(meta, dict)
        if readable and (str(meta.get("REPLY-EXPECTED", "")).strip().lower() != "yes" or me not in re.split(r"[\s,]+", str(meta.get("TO", "")))):
            continue
        # A row that is neither readable nor dated cannot be told from one that asks for a reply: owed, never let through.
        if not readable or (since is not None and at is None):
            # A readable record still names its subject: the owed reply is found by what it is about.
            subject = "(its record could not be read)" if not readable else f"{str(meta.get('SUBJECT', ''))[:70]} (its receipt time could not be read)"
            owed.append({"id": mid, "type": kind, "from": sender, "subject": subject})
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


def main_worktree(working_copy: str) -> str | None:
    """The checkout that holds the repository's .git, when `working_copy` is a linked worktree of one: Claude Code keys
    a session launched in a worktree by the directory it was launched in, which is often the main checkout. None when
    the directory is no repository or the repository is bare. Raises VcsError when git does not answer for a repository:
    the caller says so rather than let the missing candidate read as an unwritten memory."""
    # Whether a repository is there is read from the filesystem: git exits 128 alike for "no repository" and for a broken
    # one, and its message is localised.
    if not os.path.isdir(working_copy):
        return None         # a worktree swept after its job landed is gone, not a git failure
    probe = os.path.abspath(working_copy)
    while not os.path.lexists(os.path.join(probe, ".git")):
        if os.path.dirname(probe) == probe:
            return None
        probe = os.path.dirname(probe)
    common = vcs.text(working_copy, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.dirname(common) if os.path.basename(common) == ".git" else None


def memory_candidates(candidates: list[str], notes: list[str] | None = None) -> list[str]:
    """Each working copy, the main checkout of its repository, and the ancestors of both below the login's home,
    deduplicated, nearest first. The workspace CLAUDE.md invites launching in ~/projects, above the checkout; the home's
    own key is a different session's, and a directory outside the home has no ancestors to claim (the filesystem root's
    key would belong to everyone). A sibling checkout is never a candidate. A git failure is appended to `notes`."""
    home = os.path.realpath(os.path.expanduser("~"))
    found: dict[str, None] = {}
    for c in candidates:
        if not c:
            continue
        try:
            main = main_worktree(c)
        except vcs.VcsError as e:
            main = None
            if notes is not None:
                notes.append(f"git could not name the main checkout of {c} ({e})")
        for d in (os.path.abspath(c), main):
            if d is None:
                continue
            if os.path.realpath(d) != home:        # the home's own key is another session's, even when the home is itself a repository
                found[d] = None
            if not os.path.realpath(d).startswith(home + os.sep):
                continue
            while True:
                d = os.path.dirname(d)
                if not os.path.realpath(d).startswith(home + os.sep):
                    break
                found[d] = None
    return list(found)


def memory_dirs(job: dict, candidates: list[str], notes: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(the memory directories that exist, every place looked for). A reflection job's lesson belongs where it applies,
    which is any project's memory of this login, not the checkout the job happened to run in."""
    layout = _load("fabric_layout", os.path.join(FABRIC_ROOT, "tools", "fabric", "layout.py"))
    tried = list(dict.fromkeys(layout.default_memory_dir(c) for c in memory_candidates(candidates, notes)))
    dirs = [d for d in tried if os.path.isdir(d)]
    if job.get("topic") == "reflection":
        every = os.path.expanduser("~/.claude/projects/*/memory")
        tried.append(every)
        dirs += [d for d in sorted(glob.glob(every)) if os.path.isdir(d) and d not in dirs]
    return dirs, tried


def memory_changed(job: dict, candidates: list[str]) -> str | None:
    """None when a memory file changed since the job started; otherwise the problem."""
    notes: list[str] = []
    dirs, tried = memory_dirs(job, candidates, notes)
    if not dirs:
        return ("no memory directory was found for this job's working copy (looked in " + ", ".join(tried)
                + ")" + "".join(f"; {n}" for n in notes) + "; write what the job taught you as a memory")
    since = started_at(job)
    if since is None:
        return f"{job['id']} has no readable start time, so memory changes cannot be dated"
    newest = 0.0
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError as e:
            return f"the memory directory {d} could not be read ({e.strerror or e})"
        for name in names:
            try:
                newest = max(newest, os.stat(os.path.join(d, name)).st_mtime)
            except FileNotFoundError:
                continue        # gone since the listing, or a dangling link: not a change
            except OSError as e:
                return f"{os.path.join(d, name)} could not be read ({e.strerror or e})"
    if newest <= since and notes:
        return f"could not tell whether {job['id']} wrote a memory: " + "; ".join(notes)
    if newest <= since:
        return (f"your memory directory has not changed during {job['id']}: write what it taught you "
                "(one fact per file, with a roles_class) before leaving it")
    return None


def _pr_state(repo: str, number: str) -> str:
    return str(vcs.gh.pr_view(int(number), ["state"], repo=repo).get("state") or "")


def _landed(job: dict, found: dict, problems: list[str], pr_state=_pr_state) -> list[str]:
    """The artifacts that show the work on the default branch, for `done`: merged PRs, commits on origin's default branch, replies.
    `pr_state(repo, number)` asks gh for a pull request's state; `sweep` hands in one that remembers, so a PR named by many jobs is asked once."""
    landed, opened = [], []
    wc = job.get("working_copy")
    for repo, number in found["prs"]:
        try:
            state = pr_state(repo, number)
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
    default, tips = _branch_tips(job, problems)
    unfolded = []
    for name, tip in tips:
        try:
            if vcs.question(wc, "merge-base", "--is-ancestor", tip, f"refs/remotes/origin/{default}"):
                landed.append(f"branch {name} on origin/{default}")
            else:
                unfolded.append(name)
        except vcs.VcsError as e:
            problems.append(f"could not tell whether branch {name} is on the default branch ({e})")
    # A squash- or rebase-merged pull request leaves its branch un-folded: other landed evidence settles the job, and
    # only a branch with nothing beside it is refused.
    if unfolded and not landed:
        problems.append(f"branch {', '.join(unfolded)} is not on origin/{default}: it is delivered, not done (or fold it first)")
    landed += _replies(found, problems)
    if opened:
        problems.append(f"{', '.join(opened)} is still open: the job is delivered, not done (fabric-jobs deliver)")
    return landed


def _reflected(job: dict, problems: list[str]) -> list[str]:
    """A reflection pass lands no PR, sha or branch: its artifact is the fabric-reflect cursor (ADR-058). Evidence when the
    cursor of this login was closed (`fabric-reflect done`) after the job started. Keyed on the topic, which fabric-reflect-jobs
    sets, never on the title prefix a person can reword by accident. No cursor, an older one and an unreadable one are
    problems: a cursor that cannot be read is not a pass."""
    if job.get("topic") != "reflection":
        return []
    fix = "run fabric-reflect done --through <row> first"
    try:
        reflect = _load("fabric_reflect", os.path.join(FABRIC_ROOT, "tools", "fabric", "reflect.py"))
        owner = reflect.episodic.own_agent_id()
        cur = reflect.read_cursor(owner)
    except Exception as e:  # noqa: BLE001 — CursorError, JournalError, a missing id: all "could not tell", never a traceback
        # Not `fix`: fabric-reflect done reads the same cursor and fails the same way; the error already names the working remedy.
        problems.append(f"the fabric-reflect cursor could not be read: {e}")
        return []
    if not cur:
        problems.append(f"no fabric-reflect pass has been closed: {fix}")
        return []
    since = started_at(job)
    try:
        done = calendar.timegm(time.strptime(str(cur.get("done_at")), "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OverflowError):
        problems.append(f"the fabric-reflect cursor has no readable done_at; {fix}")
        return []
    if since is None:
        problems.append(f"{job['id']} has no readable start time, so the fabric-reflect cursor cannot be dated")
        return []
    if done <= since:
        problems.append(f"the fabric-reflect cursor (row {cur['row']}, {cur['done_at']}) predates {job['id']}: {fix}")
        return []
    return [f"fabric-reflect cursor at row {cur['row']}, {cur['done_at']}"]


def _replies(found: dict, problems: list[str]) -> list[str]:
    out = []
    for mid in found["replies"]:
        said = replied(mid)
        if said is True:
            out.append(f"reply {mid[:8]} sent")
        elif said is False:
            problems.append(f"reply:{mid} names no answer this login sent (a message the carrier accepted, with IN-REPLY-TO: the id gzcoord-send printed for it, or the id of the message it answers; one that failed or is pending is sent again, not named); "
                            f"if it was recorded by mistake: fabric-jobs retract <id> reply:{mid}")
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
    default, tips = _branch_tips(job, problems)
    for name, tip in tips:
        try:
            folded = vcs.question(job["working_copy"], "merge-base", "--is-ancestor", tip, f"refs/remotes/origin/{default}")
        except vcs.VcsError as e:
            problems.append(f"could not tell whether branch {name} is on the default branch ({e})")
            continue
        if folded and not opened:
            problems.append(f"branch {name} is on origin/{default}: the job is done, not delivered (fabric-jobs done)")
        else:
            replies.append(f"branch {name} on origin")
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
        evidence = _landed(job, found, problems) + _reflected(job, problems)
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
