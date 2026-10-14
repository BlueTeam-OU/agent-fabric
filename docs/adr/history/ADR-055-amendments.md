# ADR-055 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — Codex is an additional review: unavailable, the claude review alone arms

On 2026-10-13 the ChatGPT workspace that serves codex ran out of its Codex
allowance, and every arm in the fleet stopped on the both-engines rule. The
owner: "codex is 'more' not a blocking. If it is not available only claude
run", and declined paying for the API in its place ("I pay for a
subscription"). A stopgap in both settings repositories required claude
alone; this rule replaces it: the arm itself reads codex as additional, and
an unavailable codex leaves a marker on the head instead of a silent gap.

### Amendment 2026-10-14 — An absent additional review does not stop an arm

The review of #264 found the 2026-10-13 rule only half built: the marker is
posted for an unavailable model, but a codex run that failed, timed out, was
killed or never started left neither a review nor a marker, and the arm
refused, so codex blocked after all. The owner's rule stands as written on
2026-10-13 ("if it is not available only claude run"): an additional engine
with neither is absent, the arm proceeds on the required reviews and says so,
and the gate reads the same, so it never shows blocked what the arm arms. A
codex review that is present still counts, its open P1 or P2 with it.
