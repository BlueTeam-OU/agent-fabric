#!/usr/bin/env python3
"""tools/fabric/branches.py — local branch hygiene (ADR-022; ADR-040 Wave 3;
bin/fabric-branches is its shim).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      [--sweep [--all | --worktrees] | --json | -h | --help]; only the first argument
            is read (and `--all` or `--worktrees` as the second of `--sweep`), an empty one
            is none, and what else follows is ignored. `--sweep --worktrees` deletes no
            branch: the worktrees and the session scratch only (what `fabric-jobs switch`
            runs, since a queued job's branch may sit at the default branch's tip). --json is
            the control agent's read (`fabric-ctl <login> branches`): one JSON
            object on stdout, no fetch, nothing changed
  env       AGENT_FABRIC_BRANCHES_KEEP (absolute worktree paths, one per line,
            that a sweep keeps as "in use": the control agent names the
            worktrees a live process of this login stands in), then
            AGENT_FABRIC_STATE_DIR / XDG_STATE_HOME (through
            runtime/identity.py: where the sweep is recorded), PATH (git,
            gh); the working copy is the git toplevel of the current
            directory, which this changes into
  stdin     not read
  stdout    the report; --help
  stderr    every refusal, prefixed `fabric-branches: `; what git or gh
            said when a deletion they were asked for failed
  exit      0 reported, or swept; 3 (--json only) a working copy it cannot
            count: no default branch of origin known, or no origin/<default>
            here; 2 refused — an unknown argument, not in a
            git working copy, uncommitted changes with --sweep, a failed
            fetch, no default branch known (origin/HEAD unset and none in
            projects/registry.json) or none on origin, or a git call whose answer could not be
            read; 1 a sweep that deleted what it was to but could not record
            itself (or whose closing `git branch` failed)

Nothing is deleted from a remote, ever; a sweep deletes local branches and
worktrees only, and only what a fresh count and a fresh status still call
safe at the moment of deletion.

What a sweep removes, and why (the owner, 2026-10-19: pushed drains, job checkouts and review-head
checkouts piled up, 39 and 530 MB on one login in a day):
  - a linked worktree that is clean (no changes, no untracked file) and whose HEAD is reachable from a
    remote-tracking ref of a branch the remote still has (`git ls-remote`: a fetch without --prune keeps the ref
    of a branch the host deleted, and that is no proof), attached or detached: its commits live on the remote, so
    removing the directory loses nothing. Before this it also had to be on the default branch. Ignored files keep it, except Python
    bytecode (`__pycache__/`, `*.pyc`), which any run regenerates; a lock keeps it; so does the worktree the
    sweep runs in and any the caller names in use. The branch checked out in it is not touched;
  - with `--sweep --all`, that over every working copy of this login in the projects directory (the
    directories beside this one that have a `.git` directory of their own), each with its own fetch. One that
    cannot be fetched, or refuses, is named and skipped, never guessed: the rest are swept and the status is 1;
  - an ended Claude Code session's scratch under this login's claude-tmp cache ($TMPDIR/claude-<uid>/…/<session
    id>), unless the harness of this login's registry (~/.claude/sessions/<pid>.json) names it for a harness
    that is live by plan_hold's rule for its own markers, or it is the session running the command. A registry that
    cannot be read or understood calls no session ended, and is said: the worktrees a live session stands in are then known
    only through AGENT_FABRIC_BRANCHES_KEEP. A worktree a live session stands in is in use otherwise. Never
    another login's path, never a symlink.
What a sweep keeps it says with the reason (changes, commits on no remote, ignored files, lock, this one, in use,
live session); what it removes, with its size.

What differs from the bash, on purpose — every one a place where bash read a
failed git call as an answer, which for a command that deletes is the one
direction that must not happen:
  - a `git status`, `git worktree list` or `git for-each-ref` that fails is
    a refusal (exit 2), where bash read it as "no changes" / "no worktrees"
    / "no branches";
  - a linked worktree whose directory exists and whose status cannot be read
    is kept, with the reason "status unreadable", where bash called it
    clean and tried to remove it;
  - a branch whose short sha cannot be read is kept, where bash went on to
    delete it with an empty sha in the report; a name that starts with `-`
    is kept without asking git, where git would take it for an option;
  - a branch's commits that cannot be listed are said on stderr, where bash
    printed nothing;
  - the sweep's record that cannot be written is said and exits 1, where
    bash printed a traceback and exited with the last command's status;
  - pull requests are read as JSON (`gh pr list --json number,state`) and
    formatted here, where bash asked gh for a jq program (ADR-040 §5 rule 6);
  - every call is bounded: a call that does not answer is a failure.
Replicated, though odd: a branch whose upstream was pruned shows its
`b@{u}` spec on one line and `-` on the next; a branch whose commits cannot be counted shows `?`
and is kept; the local branch named for the default branch is never
listed; a worktree whose
`HEAD` line is empty is counted as the working copy's own HEAD.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gh  # noqa: E402
import git  # noqa: E402
import workingcopy  # noqa: E402

HELP = """bin/fabric-branches — local branch hygiene: what is left over in this
working copy, and the deletion of what is provably merged (agent-fabric
ADR-022).

  fabric-branches            report every local branch and worktree
  fabric-branches --sweep    report, then delete what shows 0
  fabric-branches --sweep --all   the same in every working copy of this login
                             beside this one
  fabric-branches --sweep --worktrees   the worktrees and the sessions' scratch only:
                             no branch is deleted (what fabric-jobs switch runs)
  fabric-branches --json     the same counts as one JSON object, without
                             fetching (what the control agent reads)

The number beside a branch is how many of its commits are NOT on the
remote's default branch — origin/HEAD, as the launcher reads it, else
the project's default_branch in projects/registry.json; main where that
is main — after a plain `git fetch origin`: a refspec fetch does not
move it, and a stale one makes merged work look unmerged. 0 means
everything on the branch is already on the default branch, so deleting
it loses nothing. --sweep deletes exactly those, re-counted at
deletion, and removes a worktree only when it has no changes, no
ignored files (Python bytecode excepted) and no lock, its commit is on a
remote (the default branch, or a pushed branch), and it is not the one
this runs in; it also removes the scratch of this login's ended Claude
Code sessions. What it keeps it says, with the reason; what it removes,
with its size. Anything with commits off it is reported
with its commits and its pull request, and kept: it is work still owed,
or the person's decision. The current branch and the default branch are
never touched.

Local only: no remote branch is deleted or pushed; the merge queue owns
those. A branch tracking another agent's remote branch is only a local
copy, deleted like any other when it shows 0.

Refused (exit 2) outside a git working copy, when the default branch is
unknown (never guessed), when the fetch fails, and for --sweep on a
working copy with uncommitted changes. A sweep that
completes is recorded, per working copy, in the agent's state; the
session-start hook says when this working copy's last one is old."""

# A fetch is the one call that scales with the remote, not the clone.
FETCH_TIMEOUT_S = 600
# Removing a worktree deletes its tree.
REMOVE_TIMEOUT_S = 600


class Refused(Exception):
    pass


def say(msg: str) -> None:
    # Flushed first: stdout and stderr to one pipe keep the order they had
    # when the bash echoed each line as it went.
    sys.stdout.flush()
    print(f"fabric-branches: {msg}", file=sys.stderr, flush=True)


def echo(line: str = "") -> None:
    # Flushed per line, as the bash's echo wrote: a reader that went away is
    # found at the next line, so a sweep stops between two deletions, and
    # never discovers it at exit.
    print(line, flush=True)


def read(*args: str, repo: str = ".", **kw) -> str:
    """A git call whose answer is needed: its stdout, or a Refused naming
    the call. A failure is never an empty answer."""
    try:
        return git.run(repo, *args, **kw).stdout
    except git.GitError as e:
        raise Refused(str(e)) from None


def lines_of(text: str) -> list[str]:
    """Lines as the shell counts them: newline-separated, no trailing
    empty one (str.splitlines would also split on form feeds)."""
    return text.rstrip("\n").split("\n") if text.rstrip("\n") else []


def default_branch() -> str | None:
    """The remote's default branch: origin/HEAD, as the launcher and the
    session-start hook read it; else the default_branch projects/
    registry.json gives this working copy's project. None when neither
    says: unknown, never guessed as main (a managed project's default can
    be master)."""
    try:
        r = git.run(".", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
    except git.GitError:
        r = None
    if r is not None and r.returncode == 0 and r.stdout.strip().startswith("origin/"):
        return r.stdout.strip()[len("origin/"):]
    # The registry's word for this working copy's project: its marker, else
    # its origin remote, matched as tools/fabric/workingcopy.py matches them.
    # The remote is read here, bounded: workingcopy's own git call is not.
    # What cannot be read is a refusal, as every other here (exit 2).
    try:
        registry = workingcopy.load_registry()
    except (OSError, ValueError) as e:
        raise Refused(f"projects/registry.json cannot be read ({e}); the default branch of origin is unknown") from None
    projects = registry.get("projects") if isinstance(registry, dict) else None
    if not isinstance(projects, dict):
        raise Refused("projects/registry.json has no projects map; the default branch of origin is unknown")
    if os.path.isfile(workingcopy.MARKER):
        try:
            with open(workingcopy.MARKER, encoding="utf-8") as fh:
                project = fh.read().strip()
        except (OSError, UnicodeDecodeError) as e:
            raise Refused(f"{workingcopy.MARKER} cannot be read ({e})") from None
        if project not in projects:
            raise Refused(f"{workingcopy.MARKER} names project {project!r}, which projects/registry.json does "
                          "not know; the default branch of origin is unknown")
    else:
        try:
            u = git.run(".", "remote", "get-url", "origin", check=False)
        except git.GitError as e:
            raise Refused(str(e)) from None
        try:
            project = workingcopy.project_for_remote(u.stdout.strip() if u.returncode == 0 else None, registry)
        except (AttributeError, TypeError) as e:
            raise Refused(f"projects/registry.json has a project entry that cannot be read ({e}); the default "
                          "branch of origin is unknown") from None
    entry = projects.get(project or "")
    name = entry.get("default_branch") if isinstance(entry, dict) else None
    return name if isinstance(name, str) and name else None


def ahead(ref: str, base: str) -> str:
    """How many commits of `ref` are not on `base` (origin/<default>); `?`
    when git cannot say, which is never 0."""
    try:
        r = git.run(".", "rev-list", "--count", f"{base}..{ref}", check=False)
    except git.GitError:
        return "?"
    n = r.stdout.strip()
    return n if r.returncode == 0 and re.fullmatch(r"[0-9]+", n) else "?"


def worktrees() -> list[dict]:
    """`git worktree list --porcelain`, each worktree as path, head, branch
    (short name, "" when detached) and locked."""
    found: list[dict] = []
    for line in lines_of(read("worktree", "list", "--porcelain")):
        if line.startswith("worktree "):
            found.append({"path": line[len("worktree "):], "head": "", "branch": "", "locked": False})
        elif not found:
            continue
        elif line.startswith("HEAD "):
            found[-1]["head"] = line.split()[1] if len(line.split()) > 1 else ""
        elif line.startswith("branch "):
            ref = line.split()[1] if len(line.split()) > 1 else ""
            found[-1]["branch"] = ref[len("refs/heads/"):]
        elif line.startswith("locked"):
            found[-1]["locked"] = True
    return found


def status_lines(path: str, *extra: str) -> list[str]:
    """A worktree's porcelain status, or None when git cannot say. A
    worktree whose directory is gone (prunable) has nothing on disk to
    lose: its status is empty."""
    if not os.path.lexists(path):
        return []
    try:
        r = git.run(path, "status", "--porcelain", *extra, check=False)
    except git.GitError:
        return None  # type: ignore[return-value]
    return lines_of(r.stdout) if r.returncode == 0 else None  # type: ignore[return-value]


def pull_requests(head: str) -> str:
    """`#7 OPEN, #9 MERGED` for a head, "" for none, `?` when gh cannot say."""
    try:
        rows = json.loads(gh.run(["pr", "list", "--head", head, "--state", "all", "--json", "number,state"],
                                 what="gh pr list"))
    except (gh.GhError, ValueError):
        return "?"
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return "?"

    def text(v) -> str:
        return v if isinstance(v, str) else json.dumps(v)
    return ", ".join(f"#{text(r.get('number'))} {text(r.get('state'))}" for r in rows)


def pr_head(branch: str) -> str:
    """A pull request's head is the remote branch, which a local branch
    may track under another name. Read from the branch's configuration,
    which outlives a pruned remote branch (a merged PR's, deleted by
    GitHub); @{u} fails once the remote-tracking ref is gone."""
    def config(key: str) -> str:
        try:
            r = git.run(".", "config", key, check=False)
        except git.GitError:
            return ""
        return r.stdout.rstrip("\n") if r.returncode == 0 else ""
    head = branch
    if config(f"branch.{branch}.remote") == "origin":
        merge = config(f"branch.{branch}.merge")
        if merge.startswith("refs/heads/"):
            head = merge[len("refs/heads/"):]
    return head


def load_identity():
    spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(ROOT, "runtime", "identity.py"))
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)  # type: ignore[union-attr]
    return identity


def record_sweep(top: str) -> None:
    """Per-agent state is written through runtime/identity.py (ADR-003): the
    record is a read-modify-write, and two sweeps of one login would
    otherwise lose one working copy's date."""
    identity = load_identity()
    with identity.agent_lock():
        path = os.path.join(identity.agent_state_dir(), "branch-sweep.json")
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            doc = doc if isinstance(doc, dict) else {}
        except (OSError, ValueError):
            doc = {}
        doc[top] = identity.now_iso()
        identity.atomic_write(path, json.dumps(doc, indent=2, sort_keys=True) + "\n")


# The directories live Claude Code sessions of this login stand in (their registry's cwd), filled by a sweep: a worktree one of
# them is in is in use, whichever session runs the sweep.
LIVE_CWDS: list[str] = []


def keep_paths() -> set[str]:
    """Worktrees the caller says a live process stands in (AGENT_FABRIC_BRANCHES_KEEP, one absolute path per
    line): removing one would pull the directory from under that process."""
    return {p for p in os.environ.get("AGENT_FABRIC_BRANCHES_KEEP", "").split("\n") if p}


def is_bytecode(path: str) -> bool:
    """An ignored path that is Python bytecode: any run regenerates it, so it never keeps a worktree
    (a `__pycache__/` directory is listed as one path, with its trailing slash)."""
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return name == "__pycache__" or name.endswith(".pyc")


def remote_refs(base: str) -> list[str] | None:
    """The remote-tracking refs of origin that the remote still has: `git ls-remote` against the local copies, because a
    fetch without --prune leaves the ref of a branch the host deleted, and a commit held only by that ref is not on the
    remote. When the remote cannot be asked, only `base` (just fetched, so proven) counts. None in `--json`, which does
    not touch the network and counts as the plain report always did."""
    try:
        r = git.run(".", "ls-remote", "--heads", "origin", check=False, timeout=FETCH_TIMEOUT_S)
        have = git.run(".", "for-each-ref", "--format=%(refname) %(objectname)", "refs/remotes/origin/", check=False)
    except git.GitError:
        return [base]
    if r.returncode != 0 or have.returncode != 0:
        return [base]
    # By name and by sha: a branch force-pushed since the fetch is no longer the commit the local ref holds.
    live = {f"refs/remotes/origin/{l.split(chr(9), 1)[1][len('refs/heads/'):]} {l.split(chr(9), 1)[0]}" for l in lines_of(r.stdout)
            if chr(9) in l and l.split(chr(9), 1)[1].startswith("refs/heads/")}
    # `base` always counts: it was fetched a moment ago, and a push to it since is not a reason to call its old tip unpushed.
    return sorted({l.split(" ", 1)[0] for l in lines_of(have.stdout) if l in live} | {base})


def unpushed(head: str, refs: list[str] | None = None) -> str:
    """How many commits of `head` are on none of `refs` (the remote's branches, remote_refs), or `?` when git cannot say,
    which is never 0: a worktree is removable when all its commits live on the remote. With no list, any remote-tracking
    ref counts (the report that does not fetch)."""
    try:
        if refs is None:
            r = git.run(".", "rev-list", "--count", head, "--not", "--remotes", check=False)
        else:
            r = git.run(".", "rev-list", "--count", "--stdin", check=False,
                        input=f"{head}\n" + "".join(f"^{ref}\n" for ref in refs))
    except git.GitError:
        return "?"
    n = r.stdout.strip()
    return n if r.returncode == 0 and re.fullmatch(r"[0-9]+", n) else "?"


def worktree_state(wt: dict, base: str, top: str, refs: list[str] | None = None) -> tuple[str, str]:
    """(commits not on base, why it is kept or "") for a linked worktree: kept whatever its count when it has
    changes, ignored files other than bytecode (a .env, a build) that removal deletes, commits on no remote, a
    lock (someone is using it), when it is the one this runs in, or when the caller names it in use."""
    path = wt["path"]
    changes = status_lines(path)
    ignored = status_lines(path, "--ignored", "-uall")   # each file: a package directory holding only bytecode is one `!! pkg/` without it
    n = ahead(wt["head"], base)
    why = ""
    if changes is None or ignored is None:
        why = "status unreadable"
    else:
        if changes:
            why = f"{len(changes)} uncommitted change(s)"
        n_ignored = sum(1 for l in ignored if l.startswith("!!") and not is_bytecode(l[3:]))
        if n_ignored:
            why = f"{why + ', ' if why else ''}{n_ignored} ignored path(s)"
    loose = unpushed(wt["head"], refs)
    if loose != "0":
        why = f"{why + ', ' if why else ''}{'commits on no remote unreadable' if loose == '?' else f'{loose} commit(s) on no remote'}"
    if wt["locked"]:
        why = f"{why + ', ' if why else ''}locked"
    if path == top:
        why = f"{why + ', ' if why else ''}this one"
    if path in keep_paths() or any(c == path or c.startswith(path + "/") for c in LIVE_CWDS):
        why = f"{why + ', ' if why else ''}in use"
    return n, why


def tree_bytes(path: str) -> int:
    """The bytes a directory holds, links counted as themselves and never followed."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path, onerror=lambda _e: None):
        # Files and links only: a directory's own size is the filesystem's block, not what is freed.
        for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def sessions_dir() -> str:
    """Where the harness of this login registers its sessions: under its configuration directory."""
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "sessions")


def live_sessions(registry: str | None = None) -> tuple[set[str], list[str]] | None:
    """(the ids of the sessions a live harness of this login runs, the directories they stand in), or None when that is not
    known: no registry, a file of it that cannot be read or understood. Unknown is never none; no session is then called ended.
    The harness writes ~/.claude/sessions/<pid>.json (pid, sessionId, procStart, cwd) for each session it runs; it is live by
    plan_hold's rule for its markers - the pid answers as this login and started when procStart says. The harness's own
    environment does not carry the id (only its children's does), so a scan of /proc would miss an idle session."""
    import plan_hold
    directory = registry or sessions_dir()
    try:
        names = sorted(n for n in os.listdir(directory) if n.endswith(".json"))
    except OSError:
        return None
    ids: set[str] = set()
    cwds: list[str] = []
    for name in names:
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            continue                      # the harness ended between the listing and the read
        except (OSError, ValueError):
            return None
        pid, sid = (doc.get("pid"), doc.get("sessionId")) if isinstance(doc, dict) else (None, None)
        if not isinstance(pid, int) or not isinstance(sid, str):
            return None
        if plan_hold.alive(str(pid), str(doc.get("procStart") or "")):
            ids.add(sid)
            if isinstance(doc.get("cwd"), str):
                cwds.append(doc["cwd"])
    return ids, cwds


def claude_tmp_root() -> str:
    """This login's claude-tmp cache: the harness writes its per-session scratch under $TMPDIR/claude-<uid>. The
    variable is the launcher's (the account's own TMPDIR), so no other login's directory is ever named."""
    return os.path.join(os.environ.get("TMPDIR") or "/tmp", f"claude-{os.geteuid()}")


def session_dirs(root: str) -> list[str]:
    """The `<session id>` directories under the cache: at its top, or one level down (the harness groups them by
    project). Only a real directory of this login whose name is a session id; a link or another login's is skipped."""
    out: list[str] = []
    uid = os.geteuid()

    def mine(path: str) -> bool:
        try:
            info = os.lstat(path)
        except OSError:
            return False
        return stat.S_ISDIR(info.st_mode) and info.st_uid == uid
    if not mine(root):
        return out
    for top in sorted(os.listdir(root)):
        path = os.path.join(root, top)
        if not mine(path):
            continue
        if SESSION_ID.fullmatch(top):
            out.append(path)
            continue
        for name in sorted(os.listdir(path)):
            inner = os.path.join(path, name)
            if SESSION_ID.fullmatch(name) and mine(inner):
                out.append(inner)
    return out


def sweep_sessions() -> None:
    """Remove the scratch of this login's ended sessions, and say what is removed (with its size) and what is
    kept (with why). A scratch directory is removed whole, never through a link."""
    root = claude_tmp_root()
    # Listed first: a session that starts after the listing has no directory in it, and one that started before is live below.
    found = session_dirs(root)
    registry = live_sessions()
    live = registry[0] if registry is not None else None
    mine = os.environ.get("CLAUDE_CODE_SESSION_ID", "")     # the session running this command, whatever the registry says
    for path in found:
        sid = os.path.basename(path)
        if live is None:
            echo(f"kept session scratch {path} — the sessions of this login cannot be listed: no session is called ended")
        elif sid in live or sid == mine:
            echo(f"kept session scratch {path} — live session")
        else:
            size = tree_bytes(path)
            shutil.rmtree(path, ignore_errors=True)
            echo(f"removed session scratch {path} ({human(size)})" if not os.path.lexists(path)
                 else f"kept session scratch {path} — could not be removed")


def last_sweep(top: str) -> str | None:
    """When this working copy was last swept, from the record a sweep writes (record_sweep); None for never
    or for a record that cannot be read."""
    try:
        with open(os.path.join(load_identity().agent_state_dir(), "branch-sweep.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    stamp = doc.get(top) if isinstance(doc, dict) else None
    return stamp if isinstance(stamp, str) else None


def fetched_at(top: str) -> float | None:
    """The modification time of the last fetch's FETCH_HEAD, as seconds: how old the counts' base is."""
    try:
        gitdir = read("rev-parse", "--absolute-git-dir").strip()
        return os.stat(os.path.join(gitdir, "FETCH_HEAD")).st_mtime
    except (Refused, OSError):
        return None


def report_json(top: str, current: str, dirty: int) -> int:
    """The counts of a plain report as one JSON object, for the control agent: no fetch (what it counts against
    is as old as `fetched_at` says), nothing changed. A count git could not give is null, never 0."""
    default = default_branch()
    if not default:
        say("the default branch of origin is unknown: origin/HEAD is unset and projects/registry.json names "
            "none for this working copy — nothing counted")
        return 3
    base = f"origin/{default}"
    if git.run(".", "rev-parse", "-q", "--verify", base, check=False).returncode != 0:
        say(f"no {base} here")
        return 3

    def count(n: str):
        return int(n) if n.isdigit() else None
    listing = worktrees()
    main_wt = listing[0]["path"] if listing else ""
    wts = []
    for wt in listing:
        if wt["path"] == main_wt:
            continue
        n, why = worktree_state(wt, base, top)
        wts.append({"path": wt["path"], "branch": wt["branch"] or None, "ahead": count(n), "kept_because": why or None})
    branches = [{"name": b, "ahead": count(ahead(b, base)), "current": b == current}
                for b in lines_of(read("for-each-ref", "--format=%(refname:short)", "refs/heads/")) if b != default]
    print(json.dumps({"working_copy": top, "current": current, "dirty": dirty, "default": default, "base": base,
                      "fetched_at": fetched_at(top), "last_sweep": last_sweep(top), "branches": branches,
                      "worktrees": wts}, sort_keys=True), flush=True)
    return 0


def sweep_one(b: str, checked_out: set[str], base: str) -> str:
    """Delete branch `b` if, counted again now, it is wholly on `base`,
    and say what was done in the report's words. Anything else — a count
    that is not 0 or cannot be had, a sha that cannot be read, a name git
    would take for an option, a refusal by git — is KEPT."""
    if b in checked_out:
        return f"KEPT {b} — checked out in a worktree that stays"
    sha = ""
    if not b.startswith("-"):
        try:
            s = git.run(".", "rev-parse", "--short", b, check=False)
            sha = s.stdout.strip() if s.returncode == 0 else ""
        except git.GitError:
            sha = ""
    if not sha or ahead(b, base) != "0":
        return f"KEPT {b}"
    try:
        d = git.run(".", "branch", "-q", "-D", b, check=False)
    except git.GitError as e:
        say(str(e))
        return f"KEPT {b}"
    if d.returncode != 0:
        if d.stderr:
            sys.stdout.flush()
            print(d.stderr, end="", file=sys.stderr, flush=True)
        return f"KEPT {b}"
    return f"deleted {b} ({sha})"


def git_top() -> str:
    try:
        top = git.toplevel(".")
    except git.GitError:
        top = None
    if not top:
        raise Refused("not in a git working copy")
    return top


def working_copies(top: str) -> list[str]:
    """Every working copy of this login in the projects directory (the one above this checkout): a directory of
    its own `.git` (a linked worktree has a `.git` file, and is swept through its main copy) that this login owns."""
    workspace = os.path.dirname(os.path.realpath(top))
    found = []
    for name in sorted(os.listdir(workspace)):
        path = os.path.join(workspace, name)
        try:
            if os.path.isdir(os.path.join(path, ".git")) and not os.path.islink(path) and os.stat(path).st_uid == os.geteuid():
                found.append(path)
        except OSError:
            continue
    return found


def sweep_all(top: str) -> int:
    """`--sweep` in every working copy, each with its own fetch. One that refuses (no fetch, changes, no default
    branch) is named and skipped, and the rest are swept: the status is 1 when any was skipped."""
    skipped: list[str] = []
    # Run from a linked worktree, the sweep of its main copy would not know it is the one standing here.
    here = [top, os.path.realpath(top)]
    os.environ["AGENT_FABRIC_BRANCHES_KEEP"] = "\n".join([*here, os.environ.get("AGENT_FABRIC_BRANCHES_KEEP", "")])
    for copy in working_copies(top):
        echo()
        echo(f"== {copy}")
        try:
            os.chdir(copy)
            rc = run(["--sweep"], scratch=False)
        except (Refused, git.GitError) as e:
            say(str(e))
            rc = 2
        if rc != 0:
            skipped.append(f"{copy} (exit {rc})")
    echo()
    echo("session scratch:")
    sweep_sessions()
    if skipped:
        echo(f"skipped, not swept or not recorded: {', '.join(skipped)}")
        return 1
    return 0


def run(argv: list[str], scratch: bool = True) -> int:
    first = argv[0] if argv else ""
    sweep = False
    branches = True
    if first == "":
        pass
    elif first == "--sweep":
        sweep = True
        if len(argv) > 1 and argv[1] == "--all":
            return sweep_all(git_top())
        if len(argv) > 1 and argv[1] not in ("--worktrees",):
            say(f"unknown argument '{argv[1]}' (--sweep takes --all or --worktrees)")
            return 2
        branches = not (len(argv) > 1 and argv[1] == "--worktrees")
    elif first == "--json":
        pass
    elif first in ("-h", "--help"):
        print(HELP, flush=True)
        return 0
    else:
        say(f"unknown argument '{first}' (--sweep)")
        return 2

    try:
        top = git.toplevel(".")
    except git.GitError:
        top = None
    if not top:
        say("not in a git working copy")
        return 2
    os.chdir(top)
    r = git.run(".", "symbolic-ref", "-q", "--short", "HEAD", check=False)
    current = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "(detached)"
    dirty = len(lines_of(read("status", "--porcelain")))

    if first == "--json":
        return report_json(top, current, dirty)
    echo(f"working copy: {top}")
    echo(f"on: {current}{f'  — {dirty} uncommitted change(s)' if dirty else ''}")
    if sweep and dirty:
        say("uncommitted changes here; commit or stash them first — nothing deleted")
        return 2

    # Fetched first: git 2.48 and later set a missing origin/HEAD on fetch,
    # so the default branch is read from what the fetch left. What it names
    # before the fetch is only for the failure's message.
    try:
        pre = git.run(".", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
        stale = pre.stdout.strip() if pre.returncode == 0 and pre.stdout.strip() else "default branch"
    except git.GitError:
        stale = "default branch"
    try:
        fetched = git.run(".", "fetch", "-q", "origin", check=False, timeout=FETCH_TIMEOUT_S)
        failed = fetched.returncode != 0
        err = (fetched.stdout + fetched.stderr).split("\n", 1)[0] if failed else ""
    except git.GitError as e:
        failed, err = True, e.reason
    if failed:
        say(f"git fetch origin failed ({err}); counting against a stale {stale} would call merged work "
            "unmerged — nothing done")
        return 2
    default = default_branch()
    if not default:
        say("the default branch of origin is unknown: origin/HEAD is unset (the fetch did not set it; git remote "
            "set-head origin --auto does) and projects/registry.json names none for this working copy — "
            "nothing counted")
        return 2
    base = f"origin/{default}"
    if git.run(".", "rev-parse", "-q", "--verify", base, check=False).returncode != 0:
        say(f"no {base} here")
        return 2
    refs = remote_refs(f"refs/remotes/{base}")
    registry = live_sessions()
    LIVE_CWDS[:] = registry[1] if registry is not None else []
    if registry is None:
        say(f"the sessions of this login cannot be listed ({sessions_dir()}): a worktree a live session stands in is "
            "known to be in use only through AGENT_FABRIC_BRANCHES_KEEP")

    identity = load_identity()
    host, login = identity.current_host(), identity.current_agent()
    mine = f"{host}/{login}/"

    # Worktrees first: a branch checked out in one cannot be deleted until
    # the worktree is gone.
    listing = worktrees()
    echo()
    echo("worktrees:")
    wt_remove: list[str] = []
    wt_count = 0
    main_wt = listing[0]["path"] if listing else ""
    # Kept whatever its count: the worktree this runs in (run from a linked
    # one, it is the session's own cwd), a locked one (someone is using it),
    # and one holding ignored files (a .env, a build) that removal deletes.
    for wt in listing:
        path = wt["path"]
        if path == main_wt:
            continue
        wt_count += 1
        n, why = worktree_state(wt, base, top, refs)
        echo(f"  {n:<3} {path}  {wt['branch'] or '(detached)'}  {why or 'clean'}")
        if not why:
            wt_remove.append(path)
    if not wt_count:
        echo("  (none besides the main one)")

    echo()
    echo(f"branches (commits not on {base}):")
    zero: list[str] = []
    kept: list[str] = []
    for b in lines_of(read("for-each-ref", "--format=%(refname:short)", "refs/heads/")):
        if b == default:
            continue
        n = ahead(b, base)
        try:
            u = git.run(".", "rev-parse", "--abbrev-ref", f"{b}@{{u}}", check=False)
            # Replicated from the bash: a failed `rev-parse --abbrev-ref`
            # (the remote-tracking ref pruned, the configured upstream
            # still naming it) printed the spec itself before it failed, and
            # `|| echo -` then added its own line, so the report shows
            # "b@{u}" over "-". A parser downstream of this output reads
            # that shape; fixing it is its own change.
            up = (u.stdout if u.returncode == 0 else u.stdout + "-\n").rstrip("\n")
        except git.GitError:
            up = "-"
        owner = ""
        if up.startswith("origin/"):
            rest = up[len("origin/"):]
            if not rest.startswith(mine) and rest.count("/") >= 2:
                owner = "  (tracks another agent's branch: never delete or push to the remote)"
        if b == current:
            owner += "  (current)"
        echo(f"  {n:<3} {b}  upstream={up}{owner}")
        if n == "0" and b != current:
            zero.append(b)
        elif n != "0":
            kept.append(b)

    for b in kept:
        echo()
        pr = pull_requests(pr_head(b))
        echo(f"  {b} — pull request: {pr or 'none'}")
        # A merged PR whose commits are not on the default branch was
        # squashed, or its history rewritten: the count cannot prove it
        # merged, the person can.
        if "MERGED" in pr:
            echo(f"      (merged, but these commits are not on {default}: squashed or rewritten — the person's decision)")
        try:
            log = git.run(".", "log", "--oneline", f"{base}..{b}", check=False)
            if log.returncode != 0:
                say(f"could not list the commits of {b}: {log.stderr.strip().splitlines()[-1] if log.stderr.strip() else f'exit {log.returncode}'}")
            for line in lines_of(log.stdout):
                echo(f"      {line}")
        except git.GitError as e:
            say(f"could not list the commits of {b}: {e.reason}")

    if not sweep:
        echo()
        echo(f"safe to delete (0): {' '.join(zero) or 'none'}; worktrees: {' '.join(wt_remove) or 'none'}. "
             "fabric-branches --sweep deletes exactly those.")
        return 0

    echo()
    for p in wt_remove:
        removed = False
        # Counted again now: a worktree that changed since the report is kept, with what changed.
        fresh = [w for w in worktrees() if w["path"] == p]
        why = worktree_state(fresh[0], base, top, refs)[1] if fresh else "gone"
        size = tree_bytes(p) if not why else 0
        if not why:
            try:
                rm = git.run(".", "worktree", "remove", p, check=False, timeout=REMOVE_TIMEOUT_S)
                removed = rm.returncode == 0
                if not removed and rm.stderr:
                    sys.stdout.flush()
                    print(rm.stderr, end="", file=sys.stderr, flush=True)
            except git.GitError as e:
                say(str(e))
        # The line the control agent parses (control/branches_op.py REMOVED_WORKTREE) stays as it was; the size follows.
        if removed:
            echo(f"removed worktree {p}")
            echo(f"  freed {human(size)}")
        else:
            echo(f"KEPT worktree {p}")
            if why:
                echo(f"  because {why}")
    pr_ = git.run(".", "worktree", "prune", check=False)
    if pr_.stderr:
        sys.stdout.flush()
        print(pr_.stderr, end="", file=sys.stderr, flush=True)
    # A branch checked out in a worktree that stays cannot be deleted; it is
    # kept with the reason rather than handed to git to refuse.
    try:
        checked_out = {w["branch"] for w in worktrees() if w["branch"]}
    except Refused as e:
        say(f"{e}: no branch was deleted")
        return 2
    for b in zero if branches else []:
        echo(sweep_one(b, checked_out, base))
    if kept:
        echo(f"kept, with commits off {default}: {' '.join(kept)} — work still owed, or the person's decision")
    if scratch:
        echo()
        echo("session scratch:")
        sweep_sessions()

    rc = 0
    try:
        record_sweep(top)
    except Exception as e:  # noqa: BLE001
        say(f"the sweep could not be recorded ({type(e).__name__}: {e}); the session-start hook will ask for another")
        rc = 1
    echo()
    try:
        listing_out = git.run(".", "branch", check=False)
    except git.GitError as e:
        say(str(e))
        return 1
    sys.stdout.write(listing_out.stdout)
    sys.stdout.flush()
    if listing_out.returncode != 0:
        say(f"git branch failed ({listing_out.stderr.strip() or listing_out.returncode})")
        rc = 1
    return rc


def main() -> int:
    # SIGPIPE stays ignored, as Python leaves it: a closed stdout raises
    # BrokenPipeError and the sweep stops where it is, between two
    # deletions, never in the middle of one.
    sys.stdout.reconfigure(errors="surrogateescape")
    sys.stderr.reconfigure(errors="surrogateescape")
    try:
        return run(sys.argv[1:])
    except Refused as e:
        say(str(e))
        return 2
    except git.GitError as e:
        say(str(e))
        return 2
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141


if __name__ == "__main__":
    sys.exit(main())
