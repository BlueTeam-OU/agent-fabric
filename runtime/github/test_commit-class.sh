#!/usr/bin/env bash
# runtime/github/test_commit-class.sh (lifted from the first managed project's tools/gh/ on 2026-09-19 — the commit names it; general to every managed project, whose own tools/gh/ copy is a forwarder through projects/<id>/integration/gh/) — the shared work/fix/merge classifier,
# on the subjects the count rule was calibrated against.
set -u
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
# shellcheck source=commit-class.sh
. "$SCRIPT_DIR/commit-class.sh"
failures=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; failures=$((failures + 1)); }
expect() {  # expect <class> <parents> <subject> [<answers trailer value>]
    local got; got="$(commit_class "$2" "$3" "${4:-}")"
    if [[ "$got" == "$1" ]]; then pass "$1: $3"; else fail "expected $1, got $got: $3"; fi
}
echo "commit-class: merges by parent count, whatever the subject"
expect merge "aaa bbb" "Merge origin/main"
expect merge "aaa bbb" "fix: not a merge subject but two parents"
expect work  "aaa"     "Merge-shaped subject with one parent is work"
echo "commit-class: a review fix names a review AND answers one"
expect fix "aaa" "review F4: the guard reads the count from the file"
expect fix "aaa" "pr-gate: address the blind review of #878"
expect fix "aaa" "review fixes: the three nits on the README"
expect fix "aaa" "tests: the re-review findings on 8c4ae884"
expect fix "aaa" "docs(advertiser): the venue edit rows name 3.1.0 (#861 F6)"
expect work "aaa" "docs(advertiser): the venue edit rows name 3.1.0 (F6)"
echo "commit-class: the Answers: trailer wins over any subject (seq 2821: three fixes with no review word on #892)"
expect fix  "aaa" "db: 0055's guard was too broad and stopped the file re-applying" "F3"
expect fix  "aaa" "docs(adr): ADR-071 §2.4 — a backfilled row with no known severance time keeps its updated_at" "PE-6, PR-1"
expect fix  "aaa" "feat: anything at all" "re-review F1 (the rationale)"
echo "commit-class: a subject that OPENS with the review word is an answer with no label, no fix word, no #PR (#894 review F3)"
expect fix "aaa" "review: the classifier itself"
expect fix "aaa" "re-review: wording only"
echo "commit-class: the review word as a COMPONENT's name is not an opener (agent-fabric #25: two work commits read as fixes)"
expect work "aaa" "review class: described as the review everywhere, not a stand-in"
expect work "aaa" "review brief: the lens vocabulary lists every lens"
expect fix  "aaa" "review tooling: the review round's fixes — configuration refused loudly"
# Not a label: the file says so for v2, and the opener must not admit it
# case-insensitively where the label rule is case-sensitive on purpose.
expect work "aaa" "review v2: the brief"
expect work "aaa" "review pe-6 is not a label"
# ("re-review — wording only" is NOT an opener-only case: re-review sits in the
# answer-word list too, so the fallback rule reads it as a fix as well.)
expect work "aaa" "reviewing the roster is the admin's act"
expect work "aaa" "db: 0055's guard was too broad and stopped the file re-applying" ""
expect work "aaa" "db: 0055's guard was too broad and stopped the file re-applying" "   "
expect merge "aaa bbb" "Merge origin/main" "F3"
echo "commit-class: labels of every shape the team writes (seq 2736: PE-6 and PR-1 read as work on #883)"
expect fix "aaa" "review PE-6: the pre-registered seed has one home"
expect fix "aaa" "review PR-1: the SQL belt pins all five statuses, rejected included"
expect fix "aaa" "review P3-1/P3-3/PE-5: the pre-registered row is the applicant's own"
expect fix "aaa" "re-review G2: the pattern alongside minLength"
expect fix "aaa" "docs(advertiser): no sentence left saying the address has no clear (#861 G1/G2)"
expect fix "aaa" "the review's PE-2 on the seed helper"
expect work "aaa" "docs(adr): ADR-021 §2.15 R16 — attribution resolves, never mints (#861)"
expect work "aaa" "test doc: SeedPreRegisteredApplicant's summary sits on the helper again"
expect work "aaa" "driver review: rejection ends the applicant's own lifecycle (ADR-071 §2.4)"
echo "commit-class: a bug fix, a review word alone, a fix word alone, a label alone is work"
expect work "aaa" "fix(scope): the nap is clamped to what is left"
expect work "aaa" "admin driver review: approving a driver reads the roster"
expect work "aaa" "the review decision's reason is persisted"
expect work "aaa" "wait-merged: only PRIVATE repositories' minutes count"
echo "commit-class: revert_targets reads git's own line, nothing else"
got="$(printf 'Revert \"feat: x\"\n\nThis reverts commit 0123456789abcdef0123456789abcdef01234567.\nAlso: This reverts commit abcdef1.\n' | revert_targets | tr '\n' ' ')"
[[ "$got" == "0123456789abcdef0123456789abcdef01234567 abcdef1 " ]] && pass "two targets, in order" || fail "revert_targets: $got"
got="$(printf 'Revert the thing by hand\n\nno trailer here\n' | revert_targets)"
[[ -z "$got" ]] && pass "a prose revert names no target" || fail "prose read as a target: $got"
expect work "aaa" "Revert the thing by hand"
expect work "aaa" 'Revert "feat: the used-by guard"'

echo "commit-class: a commit answering ANOTHER pull request's review is work on this one"
expect_pr() {  # expect_pr <class> <pr> <subject> [<answers>]
    local got; got="$(commit_class "aaa" "$3" "${4:-}" "$2")"
    if [[ "$got" == "$1" ]]; then pass "$1 on #$2: $3${4:+ [Answers: $4]}"; else fail "expected $1 on #$2, got $got: $3${4:+ [Answers: $4]}"; fi
}
expect_pr work 54 "review of #53 (deferred P3s): the date rules hold at their edges"
expect_pr work 948 "db: the guard re-applies" "#947 F2"
expect_pr fix  54 "review of #54 (P2 thread): the pipe guard exempts only a real pipefail"
expect_pr fix  861 "supplier: the copy for the new keys (#861 F6)"
expect_pr fix  54 "re-review F1: the chain match"
# A bare #N (an issue, an earlier PR named for context) is no foreign
# review: only a review-answer shape is (review of #53, #947 F2).
expect_pr fix  130 "review fixes: the race first reported in issue #120"
expect_pr fix  54 "re-review F1: the guard #53 added" "F1"
expect_pr work 54 "re-review of #53: the classifier" ""
# PR numbers are per repository: another repository's #53 is not this one.
expect_repo() {  # expect_repo <class> <pr> <owner/repo> <subject> [<answers>]
    local got; got="$(commit_class "aaa" "$4" "${5:-}" "$2" "$3")"
    if [[ "$got" == "$1" ]]; then pass "$1 on $3#$2: $4${5:+ [Answers: $5]}"; else fail "expected $1 on $3#$2, got $got: $4${5:+ [Answers: $5]}"; fi
}
expect_repo work 53 gzapi-org/agent-fabric "review of gzapp #53: the carried fix"
expect_repo work 53 gzapi-org/agent-fabric "db: the guard" "gzapi-org/gzapp#53 F2"
expect_repo fix  53 gzapi-org/agent-fabric "review of agent-fabric #53: the fix"
expect_repo fix  53 gzapi-org/agent-fabric "review of #53: the fix"
expect_repo fix  861 gzapi-org/gzapp "supplier: the copy (#861 F6)"
expect_pr   work 54 "supplier: the carried copy (#53 F3)"
# Every PR a list of reviews names, not only the first.
expect_pr   fix  54 "reviews on #53 and #54: the date rules"
expect_pr   fix  54 "review of #53, #54: the date rules"
expect_pr   work 55 "reviews on #53 and #54: the date rules"
expect_pr   fix  53 "Reviews on #53 AND #54: the date rules"
# A severity after the number is a review answer to that PR, like a label.
expect_pr   fix  53 "the guard (#53 P2)"
expect_pr   work 54 "the guard (#53 P2)"
# Only a form that names a repository does; "PR #N", "thread #N" and
# "the copy #N" are this repository's numbers (re-review of #55, F1-F2).
expect_repo fix  918 gzapi-org/gzapp "review F1-F4 + PE1: the guards" "PR #918 review F1-F4 and PE1"
expect_repo fix  53 gzapi-org/agent-fabric "review of PR #53: the fix"
expect_repo fix  53 gzapi-org/agent-fabric "supplier: the copy #53 F6"
expect_repo fix  53 gzapi-org/agent-fabric "review F1: the guard" "thread #53"
expect_repo work 53 gzapi-org/agent-fabric "review of other/agent-fabric#53: the fix"
expect_repo fix  53 gzapi-org/agent-fabric "review of gzapi-org/agent-fabric#53: the fix"
# The glued form names a repository only when the word is a registered one,
# like the spaced form: "PR#53" is this repository's number.
expect_repo work 53 gzapi-org/agent-fabric "review of gzapp#53: the fix"
expect_repo fix  53 gzapi-org/agent-fabric "review of agent-fabric#53: the fix"
expect_repo fix  53 gzapi-org/agent-fabric "review F1: the guard" "PR#53 F1"
expect_repo fix  53 gzapi-org/agent-fabric "review F1: the guard" "PR-#53 F1"
expect fix "aaa" "review of #53 (deferred P3s): no PR given, the old reading stands"

echo
if [[ $failures -eq 0 ]]; then echo "test_commit-class: OK — all assertions passed."; else echo "test_commit-class: FAILED — $failures assertion(s)." >&2; exit 1; fi
