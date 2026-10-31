---
role: "devex-tooling"
class: solution
topic: "boundary-pattern-as-the-consumer-resolves"
description: "a security-boundary path pattern (arm.json) holds only if written for how the tool that reads the file finds it — any depth, any case — and survives the exempt list, which arm.py applies first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5befdc1df0cd90ec
---

## a security-boundary path pattern (arm.json) holds only if written for how the tool that reads the file finds it — any depth, any case — and survives the exempt list, which arm.py applies first

InterWeave's arm.json put `.cargo/config(.toml)` on the boundary. Cargo honours `[patch]`,
`[source] replace-with` and path overrides there, the same redirection as the root Cargo.toml. It
took four review rounds (agent-fabric #90, #91, 2026-10-04), each a hole the one before had left:

1. `^\.cargo/config` was anchored at the root. Cargo reads `.cargo/config.toml` from every ancestor
   of the directory it runs in, so a nested `crates/x/.cargo/config.toml` escaped. Fixed with
   `(^|/)`.
2. arm.py drops exempt files before it matches the boundary (`exempt_re` first), and the exempt
   list held `^tools/` and `^xtask/`. So `tools/foo/.cargo/config.toml` was exempt, although the
   pattern matched it. exempt now opens with a negative lookahead for the file.
3. paths is case-insensitive but exempt was not, so `.Cargo/config.toml` under tools/ was exempt
   on a case-insensitive filesystem. The lookahead got a scoped `(?i:…)`.
4. The required non-matches (`crates/human/ui-slint/Cargo.toml`, `Cargo.lock`) had no test, so
   un-anchoring `^Cargo\.toml$` failed nothing.

**How to apply:** for each sensitive file, write down where the consuming tool looks for it (every
depth, every ancestor, letter case on a case-insensitive filesystem). Then give boundary.cases a
positive case at each of those places, including one under every exempt tree, and a negative case
for each near-miss name. A positive case only proves something when no other rule already covers
that path: a nested path under crates/transport/ proved nothing, because the directory is on the
boundary anyway. The order of the edit and who to ask are in gzapp's `arm-json-boundary-edits`
slice.

*Anchors: `projects/interweave/integration/gh/arm.json::.cargo/config`, `tools/fabric/github/arm.py::exempt_re`*

*Observed 2026-10-22 (devex-tooling)*
