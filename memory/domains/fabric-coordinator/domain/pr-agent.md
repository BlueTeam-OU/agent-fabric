---
role: "fabric-coordinator"
class: domain
topic: "pr-agent"
description: "PR-Agent (The-PR-Agent/pr-agent, ex-Qodo, MIT, Python): single-LLM-call PR tools /review /describe /improve /ask; diff-only with token-aware compression; not adopted as the fabric's reviewer; borrow ideas listed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a6f73c607b22549
---

## PR-Agent (The-PR-Agent/pr-agent, ex-Qodo, MIT, Python): single-LLM-call PR tools /review /describe /improve /ask; diff-only with token-aware compression; not adopted as the fabric's reviewer; borrow ideas listed

Read 2026-10-13 (owner asked: analyze and memorize). github.com/The-PR-Agent/pr-agent — 13.4k stars,
2.0k forks, 5,944 commits, MIT, Python; v0.47.0 on 2026-10-02, pushed 2026-10-11. Qodo donated it to a
community org (first external maintainer @naorpeled; moving to a foundation); Qodo's own product is
separate. Docs docs.pr-agent.ai; Docker image pragent/pr-agent from 0.34.2.

**What it is.** PR tools run as PR comments or CLI (`pr-agent --pr_url <url> review`, `pip install
"pr-agent[github]"`, or a GitHub Action with OPENAI_KEY + GITHUB_TOKEN): /describe (writes the PR
description), /review, /improve (committable code suggestions), /ask (Q&A on the PR), /similar_issue.
Each tool is ONE LLM call (~30 s). Models through LiteLLM (OpenAI, Claude, Gemini, DeepSeek,
OpenRouter, Ollama…). Providers: GitHub, GitLab, Bitbucket, Azure DevOps, Gitea. Prompts and
categories configurable in TOML (pr_agent/settings/configuration.toml).

**Compression strategy** (large PRs): drop binaries; order files by the repo's main languages, then
by token count; strip deletion-only hunks and list deleted files by name; ±3 lines of context;
fill with tiktoken up to a buffer, then list the rest as "other modified files", then deleted
files, hard stop at the limit.

**Caution seen:** `/help_docs` disabled since v0.36.1 for a credential-exposure issue (#2445).

**Against the fabric** ([[codex-review-routing-decision]]): our review is an agentic, blind review
of base..head that reads the live repo (code-review class + Codex, both required, judged by the
review class, ADR-053); PR-Agent sees only the compressed diff in one call, so it would be a weaker,
cheaper third opinion, not a replacement. Not adopted.
**Borrow if needed:** /describe-style PR body generation from the diff; /improve's "suggestion the
author can commit" shape for P3 findings; the compression order as a fallback when a Codex brief or
diff exceeds a model's window; TOML-configurable review categories as a model for review lenses.

*References: codex-review-routing-decision*

*Observed 2026-10-13 (fabric-coordinator)*
