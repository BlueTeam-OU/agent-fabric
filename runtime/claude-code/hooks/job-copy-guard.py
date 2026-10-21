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
     a `bash -c`/`sh -c`/`eval`/`env -S` script and a command substitution included. Only an unquoted `<<`
     outside a comment opens a heredoc (a quote-aware scan, never a regex on the raw line: a quoted `'<<X'` and a
     later line `X` must not hide the lines between; a `$(` or backquote inside double quotes is command text
     again, so `git commit -m "$(cat <<'EOF'` opens one). Every heredoc body in the command is read as commands
     when the command text, its bodies removed and a quoted string kept as one word, holds a word that runs
     stdin anywhere — a shell (`sh`, `bash`, `dash`, `zsh`, `ksh`, `fish`, `ash`, `mksh`, `csh`, `tcsh`, `yash`,
     with or without `-s`), `busybox`, `eval`, `source`, `.`, `xargs` or `env -S`. Where its stdin goes is not
     modelled (`|&`, `{ bash; } <<X`, a `while … eval` loop, `if …; then bash; fi <<X`): a command that both runs a
     shell and publishes a body is over-reported, and costs a rephrase. With no such word, a body is still read as
     commands when the substitution holding its redirect stands in a command's place (`"$(cat <<'X' …)"`). Any
     other body is data: under a quoted delimiter all of it, whatever commands its text names (a commit message, a
     review posted with `fabric-pr post-review`, a `gh pr create --body-file -` body, a `cat`); under an unquoted
     delimiter the shell expands it, so its `$(…)` and backquotes run and are read, and its plain text stays data.
     The job list is not read before this point, so a command that does not commit or publish never asks.
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
  9. the git lookups of steps 10 to 13 together passed GIT_BUDGET_S (6 s)               -> ask:
       "The job copy guard spent its 6 s budget for git lookups (<n> run, <s> s) before it could decide, and
       stopped short of the harness's 10 s hook limit, which would read as an allow. Approve only if this command
       does not commit or publish outside job J's working copy <copies> (agent-fabric ADR-037 rule 3)."
     Each lookup has its own 2 s timeout as well; the harness reads a hook it killed as no objection, so the sum
     is what keeps the guard's answer inside the 10 s.
 10. a directory the command acts in whose git toplevel lookup timed out                -> ask:
       "The job copy guard could not resolve <dir> to its checkout (git rev-parse timed out). Approve only if
       this command does not commit or publish outside job J's working copy <copies> (agent-fabric ADR-037 rule 3)."
 11. any directory the command acts in lies outside J's working copy and worktree       -> deny:
       "This session works job J in <copies>; this command commits or publishes (<what>) in <dir>, outside it. A
       session works one job's working copy (agent-fabric ADR-037 rule 3): finish or block this job, run
       `fabric-jobs switch`, and let the next job (or a REQUEST that asked for this, which intake already queued
       as a job; anything else, add it with `fabric-jobs add`) run in the fresh session switch prints. Reading
       other working copies is allowed."
 12. the command names a target repository (see THE REPOSITORIES below) and the remotes of J's copies cannot
     be read (`git -C <copy> remote -v` fails or times out for every copy)                  -> ask:
       "The job copy guard could not read the remotes of job J's working copy <copies> (git remote -v did not
       answer), so it cannot tell whether <repo> is one of them. Approve only if …"
 13. a target repository that is not one of those remotes, or cannot be read as owner/repo -> deny:
       "This session works job J in <copies>; this command commits or publishes (<what>) to <repo>, which is not a
       remote of that working copy (its remotes: <host/owner/repo, …>). A session works one job's working copy …"
 14. otherwise                                                                          -> nothing

THE DIRECTORIES A COMMAND ACTS IN, over-reported rather than modelled: the payload's cwd, every `cd`/`pushd` target
anywhere in the command (a bare `cd` is $HOME), every `git -C <dir>`, `--git-dir` and `--work-tree`, every
`git -c core.worktree=<dir>` (and `--config-env core.worktree=<var>`, whose value is a variable), every `env -C`
(`--chdir`), and every way of setting git's repository or work tree through the environment: a word
`GIT_DIR=<dir>`, `GIT_WORK_TREE=<dir>` or `GIT_COMMON_DIR=<dir>` wherever it stands — a prefix assignment, after
`env` and its options, after `export`/`declare -x`, or anywhere earlier in the same command text (an export
anywhere counts for every git in the command, and so does such a word that is only text). An `export`/`declare`
of one of those names with no value this command sets counts as a directory it cannot resolve, and so does any
setting or export of a variable that hands git configuration in (GIT_CONFIG_PARAMETERS, GIT_CONFIG_COUNT,
GIT_CONFIG_KEY_<n>, GIT_CONFIG_VALUE_<n>, GIT_CONFIG, GIT_CONFIG_GLOBAL, GIT_CONFIG_SYSTEM) or chooses which config
files or repository git finds (HOME, XDG_CONFIG_HOME, GIT_CONFIG_NOSYSTEM, GIT_CEILING_DIRECTORIES), and every
`git -c include.path=…` or `-c includeIf.<cond>.path=…` (an included file), since any of them can carry
core.worktree and the guard does not read config files (`-c user.name=…` and other plain keys are no directory). A
relative one is
resolved against the cwd and against every `cd` target before it (a chain `cd a && cd b` is caught either way),
then to its git toplevel (a git directory, `/x/.git`, is no work tree and stands as itself, so it is inside only
under J's copy). A value holding `$`, a backquote or a glob, and `cd -`, cannot be resolved and counts as outside.
Inside means equal to, or under, J's `working_copy` or J's `worktree`: a subagent's .claude/worktrees/<x> under the
clone is inside. Execution order is not modelled: a commit in the job copy followed by an unrelated
`cd /elsewhere` is denied. A false deny costs a rephrase; a false allow is the incident.

THE REPOSITORIES A COMMAND PUBLISHES TO, when it names one: `gh pr create|merge -R/--repo <repo>` (with
`--hostname` or GH_HOST as its host when given), a pull request URL among its arguments
(`http(s)://<host>/<owner>/<repo>/pull/<n>`, a deeper path, a query or a fragment after it included, the URL's host
without userinfo or port its host), on which gh
acts whatever the cwd, `fabric-pr --repo <repo> <verb>` for a writing verb, and GH_REPO
set (as a word, as for GIT_DIR) in a command that runs either. The job copy's remotes are read
(`git -C <copy> remote -v`, inside the budget), each URL normalised to owner/repo, lowercased, without .git, from
https, ssh:// or scp-style; the named repository (owner/repo, host/owner/repo or a URL) is inside only when it is
one of them, on the same host when it names one. An ssh host alias in a remote (`gh-agent:owner/repo`) does not
equal `github.com`: a host named beside the repository then denies. fabric-pr's project-id form (`--repo <project>`)
is inside when it is the job's recorded `project`, and outside otherwise: the guard does not read the registry.

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
as `git ci`); `git pull`, `git revert`, `git tag`, `gh api` writes; a heredoc body run by a later command when the command
names no runner word (`cat <<'X' > f.sh` and `sh f.sh` as two commands; a runner named in a program the command
starts, `python3 run.py <<'X'`). It is a fence for the incident's shape, not a
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
import time
import urllib.parse

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
PR_PATH = re.compile(r"/([^/]+)/([^/]+)/pull/\d+(?:/.*)?", re.S)
SHELLS = ("bash", "sh", "zsh", "dash", "ksh", "fish", "ash", "mksh", "csh", "tcsh", "yash")
# What runs the stdin a heredoc feeds it: a shell (with or without -s), eval, source, `.`, xargs, busybox (whose
# applets include shells: `busybox sh`, `busybox hush`), and env -S apart.
STDIN_RUNNERS = SHELLS + ("eval", "source", ".", "xargs", "busybox")
# The words after which a command starts, so a `.` there is the dot command and not a path argument.
COMMAND_KEYWORDS = ("then", "do", "else", "elif", "time", "exec", "command", "builtin", "nohup", "sudo")
# An assignment word, a redirection operator, a plain word (a command name or an ordinary argument), and the
# launchers that run the word after them as a command (plain_argument).
ASSIGN_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\+?=")
REDIRECT_OP = re.compile(r"\d*(?:<<?<?-?|>>?|<>|>\|)")
PLAIN_WORD = re.compile(r"[A-Za-z0-9_./+@:,=%\[\]-]+")
LAUNCHERS = ("env", "nice", "timeout", "stdbuf", "setsid", "chrt", "ionice", "taskset", "doas", "xargs")
# What may stand before a substitution that is then run as the command: assignments, a quote, a wrapper.
COMMAND_PLACE = re.compile(r"\s*(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S*|exec|command|nohup|time|sudo|env)\s+)*\"?")
CD_OPTION = re.compile(r"-[LPe@]+")
UNRESOLVABLE = re.compile(r"[$`*?\[]")
# The variables that point git at a repository or a work tree, and the two that point gh at a repository. A word
# `NAME=value` is read wherever it stands (a prefix assignment, after `env`, `export`, `declare -x`, `sudo`, or as
# text): over-reported, never modelled.
GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")
GH_ENV = ("GH_REPO", "GH_HOST")
ASSIGNMENT = re.compile(r"(%s)=(.*)" % "|".join(GIT_ENV + GH_ENV), re.S)
# The variables that hand git configuration, core.worktree among it, from the environment. Whatever they hold, the
# guard does not read it: set or exported in a command that acts, they count as a directory it cannot resolve.
# HOME and XDG_CONFIG_HOME move the global config file, GIT_CONFIG_NOSYSTEM drops the system one, and
# GIT_CEILING_DIRECTORIES changes which repository git finds: the guard reads no config file, so it over-reports them.
GIT_CONFIG_ENV = re.compile(r"(GIT_CONFIG_PARAMETERS|GIT_CONFIG_COUNT|GIT_CONFIG_KEY_\d+|GIT_CONFIG_VALUE_\d+|"
                            r"GIT_CONFIG|GIT_CONFIG_GLOBAL|GIT_CONFIG_SYSTEM|GIT_CONFIG_NOSYSTEM|"
                            r"GIT_CEILING_DIRECTORIES|HOME|XDG_CONFIG_HOME)(=.*)?", re.S)
EXPORTERS = ("export", "declare", "typeset", "local", "readonly")
# env's own options: those that take a value, and the two that matter here (-C changes the directory, -S is a
# command line of its own).
ENV_VALUE_OPTIONS = ("-u", "--unset", "-C", "--chdir", "-S", "--split-string")
OPERATOR = re.compile(r"[;&|()`]+")
GIT_TIMEOUT_S = 2.0
# The harness kills a hook at 10 s and reads that as no objection; git lookups stop at this sum, with room left for
# the interpreter's start and the job list.
GIT_BUDGET_S = 6.0
MAX_DEPTH = 3
HOME_MARK = "\0home"   # a bare `cd`: the target is $HOME
NAME_PART = re.compile(r"[A-Za-z0-9_.-]+")


def heredoc_operators(line: str, levels: list[list]) -> list[tuple[bool, str, bool, int]]:
    """The heredocs `line` opens, each (strip tabs, delimiter, delimiter quoted, where the operator's word ends in
    `line`). `levels` is the scan's state, carried from line to line and updated in place: one [closer, open quote]
    per nesting, the command text first, then each `$(`, backquote or `(` the line is inside (a quoted string and a
    substitution can run over lines). Only an unquoted `<<` outside a comment is an operator: a `<<` inside quotes is
    text, and reading it as an operator would hide the lines up to its "terminator" (review F3 on #348). A `$(` or a
    backquote inside double quotes opens unquoted command text again, so the `<<` of `git commit -m "$(cat <<'EOF'`
    is an operator."""
    ops: list[tuple[bool, str, bool, int]] = []
    i, n, word_start = 0, len(line), True
    while i < n:
        c = line[i]
        level = levels[-1]
        if level[1] == "'":
            level[1] = None if c == "'" else level[1]
            i += 1
            continue
        if c == "\\":
            i, word_start = i + 2, False
            continue
        if level[1] == '"':
            if c == '"':
                level[1] = None
            elif line.startswith("$(", i) or c == "`":
                levels.append([c if c == "`" else ")", None])
                i, word_start = i + (1 if c == "`" else 2), True
                continue
            i += 1
            continue
        if c in "'\"":
            level[1], word_start = c, False
            i += 1
            continue
        if c == "#" and word_start:
            break                                  # a comment: nothing after it is an operator
        if line.startswith("<<<", i):              # a here-string: its word is the data, on this line
            i, word_start = i + 3, False
            continue
        if line.startswith("<<", i):
            j = i + 2
            strip = j < n and line[j] == "-"
            j += 1 if strip else 0
            while j < n and line[j] in " \t":
                j += 1
            word, quoted, end = delimiter(line, j)
            if word:
                ops.append((strip, word, quoted, end))
                i = end
            else:
                i = j                              # no word it can read: what follows is scanned as text
            word_start = False
            continue
        if c in ")`" and len(levels) > 1 and level[0] == c:
            levels.pop()
        elif c == "`" or c == "(":
            levels.append([c if c == "`" else ")", None])
        word_start = c in " \t;&|()<>`"
        i += 1
    return ops


def delimiter(line: str, j: int) -> tuple[str, bool, int]:
    """(the heredoc delimiter at line[j:] with its quotes removed, whether any of it was quoted, where it ends);
    ("", …) when it has no word or a quote that does not close on this line."""
    out, quoted, quote = [], False, None
    while j < len(line):
        c = line[j]
        if quote:
            if c == quote:
                quote = None
            else:
                out.append(c)
        elif c in "'\"":
            quote, quoted = c, True
        elif c == "\\" and j + 1 < len(line):
            quoted = True
            out.append(line[j + 1])
            j += 1
        elif c in " \t;&|()<>":
            break
        else:
            out.append(c)
        j += 1
    return ("" if quote else "".join(out)), quoted, j


def plain_argument(words: list[str], i: int) -> bool:
    """Whether words[i] is plainly an argument of an ordinary command: the nearest word before it, its options
    (`-x`, `--`) stepped over, is a plain command name or argument (`git add .`, `echo "$HOME"`, `tee $LOG`). Anything
    else (nothing, an operator, an assignment, a redirection or its operand, a keyword or a launcher that runs the
    next word) leaves words[i] possibly a command word. Inverted on purpose: recognising where a command starts
    missed `x=1 .` (review F7, round 4) and then `2>&1 .`, which the tokenizer splits into `2>`, `&`, `1` (round 5);
    a shape this misreads now counts as a runner, which over-reports and never lets a sourced body through."""
    j = i - 1
    while j >= 0 and words[j].startswith("-") and words[j] != "-":
        j -= 1
    if j < 0:
        return False
    w, before = words[j], words[j - 1] if j >= 1 else ""
    if before and (before[-1] in "<>&" or REDIRECT_OP.fullmatch(before)):
        return False                                # a redirection's operand (`> out`, `2>&1`)
    if w in COMMAND_KEYWORDS or w in LAUNCHERS or ASSIGN_WORD.match(w):
        return False
    return bool(PLAIN_WORD.fullmatch(w))


def runs_stdin(text: str) -> bool:
    """Whether a pipeline's text holds a word that executes what it reads: a shell (`-s` or not), eval, source, `.`,
    xargs, busybox, or env with -S. Any word counts, not only a command's (over-reporting); a quoted argument stays one word,
    so `--title "fix sh"` is no shell. The one exception is `.`: it is the path every `git add .` names, so it counts
    only where it is not plainly an argument (plain_argument). A command word the guard cannot read (`$SHELL`, `"$0"`) counts
    as a runner too, as an unresolvable directory counts as outside."""
    words = tokens(text)
    for i, w in enumerate(words):
        expansion = "$" in w and not ASSIGN_WORD.match(w) and "<" not in w and ">" not in w
        if w == "." or expansion:
            if not plain_argument(words, i):
                return True
            continue
        name = os.path.basename(w)
        if name in STDIN_RUNNERS:
            return True
        if name == "env" and any(x in ("-S", "--split-string") or x.startswith(("-S", "--split-string="))
                                 for x in words[i + 1:]):
            return True
    return False


class _Frame:
    """One level of stdin_executed's scan: the top, or a `$(`, `<(`, `>(`, `(` or backquote it is inside."""

    def __init__(self, closer: str, at: int, quote: str | None, in_place: bool):
        self.closer, self.quote, self.in_place = closer, quote, in_place
        self.pipe_start = self.cmd_start = at
        self.pending: list[int] = []      # marks in this frame's current pipeline, nested frames' included
        self.inner: list[int] = []        # every mark inside this frame


def stdin_executed(text: str, marks: list[int]) -> set[int]:
    """The indexes of `marks` (offsets of heredoc operators in `text`, the bodies removed) whose body is executed:
    the pipeline holding the redirect runs its stdin (runs_stdin), or so does the pipeline around a substitution or
    subshell the redirect is inside, or that substitution stands in a command's place (`"$(cat <<'X' …)"`). `|&` is
    a pipe. This is one way a body counts as executed, not the only one: without_heredocs reads every body when the
    whole command holds a runner word, since a model of where stdin goes misses `{ bash; } <<X` and its kin."""
    order = sorted(range(len(marks)), key=marks.__getitem__)
    nxt, executed = 0, set()
    frames = [_Frame("", 0, None, False)]
    quote: str | None = None

    def close_pipeline(f: _Frame, at: int, width: int = 1) -> None:
        if f.pending and runs_stdin(text[f.pipe_start:at]):
            executed.update(f.pending)
        f.pending = []
        f.pipe_start = f.cmd_start = at + width

    def pop(at: int) -> str | None:
        f = frames.pop()
        close_pipeline(f, at)
        if f.in_place:
            executed.update(f.inner)
        frames[-1].pending += f.inner      # the pipeline around it holds it too
        frames[-1].inner += f.inner
        return f.quote

    def push(closer: str, at: int, width: int, substitution: bool) -> None:
        in_place = substitution and bool(COMMAND_PLACE.fullmatch(text[frames[-1].cmd_start:at]))
        frames.append(_Frame(closer, at + width, quote, in_place))

    i, n = 0, len(text)
    while i < n:
        while nxt < len(order) and marks[order[nxt]] <= i:
            frames[-1].pending.append(order[nxt])
            frames[-1].inner.append(order[nxt])
            nxt += 1
        c = text[i]
        top = frames[-1]
        if quote == "'":
            quote = None if c == "'" else quote
            i += 1
        elif c == "\\":
            i += 2
        elif quote == '"':
            if c == '"':
                quote = None
            elif text.startswith("$(", i) or c == "`":
                width = 1 if c == "`" else 2
                push(c if c == "`" else ")", i, width, True)
                quote = None
                i += width - 1
            i += 1
        elif c in "'\"":
            quote = c
            i += 1
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;&|()"):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith(("$(", "<(", ">("), i):
            push(")", i, 2, c == "$")
            i += 2
        elif c == "(":
            push(")", i, 1, False)
            i += 1
        elif c in ")`" and len(frames) > 1 and top.closer == c:
            quote = pop(i)
            i += 1
        elif c == "`":
            push("`", i, 1, True)
            i += 1
        elif text.startswith(("&&", "||"), i):
            close_pipeline(top, i, 2)
            i += 2
        elif text.startswith("|&", i):
            top.cmd_start = i + 2              # `|&` is `2>&1 |`: a pipe, never the `&` that ends a pipeline
            i += 2
        elif c in ";\n" or (c == "&" and text[i - 1:i] not in ("<", ">") and text[i + 1:i + 2] != ">"):
            close_pipeline(top, i)
            i += 1
        else:
            if c == "|" and text[i - 1:i] != ">":
                top.cmd_start = i + 1          # a pipe: the same pipeline, its next command
            i += 1
    while nxt < len(order):
        frames[-1].pending.append(order[nxt])
        frames[-1].inner.append(order[nxt])
        nxt += 1
    while len(frames) > 1:
        pop(n)
    close_pipeline(frames[0], n)
    return executed


def substitutions(body: str) -> list[str]:
    """The command substitutions in an unquoted-delimiter body, which the shell runs when it expands the body:
    `$(…)` (quote-aware inside, as the shell reads it) and backquotes. An unclosed one runs to the end."""
    out, i, n = [], 0, len(body)
    while i < n:
        if body[i] == "\\":
            i += 2
            continue
        if body.startswith("$(", i):
            depth, j, quote = 1, i + 2, None
            while j < n and depth:
                c = body[j]
                if c == "\\":
                    j += 2
                    continue
                if quote:
                    quote = None if c == quote else quote
                elif c in "'\"":
                    quote = c
                else:
                    depth += {"(": 1, ")": -1}.get(c, 0)
                j += 1
            out.append(body[i + 2:j - 1 if depth == 0 else n])
            i = j
            continue
        if body[i] == "`":
            j = i + 1
            while j < n and body[j] != "`":
                j += 2 if body[j] == "\\" else 1
            out.append(body[i + 1:j])
            i = j + 1
            continue
        i += 1
    return out


def without_heredocs(text: str) -> tuple[str, list[str]]:
    """(the command without its heredoc bodies, the scripts those bodies hold). Every body is a script when the
    command holds a runner word anywhere (runs_stdin on the whole text: over-reported, never modelled), and so is a
    body stdin_executed finds executed, whatever its delimiter. Any other body is data: under a quoted delimiter all of it
    (a commit message, a review posted with fabric-pr, a PR body, a `cat` of notes, whatever commands its text
    names); under an unquoted one the shell expands it, so its command substitutions run and are its scripts, and
    its plain text stays data."""
    lines = text.split("\n")
    kept: list[str] = []
    bodies: list[tuple[int, bool, str]] = []        # (operator offset in the kept text, quoted, body)
    levels: list[list] = [["", None]]
    pos, i = 0, 0
    while i < len(lines):
        line = lines[i]
        i += 1
        kept.append(line)
        start, pos = pos, pos + len(line) + 1
        opened = heredoc_operators(line, levels)
        for strip, word, quoted, end in opened:
            body = []
            while i < len(lines) and (lines[i].lstrip("\t") if strip else lines[i]) != word:
                body.append(lines[i])
                i += 1
            if i >= len(lines):
                kept.extend(body)   # no terminator: what followed is read as commands
                pos += sum(len(b) + 1 for b in body)
                break
            i += 1
            bodies.append((start + end, quoted, "\n".join(body)))
    stripped = "\n".join(kept)
    executed = stdin_executed(stripped, [b[0] for b in bodies])
    if bodies and runs_stdin(stripped):
        # The fallback under stdin_executed's model: a runner word anywhere in the command makes every body a
        # script. A command that both runs a shell and publishes a body is over-reported; one with no runner word
        # keeps its data.
        executed = set(range(len(bodies)))
    scripts: list[str] = []
    for k, (_, quoted, body) in enumerate(bodies):
        if k in executed:
            scripts.append(body)
        elif not quoted:
            scripts.extend(substitutions(body))
    return stripped, scripts


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


def option_value(rest: list[str], i: int, names: tuple[str, ...]) -> tuple[str | None, int]:
    """(the value of the option at rest[i] if it is one of `names`, the index after it): `-R x`, `-Rx`,
    `--repo x`, `--repo=x`. (None, i) when rest[i] is none of them."""
    w = rest[i]
    if w in names:
        return (rest[i + 1] if i + 1 < len(rest) else ""), i + 2
    for name in names:
        if name.startswith("--") and w.startswith(name + "="):
            return w[len(name) + 1:], i + 1
        if not name.startswith("--") and w.startswith(name) and len(w) > len(name):
            return w[len(name):], i + 1
    return None, i


class Reading:
    """What a command commits or publishes (`acts`), the directory words it names, in order (`dirs`, each
    (kind, word): kind "cd" for a cd/pushd target, "git" for a git -C/--git-dir/--work-tree, a GIT_DIR-like
    variable or env -C), the repositories its publishes name (`repos`, each (spelled, host or None, value, kind):
    kind "gh" or "fabric-pr"), and the GH_REPO/GH_HOST values it sets (`env`)."""

    def __init__(self):
        self.acts: list[str] = []
        self.dirs: list[tuple[str, str]] = []
        self.repos: list[tuple[str, str | None, str, str]] = []
        self.env: dict[str, list[str]] = {}
        self.exported: set[str] = set()       # GIT_DIR-like names an export/declare names without a value

    def read(self, text: str, depth: int = 0) -> None:
        text, scripts = without_heredocs(text)
        for seg in segments(tokens(text)):
            self.segment(seg, depth)
        if depth < MAX_DEPTH:
            for script in scripts:
                self.read(script, depth + 1)

    def segment(self, seg: list[str], depth: int) -> None:
        exporting = False
        for i, word in enumerate(seg):
            name = os.path.basename(word)
            assigned = ASSIGNMENT.fullmatch(word)
            configured = GIT_CONFIG_ENV.fullmatch(word)
            if configured and (configured.group(2) is not None or exporting):
                self.dirs.append(("git", f"${configured.group(1)}"))     # config from the environment: unresolvable
            elif assigned:
                var, value = assigned.groups()
                self.env.setdefault(var, []).append(value)
                if var in GIT_ENV:
                    self.dirs.append(("git", value))
            elif exporting and word in GIT_ENV:
                self.exported.add(word)
            elif word in EXPORTERS:
                exporting = True
            elif word in ("cd", "pushd"):
                self.cd(seg[i + 1:])
            elif name == "env":
                self.env_command(seg[i + 1:], depth)
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

    def env_command(self, rest: list[str], depth: int) -> None:
        """env's options: -C/--chdir is a directory the command runs in, -S/--split-string a command line. Its
        NAME=value words are read by segment, wherever they stand."""
        i = 0
        while i < len(rest) and rest[i].startswith("-") and rest[i] != "--":
            value, nxt = option_value(rest, i, ENV_VALUE_OPTIONS)
            if value is None:
                i += 1
                continue
            if rest[i].startswith(("-C", "--chdir")):
                self.dirs.append(("git", value))
            elif rest[i].startswith(("-S", "--split-string")) and depth < MAX_DEPTH:
                self.read(value, depth + 1)
            i = nxt

    def git(self, rest: list[str]) -> None:
        i = 0
        while i < len(rest):
            w = rest[i]
            if w in GIT_VALUE_OPTIONS:
                if w in GIT_DIR_OPTIONS and i + 1 < len(rest):
                    self.dirs.append(("git", rest[i + 1]))
                elif w in ("-c", "--config-env") and i + 1 < len(rest):
                    self.git_config(w, rest[i + 1])
                i += 2
                continue
            if w.startswith("--") and "=" in w:
                opt, value = w.split("=", 1)
                if opt in GIT_DIR_OPTIONS:
                    self.dirs.append(("git", value))
                elif opt == "--config-env":
                    self.git_config(opt, value)
                i += 1
                continue
            if w.startswith("-"):
                i += 1
                continue
            if w in GIT_ACTS:
                self.acts.append(f"git {w}")
            return

    def git_config(self, option: str, setting: str) -> None:
        """`-c core.worktree=V` is a --work-tree V; `--config-env core.worktree=VAR` takes it from a variable, which
        cannot be resolved. `include.path` and `includeIf.<cond>.path` make git read a file that can set
        core.worktree, and the guard reads no file: a directory it cannot resolve. Config keys are case-insensitive.
        Any other setting is no directory."""
        key, _, value = setting.partition("=")
        key = key.strip()
        lowered = key.lower()
        if lowered == "core.worktree":
            self.dirs.append(("git", value if option == "-c" else f"${value}"))
        elif lowered == "include.path" or (lowered.startswith("includeif.") and lowered.endswith(".path")):
            self.dirs.append(("git", f"${key}"))

    def gh(self, rest: list[str]) -> None:
        words, repos, urls, host, i = [], [], [], None, 0
        while i < len(rest):
            value, nxt = option_value(rest, i, GH_VALUE_OPTIONS)
            if value is not None:
                if rest[i].startswith("--hostname"):
                    host = value
                else:
                    repos.append((f"{rest[i]} {value}" if nxt == i + 2 else rest[i], value))
                i = nxt
                continue
            if not rest[i].startswith("-") and len(words) < 2:
                words.append(rest[i])
            elif url := pr_url(rest[i]):
                # gh acts on a PR URL's repository whatever the cwd: a -R of its own, its host with it.
                urls.append((rest[i], *url))
            i += 1
        if len(words) == 2 and words[0] == "pr" and words[1] in GH_ACTS:
            self.acts.append(f"gh pr {words[1]}")
            self.repos += [(spelled, host, value, "gh") for spelled, value in repos]
            self.repos += [(spelled, url_host, value, "gh") for spelled, url_host, value in urls]

    def fabric_pr(self, rest: list[str]) -> None:
        # --repo stands anywhere (fabric_pr.take_repo); the verb is the first other word.
        repos, verb, i = [], None, 0
        while i < len(rest):
            value, nxt = option_value(rest, i, ("--repo",))
            if value is not None:
                repos.append((f"--repo {value}" if nxt == i + 2 else rest[i], value))
                i = nxt
                continue
            if verb is None:
                verb = rest[i]
            i += 1
        verb = verb if verb is not None else "help"
        if verb not in READ_ONLY_PR_VERBS:
            self.acts.append(f"fabric-pr {verb}")
            self.repos += [(spelled, None, value, "fabric-pr") for spelled, value in repos]

    def publishes_by_gh(self) -> bool:
        return any(a.startswith(("gh ", "fabric-pr ")) for a in self.acts)


class Undecided(Exception):
    """A directory's checkout could not be found in time: the guard asks."""


class OverBudget(Exception):
    """The git lookups together passed GIT_BUDGET_S: the guard stops and asks before the harness's kill."""


class Git:
    """Every git the guard runs, timed against one budget. `clock` is injectable (time.monotonic by default) so a
    test can spend the budget without waiting for it."""

    def __init__(self, clock=time.monotonic, budget: float = GIT_BUDGET_S):
        self.clock, self.budget, self.spent, self.calls = clock, budget, 0.0, 0

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        """git `args`; raises OverBudget once the sum passes the budget, subprocess.TimeoutExpired on a single
        lookup's timeout, OSError when git cannot be run."""
        if self.spent >= self.budget:
            raise OverBudget()
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")}
        timeout = max(0.05, min(GIT_TIMEOUT_S, self.budget - self.spent))
        start = self.clock()
        self.calls += 1
        try:
            r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout, env=env,
                               stdin=subprocess.DEVNULL, check=False)
        except (subprocess.TimeoutExpired, OSError):
            self.charge(start)              # over budget wins over the lookup's own error
            raise
        self.charge(start)
        return r

    def charge(self, start: float) -> None:
        self.spent += self.clock() - start
        if self.spent > self.budget:
            raise OverBudget()


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


def toplevel(path: str, git: Git) -> str:
    """The checkout `path` is in, as a real path; the path itself when it is no directory or in no checkout."""
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        return real
    try:
        r = git.run(["-C", real, "rev-parse", "--show-toplevel"])
    except subprocess.TimeoutExpired:
        raise Undecided(path) from None
    except OSError:
        return real
    top = r.stdout.strip()
    return os.path.realpath(top) if r.returncode == 0 and top else real


def pr_url(word: str) -> tuple[str, str] | None:
    """(host, owner/repo) of a pull request URL, `http(s)://<host>/<owner>/<repo>/pull/<n>[/...]` whatever its query
    or fragment; the host lowercased, without userinfo or port. None for any other word."""
    try:
        parts = urllib.parse.urlsplit(word)
        host = parts.hostname
    except ValueError:
        return None
    m = PR_PATH.fullmatch(parts.path)
    if parts.scheme.lower() not in ("http", "https") or not host or not m:
        return None
    return host, f"{m.group(1)}/{m.group(2)}"


def repo_of_url(url: str) -> tuple[str, str] | None:
    """(host, owner/repo), lowercased and without .git, of a remote URL: https, ssh:// or scp-style
    (git@host:owner/repo); None for any other (a local path, a deeper path)."""
    m = re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d*)?/(.+)", url) \
        or re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(?!/)(.+)", url)
    if not m:
        return None
    path = owner_repo(m.group(2))
    return (m.group(1).lower(), path) if path else None


def owner_repo(path: str) -> str | None:
    parts = path.strip("/").removesuffix(".git").split("/")
    if len(parts) != 2 or not all(NAME_PART.fullmatch(p) for p in parts):
        return None
    return "/".join(parts).lower()


def repo_named(value: str, host: str | None) -> tuple[str | None, str] | None:
    """(host or None, owner/repo) of a repository a command names: `owner/repo`, `host/owner/repo` or a URL, with
    the --hostname/GH_HOST given beside it; None when it cannot be read so (it counts as outside)."""
    if "://" in value or re.fullmatch(r"[^/:]+@[^/:]+:.+", value):
        found = repo_of_url(value)
        return found if found and (host is None or host.lower() == found[0]) else None
    parts = value.strip("/").split("/")
    if len(parts) == 3 and NAME_PART.fullmatch(parts[0]):
        named_host = parts[0].lower()
        if host is not None and host.lower() != named_host:
            return None
        host, parts = named_host, parts[1:]
    path = owner_repo("/".join(parts))
    return (host.lower() if host else None, path) if path else None


def remotes(copy: str, git: Git) -> set[tuple[str, str]] | None:
    """The (host, owner/repo) of every remote of `copy`; None when git does not answer."""
    try:
        r = git.run(["-C", copy, "remote", "-v"])
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    found = set()
    for line in r.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2:
            repo = repo_of_url(fields[1])
            if repo:
                found.add(repo)
    return found


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


def decide(payload: dict, clock=time.monotonic) -> tuple[str, str] | None:
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
    approve = (f"Approve only if this command does not commit or publish outside job {jid}'s working copy {shown} "
               "(agent-fabric ADR-037 rule 3).")
    outside = (f"A session works one job's working copy (agent-fabric ADR-037 rule 3): finish or block this job, run "
               f"`fabric-jobs switch`, and {NEXT_JOB}. Reading other working copies is allowed.")
    git = Git(clock)
    # An export of a GIT_DIR-like name whose value this command does not set: a value from elsewhere, unresolvable.
    dirs = reading.dirs + [("git", f"${name}") for name in sorted(reading.exported) if name not in reading.env]
    try:
        for word, path in candidates(cwd, dirs):
            if path is None:
                where = f"{word} (a directory this guard does not resolve: a variable, a substitution, a glob or `cd -` counts as outside)"
            else:
                try:
                    top = toplevel(path, git)
                except Undecided:
                    return ("ask", f"The job copy guard could not resolve {word} to its checkout (git rev-parse timed out). {approve}")
                if inside(top, copies):
                    continue
                where = word if os.path.normpath(word) == top else f"{word} ({top})"
            return ("deny", f"This session works job {jid} in {shown}; this command commits or publishes ({what}) in {where}, "
                            f"outside it. {outside}")
        return judge_repos(reading, current, copies, git, what, shown, approve, outside)
    except OverBudget:
        return ("ask", f"The job copy guard spent its {GIT_BUDGET_S:g} s budget for git lookups ({git.calls} run, "
                       f"{git.spent:.1f} s) before it could decide, and stopped short of the harness's 10 s hook limit, "
                       f"which would read as an allow. {approve}")


def judge_repos(reading: Reading, current: dict, copies: list[str], git: Git, what: str, shown: str, approve: str,
                outside: str) -> tuple[str, str] | None:
    """The repositories the command's publishes name (`gh pr … -R`, `fabric-pr --repo`, GH_REPO for either) against
    the remotes of the job's copies: inside only when the named one is among them (and on the host named, when one
    is). A remote list git does not give asks; a value that cannot be read as owner/repo is outside."""
    targets = list(reading.repos)
    if reading.publishes_by_gh():
        targets += [(f"GH_REPO={v}", None, v, "gh") for v in reading.env.get("GH_REPO", [])]
    hosts = reading.env.get("GH_HOST", [])
    if hosts:                                     # gh's host for a repository named without one; every value is judged
        targets = [t for s, h, v, k in targets
                   for t in ([(s, g, v, k) for g in hosts] if h is None and k == "gh" else [(s, h, v, k)])]
    if not targets:
        return None
    project = str(current.get("project") or "").lower()
    known: set[tuple[str, str]] | None = None
    for spelled, host, value, kind in targets:
        if kind == "fabric-pr" and "/" not in value and project and value.lower() == project:
            continue                              # fabric-pr's project-id form, naming this job's project
        if known is None:
            answers = [r for r in (remotes(c, git) for c in copies) if r is not None]
            if not answers:
                return ("ask", f"The job copy guard could not read the remotes of job {current['id']}'s working copy "
                               f"{shown} (git remote -v did not answer), so it cannot tell whether {spelled} is one of "
                               f"them. {approve}")
            known = set().union(*answers)
        named = repo_named(value, host) if not UNRESOLVABLE.search(value) else None
        if named is None:
            where = f"{spelled} (a repository this guard cannot read as owner/repo counts as outside)"
        elif any(repo == named[1] and named[0] in (None, h) for h, repo in known):
            continue
        else:
            remote_list = ", ".join(sorted(f"{h}/{r}" for h, r in known)) or "none"
            where = f"{spelled}, which is not a remote of that working copy (its remotes: {remote_list})"
        return ("deny", f"This session works job {current['id']} in {shown}; this command commits or publishes ({what}) "
                        f"to {where}. {outside}")
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
