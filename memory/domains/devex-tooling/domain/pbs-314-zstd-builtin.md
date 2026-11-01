---
role: "devex-tooling"
class: domain
topic: "pbs-314-zstd-builtin"
description: "python-build-standalone 3.14 links _zstd into libpython (no lib-dynload .so); measure a module by sys.builtin_module_names or a marker, not tar listing"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 57b21e98bee03e4b
---

## python-build-standalone 3.14 links _zstd into libpython (no lib-dynload .so); measure a module by sys.builtin_module_names or a marker, not tar listing

python-build-standalone 3.14.9+20261021 install_only (x86_64, aarch64) has `compression.zstd` working, but `tar tzf` shows no `_zstd*.so`: the extension is linked into libpython3.14.so.1.0 (`"_zstd" in sys.builtin_module_names` is True; libzstd 1.5.7). On an arch you cannot run, compare a library marker (`grep -ac ZSTD_compressStream2 libpython3.14.so.1.0`) against the arch you can, as control. The build ships pip 26.2.2, so a pinned wheel can be installed offline by the build's own pip. Brotli is in neither arch (j212, 2026-10-24).

Related: ADR-064 was amended 2026-10-24 to `;ce=deflate` because the 3.13 pin lacked brotli; a brotli wheel conflicts with ADR-040's standard-library-only rule unless that record is amended.

*Observed 2026-10-24 (devex-tooling)*
