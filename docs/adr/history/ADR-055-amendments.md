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

### Amendment 2026-11-12 — rule 7 and rule 8 point at the policy data, not today's seats and lists

What changed: rule 7 no longer ends with the fleet's seats ("OpenAI
today, against Anthropic's two seats and three review models"); it keeps the
principle that a provider with one seat and one model is less
fault-tolerant by construction, and the file says so. Rule 8 no longer
states which engines `policies/arming.json` lists today; it says the policy
names the engines whose review is required and those that are additional,
and keeps the principle that an additional engine is optional and never
blocks, with the absent-engine summary naming `<engine>`.

Why: ADR-045 §5 rule 4. Rules 1-6 and rule 8's principle are engine; the
fleet's seats and its policy's current lists are data
(docs/split/adr-classification.md, ADR-055 row).

### Amendment 2026-11-13 — Codex never blocks: probe first, every failure to launch or finish posts the marker

What changed: rule 8's marker was posted only over the allowance or at
capacity. Now `fabric-review --engine codex` first makes one cheap call
through the run's own gateway and credentials, bounded in time, and
starts codex only when it shows the gateway reachable and the allowance
not spent; every failure to launch or finish (the probe unreachable,
refused or timed out, over the allowance, at capacity, the binary
missing, codex timed out or crashed) posts the unavailable marker for
the head with its reason and exits "not run". What is the caller's to
fix (a setting, routing, a sign-in the run refuses, a head that moved)
stays a refusal and posts nothing.

Why: the owner, 2026-11-12, after #575's two 20-minute codex timeouts
posted nothing while the review class's clean review was already in,
and codex was unavailable at the API: codex starts only after a cheap
call shows it can run, and if it cannot launch or finish for any
reason it must not block. The 2026-10-14 rule already let an absent
engine through; a marker now says why, on the head, for every kind.
Built by python-dev-01 in #577 (job j232); the probe's shape against
the live backend is not yet read back. Audited the same day: none of
the fourteen `repos/*.json` in either settings repository names codex
in `reviews` or `boundary_reviews`; all take the fleet's
`additional_reviews`.
