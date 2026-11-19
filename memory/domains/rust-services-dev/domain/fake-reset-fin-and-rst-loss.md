---
role: "rust-services-dev"
class: domain
topic: "fake-reset-fin-and-rst-loss"
description: "A tokio fake's \"reset\" sends FIN first; a true RST drops unsent data; who sees the RST depends on which call is active"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 8ff6eb6f0795a6a7
---

## A tokio fake's "reset" sends FIN first; a true RST drops unsent data; who sees the RST depends on which call is active

Three facts about resetting a TCP peer in a test fake (Linux, loopback), each found on PR #91 (j70):
1. Dropping a tokio `OwnedWriteHalf` calls shutdown(Write): a FIN. Zero linger then makes the last close a RST, so
   "drop both halves under zero linger" is FIN-then-RST, and a body framed by the close reads as cleanly ended.
   RST alone: `write.forget()`, and let the read half's drop make the last close.
2. A RST alone discards what the sender's kernel has not transmitted yet: 35 small writes then a zero-linger close
   delivered 51/105 bytes (78 with TCP_NODELAY); NODELAY plus a 5 ms pause delivered all of them in 299/300 trials.
   No safe API reports an empty send queue (SIOCOUTQ is an ioctl; the workspace denies unsafe), so a fake waits.
3. Which call on the receiver takes ECONNRESET decides what is tested: a parked hyper client is woken for its read
   first. To make the write take it, keep the client writing (drain its upload) and reset at once.
Turning FakeUpstream's Step::Reset into a pure RST made the fuzzed sse_framing property lose a head (502), so the shared
fake keeps FIN-then-RST; the pure RST lives in EarlyUpstream (`Ending::Reset`).

*Observed 2026-11-13 (rust-services-dev)*
