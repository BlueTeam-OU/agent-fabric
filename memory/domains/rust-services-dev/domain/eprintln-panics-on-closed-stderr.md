---
role: "rust-services-dev"
class: domain
topic: "eprintln-panics-on-closed-stderr"
description: "In a stdio child of a host that may die, never eprintln!; it panics on EPIPE (exit 101)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 8364bfcb5c9867ff
---

## In a stdio child of a host that may die, never eprintln!; it panics on EPIPE (exit 101)

`eprintln!` panics ("failed printing to stderr") on any write error but EBADF; Rust ignores SIGPIPE, so a closed stderr read end is EPIPE and a panic. A stdio MCP server whose host died takes exit 101 on its next log line. Write `let _ = writeln!(std::io::stderr().lock(), ..)`, and write any durable copy (a log file) before stderr. Found by review on BlueTeam-OU/InterWeave#419 (F1); pinned by `apps/claude-channel/tests/refused_start.rs::a_closed_stderr_neither_ends_the_bridge_nor_costs_the_file_its_lines`, which fails with eprintln! restored.

*Observed 2026-10-24 (rust-services-dev)*
