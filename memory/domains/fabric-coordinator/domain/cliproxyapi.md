---
role: "fabric-coordinator"
class: domain
topic: cliproxyapi
description: "router-for-me/CLIProxyAPI (MIT Go, 56.7k stars): exposes subscription OAuth logins (Claude Code, Codex, Gemini/Antigravity, Grok, Kimi, Devin) as OpenAI/Claude/Gemini APIs with multi-account round-robin; not adopted (one process holding…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - db0ae353389f8e20
---

## router-for-me/CLIProxyAPI (MIT Go, 56.7k stars): exposes subscription OAuth logins (Claude Code, Codex, Gemini/Antigravity, Grok, Kimi, Devin) as OpenAI/Claude/Gemini APIs with multi-account round-robin; not adopted (one process holding every login's token breaks ADR-038, 'free models through API' framing + residential-proxy sponsors = ban/terms risk, fleet already runs codex/claude natively); borrow protocol translators, per-account 5h/7d quota view, 429 cooldown

https://github.com/router-for-me/CLIProxyAPI (read 2026-10-28 through moli; README only, code not read). MIT, Go, 56.7k stars, 8.7k forks, about 4,570 commits. A large ecosystem builds on it: desktop and tray wrappers, management consoles, quota inspectors, and Panopticon, a multi-agent orchestrator that runs it as a sidecar.

**What it is:** a proxy server that takes the OAuth logins of subscription CLIs (Claude Code, ChatGPT Codex, Gemini CLI/Antigravity/AI Studio, Grok Build, Muse Code, Kimi, Devin) and serves them as OpenAI-compatible (including Responses), Gemini-compatible and Claude-compatible APIs to any client or SDK.
- Streaming, WebSocket, tools and images.
- Several accounts per provider with round-robin load balancing.
- Upstreams that speak the OpenAI protocol (OpenRouter, for example) set in config.
- A management API.
- A Go SDK of executors (one per upstream) and translators (between protocols), with a custom-provider example.
- Usage statistics were removed from the core in v6.10; third-party tools now keep them.
- Its own About line: "enjoy the free Gemini, GPT, Grok, Claude models through API".

**For the fabric: not adopted.**
1. **Credentials.** One process holding every account's OAuth token breaks ADR-038, under which each login's credential lives in its own encrypted store and only that login reads it. A compromise of the proxy would be a compromise of every account.
2. **Terms and bans.** The pitch is a subscription login turned into a general API, and several sponsors sell residential proxies "one IP per account" for multi-account operation. That is the evasion end of the market. The owner's subscription pooling ([[subscription-pool-settled]]) is accounts moved between official harnesses by stop and relaunch, which is a different thing. A proxy pretending to be the official client risks account suspension for the whole fleet.
3. **No gap to fill.** Sessions run the official `claude`. Codex reviews run the official codex CLI on the ChatGPT subscription ([[codex-chatgpt-signin-2026-10-12]], [[no-paid-openai-api-for-reviews]]). Non-Anthropic models go through the routing's broker or shim (OpenRouter) with their own keys. ADR-040's stdlib stance and the host load add to this.

**Borrow without adopting:**
- **The executor/translator split:** one translator per protocol pair, kept apart from one executor per upstream. This is the shape for the fabric's broker or shim if it grows beyond one model family.
- **A per-account quota view:** the 5 h and weekly windows, plan-based sorting, and a forecast of when quota returns (Quota Inspector, Pool Watch) for `fabric-usage` and the deck.
- **Cooldown and failover:** taking a 429'd account out of rotation until its window resets. Same lesson as [[claudemanager]].

Related: [[claudemanager]], [[codex-reviews]].

*References: claudemanager, codex-chatgpt-signin-2026-10-12, codex-reviews, no-paid-openai-api-for-reviews, subscription-pool-settled*

*Observed 2026-10-28 (fabric-coordinator)*
