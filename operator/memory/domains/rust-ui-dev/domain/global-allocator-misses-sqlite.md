---
role: "rust-ui-dev"
class: domain
topic: "global-allocator-misses-sqlite"
description: "A Rust #[global_allocator] counter does not see bundled SQLite's (or OpenSSL's) heap; read sqlite3_memory_used/highwater beside it"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - b40c500658edba67
---

## A Rust #[global_allocator] counter does not see bundled SQLite's (or OpenSSL's) heap; read sqlite3_memory_used/highwater beside it

A counting `#[global_allocator]` sees only Rust's `alloc` calls. rusqlite's bundled SQLite/SQLCipher is C compiled with no allocator override (no `SQLITE_CONFIG_MALLOC` in rusqlite 0.40 or libsqlite3-sys 0.38 build.rs), so its page cache, statements and temp store go to libc malloc, uncounted. The same holds for vendored OpenSSL. Found by review on InterWeave #556 (F1). Counting SQLite's heap too showed the start's indexed counts growing SQLite's page cache with the backlog, which the Rust counter had hidden (0.02 MiB Rust against 3.53 MiB SQLite at 20k rows).

**Why:** a heap figure measured only on the Rust side reads as the process's heap and can hide the very growth it is meant to catch.
**How to apply:** beside the Rust counter, read `rusqlite::ffi::sqlite3_memory_used()` and `sqlite3_memory_highwater(reset)` per step (default MEMSTATUS is on in the bundled build), report both, and name what neither sees (OpenSSL). See [[j211-intake]].

*References: j211-intake*

*Observed 2026-11-04 (rust-ui-dev)*
