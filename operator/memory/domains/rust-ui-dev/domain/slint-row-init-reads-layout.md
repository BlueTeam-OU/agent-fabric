---
role: "rust-ui-dev"
class: domain
topic: "slint-row-init-reads-layout"
description: "Slint 1.18 -- a repeated row that reads its geometry as it is made (init, or a changed handler's first eval) relays the whole list per row made; && guards get hoisted"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 756c196596b9b846
---

## Slint 1.18 -- a repeated row that reads its geometry as it is made (init, or a changed handler's first eval) relays the whole list per row made; && guards get hoisted

Three Slint 1.18.1 facts that together made InterWeave's message list O(new x held) per page (j77, 2026-10-31):

1. An element's `changed p => {}` handler is `ChangeTracker::init` (not `init_delayed`): `p` is EVALUATED when the instance is made, like `init => {}`. A `p` reading `self.y`/`absolute-position` forces layout right then.
2. The repeater makes a page's instances one by one (`update_all_instances`), each init inside the loop; a geometry read there solves the parent layout, and each solve calls every row's `fn_layoutinfo_v_with_constraint` (a FUNCTION, not cached), measuring every row's text again (fontique fallback lookup dominated). Measured: 64 rows above 256 held, 2 s release; with no geometry read at creation, 70 ms flat.
3. `passes/deduplicate_property_read.rs` hoists a property read twice in one binding into a `let tmp_` at the binding's TOP. In a left-assoc `a && b && c && d` it counts every operand but the last as unconditional, so `self.placed && geomA && geomB` still reads `self.y` before `placed`. Put the guarded part in ONE right-hand side, `self.placed && (geomA && geomB)`, or a ternary branch; verify in target/*/build/*/out/app.rs.

Fix shape: `property <bool> placed: false;` + `Timer { interval: 0ms; running: !self.placed; triggered => { self.placed = true; } }`, geometry bindings gated on it; the first change handler eval then records the gated value and sees the real one later. Found with an in-process SIGPROF sampler (glibc backtrace + addr2line) since the host has no perf. Test: `crates/human/ui-slint/tests/draw_cost.rs`. See [[desktop-paging-relayout-cost]], [[slint-image-equality]].

*References: desktop-paging-relayout-cost, slint-image-equality*

*Observed 2026-10-31 (rust-ui-dev)*
