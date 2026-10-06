#!/usr/bin/env python3
"""tools/fabric/branches.py — local branch hygiene (ADR-022; ADR-040 Wave 3;
bin/fabric-branches is its shim).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      [--sweep | -h | --help]; only the first argument is read, an
            empty one is none, and what follows it is ignored
  env       AGENT_FABRIC_STATE_DIR / XDG_STATE_HOME (through
            runtime/identity.py: where the sweep is recorded), PATH (git,
            gh); the working copy is the git toplevel of the current
            directory, which this changes into
  stdin     not read
  stdout    the report; --help
  stderr    every refusal, prefixed `fabric-branches: `; what git or gh
            said when a deletion they were asked for failed
  exit      0 reported, or swept; 2 refused — an unknown argument, not in a
            git working copy, uncommitted changes with --sweep, a failed
            fetch, no default branch known (origin/HEAD unset and none in
            projects/registry.json) or none on origin, or a git call whose answer could not be
            read; 1 a sweep that deleted what it was to but could not record
            itself (or whose closing `git branch` failed)

Nothing is deleted from a remote, ever; a sweep deletes local branches and
worktrees only, and only what a fresh count and a fresh status still call
safe at the moment of deletion.

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
and is kept; a local branch named `main` is never listed; a worktree whose
`HEAD` line is empty is counted as the working copy's own HEAD.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
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

The number beside a branch is how many of its commits are NOT on the
remote's default branch — origin/HEAD, as the launcher reads it, else
the project's default_branch in projects/registry.json; main where that
is main — after a plain `git fetch origin`: a refspec fetch does not
move it, and a stale one makes merged work look unmerged. 0 means
everything on the branch is already on the default branch, so deleting
it loses nothing. --sweep deletes exactly those, re-counted at
deletion, and removes a worktree only when it has no changes, no
ignored files and no lock, its commit is on the default branch, and it
is not the one this runs in. Anything with commits off it is reported
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
    project = workingcopy.resolve(".").get("project")
    entry = (workingcopy.load_registry().get("projects") or {}).get(project or "") or {}
    name = entry.get("default_branch")
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


def run(argv: list[str]) -> int:
    first = argv[0] if argv else ""
    sweep = False
    if first == "":
        pass
    elif first == "--sweep":
        sweep = True
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

    echo(f"working copy: {top}")
    echo(f"on: {current}{f'  — {dirty} uncommitted change(s)' if dirty else ''}")
    if sweep and dirty:
        say("uncommitted changes here; commit or stash them first — nothing deleted")
        return 2

    default = default_branch()
    if not default:
        say("the default branch of origin is unknown: origin/HEAD is unset (git remote set-head origin --auto "
            "sets it) and projects/registry.json names none for this working copy — nothing counted")
        return 2
    base = f"origin/{default}"
    try:
        fetched = git.run(".", "fetch", "-q", "origin", check=False, timeout=FETCH_TIMEOUT_S)
        failed = fetched.returncode != 0
        err = (fetched.stdout + fetched.stderr).split("\n", 1)[0] if failed else ""
    except git.GitError as e:
        failed, err = True, e.reason
    if failed:
        say(f"git fetch origin failed ({err}); counting against a stale {base} would call merged work "
            "unmerged — nothing done")
        return 2
    if git.run(".", "rev-parse", "-q", "--verify", base, check=False).returncode != 0:
        say(f"no {base} here")
        return 2

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
        changes = status_lines(path)
        ignored = status_lines(path, "--ignored")
        n = ahead(wt["head"], base)
        why = ""
        if changes is None or ignored is None:
            why = "status unreadable"
        else:
            if changes:
                why = f"{len(changes)} uncommitted change(s)"
            n_ignored = sum(1 for l in ignored if l.startswith("!!"))
            if n_ignored:
                why = f"{why + ', ' if why else ''}{n_ignored} ignored path(s)"
        if wt["locked"]:
            why = f"{why + ', ' if why else ''}locked"
        if path == top:
            why = f"{why + ', ' if why else ''}this one"
        echo(f"  {n:<3} {path}  {wt['branch'] or '(detached)'}  {why or 'clean'}")
        if n == "0" and not why:
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
        clean = status_lines(p, "--ignored")
        if clean is not None and not clean:
            try:
                rm = git.run(".", "worktree", "remove", p, check=False, timeout=REMOVE_TIMEOUT_S)
                removed = rm.returncode == 0
                if not removed and rm.stderr:
                    sys.stdout.flush()
                    print(rm.stderr, end="", file=sys.stderr, flush=True)
            except git.GitError as e:
                say(str(e))
        echo(f"removed worktree {p}" if removed else f"KEPT worktree {p}")
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
    for b in zero:
        echo(sweep_one(b, checked_out, base))
    if kept:
        echo(f"kept, with commits off {default}: {' '.join(kept)} — work still owed, or the person's decision")

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
