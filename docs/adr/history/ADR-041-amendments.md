# ADR-041 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-05 — `GZCOORD_JOURNAL=off` is a recorded break-glass

Rules 3 and 4 make the journal the precondition of every crossing: kept
before it is posted, kept before it is acknowledged. The send and inbox
tools have honoured `GZCOORD_JOURNAL=off` since the journal landed, so
that an operator whose journal cannot be opened can still talk; the
tests pin it. An external review (2026-10-05) found an undocumented
generic variable weakening what the record calls an invariant, with no
trace of what crossed. The variable stays, as a break-glass the record
names (rule 10): each bypassed send and each addressed inbound record
appends an audit line before it crosses, and a line that cannot be
written refuses the crossing. python-dev-01's supply,
`tools/fabric/gzcoord/bypass.py`, does it, with
`tests/test_gzcoord_bypass.py`.

### Amendment 2026-10-06 — A bypassed send records its outcome

The review of #97 found that a bypassed send's record said only that a
crossing was attempted: a reader could not tell a message the relay took
from one it refused. The send now writes its line as "pending" before the
post and a second line after it: "accepted" with the carrier sequence,
"failed" only when the post provably never reached the relay (a 4xx, a
connection refused, a token refused before it left), and "unknown"
otherwise — a timeout or a 5xx may come after the relay stored it. The
journal's own row follows the same rule. Delivered by python-dev-01 on
its contributor branch, reviewed there.
