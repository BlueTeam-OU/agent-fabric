---
role: "fabric-coordinator"
class: solution
topic: "impeccable-no-network-on-detect"
description: "impeccable engine 0.1.18: --version, detect --list-rules, detect <dir> open no socket even without DO_NOT_TRACK"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e5e92385172290e7
---

## impeccable engine 0.1.18: --version, detect --list-rules, detect <dir> open no socket even without DO_NOT_TRACK

Measured 2026-10-30 on the pinned asset (engine-v0.1.18 impeccable-linux-x64, sha256 736ed785…f648; registry entry from PR #421): under `unshare -rn strace -f -e trace=connect,socket`, empty env (no DO_NOT_TRACK), scratch HOME, `--version`, `detect --list-rules` and `detect <local dir>` made no socket call and wrote no file to HOME. Control: curl under the same trace showed AF_INET sockets. So the fabric's own unflagged `--version` proof (tools_install / tools_check) sends no telemetry; DO_NOT_TRACK=1 still matters for a URL target or other subcommands, which were not traced. Related: [[j460-handover-2026-10-30]].

**`<verb> --help` is not safe (reported by brand-comms-01, OBSERVATION 01a18b5e, 2026-10-30).** Five verbs ignore `--help` and run: palette, signals, concept-seed, embed-prompt and generate-image. From the 0.1.18 source, concept-seed sends a roll request to impeccable.style even with DO_NOT_TRACK set. So the only command to clear for any brief is `detect` (plus `--version`), never "any verb with --help".

*References: j460-handover-2026-10-30*

*Anchors: `projects/registry.json::impeccable-linux-x64`*

*Observed 2026-10-30 (fabric-coordinator)*
