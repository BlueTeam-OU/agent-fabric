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

Output: a deny decision, or the command rewritten to run with a clean
environment (CLEAN_ENV below) and no permission decision. Exit 0 always --
exit 2 would block; a guard that cannot parse its input allows and says
nothing. A guard that
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
import shlex
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
# push` through, round 8.) git's options known to take no word (--no-pager,
# -p, -P...) never take one. The deny patterns read an unknown option
# broadly and the search exemption (SEARCH) narrowly, so a misreading can
# only refuse, or fall to the full rules, which do not refuse a bare home
# path (a git option no git has; git itself rejects it). env's generic branch takes no separated word: an env option
# that takes one is named. The time budget below is what holds if one is
# missed.
GIT_WRITE = r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?([^\s]*/)?git(?:[\s]+(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))[\s]+[^\s]+|(?:-[pPhv]|--(?:no-pager|paginate|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|html-path|man-path|info-path|version|help))(?=[\s]|$)|(?!(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))|(?:-[pPhv]|--(?:no-pager|paginate|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|html-path|man-path|info-path|version|help)))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+(push|commit|add|rm|mv|checkout|switch|restore|reset|stash|rebase|merge|cherry-pick|revert|clean|am|apply|fetch|pull|gc|tag[\s]+(-[adsfm]|--delete|--force|[A-Za-z0-9][^\s]*)|worktree[\s]+(add|remove|prune|move|lock|unlock|repair)|branch[\s]+(-[dDmMc]|--delete|--move|--copy)|remote[\s]+(add|remove|rm|rename|set-url)|config([\s]+(--(local|worktree|global|system)|(-f|--file)[\s]+[^\s]+))*[\s]+(set|unset|--add|--unset|--unset-all|--replace-all|--rename-section|--remove-section|--edit|-e|rename-section|remove-section|edit|[A-Za-z][A-Za-z0-9-]*\.[^\s]+[\s]+[^\s;&|-][^\s;&|]*))([\s]|$|[);&|])'
INSTALL = r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?((pnpm|npm|yarn)([\s]+-[A-Za-z-]+)*[\s]+(install|i|add|remove|rm|update|up|dedupe)([\s]|$|[);&|])|(flutter|dart)[\s]+pub[\s]+(get|add|remove|upgrade|downgrade)([\s]|$|[);&|])|dotnet[\s]+(restore|add|remove)([\s]|$|[);&|])|pip3?[\s]+install([\s]|$|[);&|])|cargo[\s]+(add|install)([\s]|$|[);&|]))'

# Secrets. Every account's shell carried its synced secrets in the
# environment (~/.bashrc sourced secrets.env until ADR-038 rule 9), and a
# session started from such a shell still can, so a reviewer listing its
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
SECRET_PATH = r'secrets?[^\s/]*\.env|\.config/agent-fabric|agent-fabric/(secrets|children)|\.password-store|\.gnupg|/proc/[^\s]*/environ|--export-secret|(^|[;&|(]|`)[\s]*pass[\s]+(show|ls|find|grep|otp)|(fabric-secrets|secret_store\.py)[\s]+(store[\s]+)?(get|show|export-key|bundle|child-bundle|paper|recovery-copy)|(^|[\s"=<>(])/([^\s/]*[*?[{]|p)[^\s/]*(/|[\s]|$)|(^|[;&|(`][\s]*|[\s])(ba|z|k|da)?sh[\s]+([^;&|]*[\s])?(-[a-zA-Z]*[il][a-zA-Z]*|--login|--rcfile|--init-file)([\s=]|$)|(^|[;&|(`]|\bthen|\bdo)[\s]*(source|\.)[\s]+[^\s;&|]*(\.bashrc|\.bash_profile|\.bash_login|\.profile|\.zshrc|\.zprofile|secrets?[^\s/;&|]*\.env|[*?[])'
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
SEARCH = r'^[\s]*(grep|egrep|fgrep|rg|ag|git(?:[\s]+(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))[\s]+[^\s]+|(?!(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*)?))*[\s]+(grep|log|show|diff|blame))([\s]|$)'
SUBSTITUTION = r'\$\(|`|[<>]\('

# A directory change outlives the command (the harness keeps the shell's
# directory between calls; under the clean-environment rewrite a cd inside
# `bash -c` no longer does, and the rule stays for a command the rewrite
# misses), so a later search of . would read wherever it
# went: no cd or pushd home (bare, -, ~), into a home's hidden directories,
# up out of the clone (..), or to /, /home, /root, /proc.
CD = r'^[\s]*(cd|pushd)([\s]+-[LPe@]+)*[\s]*($|-([\s]|$)|~)'
CD_ANY = r'^[\s]*(cd|pushd)([\s]|$)'
# A word the shell rewrites before cd sees it (a glob, a brace: `.[.]` and
# `{.,.}` are .. to cd, never to CD_UP), or an argument that is an option or
# `--` (cd -- goes home; -P/-L let the next word be anything): what the cd
# reaches is not what the text says, so it is refused rather than modelled.
CD_ODD = r'^[\s]*(cd|pushd)[\s]+([^\s]*[][*?{}]|-)'
CD_STEP = r"(^|[\s{(]|then|do|else)[\s]*((command|builtin)[\s]+)?(cd|pushd|popd)([\s]|$)"
TRIVIAL = r"^[\s]*([0-9]*|[})]+|fi|done|esac|true|false|:|[0-9]*>[\s]*/dev/null)?[\s]*$"
CD_UP = r"(^|[\s/\"'])\.\.(/|[\s\"']|$)"

# Shell escapes that would carry any of the above past a string match, and
# the routine in-place file writes. Also what makes an allowed tool run a
# program the guard never sees: git's one-shot config (-c / --config-env:
# diff.external, core.pager), a GIT_*, PAGER or EDITOR assignment, rg --pre,
# find -exec / -ok, git grep -O in any option cluster or --op... prefix (its
# pager is a shell command). git's -c only among its global options, so
# `git grep -c` and `git log -c` count as reads. Redirections are allowed only to /dev/null (the
# reviewer's own quieting) or to another fd.
ESCAPE = (r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?(eval|exec|(ba|z|da|k)?sh[\s]+-[a-zA-Z]*c)([\s]|$)|(^|[^A-Za-z0-9_.-])git(?:[\s]+(?:(?:-C|--(?:git-dir|work-tree|namespace|super-prefix|attr-source|list-cmds))[\s]+[^\s]+|(?:-[pPhv]|--(?:no-pager|paginate|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|html-path|man-path|info-path|version|help))(?=[\s]|$)|(?!(?:(?:-C|--(?:git-dir|work-tree|namespace|super-prefix|attr-source|list-cmds))|(?:-[pPhv]|--(?:no-pager|paginate|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|html-path|man-path|info-path|version|help)))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+(-c([\s]|$)|--config-env)|(^|[^A-Za-z0-9_.-])git(?:[\s]+(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))[\s]+[^\s]+|(?:-[pPhv]|--(?:no-pager|paginate|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|html-path|man-path|info-path|version|help))(?=[\s]|$)|(?!(?:(?:-[Cc]|--(?:git-dir|work-tree|namespace|super-prefix|config-env|attr-source|list-cmds))|(?:-[pPhv]|--(?:no-pager|paginate|bare|literal-pathspecs|glob-pathspecs|noglob-pathspecs|icase-pathspecs|no-replace-objects|no-lazy-fetch|no-optional-locks|no-advice|html-path|man-path|info-path|version|help)))(?:[\s]|$))-[A-Za-z-]+(?:=[^\s]*|[\s]+[^\s-][^\s]*)?))*[\s]+grep[\s]([^;&|]*[\s\"' "'" r'])?(-[A-Za-z]*O|--op)|(^|[;&|(`\s])(GIT_[A-Z0-9_]+|PAGER|LESSOPEN|LESSCLOSE|EDITOR|VISUAL)=|[\s]--pre([\s=]|$)|[\s]-(exec|execdir|ok|okdir)([\s]|$)')
WRITE = r'(^|[;&|(]|`)[\s]*(sudo[\s]+)?(sed[\s]+(-[a-zA-Z]*i|--in-place)|tee|rm|mv|cp|truncate|chmod|chown|ln|install|patch|rsync)([\s]|$)'

# A hook that runs past the agent file's timeout (10 s) is not a refusal, so
# the verdict runs in a child given this budget, and a child that is late,
# dies or answers nothing is a deny. AGENT_FABRIC_REVIEW_GUARD_BUDGET may only
# shorten it (the tests' seam).
BUDGET_S = 3.0

REASONS = {
    "slow": "The review-class bash guard could not judge this command within its time budget, so it is denied. Split it into simpler commands.",
    "error": "The review-class bash guard failed while judging this command, so it is denied. Report without it, or split it into simpler commands.",
    "secret": "The review class may not print the environment, expand a secret-shaped variable, or read secret material (secrets.env, the stores, gpg keys, /proc/*/environ): an account's environment or files may carry its credentials, and what you print enters the transcript. Describe a secret by its name and shape only. To run a check in a clean environment, use env -i NAME=value \u2026 command.",
    "moved": "The review class may not change directory to a home, a hidden directory in one, up out of the clone (..), or back (cd, cd -, cd --, cd ~), nor through a glob, a brace or an option (cd .[.], cd {a,b}, cd -P): what the command does after the cd would read there. Name the path in the command, or use git -C <path>.",
    "cd-last": "A cd that ends a command does not last: each command the review class runs is its own shell, so the next one starts where this one did. Put the work after it in the same command (cd <dir> && git log ...), or name the directory (git -C <dir> ..., grep -rn x <dir>).",
    "escape": "The review class may not use shell escapes (eval, exec, sh -c): they carry a write past this guard. Run the command directly.",
    "write": "The review class runs in the session clone and is READ-ONLY: no in-place edits, no file writes, no redirection except to /dev/null. Report what you would have changed instead. A review is posted as: fabric-pr post-review <pr> [--model <name>] <<'EOF' … EOF (a quoted tag; nothing after the terminator).",
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


# The review class's one write is its review: `fabric-pr post-review <N>`
# with the body on stdin as ONE heredoc whose tag is quoted, and only the
# verb's own options, each at most once, in either order: --model <name>
# (a label post_review.py records, not a routing choice, so any plain word)
# and --dry-run. Quoting any part of the tag stops bash expanding the body;
# only the whole 'TAG' and "TAG" forms are admitted, and not <<-, a second
# shape nothing needs. The body is data, so the word and redirection rules
# judge the command line alone, and the first line equal to the tag must be
# the command's last: nothing runs after it.
_MODEL = r"[ \t]+--model[ \t]+(?!-)[A-Za-z0-9._-]+"
_DRY_RUN = r"[ \t]+--dry-run"
POST_REVIEW = re.compile(r"[ \t]*((?:cd[ \t]+(?!-)[^\s;&|<>()`$'\"\\\[\]*?{}]+[ \t]+&&[ \t]+)?fabric-pr[ \t]+post-review[ \t]+[0-9]+"
                         rf"(?:{_MODEL}(?:{_DRY_RUN})?|{_DRY_RUN}(?:{_MODEL})?)?)"
                         r"[ \t]+<<[ \t]*(['\"])([A-Za-z0-9_]+)\2[ \t]*")


def posted_review(cmd: str) -> str | None:
    """The command line of a review posted in exactly that shape, else None."""
    lines = cmd.split("\n")
    m = POST_REVIEW.fullmatch(lines[0])
    if not m or m.group(3) not in lines[1:]:
        return None
    return m.group(1) if lines.index(m.group(3), 1) == len(lines) - 1 else None


def verdict(cmd: str) -> str | None:
    head = posted_review(cmd)
    if head is not None:
        return verdict(head)
    segments, exempt = split_unquoted(cmd)
    secret = moved = False
    for seg in segments:
        if found(CD_ANY, seg) and (found(CD, seg) or found(CD_ODD, seg) or found(CD_UP, seg) or found(HOME_PATH, seg)):
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
    # Under the rewrite the command runs in its own `bash -c`, so a cd that
    # ends it changes nothing the next call sees: the reviewer would then
    # read, search and test the directory it meant to leave (Codex on #97).
    # A cd before more work in the same command still applies to that work.
    # The cut also splits a redirection's `2>&1` and leaves a closing `}`,
    # `fi` or `|| true` behind, so it is the last cd-like segment that
    # counts, when nothing after it does work (#97's round 4).
    for i in range(len(segments) - 1, -1, -1):
        if found(CD_STEP, segments[i]):
            if all(found(TRIVIAL, seg) for seg in segments[i + 1:]):
                return "cd-last"
            break
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


# What a command the fence lets through keeps of its environment: the
# variables a build or a test needs to find its tools and a place to write,
# and nothing else. An account's shell carried its synced secrets
# (~/.bashrc sourced secrets.env before ADR-038 rule 9; a session from an
# older shell still may), and the patterns above judge spellings,
# which bash can always outrun (#96: nine rounds, each a new one); a command
# that starts from this list inherits no secret, however it is spelled. It
# removes the inherited environment, not every way back to it: the account's
# files, a parent's /proc environ and a shell init file that sources
# secrets.env stay reachable by some spelling. SECRET_PATH refuses the
# routine ones and closes none; keeping secrets off what the session can
# read is what would.
# The names are fixed here and the values are expanded by the reviewer's
# own shell when the command runs, so no value passes through this hook.
# Measured: docs/live-checks/2026-10-05-hook-updated-input.md.
CLEAN_ENV = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "PWD", "TERM", "TMPDIR", "TZ",
             "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "XDG_RUNTIME_DIR",
             "AGENT_FABRIC_ROOT", "AGENT_FABRIC_PYTHON",
             # The session markers: no secret, and what a tool reads to refuse
             # inside a model session (fabric-secrets store paper, a role
             # rebind); without them those refusals would not fire.
             "CLAUDECODE", "CLAUDE_ENV_FILE", "AGENT_FABRIC_LAUNCH_PROFILE")
assert not any(re.search(r"TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_KEY", n) for n in CLEAN_ENV)


def wrapped(cmd: str) -> str:
    """cmd run by bash with only CLEAN_ENV, each kept only when it is set
    (an empty TZ is not an unset one). --norc: bash reads ~/.bashrc, which
    sourced secrets.env before ADR-038 rule 9 and may again by a hand
    edit, for `bash -c` whose stdin is a socket (measured in
    #97's review; the harness gives /dev/null today), so the rewrite must
    not depend on what stdin it is given."""
    keep = " ".join('${%s+"%s=$%s"}' % (n, n, n) for n in CLEAN_ENV)
    return f"/usr/bin/env -i {keep} bash --norc --noprofile -c {shlex.quote(cmd)}"


def main() -> int:
    try:
        tool_input = json.load(sys.stdin)["tool_input"]
        cmd = tool_input["command"]
    except Exception:
        return 0
    if not isinstance(cmd, str) or not cmd:
        return 0
    why = judged(cmd.rstrip("\n"))
    if why:
        out = {"hookEventName": "PreToolUse", "permissionDecision": "deny",
               "permissionDecisionReason": REASONS[why]}
    else:
        # No permission decision: the rewrite changes what runs and nothing
        # about who may run it; the session's own permission checks still
        # apply. The whole input goes back, so a timeout, a description or a
        # background run is kept.
        out = {"hookEventName": "PreToolUse", "updatedInput": {**tool_input, "command": wrapped(cmd)}}
    print(json.dumps({"hookSpecificOutput": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
