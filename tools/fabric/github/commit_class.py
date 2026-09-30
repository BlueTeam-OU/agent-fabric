#!/usr/bin/env python3
"""tools/fabric/github/commit_class.py — ONE classifier for "is this commit a
review fix": merge, fix or work (ADR-019's count rule, ADR-040's first
Wave 1 port). runtime/github/commit-class.sh is its shim, sourced by
pr-gate.sh and the managed projects' forwarders; results.py imports it.

    commit_class.py class <parents> <subject> [<answers>] [<pr>] [<owner/repo>]
                                          prints merge | fix | work
    commit_class.py revert-targets        the shas a commit body (stdin) reverts

CONTRACT, frozen from the bash (ADR-040 §5 rule 3): the arguments above, in
that order, the optional ones may be empty; one word on stdout; exit 0.
<parents> is the space-separated parent list (git log %P); <answers> the
value of the commit's `Answers:` trailer (git log
%(trailers:key=Answers,valueonly)).

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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
FORM = r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#|[A-Za-z0-9_.-]+#|[A-Za-z0-9_.-]+\s+#|#)[0-9]+"
LABEL = r"[A-Z]{1,2}-?[0-9]+"


def known_repos(registry: str | None = None) -> set[str]:
    """The repository names the fabric registers: each project id and the
    name of each of its remotes, lower-cased. An unreadable registry names
    none."""
    try:
        reg = json.load(open(registry or os.path.join(ROOT, "projects", "registry.json"), encoding="utf-8"))
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


def classify(parents: str, subject: str, answers: str = "", pr: str = "", repo: str = "") -> str:
    if " " in parents.strip():
        return "merge"
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
            return "work"
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
    if (re.search(r"(?:^|[^A-Za-z])(?:re-review|(?<![A-Za-z]-)review'?s?|findings?|nits?)(?:[^A-Za-z]|$)", subject, re.I)
            or re.search(rf"[A-Za-z]-(?i:reviews?'?s?)\s+{LABEL}(?:[^A-Za-z0-9]|$)", subject)) and (
            re.search(r"(?:^|[^A-Za-z])(?:fix(?:es|ed)?|address(?:es|ed|ing)?|answer(?:s|ed)?|round|re-review|nits?|findings?)(?:[^A-Za-z0-9]|$)|#[0-9]+",
                      subject, re.I)
            or re.search(rf"(?:^|[^A-Za-z0-9]){LABEL}(?:-[0-9]+)?(?:[^A-Za-z0-9]|$)", subject)):
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
    if argv[:1] == ["class"] and 3 <= len(argv) <= 6:
        print(classify(*argv[1:]))
        return 0
    if argv == ["revert-targets"]:
        for sha in revert_targets(sys.stdin.read()):
            print(sha)
        return 0
    print("usage: commit_class.py class <parents> <subject> [<answers>] [<pr>] [<owner/repo>] | revert-targets", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
