#!/usr/bin/env python3
"""runtime/claude-code/hooks/review-bash-guard.py: the Bash fence around the
review class. Claude Code PreToolUse hook on Bash, scoped to the code-review
agent (declared in runtime/claude-code/agents/code-review.md frontmatter, so
it runs ONLY while that agent is active), and called by
subagent-clone-guard.sh for every other class dispatched unisolated.
review-bash-guard.sh beside it is the path both call and finds the fleet's
Python; bootstrap installs the pair user-scope under ~/.claude/hooks/, where
the agent file looks after the launch project's .claude/.

WHY. The review class runs in the session's clone with no worktree, so the
only thing between a reviewer and the session's branch is what it is allowed
to run. Its charter says "read-only, no git writes" -- a promise. This is the
fence: under this project's permissions `git push` is auto-allowed and
unprompted, so a reviewer that pushed would push the session's real branch.
And a build that runs an install rewrites tracked lockfiles (pubspec.lock,
pnpm-lock.yaml), which `git add -A` in the session would then commit. Both
denied here whatever the prompt said. This is a fence against the ROUTINE
path -- the git and install spellings an agent reaches for, in-place file
writes and shell escapes -- not a sandbox: a determined `python3 -c` can
still write. The charter is what governs the rest.

Denies: printing the environment or secret material (below), changing
directory out of the clone, and state-changing git (push, commit, add, rm,
mv, checkout, switch, restore, reset, stash, rebase, merge, cherry-pick,
revert, tag, branch creation/deletion, clean, worktree, am, apply, fetch,
pull, remote and config changes, gc) and package installs/restores (pnpm/
npm/yarn install|add|remove|update, flutter/dart pub get|add|upgrade, dotnet
restore|add, pip install, cargo add). Allows everything else: read-only git,
validators, guards, builds and tests that need no install (dotnet build/test
--no-restore; pnpm --filter X test).

Output: a deny decision, or nothing. Exit 0 always -- exit 2 would block; a
guard that cannot parse its input allows and says nothing. A guard that
cannot RUN denies (the shim, when the fleet's Python is missing): the
reviewer never needs Bash to finish, and the failure mode of allowing is a
push to the session's real branch.

Ported from bash when the round-3 fix took it past ADR-040's 150 lines; the
patterns are the bash guard's, translated mechanically ([[:space:]] to \\s),
and each is applied line by line as grep applied it, so no class crosses a
newline. tests/test_review_bash_guard_cli.py, with its table in
tests/fixtures/review-bash-guard-cases.json, is the oracle.
"""
from __future__ import annotations

import json
import os
import re
import select
import signal
import sys

# Python's re backtracks where grep did not, so a quantified group whose
# pieces can match the same text is exponential on a crafted command (CodeQL
# on #96: `git` and many `\t--`). Every repeated option group here is
# unambiguous: an option known to take the next word as its argument (git
# -C, -c, --git-dir, --attr-source...; env's -u/-C/-S clusters and their
# long forms) takes it whatever it is, as getopt does, and the generic
# branch refuses exactly those; any other option may take a next word that
# does not start with "-", so an option git or env adds later still reads
# right, and no word can be read two ways. (Refusing every argument that
# starts with "-" let `env -u -.` and `git -C -. push` through, round 7;
# listing only the options known to take one let `git --attr-source HEAD
# push` through, round 8.) The time budget below is what holds if one is
# missed.
GIT_WRITE = r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?([^\s]*/)?git(?:[\s]+(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))[\s]+[^\s]+|(?!(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+(push|commit|add|rm|mv|checkout|switch|restore|reset|stash|rebase|merge|cherry-pick|revert|clean|am|apply|fetch|pull|gc|tag[\s]+(-[adsfm]|--delete|--force|[A-Za-z0-9][^\s]*)|worktree[\s]+(add|remove|prune|move|lock|unlock|repair)|branch[\s]+(-[dDmMc]|--delete|--move|--copy)|remote[\s]+(add|remove|rm|rename|set-url)|config([\s]+(--(local|worktree|global|system)|(-f|--file)[\s]+[^\s]+))*[\s]+(set|unset|--add|--unset|--unset-all|--replace-all|--rename-section|--remove-section|--edit|-e|rename-section|remove-section|edit|[A-Za-z][A-Za-z0-9-]*\.[^\s]+[\s]+[^\s;&|-][^\s;&|]*))([\s]|$|[);&|])'
INSTALL = r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?((pnpm|npm|yarn)([\s]+-[A-Za-z-]+)*[\s]+(install|i|add|remove|rm|update|up|dedupe)([\s]|$|[);&|])|(flutter|dart)[\s]+pub[\s]+(get|add|remove|upgrade|downgrade)([\s]|$|[);&|])|dotnet[\s]+(restore|add|remove)([\s]|$|[);&|])|pip3?[\s]+install([\s]|$|[);&|])|cargo[\s]+(add|install)([\s]|$|[);&|]))'

# Secrets. Every account's shell carries its synced secrets in the
# environment (~/.bashrc sources secrets.env), so a reviewer listing its
# environment prints them into its transcript and the model's input: on
# 2026-10-04 one did, and the operator's signing key was rotated (#95).
# Denied in any command: the environment printed whole (env or printenv as a
# word with no command to run, bare set/export, declare -p/-x, os.environ /
# process.env / %ENV / ENVIRON / $ENV taken whole, BSD `ps e`), a
# secret-shaped name read (a $NAME expansion, ${!indirection}, or
# environ/getenv/process.env/ENVIRON near a secret-shaped name), and secret
# material by path (secret*.env, .config/agent-fabric, the stores,
# .password-store, .gnupg, /proc/*/environ, gpg's secret export, pass,
# fabric-secrets store get). `env -i ... cmd` stays allowed: it RUNS a command
# in a clean environment. A code SEARCH (grep, rg, git grep / log / show /
# diff / blame) may name these words as patterns and is refused only when it
# names a home, a hidden directory in one, or /proc as a path; the exemption
# covers that search alone, never what is chained or substituted into it.
# This is a fence for the routine spellings, not a sandbox: secret
# minimisation (keeping a secret out of the session's environment) is the
# control.
ENV_PRINT = (r'(^|[^A-Za-z0-9_.-])\\?(env|printenv)([\s]+(-[0iv]*[uCS](?:[\s]+[^\s]+|[^\s]+)|--(?:u|ch|sp)[A-Za-z-]*(?:=[^\s]*|[\s]+[^\s]+)|-(?![0iv]*[uCS]|-(?:u|ch|sp))[A-Za-z0-9-]+(?:=[^\s]*)?|[A-Za-z_][A-Za-z0-9_]*=[^\s]*))*[\s]*($|[;&|)<>#' "'" r'"`])|(^|[^A-Za-z0-9_.-])printenv([^A-Za-z0-9_.-]|$)|(^|[;&|(]|`)[\s]*set[\s]*($|[;&|)#])|(^|[;&|(]|`)[\s]*(export|declare|typeset)[\s]*($|[;&|)#])|(export|declare|typeset)[\s]+-[a-zA-Z]*[px]|compgen[\s]+-[a-zA-Z]*[ev]|os\.environ($|[^.[A-Za-z0-9_]|\.(copy|items|keys|values|__))|process\.env($|[^.[A-Za-z0-9_])|%ENV|ENVIRON($|[^[A-Za-z0-9_])|\$ENV($|[^A-Za-z0-9_])|(^|[^A-Za-z0-9_.-])ps([\s]+-[^\s]+)*[\s]+[a-zA-Z]*e[a-zA-Z]*([\s;|&]|$)')
SECRET_VAR = r'\$\{?[A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_KEY)|\$\{!|(environ|getenv|process\.env|ENVIRON|%ENV|\$ENV)[^;|&]{0,60}(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_KEY)'
SECRET_PATH = r'secrets?[^\s/]*\.env|\.config/agent-fabric|agent-fabric/(secrets|children)|\.password-store|\.gnupg|/proc/[^\s]*/environ|--export-secret|(^|[;&|(]|`)[\s]*pass[\s]+(show|ls|find|grep|otp)|(fabric-secrets|secret_store\.py)[\s]+(store[\s]+)?(get|show|export-key|bundle|child-bundle)'
# A search's PATH, as opposed to its pattern: a home itself or anything under
# one of its hidden directories (~/.config, ~/.local/share, the stores,
# .gnupg), the same reached by climbing out of the clone (../../.config), /,
# /home and /root as roots, anything in /proc, a home named through a . or ..
# component (~/., ~/projects/..), and any climb of two levels or more (from a
# clone, ../.. is its home).
HOME_PATH = (r'(~|\$HOME|\$\{HOME\}|/home/[^/\s""' "'" r']+|/root)(/[^\s""' "'" r']*)?/\.\.?(/|[\s""' "'" r';&|)]|$)|\.\.(/[^\s""' "'" r']*)?/\.\.(/|[\s""' "'" r';&|)]|$)|(~|\$HOME|\$\{HOME\}|/home/[^/\s"' "'" r']+|/root)(/\.[^/\s"' "'" r']+(/[^\s"' "'" r']*)?)?/?([\s"' "'" r';&|)]|$)|(^|[\s"' "'" r'=])(\.\./)+\.[^/\s"' "'" r']+|(^|[\s"' "'" r'=])/(home|root|proc)?/?([\s"' "'" r';&|)]|$)|(^|[\s"' "'" r'=])/proc(/[^\s]*)?([\s"' "'" r';&|)]|$)|/proc/[^\s]*/environ')
# A search path written with bash's expansions reaches what HOME_PATH names
# without naming it (/h*/*/.config/..., /{home,x}/..., ~user, .?/.?): any
# glob or brace in an absolute or ~ path, ~name, and a glob in a component
# that starts with "." count as a home path. This closes the routine
# spellings in a search only; a reader judged by the full rules (cat, an
# interpreter's open()) can expand a path just as well, which no string
# fence can follow -- the control for that is keeping secrets out of what
# the session can read.
GLOB_PATH = r"(^|[\s\"'=])[~/][^\s]*[*?[{]|(^|[\s\"'=])~[A-Za-z_]|(^|[\s\"'=/])\.[^\s/]*[*?[{]"
SEARCH = r'^[\s]*(grep|egrep|fgrep|rg|ag|git(?:[\s]+(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))[\s]+[^\s]+|(?!(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+(grep|log|show|diff|blame))([\s]|$)'
SUBSTITUTION = r'\$\(|`|[<>]\('

# A directory change outlives the command (the harness keeps the shell's
# directory between calls), so a later search of . would read wherever it
# went: no cd or pushd home (bare, -, ~), into a home's hidden directories,
# up out of the clone (..), or to /, /home, /root, /proc.
CD = r'^[\s]*(cd|pushd)([\s]+-[LPe@]+)*[\s]*($|-([\s]|$)|~)'
CD_ANY = r'^[\s]*(cd|pushd)([\s]|$)'
CD_UP = r"(^|[\s/\"'])\.\.(/|[\s\"']|$)"

# Shell escapes that would carry any of the above past a string match, and
# the routine in-place file writes. Also what makes an allowed tool run a
# program the guard never sees: git's one-shot config (-c / --config-env:
# diff.external, core.pager), a GIT_*, PAGER or EDITOR assignment, rg --pre,
# find -exec / -ok, git grep -O in any option cluster or --op... prefix (its
# pager is a shell command). git's -c only among its global options, so
# `git grep -c` and `git log -c` count as reads. Redirections are allowed only to /dev/null (the
# reviewer's own quieting) or to another fd.
ESCAPE = (r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?(eval|exec|(ba|z|da|k)?sh[\s]+-[a-zA-Z]*c)([\s]|$)|(^|[^A-Za-z0-9_.-])git(?:[\s]+(?:(?:-C|--(?:git-dir|work-tree|namespace|super-prefix|attr-source|list-cmds))[\s]+[^\s]+|(?!(?:-C|--(?:git-dir|work-tree|namespace|super-prefix|attr-source|list-cmds))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+(-c([\s]|$)|--config-env)|(^|[^A-Za-z0-9_.-])git(?:[\s]+(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))[\s]+[^\s]+|(?!(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+grep[\s]([^;&|]*[\s\"' "'" r'])?(-[A-Za-z]*O|--op)|(^|[;&|(`\s])(GIT_[A-Z0-9_]+|PAGER|LESSOPEN|LESSCLOSE|EDITOR|VISUAL)=|[\s]--pre([\s=]|$)|[\s]-(exec|execdir|ok|okdir)([\s]|$)')
WRITE = r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?(sed[\s]+(-[a-zA-Z]*i|--in-place)|tee|rm|mv|cp|truncate|chmod|chown|ln|install|patch|rsync)([\s]|$)'

# A hook that runs past the agent file's timeout (10 s) is not a refusal, so
# the verdict runs in a child given this budget, and a child that is late,
# dies or answers nothing is a deny. AGENT_FABRIC_REVIEW_GUARD_BUDGET may only
# shorten it (the tests' seam).
BUDGET_S = 3.0

REASONS = {
    "slow": "The review-class bash guard could not judge this command within its time budget, so it is denied. Split it into simpler commands.",
    "error": "The review-class bash guard failed while judging this command, so it is denied. Report without it, or split it into simpler commands.",
    "secret": "The review class may not print the environment, expand a secret-shaped variable, or read secret material (secrets.env, the stores, gpg keys, /proc/*/environ): every account's environment carries its credentials, and what you print enters the transcript. Describe a secret by its name and shape only. To run a check in a clean environment, use env -i NAME=value \u2026 command.",
    "moved": "The review class may not change directory to a home, a hidden directory in one, up out of the clone (..), or back (cd, cd -, cd ~): the shell keeps its directory between calls, so what you search next would read it. Name the path in the command, or use git -C <path>.",
    "escape": "The review class may not use shell escapes (eval, exec, sh -c): they carry a write past this guard. Run the command directly.",
    "write": "The review class runs in the session clone and is READ-ONLY: no in-place edits, no file writes, no redirection except to /dev/null. Report what you would have changed instead.",
    "git": "The review class runs in the session clone and is READ-ONLY: no state-changing git (push, commit, checkout, reset, stash, ...). Read-only history (log, show, diff, blame) is expected of you. Report what you would have changed instead.",
    "install": "The review class may not run installs or restores (pub get, pnpm install, dotnet restore, ...): they rewrite tracked lockfiles in the session clone. Build and test only with what is already restored (dotnet build/test --no-restore, pnpm --filter <app> test), or say the check needs an install and skip it.",
}


def found(pattern: str, text: str) -> bool:
    """grep -qE: a match on any one line."""
    rx = re.compile(pattern)
    return any(rx.search(line) for line in text.split("\n"))


def split_unquoted(cmd: str) -> tuple[list[str], bool]:
    """The command cut at ; & | and newlines OUTSIDE quotes, and whether the
    cut can be trusted to agree with bash about what is quoted. An exemption
    over the whole command let `grep x f; env` through (#96 round 2); a cut
    blind to quotes made a search of the middle of `python3 -c "a;grep
    =...;b"` (round 3); a comment hid a quote from the cut, so `grep x #'`,
    a line running env, and `#'` read as one quoted search (round 4),
    and a continuation (backslash-newline) hid a comment the same way
    (round 5). Modelling each construct bash quotes by would only move the
    next gap, so the cut is trusted only where it cannot disagree with
    bash: ONE line (bash parses a whole line before it runs any of it, and
    a comment there runs nothing, so # needs no rule of its own), no quote
    left open, no $'...' (an escaped quote bash reads and the cut does not),
    no ${...} (whose quotes bash parses by rules of their own), and no
    substitution anywhere in the command. Otherwise no segment is exempt and
    every one answers to the full rules: a search refused, never a command
    admitted."""
    segments, cur, quote, i = [], [], "", 0
    trusted = not re.search(SUBSTITUTION, cmd) and not any(x in cmd for x in ("$'", "${", "\n"))
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and quote != "'":
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        if quote:
            if c == quote:
                quote = ""
            cur.append(c)
        elif c in "\"'":
            quote = c
            cur.append(c)
        elif c in ";&|\n":
            segments.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    segments.append("".join(cur))
    return segments, trusted and not quote


def verdict(cmd: str) -> str | None:
    segments, exempt = split_unquoted(cmd)
    secret = moved = False
    for seg in segments:
        if found(CD_ANY, seg) and (found(CD, seg) or found(CD_UP, seg) or found(HOME_PATH, seg)):
            moved = True
        if exempt and found(SEARCH, seg):
            secret |= found(HOME_PATH, seg) or found(GLOB_PATH, seg) or found(SECRET_VAR, seg)
        elif found(ENV_PRINT, seg) or found(SECRET_VAR, seg) or found(SECRET_PATH, seg):
            secret = True
    # The cut loses the separators some patterns anchor on; the whole command
    # still answers to them unless a segment was an exempt search.
    if not secret and not (exempt and any(found(SEARCH, s) for s in segments)):
        secret = found(ENV_PRINT, cmd) or found(SECRET_VAR, cmd) or found(SECRET_PATH, cmd)
    if secret:
        return "secret"
    if moved:
        return "moved"
    if found(ESCAPE, cmd):
        return "escape"
    stripped = "\n".join(
        re.sub(r">>?[^\S\n]*/dev/null", "", re.sub(r"[0-9]*>&[0-9-]*", "", line))
        for line in cmd.split("\n"))
    if found(WRITE, cmd) or ">" in stripped:
        return "write"
    if found(GIT_WRITE, cmd):
        return "git"
    if found(INSTALL, cmd):
        return "install"
    return None


def judged(cmd: str) -> str | None:
    """verdict(cmd) from a child within the budget; "slow" or "error" when
    the child does not answer in time or answers nothing."""
    budget = BUDGET_S
    try:
        budget = min(budget, float(os.environ.get("AGENT_FABRIC_REVIEW_GUARD_BUDGET", budget)))
    except ValueError:
        pass
    if not budget > 0:
        return "slow"
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        try:
            answer = verdict(cmd) or "allow"
        except BaseException:
            answer = "error"
        os.write(w, answer.encode())
        os._exit(0)
    os.close(w)
    ready, _, _ = select.select([r], [], [], max(budget, 0.0))
    if not ready:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        return "slow"
    answer = os.read(r, 64).decode(errors="replace")
    os.waitpid(pid, 0)
    if answer == "allow":
        return None
    return answer if answer in REASONS else "error"


def main() -> int:
    try:
        cmd = json.load(sys.stdin)["tool_input"]["command"]
    except Exception:
        return 0
    if not isinstance(cmd, str) or not cmd:
        return 0
    why = judged(cmd.rstrip("\n"))
    if why:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASONS[why]}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
