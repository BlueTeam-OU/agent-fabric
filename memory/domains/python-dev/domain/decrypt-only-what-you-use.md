---
role: "python-dev"
class: domain
topic: "decrypt-only-what-you-use"
description: "code that reads a store of secrets in bulk, or decodes a decrypted value — read only the names used; a decode error's message quotes the bytes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3432797f23bfeaec
---

## code that reads a store of secrets in bulk, or decodes a decrypted value — read only the names used; a decode error's message quotes the bytes

A UnicodeDecodeError's message quotes the offending byte and its position
("can't decode byte 0xff in position 3"): from a secret, that is a leak in
an error line. And decoding every entry of a store a user can write any bytes
into lets one entry fail every reader. j49 review (agent-fabric
3c9b4298): values(only=...) decrypts the names a caller uses; equality is
checked on bytes; a value that must be text and is not is an error naming
the entry; a UnicodeError reaching a report is said by its class. Related:
[[shell-text-secrets-and-git-answers]].

*References: shell-text-secrets-and-git-answers*

*Observed 2026-10-07 (python-dev)*
