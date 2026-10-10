---
role: "devex-tooling"
class: domain
topic: "aot-snapshot-byte-find-needs-a-positive-control"
description: "A byte-find on a Flutter release snapshot (libapp.so) passes on an --obfuscate build because the names are gone; require a control string that only an unobfuscated snapshot carries."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - e4a33c4ce3a9eaca
---

## A byte-find on a Flutter release snapshot (libapp.so) passes on an --obfuscate build because the names are gone; require a control string that only an unobfuscated snapshot carries.

Measured 2026-09-16 on Flutter 3.47.3 (linux release bundle of a probe
app calling `MCPToolkitBinding` from `lib/`): the plain snapshot
carries `package:mcp_toolkit/` ×19 and the byte `mcp_toolkit` ×27;
with `--obfuscate --split-debug-info` no toolkit library URI survives
and the marker is left once, in a string literal. In a plain snapshot
non-entrypoint library URIs of the app's own files and plain class
names are dropped too (only the entrypoint's `package:<app>/main.dart`
and widget class names survive), so "the app's package name" is not
a usable control either.

**How to apply:** `tools/checks/check_flutter_apk_has_no_toolkit.sh`
(PR #796) requires `package:flutter/src/widgets/framework.dart` in
every Dart-code member — 1 in every plain snapshot and kernel, 0 in
every obfuscated one — and exits 2 (unmeasured) without it. Any other
byte-find on a built binary needs the same shape: a marker that must
be absent AND a control that must be present, or it is
[[a-passing-run-without-the-trigger-measures-nothing]].

*References: a-passing-run-without-the-trigger-measures-nothing*

*Observed 2026-09-16 (devex-tooling)*
