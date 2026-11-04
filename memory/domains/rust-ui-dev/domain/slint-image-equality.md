---
role: "rust-ui-dev"
class: domain
topic: "slint-image-equality"
description: "Slint 1.18 Image equality -- an empty image equals nothing (not its clone), a pixel image compares by buffer pointer; a row struct holding one never compares equal"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 71f5b93c907cc0f5
---

## Slint 1.18 Image equality -- an empty image equals nothing (not its clone), a pixel image compares by buffer pointer; a row struct holding one never compares equal

In i-slint-core 1.18.1 `ImageInner::eq` ends `_ => false`, so `Image::default() != Image::default()`, a clone included; `SharedImageBuffer::eq` compares the data POINTER, so `Image::from_rgba8(clone_from_slice(..))` made twice from the same pixels differs too. A generated Slint struct holding an `image` field therefore never equals itself made again: a compare-before-set over `VecModel` rows (InterWeave's `update_by_key`, the contacts list) sets every such row on every render.

Rule: never put `Image::default()` in a row struct; use one shared placeholder (a thread_local 1x1 `from_rgba8` image whose clones share the buffer) and cache each real photo's `Image` per source, cloning it. InterWeave j77 (2026-10-31): `cards::no_photo`, `DrawnBody.card_photo`; tests `a_render_that_changes_nothing_leaves_every_{message,contact}_row_equal`, both mutation-checked.

Measured: fixing it took the per-page message row sets from N held to 0 but did NOT change the first draw after a page (still ~7 ms per held row in release), so a set of an equal-but-for-image row is not where that cost is. See [[desktop-paging-relayout-cost]].

*References: desktop-paging-relayout-cost*

*Observed 2026-10-31 (rust-ui-dev)*
