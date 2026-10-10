---
role: "python-dev"
class: domain
topic: "verify-status-from-stderr-is-forgeable"
description: "parsing [GNUPG:] lines from git verify-commit --raw stderr — git's own error quotes the signature header; gate on exit 0"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b9e187e8308e2f92
---

## parsing [GNUPG:] lines from git verify-commit --raw stderr — git's own error quotes the signature header; gate on exit 0

`git verify-commit --raw` puts gpg's status lines on stderr, and on failure
also git's own message: "fatal: bad/incompatible signature '<header>'"
quotes the commit's gpgsig header with its newlines. A pusher can put
"[GNUPG:] VALIDSIG <writer subkey> ... <writer primary>" (public
fingerprints) in that header and a line-prefix parser takes it as gpg's
verdict. Rule: a VALIDSIG counts only when verify-commit exited 0 (then
stderr is gpg's alone). Also: silence (no status) means both "unsigned" and
"gpg never ran" — tell them apart from the object (cat-file), and only the
store's own-format header (gpgsig sha1 / gpgsig-sha256 sha256) with PGP
SIGNATURE armour may count as "gpg never ran"; junk in armour makes gpg
say NODATA. Found on PR #112 (2026-10-07, b9fbe79d; pre-existing since
d691b9f1), reproduced by a test that failed before the fix.

*Observed 2026-10-07 (python-dev)*
