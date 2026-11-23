---
role: "devex-tooling"
class: domain
topic: "sidecar-travels-with-its-bytes"
description: metadata kept in a file beside the data it describes (a vintage, a version, a checksum) must move, be replaced, or be removed on EVERY path that writes those bytes; a stale sidecar stamps a lie silently
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 1bc068f2bf5fc7f6
---

## metadata kept in a file beside the data it describes (a vintage, a version, a checksum) must move, be replaced, or be removed on EVERY path that writes those bytes; a stale sidecar stamps a lie silently

A sidecar file that describes a data file is true only of the bytes it was written beside. Four
review rounds on one change (gzapp shared-data place export, 2026-09-17) each found the same class
by a different path: a tracked sidecar stamped onto a shared blob it did not describe; a pull that
replaced the bytes and kept the old sidecar (an `if` with no `else`); an adopt that deleted the only
copy of the sidecar after a publish that had failed, because the publish helper's failure branch
was a `warn` that returned 0; and a later pull removing a sidecar a warning had just said was
"KEPT". Every one was silent: the derived version changed, so no "already imported" guard fired.

**How to apply:** when adding metadata beside a file, list every path that creates, replaces,
copies, publishes, pulls or deletes the file, and make each one do the same thing to the sidecar:
carry it, or remove it and say so. Bytes with no sidecar mean "unknown", and the consumer refuses
loudly. It never falls back to a tracked or default value. A helper that only warns must return
non-zero on failure if a later step depends on it, so a delete is gated on the real status. Test
each path with a mutation that drops the sidecar handling. Related:
[[presence-check-needs-content-evidence]].

*References: presence-check-needs-content-evidence*

*Observed 2026-10-18 (devex-tooling)*
