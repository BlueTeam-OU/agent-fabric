---
role: "rust-services-dev"
class: workflow
topic: "shape-only-capture"
description: "how to measure what identifiers a harness sends without recording any value; reading a login's real Claude config is refused"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5fc4072559169edc
---

## how to measure what identifiers a harness sends without recording any value; reading a login's real Claude config is refused

To show what identifiers a client sends without holding any value:
- Use a loopback fake under `unshare -rn` that writes shapes only: label words copied from the fake's own constants, other letter/digit runs as class and length, UUIDs as `<uuid>`, map keys only if they have no digit.
- Compare against the first request inside the fake's process and record only true/false, which shows persistence across sessions.
- Run each client twice on one fresh home to get two sessions of one device.

spikes/user-id-shape in agent-fabric-gateway (217cf79) is the instrument.

Listing identity keys of this login's real ~/.claude.json was refused by the auto-mode classifier (Credential Exploration, 2026-10-19). Answer config questions by seeding a fresh config with synthetic values instead.

In ugrep (the grep here), `.{0,300}` context patterns fail on "complexity limits"; use a Python window script.

moli on platform.claude.com, openrouter.ai and platform.openai.com times out by default; `--disable-js` works, as do `.md` page URLs.

*Observed 2026-10-19 (rust-services-dev)*
