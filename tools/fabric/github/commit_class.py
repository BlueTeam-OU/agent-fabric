#!/usr/bin/env python3
"""tools/fabric/github/commit_class.py — ONE classifier for "is this commit a
review fix": merge, fix or work (ADR-019's count rule, ADR-040's first
Wave 1 port). runtime/github/commit-class.sh is its shim, sourced by
pr-gate.sh and the managed projects' forwarders; results.py imports it.

    commit_class.py class <parents> <subject> [<answers>] [<pr>] [<owner/repo>] [<kind>] [<head>] [<base>]
                                          prints merge | fix | work
    commit_class.py revert-targets        the shas a commit body (stdin) reverts

CONTRACT, frozen from the bash (ADR-040 §5 rule 3): the arguments above, in
that order, the optional ones may be empty; one word on stdout; exit 0.
<parents> is the space-separated parent list (git log %P); <answers> the
value of the commit's `Answers:` trailer (git log
%(trailers:key=Answers,valueonly)); <kind> the value of its `Kind:` trailer
(the last when there are several); <head> the counted PR's head, which
lets a fold be read (below). <kind> and <head> came last so every older
caller's argv still means what it meant.

WHY EACH RULE (carried from the bash, which recorded the incidents):

A review FIX is a subject that names a REVIEW (review, re-review,
finding(s), nit(s), as words) AND says it answers one (a finding label
F3/N1/P2, fix/address/answer, a round, a #PR, or a nit or finding word
again) — or carries a finding label AND a #PR with no review word at all,
the supplier's shape "(#861 F6)". Either half alone misreads the managed
project: the review word alone made "admin driver review: approving …" and
"the review decision's reason" fixes; a fix: opener alone made 804 of the
last 3000 subjects fixes — that repository writes bug fixes as fix(scope):
— and turned a "split" into an "arm" on #757 (2026-09-18 re-review, F1).
Measured on those 3000: 95 read as fixes.

THE TRAILER, `Answers: <finding labels>`, is read FIRST: a commit that
carries it is a review fix whatever its subject says. A fix commit whose
subject names no review at all ("db: 0055's guard was too broad and
stopped the file re-applying") read as work on #892, 18 > 16, and the
ceiling refused a PR that held 15. Any non-empty value counts.

THE DECLARATION, `Kind: work | review-fix`, outranks everything below
(ADR-019 §5 rule 3): the commit-msg hook asks every commit for it, after
two sessions' counts were misread the same day — review fixes with no
Answers: read as work, "findings" commits read as fixes. Kind: work is
work, whatever the subject says. Kind: review-fix is a fix, EXCEPT where
the rule for the PR being counted says the commit answers another PR's
review: the hook stamps review-fix on any commit with Answers:, and a
follow-up PR's commit answering #53's findings is that PR's own work —
the declaration says what the commit is, not whose band it falls in. A
missing, empty or unknown value (an older commit, one made without the
hook) is read exactly as before.

A FOLD is the exception to that other-PR rule (ADR-019 §5 rule 3,
amended 2026-10-08): a PR closed unmerged whose head lies inside the
counted range, <base>..<head>, was folded in — merged unrebased into this
branch, then closed — and its review fixes are fixes here. gateway#10
folded into #11 read 8 work where 6 was right. A head already inside the
base was folded into an earlier PR, and a follow-up answering it is work.
Telling a fold from a follow-up needs GitHub (state) and git (ancestry),
so it is asked only with <head> (and the range's <base> where the caller
has it), once per PR named (Folds). A PR that cannot be read keeps the reading from
before the amendment, work, and says so on stderr, so the session
counting sees which commits it could not place.

A finding LABEL is one or two capitals, an optional dash, digits, an
optional -digits: F4, P3, N12, G1, PE-6, PR-1, P3-1. The first shape was
[FNP][0-9]+ and read "review PE-6:" and "review PR-1:" as WORK — four on
#883 inflated the count from 8 to 13. Case-sensitive on purpose: "v2",
"utf8", "sha1" are not labels; a three-letter run (ADR-071, OTP) is not
either.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import gh  # noqa: E402
import git  # noqa: E402
import roots  # noqa: E402
FORM = r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#|[A-Za-z0-9_.-]+#|[A-Za-z0-9_.-]+\s+#|#)[0-9]+"
LABEL = r"[A-Z]{1,2}-?[0-9]+"


def known_repos(registry: str | None = None) -> set[str]:
    """The repository names the fabric registers: each project id and the
    name of each of its remotes, lower-cased. An unreadable registry names
    none."""
    try:
        reg = json.load(open(registry or roots.projects_registry(engine=roots.code_root()), encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    names = set()
    for pid, p in (reg.get("projects") or reg).items():
        if not isinstance(p, dict):
            continue
        names.add(pid.lower())
        for r in p.get("remotes") or []:
            names.add(re.sub(r"\.git$", "", r).rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower())
    return names


def _ref(ref: str, here: str) -> str:
    """One reference -> the PR number it names, or "x" when it names another
    repository than <owner/repo>. Without a repository only the number counts."""
    here = here.lower()
    n, pre = ref.rsplit("#", 1)[1], ref.rsplit("#", 1)[0]
    if not here:
        return n
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", pre):
        return n if pre.lower() == here else "x"
    m = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*", pre)
    if m:
        # "repo#N" or "repo #N": a repository only when the fabric registers
        # the word ("PR#53" is this repository's #53). An unreadable
        # registry names none, so the number is compared — a miscount at
        # worst, never a refusal.
        word = m.group(1).lower()
        return "x" if word != here.rsplit("/", 1)[-1] and word in known_repos() else n
    return n


def kind(value: str) -> str:
    """A `Kind:` value as the hook reads it: the LAST of several (one per
    line, or as git joins them), case-insensitive, surrounding space
    ignored. Anything but work or review-fix is no declaration: ""."""
    values = [v.strip().lower() for v in re.split(r"[\n\x1f]", value) if v.strip()]
    return values[-1] if values and values[-1] in ("work", "review-fix") else ""


TRAILER_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*:[ \t]*(.*)$")


def kind_of(body: str) -> str:
    """The declared kind in a commit message, read where git reads it: the
    trailer block, its final paragraph. A `Kind:` line in the prose above
    declares nothing, as the hook's own test says, and pr_gate (which asks
    git for %(trailers)) agrees — reading it anywhere made one commit work
    here and a fix there (#120 re-review, N1).

    The block is the last paragraph when EVERY line in it is `Key: value`
    or a continuation (leading whitespace). Git also accepts a block that is
    mostly trailers with some prose; such a block reads here as no
    declaration, so the commit falls back to the rules before Kind:, never
    to a kind git would not report. A subprocess per commit (git
    interpret-trailers) was the exact alternative, and results.py
    classifies whole histories."""
    return kind("\n".join(trailer_values(body, "Kind")))


def answers_of(body: str) -> str:
    """The `Answers:` values of a commit message, as pr_gate asks git for
    them (%(trailers:key=Answers,valueonly,unfold,separator=%x20)): from
    the trailer block only, unfolded, joined by a space. A line in the
    prose above answers nothing there, so it answers nothing here."""
    return " ".join(trailer_values(body, "Answers"))


def trailer_values(body: str, key: str) -> list[str]:
    """Each value of trailer <key> (any case) in the block kind_of
    describes, a continuation line unfolded onto it with one space."""
    paragraphs = [p for p in re.split(r"\n[ \t]*\n", body.strip("\n")) if p.strip()]
    if not paragraphs:
        return []
    lines = paragraphs[-1].split("\n")
    if not all(TRAILER_LINE.match(line) or (line[:1] in (" ", "\t") and line.strip()) for line in lines):
        return []
    values: list[str] = []
    current = None
    for line in lines:
        if line[:1] in (" ", "\t"):
            if current is not None:
                values[current] = f"{values[current]} {line.strip()}".strip()
            continue
        m = re.match(rf"^{re.escape(key)}:[ \t]*(.*)$", line, re.I)
        current = len(values) if m else None
        if m:
            values.append(m.group(1).strip())
    return values


class Folds:
    """Whether PR <n> was folded into this range: closed, not merged, and
    its head inside <base>..<head> — an ancestor of <head> and, with a
    <base>, not of it. A PR folded into an EARLIER PR that has since
    merged has its head inside the base, and a later follow-up answering
    it is work here (ADR-019 rule 3, "its head inside this range").
    Asked once per PR number — a range names
    the same PR in every fix of its review, and each ask is a gh call. An
    unreadable PR or ancestry is "no" (the follow-up reading), said on
    stderr once."""

    def __init__(self, repo: str, head: str, cwd: str = ".", timeout: float = 30, base: str = "",
                 ancestor: Callable[[str, str], bool] | None = None):
        self.repo, self.head, self.base, self.cwd, self.timeout = repo, head, base, cwd, timeout
        # Without a clone of <repo> to ask (results.py reads every registered
        # repository through GitHub), ancestry is asked of `ancestor`.
        self.ancestor = ancestor
        self._seen: dict[str, bool] = {}
        self._is_full: bool | None = None

    def __call__(self, n: str) -> bool:
        if n not in self._seen:
            self._seen[n] = self._look(n)
        return self._seen[n]

    def _full(self) -> bool:
        """Whether this clone holds the whole history, asked once; a clone
        that cannot say is not taken to be full."""
        if self._is_full is None:
            try:
                self._is_full = git.out(self.cwd, "rev-parse", "--is-shallow-repository",
                                        timeout=self.timeout) == "false"
            except git.GitError:
                self._is_full = False
        return self._is_full

    def _unread(self, n: str, why: str) -> bool:
        # The repository is named: results.py reads several in one run.
        where = f"{self.repo}#{n}" if self.repo else f"#{n}"
        print(f"commit-class: {where} could not be read ({why}); its review's fixes count as work here", file=sys.stderr)
        return False

    def _look(self, n: str) -> bool:
        try:
            pr = gh.pr_view(int(n), ["state", "mergedAt", "headRefOid"], repo=self.repo or None, timeout=self.timeout)
        except gh.GhError as e:
            return self._unread(n, str(e))
        except ValueError:
            return self._unread(n, "gh's answer is not JSON")
        if not isinstance(pr, dict):
            return self._unread(n, "gh's answer is not an object")
        if pr.get("state") != "CLOSED" or pr.get("mergedAt"):
            return False
        oid = pr.get("headRefOid")
        if not isinstance(oid, str) or not re.fullmatch(r"[0-9a-f]{7,64}", oid):
            return self._unread(n, "no head sha")
        if self.ancestor is not None:
            # The same range rule as the clone's below: inside base..head.
            # GitHub's history is whole, so its no needs no shallow check.
            try:
                if not self.ancestor(oid, self.head):
                    return False
                return not (self.base and self.ancestor(oid, self.base))
            except gh.GhError as e:
                return self._unread(n, str(e))
        try:
            # A YES from merge-base --is-ancestor is a path git walked, true
            # in any clone. A NO is only as good as the history behind it:
            # in a shallow clone the walk stops at the boundary and answers
            # no for a commit that lies beyond it. So a no — for the head
            # or the base — is trusted only from a full clone; a shallow
            # one cannot place the PR, which is read as unread (work, named).
            if not git.ok(self.cwd, "merge-base", "--is-ancestor", oid, self.head, timeout=self.timeout):
                return False if self._full() else self._unread(n, "a shallow clone cannot rule out its head")
            if not self.base:
                return True
            if git.ok(self.cwd, "merge-base", "--is-ancestor", oid, self.base, timeout=self.timeout):
                return False   # folded into an earlier PR, already in the base
            return True if self._full() else self._unread(n, "a shallow clone cannot rule its head out of the base")
        except git.GitError as e:
            # A head this clone does not have is no ancestor of one it has,
            # when the clone holds the whole history — a closed PR that was
            # never folded is the usual case, and says nothing. A shallow
            # clone, or a counted head it lacks, cannot answer.
            try:
                if git.ok(self.cwd, "rev-parse", "--verify", "-q", f"{self.head}^{{commit}}", timeout=self.timeout) \
                        and git.out(self.cwd, "rev-parse", "--is-shallow-repository", timeout=self.timeout) == "false" \
                        and not git.ok(self.cwd, "rev-parse", "--verify", "-q", f"{oid}^{{commit}}", timeout=self.timeout):
                    return False
            except git.GitError:
                pass
            return self._unread(n, e.reason)


def on_github(repo: str, timeout: float = 30) -> Callable[[str, str], bool]:
    """Folds' ancestry asked of GitHub's compare: whether <oid> is an
    ancestor of <head> in <repo>. Measured 2026-10-09: "ahead" or
    "identical" is yes, "behind" or "diverged" no; a sha GitHub lacks is
    HTTP 404, and that, or any other answer, is a GhError — unread, never
    "no"."""
    def ancestor(oid: str, head: str) -> bool:
        doc = gh.api(f"repos/{repo}/compare/{oid}...{head}?per_page=1", timeout=timeout)
        status = doc.get("status") if isinstance(doc, dict) else None
        if status in ("ahead", "identical"):
            return True
        if status in ("behind", "diverged"):
            return False
        raise gh.GhError("gh api compare", f"no ancestry in the answer (status {status!r})")
    return ancestor


def classify(parents: str, subject: str, answers: str = "", pr: str = "", repo: str = "", kind_value: str = "",
             folded: Callable[[str], bool] | None = None) -> str:
    if " " in parents.strip():
        return "merge"
    declared = kind(kind_value)
    if declared == "work":
        return "work"
    # With the PR being counted: a commit whose subject or Answers: names
    # pull requests, none of them this one, answers ANOTHER PR's review — a
    # follow-up's own work, which the band counts. Read as a fix it moved a
    # managed project's PR from 7 work to 3, and a coordinator follow-up of
    # agent-fabric #53 the same way. Only a review-answer shape names the
    # PR answered — "review of #53", "#947 F2", or a #N in the Answers:
    # trailer; a bare #N in a subject is an issue or a PR named for
    # context, and says nothing (review of #55). A reference names another
    # repository only in a form that names one: owner/repo#N, or repo#N /
    # "repo #N" where repo is a project the fabric registers — never
    # "PR #918", "thread #53" or "the copy #53".
    if pr:
        found = []
        for m in re.finditer(rf"(?:re-)?reviews?\s+(?:of|on|for)\s+{FORM}(?:(?:\s*,\s*|\s+and\s+){FORM})*", subject, re.I):
            tail = re.sub(r"^(?:re-)?reviews?\s+(?:of|on|for)\s+", "", m.group(0), flags=re.I)
            found += re.split(r"\s*,\s*|\s+and\s+", tail, flags=re.I)
        found += [re.sub(rf"\s+{LABEL}$", "", m.group(0)) for m in re.finditer(rf"{FORM}\s+{LABEL}", subject)]
        found += [m.group(0) for m in re.finditer(FORM, answers)]
        refs = {_ref(r, repo) for r in found if r}
        if refs and str(pr) not in refs:
            # Every PR named folded into this range: its review's fixes are
            # this PR's fixes. Another repository's ("x") is never a fold.
            if folded is not None and "x" not in refs and all(folded(n) for n in sorted(refs)):
                return "fix"
            return "work"
    if declared == "review-fix":
        return "fix"
    if answers.strip():
        return "fix"
    # A subject that OPENS with the review word AS THE SCOPE — "review: …",
    # "re-review: …" — is an answer to one with nothing else to say so. The
    # word followed by another word before the colon is a component whose
    # name contains it — "review class: …", "review brief: …" — and falls
    # through to the general rule, which still needs an answer word.
    if re.match(r"(?:re-)?review:", subject, re.I):
        return "fix"
    # The review word inside a hyphenated tool name — post-review,
    # pr-review-status — names the tool, not a review: "post-review,
    # pr-reply: the launched role … (#68 carried)" read as a fix on #70.
    # "re-review" is the one hyphenated form that is a review; so is any
    # hyphenated one a finding label follows — "code-review F3: …" names
    # the review class's finding, and read as work it moved the band
    # (review of #71).
    # The label stays case-sensitive there, as everywhere: "post-review v2"
    # is a version, not a finding (re-review of #71).
    #
    # "findings" and "nits" are one side or the other, never both: with a
    # review word they are the answer ("review nits", "the re-review
    # findings on 8c4ae884"), and with an answer word they are the review
    # ("address the findings"); alone they are work — "Findings for
    # question 1: a seed on the fleet's host" is a spike reporting what it
    # found, and read as its own answer it moved a spike PR's count.
    review = (re.search(r"(?:^|[^A-Za-z])(?:re-review|(?<![A-Za-z]-)review'?s?)(?:[^A-Za-z]|$)", subject, re.I)
              or re.search(rf"[A-Za-z]-(?i:reviews?'?s?)\s+{LABEL}(?:[^A-Za-z0-9]|$)", subject))
    finding = re.search(r"(?:^|[^A-Za-z])(?:findings?|nits?)(?:[^A-Za-z0-9]|$)", subject, re.I)
    answer = (re.search(r"(?:^|[^A-Za-z])(?:fix(?:es|ed)?|address(?:es|ed|ing)?|answer(?:s|ed)?|round|re-review)(?:[^A-Za-z0-9]|$)|#[0-9]+",
                        subject, re.I)
              or re.search(rf"(?:^|[^A-Za-z0-9]){LABEL}(?:-[0-9]+)?(?:[^A-Za-z0-9]|$)", subject))
    if (review and (answer or finding)) or (finding and answer):
        return "fix"
    # No review word: a finding label of the narrow F/G/N/P shape WITH a #PR
    # is the supplier's "(#861 F6)"; the wide shape stays out here so
    # "ADR-021 R16 … #861" (a rule number) is not read as an answer.
    if re.search(r"(?:^|[^A-Za-z])[FGNP][0-9]+(?:[^A-Za-z0-9]|$)", subject) and re.search(r"#[0-9]+", subject):
        return "fix"
    return "work"


def revert_targets(body: str) -> list[str]:
    """A REVERT AND WHAT IT REVERTS NET TO ZERO WORK when both are in the
    range (a PR carried a revert of two of its own commits, and the gate
    said "9 work — arm" where the honest count was 7). The fact is git's
    own line, "This reverts commit <sha>."; a "Revert …" subject without it
    is prose and stays whatever its words say. The caller has the range."""
    return [m.group(1) for m in re.finditer(r"This reverts commit ([0-9a-f]{7,40})", body)]


def main(argv: list[str]) -> int:
    if argv[:1] == ["class"] and 3 <= len(argv) <= 9:
        args = argv[1:] + [""] * (9 - len(argv))
        parents, subject, answers, pr, repo, kind_value, head, base = args[:8]
        folded = Folds(repo, head, base=base) if pr and head else None
        print(classify(parents, subject, answers, pr, repo, kind_value, folded))
        return 0
    if argv == ["revert-targets"]:
        for sha in revert_targets(sys.stdin.read()):
            print(sha)
        return 0
    print("usage: commit_class.py class <parents> <subject> [<answers>] [<pr>] [<owner/repo>] [<kind>] [<head>] [<base>]"
          " | revert-targets", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
