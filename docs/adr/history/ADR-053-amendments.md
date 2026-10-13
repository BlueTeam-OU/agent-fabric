# ADR-053 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — the sandbox proven before the run; Codex's own fetches off

§5 rule 2 gains the sandbox proof and rule 3 the features switched off.
Rule 2 said the sandbox was read-only and nothing checked it started;
the first two Codex reviews ran with no tool host and read nothing
(#229), so a run's preconditions are now proved, not assumed. Rule 3
said the gateway was Codex's only upstream, and a 30-second strace of
`codex exec` against a local gateway showed Codex fetching
`github.com/openai/plugins.git` on its own: 11 git executions and 7
non-loopback connects with the default features, none with the five
features off (docs/live-checks/2026-10-13-codex-engine-egress.md).
Built in `tools/fabric/review_codex.py` (`prove_sandbox`, the
`[features]` block of the engine's Codex home) by python-dev-03.

### Amendment 2026-10-13 — every login runs the Codex review on a synced access token; both engines by default

§5 rule 6's default moves from `["claude"]` to `["claude", "codex"]`, and
rule 8 says how every login gets the credential. The first Codex review
that read its range (#230's, after merge) found four defects the review
class had passed, all confirmed by the review class; one engine misses
what the other sees, so the fleet's default is both. Only the
coordinator's login was signed in to ChatGPT, so the credential path
comes first and the default follows it.

Three paths were weighed. Copying the whole sign-in puts a refresh token
in every home, and many holders of one rotating refresh token can
invalidate each other. Running every Codex review on the coordinator's
login makes it the fleet's bottleneck and single point of failure. One
shared gateway holding the token needs either one gateway-local key for
every login or a gateway change for a key per login, and stops every
review when it stops. The chosen path copies only the access token,
which expires by itself (240 hours) and cannot renew itself, and keeps
one gateway per review, as rule 3 already has.

The owner's word, in the coordinator's session on 2026-10-13: "Required
everywhere" for the default, "go with B" for the access-token path.

### Amendment 2026-10-13 — the record requires a review, policy names the engines; the fleet requires both

§5 rule 6 no longer names engines or a default: it requires a review by
every engine the arming policy names, and the policy is where the names
live. The earlier text named `["claude", "codex"]` as the default to be
set once two conditions held; both now hold (every login holds the
synced access token, rule 8; a Codex review ran from python-dev-01's
login on #232), and `policies/arming.json` now lists both engines in
`reviews` and `boundary_reviews`. The review class stays required on every pull request (ADR-020); the
one exception is ADR-054 rule 10's, for Codex-written work. No escape hatch for a
Codex capacity failure: a pull request waits for the engine. The owner's
word, in the coordinator's session: "add codex review for all agents,
change adr-053 so it don't specify the reviewer - only that review is
required".
