#!/usr/bin/env python3
"""The shared work/fix/merge classifier (tools/fabric/github/commit_class.py,
reached by callers through the sourced runtime/github/commit-class.sh), on
the subjects the count rule was calibrated against. Ported from
runtime/github/test_commit-class.sh (ADR-040 Wave 6), case for case: as there,
every case of the table goes through the sourced shim with all five
arguments, so a shim or CLI that dropped one fails the cases that turn
on it. Plain script: prints ok/FAIL, exit 1 on
any failure."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.abspath(os.environ.get("COMMIT_CLASS") or os.path.join(ROOT, "runtime", "github", "commit-class.sh"))
if not os.path.isfile(SHIM):
    sys.exit(f"test: script under test not found at {SHIM}")

AF = "gzapi-org/agent-fabric"
# (expected, parents, subject, answers, pr, repo), grouped as the bash
# suite grouped them; each group's heading carries the incident it pins.
CASES: list[tuple[str, list[tuple[str, str, str, str, str, str]]]] = [
    ("merges by parent count, whatever the subject", [
        ("merge", "aaa bbb", "Merge origin/main", "", "", ""),
        ("merge", "aaa bbb", "fix: not a merge subject but two parents", "", "", ""),
        ("work", "aaa", "Merge-shaped subject with one parent is work", "", "", ""),
    ]),
    ("a review fix names a review AND answers one", [
        ("fix", "aaa", "review F4: the guard reads the count from the file", "", "", ""),
        ("fix", "aaa", "pr-gate: address the blind review of #878", "", "", ""),
        ("fix", "aaa", "review fixes: the three nits on the README", "", "", ""),
        ("fix", "aaa", "tests: the re-review findings on 8c4ae884", "", "", ""),
        ("fix", "aaa", "docs(advertiser): the venue edit rows name 3.1.0 (#861 F6)", "", "", ""),
        ("work", "aaa", "docs(advertiser): the venue edit rows name 3.1.0 (F6)", "", "", ""),
    ]),
    ("the Answers: trailer wins over any subject (seq 2821: three fixes with no review word on #892)", [
        ("fix", "aaa", "db: 0055's guard was too broad and stopped the file re-applying", "F3", "", ""),
        ("fix", "aaa", "docs(adr): ADR-071 §2.4 — a backfilled row with no known severance time keeps its updated_at",
         "PE-6, PR-1", "", ""),
        ("fix", "aaa", "feat: anything at all", "re-review F1 (the rationale)", "", ""),
    ]),
    ("a subject that OPENS with the review word is an answer with no label, no fix word, no #PR (#894 review F3)", [
        ("fix", "aaa", "review: the classifier itself", "", "", ""),
        ("fix", "aaa", "re-review: wording only", "", "", ""),
    ]),
    ("the review word as a COMPONENT's name is not an opener (agent-fabric #25: two work commits read as fixes)", [
        ("work", "aaa", "review class: described as the review everywhere, not a stand-in", "", "", ""),
        ("work", "aaa", "review brief: the lens vocabulary lists every lens", "", "", ""),
        ("fix", "aaa", "review tooling: the review round's fixes — configuration refused loudly", "", "", ""),
        # Not a label: the file says so for v2, and the opener must not admit
        # it case-insensitively where the label rule is case-sensitive on
        # purpose.
        ("work", "aaa", "review v2: the brief", "", "", ""),
        ("work", "aaa", "review pe-6 is not a label", "", "", ""),
        # ("re-review — wording only" is NOT an opener-only case: re-review
        # sits in the answer-word list too, so the fallback rule reads it as
        # a fix as well.)
        ("work", "aaa", "reviewing the roster is the admin's act", "", "", ""),
        ("work", "aaa", "db: 0055's guard was too broad and stopped the file re-applying", "", "", ""),
        ("work", "aaa", "db: 0055's guard was too broad and stopped the file re-applying", "   ", "", ""),
        ("merge", "aaa bbb", "Merge origin/main", "F3", "", ""),
    ]),
    ("the review word inside a hyphenated tool name names the tool (agent-fabric #70)", [
        ("work", "aaa", "post-review, pr-reply: the launched role; a rename into locale/ (#68 carried)", "", "", ""),
        ("work", "aaa", "pr-review-status: say the head it read (#881)", "", "", ""),
        ("fix", "aaa", "post-review: answer the re-review of #70", "", "", ""),
        ("fix", "aaa", "code-review F3: the guard anchors", "", "", ""),
        ("fix", "aaa", "peer-review P1: refuse on null", "", "", ""),
        ("fix", "aaa", "self-review F2: tidy", "", "", ""),
        ("work", "aaa", "post-review v2: the marker gains a field (#881)", "", "", ""),
        ("work", "aaa", "post-review x86 hosts: fix the path", "", "", ""),
    ]),
    ("labels of every shape the team writes (seq 2736: PE-6 and PR-1 read as work on #883)", [
        ("fix", "aaa", "review PE-6: the pre-registered seed has one home", "", "", ""),
        ("fix", "aaa", "review PR-1: the SQL belt pins all five statuses, rejected included", "", "", ""),
        ("fix", "aaa", "review P3-1/P3-3/PE-5: the pre-registered row is the applicant's own", "", "", ""),
        ("fix", "aaa", "re-review G2: the pattern alongside minLength", "", "", ""),
        ("fix", "aaa", "docs(advertiser): no sentence left saying the address has no clear (#861 G1/G2)", "", "", ""),
        ("fix", "aaa", "the review's PE-2 on the seed helper", "", "", ""),
        ("work", "aaa", "docs(adr): ADR-021 §2.15 R16 — attribution resolves, never mints (#861)", "", "", ""),
        ("work", "aaa", "test doc: SeedPreRegisteredApplicant's summary sits on the helper again", "", "", ""),
        ("work", "aaa", "driver review: rejection ends the applicant's own lifecycle (ADR-071 §2.4)", "", "", ""),
    ]),
    ("a bug fix, a review word alone, a fix word alone, a label alone is work", [
        ("work", "aaa", "fix(scope): the nap is clamped to what is left", "", "", ""),
        ("work", "aaa", "admin driver review: approving a driver reads the roster", "", "", ""),
        ("work", "aaa", "the review decision's reason is persisted", "", "", ""),
        ("work", "aaa", "wait-merged: only PRIVATE repositories' minutes count", "", "", ""),
    ]),
    ("a revert's subject is work", [
        ("work", "aaa", "Revert the thing by hand", "", "", ""),
        ("work", "aaa", 'Revert "feat: the used-by guard"', "", "", ""),
    ]),
    ("a commit answering ANOTHER pull request's review is work on this one", [
        ("work", "aaa", "review of #53 (deferred P3s): the date rules hold at their edges", "", "54", ""),
        ("work", "aaa", "db: the guard re-applies", "#947 F2", "948", ""),
        ("fix", "aaa", "review of #54 (P2 thread): the pipe guard exempts only a real pipefail", "", "54", ""),
        ("fix", "aaa", "supplier: the copy for the new keys (#861 F6)", "", "861", ""),
        ("fix", "aaa", "re-review F1: the chain match", "", "54", ""),
        # A bare #N (an issue, an earlier PR named for context) is no foreign
        # review: only a review-answer shape is (review of #53, #947 F2).
        ("fix", "aaa", "review fixes: the race first reported in issue #120", "", "130", ""),
        ("fix", "aaa", "re-review F1: the guard #53 added", "F1", "54", ""),
        ("work", "aaa", "re-review of #53: the classifier", "", "54", ""),
        # PR numbers are per repository: another repository's #53 is not
        # this one.
        ("work", "aaa", "review of gzapp #53: the carried fix", "", "53", AF),
        ("work", "aaa", "db: the guard", "gzapi-org/gzapp#53 F2", "53", AF),
        ("fix", "aaa", "review of agent-fabric #53: the fix", "", "53", AF),
        ("fix", "aaa", "review of #53: the fix", "", "53", AF),
        ("fix", "aaa", "supplier: the copy (#861 F6)", "", "861", "gzapi-org/gzapp"),
        ("work", "aaa", "supplier: the carried copy (#53 F3)", "", "54", ""),
        # Every PR a list of reviews names, not only the first.
        ("fix", "aaa", "reviews on #53 and #54: the date rules", "", "54", ""),
        ("fix", "aaa", "review of #53, #54: the date rules", "", "54", ""),
        ("work", "aaa", "reviews on #53 and #54: the date rules", "", "55", ""),
        ("fix", "aaa", "Reviews on #53 AND #54: the date rules", "", "53", ""),
        # A severity after the number is a review answer to that PR, like a
        # label.
        ("fix", "aaa", "the guard (#53 P2)", "", "53", ""),
        ("work", "aaa", "the guard (#53 P2)", "", "54", ""),
        # Only a form that names a repository does; "PR #N", "thread #N" and
        # "the copy #N" are this repository's numbers (re-review of #55,
        # F1-F2).
        ("fix", "aaa", "review F1-F4 + PE1: the guards", "PR #918 review F1-F4 and PE1", "918", "gzapi-org/gzapp"),
        ("fix", "aaa", "review of PR #53: the fix", "", "53", AF),
        ("fix", "aaa", "supplier: the copy #53 F6", "", "53", AF),
        ("fix", "aaa", "review F1: the guard", "thread #53", "53", AF),
        ("work", "aaa", "review of other/agent-fabric#53: the fix", "", "53", AF),
        ("fix", "aaa", "review of gzapi-org/agent-fabric#53: the fix", "", "53", AF),
        # The glued form names a repository only when the word is a
        # registered one, like the spaced form: "PR#53" is this
        # repository's number.
        ("work", "aaa", "review of gzapp#53: the fix", "", "53", AF),
        ("fix", "aaa", "review of agent-fabric#53: the fix", "", "53", AF),
        ("fix", "aaa", "review F1: the guard", "PR#53 F1", "53", AF),
        ("fix", "aaa", "review F1: the guard", "PR-#53 F1", "53", AF),
        ("fix", "aaa", "review of #53 (deferred P3s): no PR given, the old reading stands", "", "", ""),
    ]),
]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_"))}

    def sourced(script: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", "-c", f'. "$1"; {script}', "_", SHIM], input=stdin, env=env,
                              capture_output=True, text=True, timeout=300)

    # One bash for the whole table, as the bash suite sourced the shim once;
    # US-separated fields keep an empty or blank argument in its place, which
    # a whitespace IFS would collapse.
    table = [case for _, cases in CASES for case in cases]
    r = sourced("while IFS=$'\\x1f' read -r p s a n o; do "
                'commit_class "$p" "$s" "$a" "$n" "$o" </dev/null || echo "exit $?"; done',
                "".join("\x1f".join(case[1:]) + "\n" for case in table))
    got = r.stdout.splitlines()
    if r.returncode != 0 or len(got) != len(table):
        check(f"the table runs through the shim ({len(table)} classes)", False,
              f"exit {r.returncode}, {len(got)} lines\n{r.stderr}")
        got += [""] * (len(table) - len(got))
    classes = iter(got)
    for heading, cases in CASES:
        print(f"commit-class: {heading}")
        for want, _parents, subject, answers, pr, repo in cases:
            have = next(classes)
            on = f" on {repo}#{pr}" if repo else (f" on #{pr}" if pr else "")
            check(f"{want}{on}: {subject}{f' [Answers: {answers}]' if answers else ''}", have == want, f"got {have}")

    print("commit-class: revert_targets reads git's own line, nothing else")
    sha = "0123456789abcdef0123456789abcdef01234567"
    out = sourced("revert_targets",
                  f'Revert "feat: x"\n\nThis reverts commit {sha}.\nAlso: This reverts commit abcdef1.\n').stdout
    check("two targets, in order", out.split() == [sha, "abcdef1"], repr(out))
    out = sourced("revert_targets", "Revert the thing by hand\n\nno trailer here\n").stdout
    check("a prose revert names no target", out == "", repr(out))
    out = sourced("revert_targets", "Revert x\n\nThis reverts commit abcdef1.\nThis reverts commit 1234567.\n").stdout
    check("revert_targets reads the body on stdin, one sha a line", out == "abcdef1\n1234567\n", repr(out))

    print(f"\ntest_commit_class_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
