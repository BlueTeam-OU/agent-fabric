---
role: "fabric-coordinator"
class: domain
topic: "cloudflare-tsrs-upstream-sync"
description: "Cloudflare/VoidZero tsrs (Rust port of TypeScript, 2026-10): production-grade players run an AI-made port kept faithful by an agent upstream-sync loop (daily diff review → tracking issues, nightly upstream test suite as a compatibility…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6be51198f0250062
---

## Cloudflare/VoidZero tsrs (Rust port of TypeScript, 2026-10): production-grade players run an AI-made port kept faithful by an agent upstream-sync loop (daily diff review → tracking issues, nightly upstream test suite as a compatibility matrix); borrow for the herdr fork and ports

https://blog.cloudflare.com/typescript-rust-port/ (read 2026-10-27 through moli). Cloudflare and VoidZero, with Owner.com, are building **tsrs** (github.com/oxc-project/tsrs), a Rust port of the TypeScript compiler. It is incubated in the Oxc toolchain, done with the TypeScript team, and not a fork: the TypeScript team keeps sole control of the language, and the port follows its decisions strictly.

The owner's framing: Cloudflare is a production-grade player, so the practices described carry weight.
- **The numbers.** Up to 8x faster than TypeScript 7.0 with ~70% less memory, at the same number of type-check workers, benchmarked on the same configuration as the TypeScript team. Some optimisations went back upstream into TS 7.1 (up to 2.5x faster).
- **Status.** An experimental npm release (`npx tsrs`), with known differences such as diagnostic order. A stable release is promised.
- **Why now.** "Frontier AI models can now do large-scale ports almost independently in a matter of days." Slopforks, faithful ports and re-architected versions all exist. What separates a faithful port is the discipline that keeps it in sync, not the port itself.
- **Why Rust.** WebAssembly without shipping a garbage collector, so whole toolchains run sandboxed in Workers, in a browser or on a device. Cloudflare pitches this for agents: a development toolchain end-to-end in a sandbox.
- **How it stays faithful** (the Vinext/Next.js process): every morning an agent reviews upstream changes, fetches the diffs and opens tracking issues for anything that could affect the port. Every night the upstream test suite runs against the port, regenerating a compatibility matrix. When a gap shows, agents find the change in both codebases, build a reproduction, port the relevant tests and propose a fix. Performance wins go back upstream.
- **Consolidation.** tsrs and Theo Browne's tsc-rs are being merged into one package with LSP.

**For the fabric:** nothing to adopt directly; we compile no TypeScript, and gzapp's web clients can wait for a stable tsrs. **Borrow the sync loop:**
1. **The herdr fork** (agent-fabric-fleetdeck, from herdrdev/herdr): a daily agent job that reviews upstream's new commits and opens issues for those touching the fork's changes, plus a nightly run of upstream's test suite against the fork as a compatibility matrix. Changes general to herdr go upstream as pull requests, as the project note already says.
2. **Ports:** an AI-made port is trustworthy only with the original's test suite as its oracle, run continuously. Wave 9 (bash to Python) did this with bash oracles. Keep that the rule for any future port (InterWeave pieces, Rust ports).
3. **Production signal:** a large production player now ships AI-made large-scale ports. The discipline is a published oracle, upstream ownership kept, and differences listed before a stable release.

Related: [[bash-to-python-wave-9]], [[harness2]].

*References: bash-to-python-wave-9, harness2*

*Observed 2026-10-27 (fabric-coordinator)*
