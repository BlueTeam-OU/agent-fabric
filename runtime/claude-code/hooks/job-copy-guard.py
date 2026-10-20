#!/usr/bin/env python3
"""runtime/claude-code/hooks/job-copy-guard.py — the job copy guard (agent-fabric ADR-037 rule 3; j323;
job-copy-guard.sh beside it is its forwarder, run by the PreToolUse hook on Bash of
runtime/claude-code/workspace/settings.json and .claude/settings.json).

CONTRACT:
  argv      none read
  stdin     the PreToolUse payload, JSON: agent_id, tool_name, cwd, session_id, tool_input.command
  env       CLAUDE_CODE_SESSION_ID (before the payload's session_id, as plan_hold.py reads it); AGENT_FABRIC_ROOT
            (empty or unset: the checkout three directories above this file), where tools/fabric/jobsparts/ and
            runtime/identity.py are; what identity.py reads to find the login's job list (XDG_STATE_HOME,
            AGENT_FABRIC_STATE_DIR); HOME (`~`, a bare `cd`); PATH (git)
  stdout    nothing (allow); or one compact line, a deny or an ask
  stderr    nothing of its own
  exit      0, always; a payload it cannot read is allowed and said nothing about. A crash is a non-zero exit,
            which the forwarder turns into an ask.

DECISIONS, in order, with their exact words:
  1. a payload that is not a JSON object, a tool_name other than Bash, or no command   -> nothing
  2. agent_id present and non-empty (a subagent)                                        -> nothing
     Subagents run in worktrees under the session clone; the subagent clone guard fences them.
  3. the command does not commit or publish                                             -> nothing
     It commits or publishes when it holds `git commit|push|merge|rebase|cherry-pick|am` (git's global options,
     `-C <dir>` among them, may come before the subcommand), `gh pr create|merge`, or `fabric-pr <verb>` for any
     verb but the read-only ones in READ_ONLY_PR_VERBS (an unknown verb counts). Found anywhere in the command,
     a `bash -c`/`sh -c`/`eval` script and a heredoc fed to a shell included. The job list is not read before
     this point, so a command that does not commit or publish never asks.
  4. the job list or the module that reads it cannot be read                           -> ask:
       "The job copy guard could not read this login's job list (<what failed>). Approve only if this command
       does not commit or publish outside the working copy of this session's job (agent-fabric ADR-037 rule 3)."
  5. this session worked a job W other than the active one (records.session_worked, asked of the list without
     the active job), with a job J active                                               -> deny:
       "This session worked job W, which has left active; job J is active now, and it belongs to a fresh
       session. This command commits or publishes (<what>). Once a session has worked a job, the next one runs
       in a fresh session (agent-fabric ADR-037 rule 3): run `fabric-jobs switch` (or the `fabric-fresh --job J`
       it printed) and do this work there. Reading working copies is allowed."
  6. the same, with no job active                                                       -> deny:
       "This session worked job W, which has left active, and no job is active. This command commits or publishes
       (<what>). Once a session has worked a job, the next one runs in a fresh session (agent-fabric ADR-037 rule
       3): run `fabric-jobs switch`, and let the next job (or a REQUEST that asked for this, which intake already
       queued as a job; anything else, add it with `fabric-jobs add`) run in the fresh session switch prints.
       Reading working copies is allowed."
  7. no job active (and none worked here: an unbound session, the owner's own)         -> nothing
  8. job J active, recording neither a working copy nor a worktree                      -> ask:
       "Job J records no working copy, so the job copy guard cannot tell where this session may commit or publish.
       Approve only if this command acts in the working copy of job J (agent-fabric ADR-037 rule 3)."
  9. a directory the command acts in whose git toplevel lookup timed out                -> ask:
       "The job copy guard could not resolve <dir> to its checkout (git rev-parse timed out). Approve only if
       this command does not commit or publish outside job J's working copy <copies> (agent-fabric ADR-037 rule 3)."
 10. any directory the command acts in lies outside J's working copy and worktree       -> deny:
       "This session works job J in <copies>; this command commits or publishes (<what>) in <dir>, outside it. A
       session works one job's working copy (agent-fabric ADR-037 rule 3): finish or block this job, run
       `fabric-jobs switch`, and let the next job (or a REQUEST that asked for this, which intake already queued
       as a job; anything else, add it with `fabric-jobs add`) run in the fresh session switch prints. Reading
       other working copies is allowed."
 11. otherwise                                                                          -> nothing

THE DIRECTORIES A COMMAND ACTS IN, over-reported rather than modelled: the payload's cwd, every `cd`/`pushd` target
anywhere in the command (a bare `cd` is $HOME), every `git -C <dir>`, `--git-dir` and `--work-tree`. A relative
one is resolved against the cwd and against every `cd` target before it (a chain `cd a && cd b` is caught either
way), then to its git toplevel. A target holding `$`, a backquote or a glob, and `cd -`, cannot be resolved and
counts as outside. Inside means equal to, or under, J's `working_copy` or J's `worktree`: a subagent's
.claude/worktrees/<x> under the clone is inside. Execution order is not modelled: a commit in the job copy
followed by an unrelated `cd /elsewhere` is denied. A false deny costs a rephrase; a false allow is the incident.

WHY "worked a job other than the active one", and not "worked the active one": `fabric-jobs switch` activates the
next job in the session that runs it (verbs.switch_job, then prints `fabric-fresh --job J`), so the old session's
id is in J's log too. Counting that as "this session worked J" would let the session that just switched go on
committing in J's copy — the incident one step later. A session launched by `fabric-fresh --job J` has worked
nothing (J was activated by another session) and is allowed J's copies; the session that switched has worked W
and is allowed nothing.

WHY. 2026-10-20 (the owner's report through architect-cto-01): a session launched on one project closed its job,
took another project's question with REPLY-EXPECTED, cd'd into that project's working copy and committed there without
`fabric-jobs switch`. Its own reasoning noticed the switch rule and went on. ADR-037 rule 3 says that once a
session has worked a job, every next job gets a fresh session; prose did not hold, so the rule has a fence. The
inbox needs no change for it: a REQUEST addressed to this login is already queued as a job when it is delivered
(tools/fabric/gzcoord/intake.py queue_received, called by the inbox; the operator's send adds it through jobs-add),
so the work exists as a job and this guard is what stops it being done in place. A message of another type (a
QUESTION, an OBSERVATION with REPLY-EXPECTED) is not queued: the deny says to add it.

WHAT IT DOES NOT FENCE: reads of any working copy (git log/diff/status/fetch, cat, grep); a subagent (the clone
guard's lane); a commit a hook or a script makes without the command naming it (`make release`, a git alias such
as `git ci`); `git pull`, `git revert`, `git tag`, `gh api` writes. It is a fence for the incident's shape, not a
sandbox: the git hooks are the place for enforcement at the point of the commit.

THE SESSION ID: CLAUDE_CODE_SESSION_ID, else the payload's session_id (one value, two carriers). With neither, the
session counts as having worked no job: records.session_worked's `last` fallback (any job that left active) would
lock an unlaunched shell out of every commit, and a fence must not do that.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True   # the job module it loads leaves no __pycache__ in the tree

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

GIT_ACTS = ("commit", "push", "merge", "rebase", "cherry-pick", "am")
GH_ACTS = ("create", "merge")
# fabric-pr verbs that read and never write (tools/fabric/github/fabric_pr.py VERBS, each module's contract):
# gate, review-status, sessions, counts, owed-supply and compliance list; wait-merged waits; trial-merge combines
# branches in a worktree of its own and leaves the caller's clone untouched. post-review, reply and arm write;
# a verb not named here (a new one) counts as writing.
READ_ONLY_PR_VERBS = ("gate", "review-status", "sessions", "trial-merge", "wait-merged", "owed-supply", "compliance",
                      "counts", "help", "-h", "--help")
GIT_VALUE_OPTIONS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix",
                     "--attr-source", "--list-cmds")
GIT_DIR_OPTIONS = ("-C", "--git-dir", "--work-tree")
GH_VALUE_OPTIONS = ("-R", "--repo", "--hostname")
SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
CD_OPTION = re.compile(r"-[LPe@]+")
UNRESOLVABLE = re.compile(r"[$`*?\[]")
# `<<WORD`, `<<-WORD`, `<<'WORD'`, `<<"WORD"`; never `<<<` (a here-string: its word is the data, on the same line).
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
OPERATOR = re.compile(r"[;&|()`]+")
TOPLEVEL_TIMEOUT_S = 2.0
MAX_DEPTH = 3
HOME_MARK = "\0home"   # a bare `cd`: the target is $HOME


def without_heredocs(text: str) -> tuple[str, list[str]]:
    """(the command without its heredoc bodies, the bodies fed to a shell). A body is data — a commit message,
    a file — unless the line that opens it runs a shell, when it is a script and is read as one."""
    kept, scripts, pending = [], [], []
    body: list[str] = []
    for line in text.split("\n"):
        if pending:
            strip, word, shell = pending[0]
            if (line.lstrip("\t") if strip else line) == word:
                pending.pop(0)
                if shell:
                    scripts.append("\n".join(body))
                body = []
            else:
                body.append(line)
            continue
        kept.append(line)
        opened = HEREDOC.findall(line)
        runs_shell = any(os.path.basename(w) in SHELLS or w == "eval" for w in re.split(r"[\s;&|()]+", line))
        pending.extend((dash == "-", word, runs_shell) for dash, _, word in opened)
    if pending:
        kept.extend(body)     # no terminator: the `<<` was text (a quoted word), and what followed is read as commands
    return "\n".join(kept), scripts


def tokens(text: str) -> list[str]:
    """Shell words and operators. Quotes it cannot balance are dropped and the text read again: over-reading."""
    # A backquote stands apart, so an unquoted `…` is a segment of its own; a quoted one stays in its word, which
    # Reading.segment reads again.
    flat = text.replace("\\\n", "").replace("\n", " ; ").replace("`", " ` ")
    for attempt in (flat, re.sub(r"['\"]", " ", flat)):
        try:
            lex = shlex.shlex(attempt, posix=True, punctuation_chars=";&|()")
            lex.whitespace_split = True
            lex.commenters = ""
            return list(lex)
        except ValueError:
            continue
    return flat.split()


def segments(words: list[str]) -> list[list[str]]:
    out, cur = [], []
    for w in words:
        if OPERATOR.fullmatch(w):
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(w)
    if cur:
        out.append(cur)
    return out


class Reading:
    """What a command commits or publishes (`acts`) and the directory words it names, in order (`dirs`, each
    (kind, word): kind "cd" for a cd/pushd target, "git" for a git -C/--git-dir/--work-tree)."""

    def __init__(self):
        self.acts: list[str] = []
        self.dirs: list[tuple[str, str]] = []

    def read(self, text: str, depth: int = 0) -> None:
        text, scripts = without_heredocs(text)
        for seg in segments(tokens(text)):
            self.segment(seg, depth)
        if depth < MAX_DEPTH:
            for script in scripts:
                self.read(script, depth + 1)

    def segment(self, seg: list[str], depth: int) -> None:
        for i, word in enumerate(seg):
            name = os.path.basename(word)
            if word in ("cd", "pushd"):
                self.cd(seg[i + 1:])
            elif name == "git":
                self.git(seg[i + 1:])
            elif name == "gh":
                self.gh(seg[i + 1:])
            elif name == "fabric-pr":
                self.fabric_pr(seg[i + 1:])
            elif depth < MAX_DEPTH and name in SHELLS:
                script = next((seg[j + 1] for j in range(i + 1, len(seg) - 1)
                               if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", seg[j])), None)
                if script is not None:
                    self.read(script, depth + 1)
            elif depth < MAX_DEPTH and word == "eval":
                self.read(" ".join(seg[i + 1:]), depth + 1)
            elif depth < MAX_DEPTH and ("$(" in word or "`" in word):
                self.read(word.replace("$(", " ; "), depth + 1)     # a substitution inside a quoted word runs too

    def cd(self, rest: list[str]) -> None:
        args = [w for w in rest if not CD_OPTION.fullmatch(w) and w != "--"]
        self.dirs.append(("cd", args[0] if args else HOME_MARK))

    def git(self, rest: list[str]) -> None:
        i = 0
        while i < len(rest):
            w = rest[i]
            if w in GIT_VALUE_OPTIONS:
                if w in GIT_DIR_OPTIONS and i + 1 < len(rest):
                    self.dirs.append(("git", rest[i + 1]))
                i += 2
                continue
            if w.startswith("--") and "=" in w:
                opt, value = w.split("=", 1)
                if opt in GIT_DIR_OPTIONS:
                    self.dirs.append(("git", value))
                i += 1
                continue
            if w.startswith("-"):
                i += 1
                continue
            if w in GIT_ACTS:
                self.acts.append(f"git {w}")
            return

    def gh(self, rest: list[str]) -> None:
        words, i = [], 0
        while i < len(rest) and len(words) < 2:
            w = rest[i]
            if w in GH_VALUE_OPTIONS:
                i += 2
                continue
            if not w.startswith("-"):
                words.append(w)
            i += 1
        if len(words) == 2 and words[0] == "pr" and words[1] in GH_ACTS:
            self.acts.append(f"gh pr {words[1]}")

    def fabric_pr(self, rest: list[str]) -> None:
        i = 0
        while i < len(rest) and (rest[i] == "--repo" or rest[i].startswith("--repo=")):
            i += 2 if rest[i] == "--repo" else 1
        verb = rest[i] if i < len(rest) else "help"
        if verb not in READ_ONLY_PR_VERBS:
            self.acts.append(f"fabric-pr {verb}")


class Undecided(Exception):
    """A directory's checkout could not be found in time: the guard asks."""


def candidates(cwd: str, dirs: list[tuple[str, str]]) -> list[tuple[str, str | None]]:
    """(the word as the command spells it, its absolute path or None when it cannot be resolved), cwd first."""
    out: list[tuple[str, str | None]] = [(cwd, os.path.normpath(cwd))]
    bases = [os.path.normpath(cwd)]
    for kind, word in dirs:
        if word == HOME_MARK:
            word, paths = "cd (no target: $HOME)", [os.path.expanduser("~")]
        elif word in ("", "-") or UNRESOLVABLE.search(word):
            out.append((word or "''", None))
            continue
        else:
            spelled = os.path.expanduser(word) if word.startswith("~") else word
            if spelled.startswith("~"):
                out.append((word, None))
                continue
            paths = [spelled] if os.path.isabs(spelled) else [os.path.join(b, spelled) for b in bases]
        paths = [os.path.normpath(p) for p in paths]
        out.extend((word, p) for p in paths)
        if kind == "cd":
            bases.extend(p for p in paths if p not in bases)
    return out


def toplevel(path: str) -> str:
    """The checkout `path` is in, as a real path; the path itself when it is no directory or in no checkout."""
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        return real
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")}
    try:
        r = subprocess.run(["git", "-C", real, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           timeout=TOPLEVEL_TIMEOUT_S, env=env, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        raise Undecided(path) from None
    except OSError:
        return real
    top = r.stdout.strip()
    return os.path.realpath(top) if r.returncode == 0 and top else real


def inside(path: str, copies: list[str]) -> bool:
    return any(path == c or path.startswith(c.rstrip("/") + "/") for c in copies)


def records_module():
    """tools/fabric/jobsparts/records.py, loaded the way jobs.py loads its parts: the package BY PATH as
    fabric_jobs, so nothing on sys.path (under -I, the standard library alone) answers for its imports."""
    parts = os.path.join(FABRIC_ROOT, "tools", "fabric", "jobsparts")
    spec = importlib.util.spec_from_file_location("fabric_jobs", os.path.join(parts, "__init__.py"),
                                                  submodule_search_locations=[parts])
    if spec is None or spec.loader is None:
        raise ImportError(f"no package at {parts}")
    package = importlib.util.module_from_spec(spec)
    sys.modules["fabric_jobs"] = package
    spec.loader.exec_module(package)
    return importlib.import_module("fabric_jobs.records")


def emit(kind: str, reason: str) -> None:
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind,
                                  "permissionDecisionReason": reason}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")


NEXT_JOB = ("let the next job (or a REQUEST that asked for this, which intake already queued as a job; anything "
            "else, add it with `fabric-jobs add`) run in the fresh session switch prints")


def decide(payload: dict) -> tuple[str, str] | None:
    if payload.get("agent_id"):
        return None                               # a subagent: the clone guard's lane
    if payload.get("tool_name") not in (None, "", "Bash"):
        return None
    command = (payload.get("tool_input") or {}).get("command") if isinstance(payload.get("tool_input"), dict) else None
    if not isinstance(command, str) or not command.strip():
        return None
    reading = Reading()
    reading.read(command)
    if not reading.acts:
        return None                               # the job list is not touched for a command that neither commits nor publishes
    what = ", ".join(dict.fromkeys(reading.acts))

    try:
        records = records_module()
        doc = records.identity.read_jobs()
        jobs = doc["jobs"]
        session = records.session_id() or (payload.get("session_id") if isinstance(payload.get("session_id"), str) else None) or None
        current = records.active(doc)
        # Asked of the list without the active job: a session that switched has the active job's start in its log
        # too, and is still a session that has worked another (see WHY above).
        worked = records.session_worked({**doc, "jobs": [j for j in jobs if j is not current]}, session) if session else None
    except (Exception, SystemExit) as e:  # noqa: BLE001 — whatever fails, the answer is an ask
        detail = " ".join(str(e).split())[:200] or type(e).__name__
        return ("ask", f"The job copy guard could not read this login's job list ({detail}). Approve only if this command "
                       "does not commit or publish outside the working copy of this session's job (agent-fabric ADR-037 rule 3).")

    if worked:
        rule = ("Once a session has worked a job, the next one runs in a fresh session (agent-fabric ADR-037 rule 3): ")
        if current:
            return ("deny", f"This session worked job {worked}, which has left active; job {current['id']} is active now, "
                            f"and it belongs to a fresh session. This command commits or publishes ({what}). {rule}run "
                            f"`fabric-jobs switch` (or the `fabric-fresh --job {current['id']}` it printed) and do this work "
                            "there. Reading working copies is allowed.")
        return ("deny", f"This session worked job {worked}, which has left active, and no job is active. This command "
                        f"commits or publishes ({what}). {rule}run `fabric-jobs switch`, and {NEXT_JOB}. Reading working "
                        "copies is allowed.")
    if not current:
        return None                               # an unbound session: no job, none worked

    jid = current["id"]
    copies_named = [p for p in (current.get("working_copy"), current.get("worktree")) if isinstance(p, str) and p]
    if not copies_named:
        return ("ask", f"Job {jid} records no working copy, so the job copy guard cannot tell where this session may "
                       f"commit or publish. Approve only if this command acts in the working copy of job {jid} "
                       "(agent-fabric ADR-037 rule 3).")
    copies = list(dict.fromkeys(os.path.realpath(os.path.expanduser(p)) for p in copies_named))
    shown = " and ".join(copies_named)
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) and payload.get("cwd") else os.getcwd()
    for word, path in candidates(cwd, reading.dirs):
        if path is None:
            where = f"{word} (a directory this guard does not resolve: a variable, a substitution, a glob or `cd -` counts as outside)"
        else:
            try:
                top = toplevel(path)
            except Undecided:
                return ("ask", f"The job copy guard could not resolve {word} to its checkout (git rev-parse timed out). "
                               f"Approve only if this command does not commit or publish outside job {jid}'s working copy "
                               f"{shown} (agent-fabric ADR-037 rule 3).")
            if inside(top, copies):
                continue
            where = word if os.path.normpath(word) == top else f"{word} ({top})"
        return ("deny", f"This session works job {jid} in {shown}; this command commits or publishes ({what}) in {where}, "
                        "outside it. A session works one job's working copy (agent-fabric ADR-037 rule 3): finish or "
                        f"block this job, run `fabric-jobs switch`, and {NEXT_JOB}. Reading other working copies is allowed.")
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    verdict = decide(payload)
    if verdict:
        emit(*verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
