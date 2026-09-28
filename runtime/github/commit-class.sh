#!/usr/bin/env bash
# runtime/github/commit-class.sh (lifted from the first managed project's tools/gh/ on 2026-09-19 — the commit names it; general to every managed project, whose own tools/gh/ copy is a forwarder through projects/<id>/integration/gh/) — sourced, not run.
#
# ONE classifier for "is this commit a review fix" — the count rule
# (agent-fabric ADR-019, the arming band: 8–16 WORK commits arm at the
# review gate, under 8 ask the owner or state a class, over 16 is
# advice for the next batch; review fixes never count) is applied by
# pr-gate.sh on open PRs and by whatever measures merged ones after
# the fact, and two copies of the regex would drift the band between
# them.
#
# A review FIX is a subject that names a REVIEW (review, re-review,
# finding(s), nit(s), as words) AND says it answers one (a finding label
# F3/N1/P2, fix/address/answer, a round, a #PR, or a nit or finding word
# again) — or carries a finding label AND a #PR with no review word at
# all, the supplier's shape "(#861 F6)". Either half alone misreads this repository: the review word
# alone made "admin driver review: approving …" and "the review
# decision's reason" fixes; a fix: opener alone made 804 of the last
# 3000 subjects fixes — this repository writes bug fixes as fix(scope):
# — and turned a "split" into an "arm" on #757 (2026-09-18 re-review,
# F1). Measured on those 3000: 95 read as fixes, e.g. "review F4: …",
# "…: address the blind review of …", "review fixes: …", "…the
# re-review findings on 8c4ae884".
#
#   commit_class <parents> <subject> [<answers>] [<pr>] [<owner/repo>]   → prints merge | fix | work
#
# <parents> is the space-separated parent list (git log %P): two or
# more parents is a merge, whatever the subject says. <answers> is the
# value of the commit's `Answers:` trailer (git log
# %(trailers:key=Answers,valueonly)), empty when absent.
#
# THE TRAILER, `Answers: <finding labels>`, is read FIRST: a commit that
# carries it is a review fix whatever its subject says. It exists
# because the third shape a regex cannot reach appeared on #892
# (backend-dev-02, 2026-09-19, seq 2821): a fix commit whose subject
# describes the fix and names no review at all — "db: 0055's guard was
# too broad and stopped the file re-applying" — three of them read as
# work, 18 > 16, and the ceiling refused a PR that held 15. The
# information is absent from the prose; only the author can put it
# back, and a trailer is where a git message keeps facts about itself.
#
#     Answers: F3
#     Answers: PE-6, PR-1
#     Answers: re-review F1 (the \b rationale)
#
# Any non-empty value counts. The regexes below stay for every commit
# written before the trailer existed and for the habit that will not
# take.

# A finding LABEL is one or two capitals, an optional dash, digits, an
# optional -digits: F4, P3, N12, G1, PE-6, PR-1, P3-1. The first shape
# was [FNP][0-9]+ and read "review PE-6:" and "review PR-1:" as WORK —
# four of them on #883 inflated the count from 8 to 13, the direction
# the floor exists to catch (backend-dev-02, 2026-09-18, seq 2736).
# Case-sensitive on purpose: "v2", "utf8", "sha1" are not labels; a
# three-letter run (ADR-071, OTP) is not either.
# The repository names the fabric registers (projects/registry.json): each
# project id and the name of each of its remotes, lower-cased.
_commit_class_known_repos() {
    local reg; reg="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/projects/registry.json"
    jq -r '(.projects // .) | to_entries[] | .key, (.value.remotes // [])[]' "$reg" 2>/dev/null \
        | sed -E 's#\.git$##; s#.*[/:]##' | tr '[:upper:]' '[:lower:]' | sort -u
}

# One reference → the PR number it names, or "x" when it names another
# repository than <owner/repo>. Without a repository only the number counts.
_commit_class_ref() {
    local ref="$1" here="${2,,}" n="${1##*#}" pre="${1%#*}" word
    [[ -n "$here" ]] || { echo "$n"; return; }
    if [[ "$pre" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
        [[ "${pre,,}" == "$here" ]] && echo "$n" || echo x
    elif [[ "$pre" =~ ^([A-Za-z0-9_.-]+)[[:space:]]*$ ]]; then
        # "repo#N" or "repo #N": a repository only when the fabric registers
        # the word ("PR#53" is this repository's #53). An unreadable
        # registry names none, so the number is compared — a miscount at
        # worst, never a refusal.
        word="${BASH_REMATCH[1],,}"
        if [[ "$word" != "${here##*/}" ]] && grep -qxF -- "$word" <<<"$(_commit_class_known_repos)"; then echo x; else echo "$n"; fi
    else
        echo "$n"
    fi
}

commit_class() {
    local parents="$1" subject="$2" answers="${3:-}" pr="${4:-}" repo="${5:-}"
    if [[ "$parents" == *" "* ]]; then echo merge; return 0; fi
    # With the PR being counted: a commit whose subject or Answers: names
    # pull requests, none of them this one, answers ANOTHER PR's review —
    # a follow-up's own work, which the band counts. Read as a fix it
    # moved a managed project's PR from 7 work to 3, and a coordinator
    # follow-up of agent-fabric #53 the same way. Without the number the old reading
    # stands (a project forwarder that passes three arguments).
    # Only a review-answer shape names the PR answered — "review of #53",
    # "#947 F2", or a #N in the Answers: trailer; a bare #N in a subject is
    # an issue or a PR named for context, and says nothing (review of #55).
    # PR numbers are per repository. A reference names another repository
    # only in a form that names one: owner/repo#N (compared with the owner),
    # or repo#N / "repo #N" where repo is a project the fabric registers —
    # never "PR #918", "thread #53" or "the copy #53" (review of #55). A
    # reference to another repository reads as "x", never as this PR.
    if [[ -n "$pr" ]]; then
        local ref refs="" form='([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#|[A-Za-z0-9_.-]+#|[A-Za-z0-9_.-]+[[:space:]]+#|#)[0-9]+'
        # "reviews on #53 and #54", "review of #53, #54": every PR in the
        # list, split as case-blindly as it is matched ("AND").
        while IFS= read -r ref; do
            [[ -n "$ref" ]] && refs+="$(_commit_class_ref "$ref" "$repo")"$'\n'
        done < <( { grep -oiE "(re-)?reviews?[[:space:]]+(of|on|for)[[:space:]]+$form(([[:space:]]*,[[:space:]]*|[[:space:]]+and[[:space:]]+)$form)*" <<<"$subject" \
                      | sed -E 's/^(re-)?reviews?[[:space:]]+(of|on|for)[[:space:]]+//I' \
                      | sed -E 's/([[:space:]]*,[[:space:]]*|[[:space:]]+and[[:space:]]+)/\n/gI'
                    grep -oE "${form}[[:space:]]+[A-Z]{1,2}-?[0-9]+" <<<"$subject" \
                      | sed -E 's/[[:space:]]+[A-Z]{1,2}-?[0-9]+$//'
                    grep -oE "$form" <<<"$answers"; } )
        refs="$(sed '/^$/d' <<<"$refs" | sort -u)"
        if [[ -n "$refs" ]] && ! grep -qx "$pr" <<<"$refs"; then echo work; return 0; fi
    fi
    if [[ -n "${answers//[[:space:]]/}" ]]; then echo fix; return 0; fi
    # A subject that OPENS with the review word AS THE SCOPE — "review:
    # …", "re-review: …" — is an answer to one with nothing else to say
    # so. The word followed by another word before the colon is a
    # component whose name contains it — "review class: …", "review
    # tooling: …", "review brief: …" — and says nothing about answering
    # a review; the wider opener read a work commit about the review
    # class on agent-fabric #25 as a fix. Such a subject falls through
    # to the general rule, which still needs an answer word: "review
    # PE-6: …" and "re-review F1: …" are fixes there, by their label,
    # and "review tooling: the round's fixes" by its fix word — while a
    # fix whose subject names neither carries the Answers: trailer.
    if grep -qiE "^(re-)?review:" <<<"$subject"; then echo fix; return 0; fi
    if grep -qiE "(^|[^A-Za-z])(re-review|review'?s?|findings?|nits?)([^A-Za-z]|$)" <<<"$subject" \
       && { grep -qiE '(^|[^A-Za-z])(fix(es|ed)?|address(es|ed|ing)?|answer(s|ed)?|round|re-review|nits?|findings?)([^A-Za-z0-9]|$)|#[0-9]+' <<<"$subject" \
            || grep -qE '(^|[^A-Za-z0-9])[A-Z]{1,2}-?[0-9]+(-[0-9]+)?([^A-Za-z0-9]|$)' <<<"$subject"; }; then
        echo fix; return 0
    fi
    # No review word: a finding label of the narrow F/G/N/P shape WITH a
    # #PR is the supplier's "(#861 F6)"; the wide shape stays out here so
    # "ADR-021 R16 … #861" (a rule number) is not read as an answer.
    if grep -qE '(^|[^A-Za-z])[FGNP][0-9]+([^A-Za-z0-9]|$)' <<<"$subject" && grep -qE '#[0-9]+' <<<"$subject"; then
        echo fix; return 0
    fi
    echo work
}

# A REVERT AND WHAT IT REVERTS NET TO ZERO WORK when both are in the range
# (devex-tooling and architect-cto, 2026-09-20: a PR carried a revert of
# two of its own commits; the classifier counted the revert as work and
# the reverted commits as work, and the gate said "9 work — arm" where
# the honest count was 7, under the band). The machine-readable fact is
# git's own line in the revert's body, "This reverts commit <sha>."; a
# "Revert …" subject without it is prose and stays whatever its words
# say. A revert whose partner is NOT in the range — reverting something
# already on main — keeps its class as before: it changes the tree. The
# caller has the range; this prints the shas a body names, one per line.
revert_targets() {
    grep -oE 'This reverts commit [0-9a-f]{7,40}' | awk '{print $4}'
}
