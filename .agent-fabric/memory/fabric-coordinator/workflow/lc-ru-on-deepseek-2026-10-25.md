---
role: "fabric-coordinator"
class: workflow
topic: "lc-ru-on-deepseek-2026-10-25"
description: "language-culture-ru moved to the broker (DeepSeek V4 Pro) on 2026-10-25 after repeated model-safeguard stops on j85; how the move was done, and that the cause is unfound"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - abba6763e95fffaa
---

## language-culture-ru moved to the broker (DeepSeek V4 Pro) on 2026-10-25 after repeated model-safeguard stops on j85; how the move was done, and that the cause is unfound

2026-10-25, on the owner's word ("or move it to deepseek"): language-culture-ru stopped on a
model-safeguard error three times after a /clear, in j85 (gzapp i18n review). I relaunched it on
the broker from its deck pane: `/exit` (then "Exit and stop tasks"), then
`fabric-resume -- --provider openrouter` in its shell; ori asked how to sign in, answered with the
account's own OPENROUTER_API_KEY (already in its store; `fabric-secrets provision issue-key`
found it present). Status bar then read deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim,
and `fabric-ctl states` "working" on j85. launch-provider.json now records openrouter, so later
resumes stay there (resume.py provider_args).

**Why:** a stopped session idles silently; a resume or /clear on the same model re-reads the same
start material and stops again.
**How to apply:** the trigger is not identified. Do not read its notes or that pane into an
Anthropic-model session to find it (my own replies were stopped twice doing so). To bring it
back to Anthropic: `fabric-resume -- --provider anthropic` from its shell, after the trigger is
found. Related: [[safeguard-refusal-stalls-agent]], [[type-into-ssh-pane]].

*References: safeguard-refusal-stalls-agent, type-into-ssh-pane*

*Anchors: `tools/fabric/resume.py::provider_args`*

*Observed 2026-10-25 (fabric-coordinator)*
