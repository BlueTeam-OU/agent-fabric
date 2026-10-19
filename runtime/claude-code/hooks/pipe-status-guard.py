#!/usr/bin/env python3
"""runtime/claude-code/hooks/pipe-status-guard.py — the pipe-status guard (ADR-040 Wave 9 batch 5;
pipe-status-guard.sh beside it is its forwarder, run by the PreToolUse hook on Bash of
runtime/claude-code/workspace/settings.json and .claude/settings.json, for every session).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none read
  stdin     the PreToolUse payload, JSON: tool_input.command, read as jq's `.tool_input.command // empty`
  env       PATH (jq's presence, below); nothing else
  stdout    nothing (allow), or one compact hookSpecificOutput line: hookEventName PreToolUse, permissionDecision
            deny, permissionDecisionReason
            "A check piped into a filter and chained with && into a commit, push or merge tests the filter's
            exit status, not the check's: a failed check would still commit. Run the check to a log, capture
            rc=$?, and commit only on 0."
  stderr    nothing
  exit      0, always

DECISIONS, in order:
  1. no `jq` on PATH -> nothing. This module needs no jq; the bash allowed without it ("a fence against a habit,
     not a sandbox") and its oracle holds that case, so the check is kept as the bash had it. It is an allow
     with the tool missing, the one place this guard fails open; dropping it is the coordinator's call.
  2. stdin not JSON, or the command read with an error (tool_input a string, a number, true, an array) ->
     nothing
  3. the command absent, null, false or empty                        -> nothing
  4. the command made one line (each newline a space, then each `\\ ` a space), every `&` that is not part of
     `&&` dropped, then searched for
        \\|SP*(tail|head|grep|sed|cut|wc|awk|sort|uniq|tee)\\b[^;]*&&.*\\bWRITE\\b
     WRITE: `git`, any global options (each `-x` or `--x`, optionally with one argument: a "…" or '…' string
     or a word not starting with `-`), then commit or push; or `gh pr merge` / `gh pr create`. SP is
     [[:space:]] as GNU grep reads it in a UTF-8 locale (an em space is one, a no-break space is not). A match
     -> deny. refused() decides that match in linear time, without `re` (its docstring says why).

NOT BYTE-IDENTICAL to the bash:
  - the bash searched with GNU grep -E; this decides the same expression by hand (refused()). Checked against
    the expression compiled as a Python pattern on 300 000 generated commands: no disagreement.
  - a command that is not a string is rendered as Python's JSON, not jq's: an array or object is printed
    indented by both, so the strings in it are searched as the bash searched them; a number differs only in
    its spelling (jq 1.8 kept the literal) and holds no pipe.
  - `\\b` follows Python's Unicode word characters, where GNU grep followed glibc's UTF-8 locale: measured
    over every code point, the two disagree on 2410 (1495 grep alone calls word, mostly combining marks; 915
    Python alone, mostly numerals of other scripts). Only a filter, `git`, `gh` or a subcommand glued to one
    of those is read differently, in either direction; such a word names no command the shell would run as
    git or tail. Under LANG=C grep read bytes; this reads characters whatever the locale.
  - a stream of several JSON values, a NaN, a lone surrogate: read as jq 1.8 reads them.

WHY, the bash's header kept: `check | tail -1 && git commit` tests tail's exit status, which is 0 whatever the
check did, so a failed lint, suite or gate still commits, pushes or merges. A written rule did not hold: the
coordinator did it six times, the last one pushing a red test to a pull request. A pipe followed by `;` is not
refused (nothing is chained on it), nor a pipe no commit, push or merge follows.
Only `&&` chains matter. Every other `&` — in a redirection (`2>&1`, `>& log`, `&>log`, `<&0`), a `|&` pipe or
a background job — is dropped before matching, so no spelling of a redirection hides the chain (review of #54:
each narrower rule left one).
No exemption for pipefail: telling a `set -o pipefail` the shell runs from one in an echo, a comment or a
subshell is a shell parser this hook is not, and each attempt left a bypass (review of #54). The way through is
the one the message names: run the check, capture its status, commit on 0.
"""
from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # `python -I` leaves this directory off
import hook_jq  # noqa: E402

FILTERS = ("tail", "head", "grep", "sed", "cut", "wc", "awk", "sort", "uniq", "tee")   # no one a prefix of another
# [[:space:]] as GNU grep reads it in a UTF-8 locale: Python's str.isspace() but for the eight it adds
# (U+001C-U+001F, U+0085, U+00A0, U+2007, U+202F), measured over every code point on 2026-10-19; an em space is
# one, as grep said.
NOT_GREP_SPACE = frozenset("\x1c\x1d\x1e\x1f\x85\xa0  ")
REASON = ("A check piped into a filter and chained with && into a commit, push or merge tests the filter's exit status, "
          "not the check's: a failed check would still commit. Run the check to a log, capture rc=$?, and commit only on 0.")


def command(value) -> list:
    c = hook_jq.index(hook_jq.index(value, "tool_input"), "command")
    return [] if c is None or c is False else [c]


def flatten(cmd: str) -> str:
    # One line: a continuation or a newline must not hide the chain.
    flat = cmd.replace("\n", " ").replace("\\ ", " ")
    return flat.replace("&&", "\x01").replace("&", "").replace("\x01", "&&")


def refused(cmd: str) -> bool:
    """Whether the ERE of the header matches the flattened command, decided in linear time.

    WHY NOT `re`: the ERE as one Python pattern backtracks `[^;]*&&.*` over every filter and every `git`, and took
    9 s on a 4 KB command of repeated `| tail && git -C 'a' -c` (cubic). A hook that outlives the harness's timeout
    is read as no objection, so a long enough command would have walked past a guard that grep's DFA held in linear
    time. Here each piece of the ERE is matched once per position. Every run of [[:space:]], or of its complement,
    is taken whole: what follows each such run in the ERE cannot start with the same class."""
    flat = flatten(cmd)
    n = len(flat)
    sp_end = [n] * (n + 1)      # first index >= i that is not [[:space:]]
    nsp_end = [n] * (n + 1)     # first index >= i that is [[:space:]]
    amp = [-1] * (n + 1)        # first `&&` at or after i
    semi = [n] * (n + 1)        # first `;` at or after i
    dq = [-1] * (n + 1)         # first `"` at or after i
    sq = [-1] * (n + 1)         # first `'` at or after i
    for i in range(n - 1, -1, -1):
        c = flat[i]
        space = c.isspace() and c not in NOT_GREP_SPACE
        sp_end[i] = sp_end[i + 1] if space else i
        nsp_end[i] = i if space else nsp_end[i + 1]
        amp[i] = i if flat.startswith("&&", i) else amp[i + 1]
        semi[i] = i if c == ";" else semi[i + 1]
        dq[i] = i if c == '"' else dq[i + 1]
        sq[i] = i if c == "'" else sq[i + 1]

    def word(i: int) -> bool:
        return 0 <= i < n and (flat[i].isalnum() or flat[i] == "_")    # Python's \w

    def ends_word(i: int, w: str) -> bool:
        """`w\\b` at i."""
        return flat.startswith(w, i) and not word(i + len(w))

    # \|SP*FILTER\b[^;]*&& : the earliest `&&` that any piped filter reaches with no `;` between.
    first = -1
    for i in range(n):
        if flat[i] != "|":
            continue
        j = sp_end[i + 1]
        for f in FILTERS:
            if ends_word(j, f):
                a = amp[j + len(f)]
                if a != -1 and semi[j + len(f)] > a and (first == -1 or a < first):
                    first = a
                break
    if first == -1:
        return False

    # What may follow `git`: (SP+ -NSP+ (SP+ ("[^"]*"|'[^']*'|[^-SP]NSP*))?)* SP+ (commit|push)\b, from each
    # position, right to left.
    after_git = [False] * (n + 1)
    for p in range(n - 1, -1, -1):
        k = sp_end[p]
        if k == p:
            continue                                   # every way on starts with SP+
        if ends_word(k, "commit") or ends_word(k, "push"):
            after_git[p] = True
            continue
        if k >= n or flat[k] != "-" or nsp_end[k + 1] == k + 1:
            continue
        m = nsp_end[k + 1]                             # past the option, -NSP+
        if after_git[m]:
            after_git[p] = True
            continue
        k2 = sp_end[m]
        if k2 == m or k2 >= n:
            continue
        ends = [nsp_end[k2]] if flat[k2] != "-" else []       # its argument, a word
        if flat[k2] == '"' and dq[k2 + 1] != -1:
            ends.append(dq[k2 + 1] + 1)                        # or a "…" string
        if flat[k2] == "'" and sq[k2 + 1] != -1:
            ends.append(sq[k2 + 1] + 1)                        # or a '…' string
        after_git[p] = any(after_git[q] for q in ends)

    # .*\b(git… | gh SP+ pr SP+ (merge|create)\b) anywhere after that `&&`
    for w in range(first + 2, n):
        if flat[w] != "g" or word(w - 1):
            continue
        if flat.startswith("git", w) and after_git[w + 3]:
            return True
        if flat.startswith("gh", w):
            k = sp_end[w + 2]
            if k > w + 2 and flat.startswith("pr", k):
                k2 = sp_end[k + 2]
                if k2 > k + 2 and (ends_word(k2, "merge") or ends_word(k2, "create")):
                    return True
    return False


def main() -> int:
    if shutil.which("jq") is None:
        return 0
    values, ok = hook_jq.run(sys.stdin.buffer.read().decode("utf-8", "replace"), command)
    if not ok:
        return 0
    cmd = hook_jq.captured(values)
    if cmd and refused(cmd):
        hook_jq.write(hook_jq.decision("PreToolUse", "deny", REASON) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
