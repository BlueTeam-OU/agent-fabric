#!/usr/bin/env bash
# Claude Code PreToolUse hook for the Agent tool: the dispatch guard.
#
# Reads the tool call on stdin, prints a hookSpecificOutput JSON object
# to deny or ask, or prints nothing to allow. The rules it enforces, and
# the incidents behind each one, are in the subagent-dispatch skill
# (policies/subagent-dispatch/SKILL.md); agent-fabric ADR-005 and ADR-020
# are the decisions. This file exists so the program can be
# READ and TESTED (.claude/test_agent-dispatch-guard.sh) -- it used to
# be a one-line jq string inside settings.json, which nothing exercised.
#
# TWO CLASSES OF DISPATCH, decided in this order:
#
#   fork            -> allowed; a fork continues the session.
#   REVIEW class    -> subagent_type "code-review" AND description
#                      beginning "review" / "re-review" (any word
#                      form: Reviewing, Re-review of ...) AND model
#                      "fable" AND NO isolation. All four, or denied --
#                      never asked. Standing authorisation for the
#                      class: a review's failure mode is not a retry,
#                      it is a green PR that merges, so no per-dispatch
#                      prompt and no dropping to a cheaper tier because
#                      a review looks small. No worktree, because a
#                      review writes nothing and worktree.baseRef=head
#                      would hide uncommitted work from the one agent
#                      that must see it; the tree is read-only for it.
#                      WHY fable and not opus: the Agent tool's model
#                      field accepts only the tier aliases, and on the
#                      broker path one alias carries one exported
#                      model. code-high rides opus, so a reviewer on
#                      opus IS code-high's model -- on 2026-09-13 that
#                      was GLM 5.3. fable is the alias nothing else
#                      rides; the launcher exports the review-grade
#                      model under it and gates exactly that export.
#   CODING class   -> subagent_type code-low / code-medium / code-high:
#                      the class DECIDES the tier. `model` must be the
#                      alias runtime/claude-code/aliases.json binds to
#                      that class (haiku / sonnet / opus); anything
#                      else is denied, unset included. A class whose
#                      alias could be overridden per call is decorative:
#                      code-high on sonnet is "high" work on the cheap
#                      tier with nothing to say so. The alias stays on
#                      the call rather than being inferred, because it
#                      is what the harness resolves and what the broker
#                      launcher exports per session; the class is the
#                      vocabulary, the alias its binding, and the two
#                      must agree. code-high asks (premium).
#   READ-ONLY types -> Explore, Plan, claude-code-guide: no writing
#                      tool in their definition, and the clone guard
#                      (subagent-clone-guard.sh) fences their Bash in
#                      the session clone. Model required (the tier is
#                      still a choice); isolation NOT required — a
#                      worktree at baseRef=head would hide the
#                      uncommitted work a search or a plan is asked
#                      about, as it would for a review. Found
#                      2026-09-16: every Explore dispatch was denied
#                      and the research was done by hand.
#   locale-worker   -> the language-culture role's worker: a one-inert-tool
#                      subagent whose system prompt and every input are
#                      the locale's language, so its reasoning cannot
#                      start from English it never saw (the CEO,
#                      2026-09-17; docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).
#                      Model required; isolation must be ABSENT (it
#                      writes nothing, a worktree protects nothing);
#                      any alias allowed and never asked — language
#                      judgement is premium by design. The dispatcher's
#                      role is not checked here (no branch checks it):
#                      the agent file exists only on a language-culture
#                      login (install-agent-files.sh), and an unknown
#                      type fails in the harness before this hook runs.
#   everything else -> model required; isolation "worktree" required;
#                      opus/fable ask (per-dispatch authorisation).
#
# WHY the description prefix is a condition and not a substitute for
# the type: a hook that granted the exemption on review-ish WORDS would
# be satisfiable by phrasing. Here the words can only NARROW -- the type
# is a file in the repo, and the prefix stops a writing dispatch
# ("Address review feedback") from wearing the review type and running
# unisolated in the clone. Another project learned exactly that the
# hard way: a guard that matched "review" anywhere let it through.
#
# WHY the model condition sits inside the review branch: keyed on the
# type alone, a sonnet or haiku dispatch would take the exemption and
# evade the rule beside it. Both halves, or neither.
set -uo pipefail

# A permission gate that cannot run must not vanish into an allow. jq
# missing is the one dependency; without it, ASK -- the person at the
# keyboard sees why -- rather than let every dispatch through unchecked.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"The dispatch guard could not run (jq is not installed). Approve only if you have checked model and isolation yourself. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md)."}}'
  exit 0
fi

# The class->alias binding, from the file the launcher exports from. A
# missing or unreadable file must not silently loosen the check: the
# class branch then denies with a message that says so.
ALIASES="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)/aliases.json"
ALIAS_JSON="$(jq -c '.aliases // {}' "$ALIASES" 2>/dev/null || echo '{}')"

# THE FILE PIN. Under a fabric launch (runtime/openrouter/launch, either
# provider) the review class runs on the model routing resolves for it —
# but not through the fable export: code-plan rides fable too, and one
# alias carries one export, so through it the reviewer would follow
# code-plan (as it once followed code-high on opus, 2026-09-13). Verified
# live 2026-09-15 on plain claude: the Agent tool's `model` accepts only
# the four aliases (a hook rewriting it to a model id is rejected at
# schema validation), the dispatch's `model` outranks the agent file's,
# and an agent file whose frontmatter names a model id runs on it when
# the dispatch leaves `model` unset. So the pin lives in the reviewer's
# agent file (install-agent-files.sh writes it there at launch, for the
# launch's provider, merged for this login — `pins --me`), and this
# guard — AFTER the review rules have held, `model: fable` included —
# allows the dispatch with `model` removed, so the file's pin applies.
# The file is checked against the same resolution first: another launch
# of this account on the other provider rewrites it, and a reviewer on a
# model nothing chose for this session is denied, not run. Only under a
# fabric launch; anywhere else the alias reaches the harness as written.
PINNED_JSON='{}'; FILE_MODEL=""; ROUTED_EFFORT_JSON='{}'; FILE_EFFORT_JSON='{}'
if [[ -n "${AGENT_FABRIC_LAUNCH_PROVIDER:-}" ]]; then
  ROUTING="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../.." && pwd)/tools/fabric/routing.py"
  PINNED_JSON="$(python3 "$ROUTING" pins --me --provider "$AGENT_FABRIC_LAUNCH_PROVIDER" 2>/dev/null | awk '{printf "%s\"%s\":\"%s\"", (NR>1?",":""), $1, $3} END {print ""}' | sed 's/^/{/; s/$/}/')"
  jq -e . <<<"$PINNED_JSON" >/dev/null 2>&1 || PINNED_JSON='{}'
  FILE_MODEL="$(sed -n '0,/^model: /s/^model: //p' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agents/code-review.md" 2>/dev/null || true)"
  # THE SAME CHECK, FOR THE OTHER ROUTED DIMENSION. install-agent-files.sh
  # writes an `effort:` into EVERY class file, not just the reviewer's
  # `model:`, so the cross-provider rewrite this guard already catches for
  # the review model can strand any class at the other provider's level —
  # an openrouter launch leaves GLM's clamp in code-medium.md and an
  # anthropic session dispatches at it. Both maps are built here, for all
  # five classes, and handed to jq like the two above: the dispatched class
  # need not be known before jq, so nothing reads the call first.
  # Compared FILE-first and only when the file carries a line: a missing
  # one is an install that predates effort, not another launch's value,
  # and denying on absence would block every dispatch on every account
  # until it relaunched. A cross-provider rewrite always WRITES a line,
  # so the direction that matters is still caught.
  ROUTED_EFFORT_JSON="$(python3 "$ROUTING" efforts --me --provider "$AGENT_FABRIC_LAUNCH_PROVIDER" 2>/dev/null | awk '$2 != "-" {printf "%s\"%s\":\"%s\"", (n++ ? "," : ""), $1, $2} END {print ""}' | sed 's/^/{/; s/$/}/')"
  jq -e . <<<"$ROUTED_EFFORT_JSON" >/dev/null 2>&1 || ROUTED_EFFORT_JSON='{}'
  FILE_EFFORT_JSON="$(for k in code-low code-medium code-high code-plan code-review; do
        v="$(sed -n '0,/^effort: /s/^effort: //p' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/agents/$k.md" 2>/dev/null || true)"
        [[ -n "$v" ]] && printf '%s\n' "$k $v"
      done | awk '{printf "%s\"%s\":\"%s\"", (n++ ? "," : ""), $1, $2} END {print ""}' | sed 's/^/{/; s/$/}/')"
  jq -e . <<<"$FILE_EFFORT_JSON" >/dev/null 2>&1 || FILE_EFFORT_JSON='{}'
fi

jq -c --argjson aliases "$ALIAS_JSON" --argjson pinned "$PINNED_JSON" --arg file_model "$FILE_MODEL" \
      --argjson routed_effort "${ROUTED_EFFORT_JSON:-{\}}" --argjson file_effort "${FILE_EFFORT_JSON:-{\}}" '
  def deny(reason): {hookSpecificOutput:{hookEventName:"PreToolUse",
                     permissionDecision:"deny",
                     permissionDecisionReason:reason}};
  def ask(reason):  {hookSpecificOutput:{hookEventName:"PreToolUse",
                     permissionDecision:"ask",
                     permissionDecisionReason:reason}};
  (.tool_input // {}) as $t
  | ($t.subagent_type // "") as $type
  | (($t.model // "") | ascii_downcase) as $model
  | ($t.isolation // "") as $iso
  | (($t.description // "") | ascii_downcase
     | test("^\\s*(re-)?review")) as $review_desc
  | if $type == "fork" then empty
    elif $type == "blind-reviewer" then
      deny("subagent_type \"blind-reviewer\" is the retired name of the review class; dispatch it as subagent_type: code-review (the capability class, like code-low/medium/high/plan), everything else unchanged. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
    elif $type == "code-review" then
      if ($review_desc | not) then
        deny("code-review dispatch whose description does not BEGIN with review or re-review. The review class is read-only and unisolated; a writing task under this type would run in the session clone. Describe a review as one, or dispatch a normal agent with isolation worktree. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif $model != "fable" then
        deny("Review dispatch with model \"" + ($t.model // "unset") + "\". The review class rides the fable alias, always: set model: fable. Not opus -- code-high rides opus, and one alias carries one exported model, so a reviewer on opus is whatever code-high resolves to (on the broker, whatever the column pins there). Not unset -- the review is not a retryable step, its failure mode is a green PR that merges. The Agent tool accepts no full model id; under a fabric launch this guard drops the alias after checking it and the agent file of the reviewer carries the model routing resolved for code-review. That capability is gated by agent-fabric routing/policies/review-grade.json, and the launcher (runtime/openrouter/launch) refuses a profile that resolves it to anything else, so policy stays here and vendor plumbing stays in routing/. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif $iso != "" then
        deny("Review dispatch sets isolation. A review writes nothing, so isolation protects nothing, and it hurts: worktree.baseRef is head, so a reviewer in a worktree cannot see uncommitted work. Omit isolation, pass the repository path, and tell the agent the tree is read-only and it runs no git writes. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif ($pinned["code-review"] // "") != "" and $file_model != $pinned["code-review"] then
        deny("Review dispatch under a fabric launch, but the agent file of the reviewer says model \"" + $file_model + "\" while this launch resolves code-review to \"" + $pinned["code-review"] + "\". Either another launch of this account (the other provider) has rewritten ~/.claude/agents/code-review.md since this session started, or the fabric checkout moved under this session and now routes the review class to a different model; either way a reviewer would run on a model nothing chose for this session. Re-run agent-fabric/bin/fabric-model apply from this session, or relaunch. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif ($file_effort | has("code-review")) and ($routed_effort["code-review"] // "") != $file_effort["code-review"] then
        deny("Review dispatch under a fabric launch, but the agent file of the reviewer says effort \"" + $file_effort["code-review"] + "\" while this launch resolves code-review to \"" + ($routed_effort["code-review"] // "none") + "\". Either another launch of this account has rewritten it since this session started, or the fabric checkout moved under this session and now routes the review class differently. Re-run agent-fabric/bin/fabric-model apply from this session, or relaunch. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif ($pinned["code-review"] // "") != "" then
        # The rules held; under a fabric launch the reviewer file carries the pin.
        {hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"allow",
          permissionDecisionReason:("Review dispatch under a fabric launch: model fable checked, then removed so the reviewer runs on its pinned model " + $pinned["code-review"] + " (the agent file, from routing) while fable itself stays the tier of code-plan."),
          updatedInput:($t | del(.model))}}
      else empty end
    elif $type == "locale-worker" then
      # Before the review-description branch: reviewing a text in the locale
      # is the job of the worker itself, and its description is in the locale;
      # a description that begins with review names no reviewer class here.
      if ($model | length) == 0 then
        deny("locale-worker dispatch has no model set. The worker reads nothing, but its tier is still a choice, and unset means the session model by accident. Set model explicitly (opus is the design: language judgement is premium work). See docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md.")
      elif $iso != "" then
        deny("locale-worker dispatch sets isolation. The worker writes nothing anywhere — its one tool reads and writes no file — so isolation protects nothing; omit it. See docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md.")
      else empty end
    elif $review_desc then
      deny("Description begins with review but subagent_type is \"" + $type + "\". A code review is the code-review class (fable, no isolation, no session context) -- not a general agent on a cheaper tier. If this is not a code review, re-word the description (Audit ..., Check ..., Inspect ...). See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
    elif ($type | test("^code-(low|medium|high|plan)$")) then
      ($aliases[$type] // "") as $alias
      | if $alias == "" then
          deny("Dispatch names the class \"" + $type + "\" but runtime/claude-code/aliases.json binds no alias to it (file missing, unreadable, or the class is not in it). The class decides the tier and this guard cannot tell which; nothing is inferred. Fix the binding, or set model to the alias the class is documented to ride. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
        elif $model != $alias then
          deny("Dispatch names the class \"" + $type + "\" with model \"" + ($t.model // "unset") + "\"; that class rides the " + $alias + " alias (runtime/claude-code/aliases.json), and the two must agree -- a class whose tier a call can override is a label, and " + $type + " on another tier is that work on a model nothing chose for it. Set model: " + $alias + ", or name the class that rides the tier you mean. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
        elif $iso != "worktree" then
          deny("Agent dispatch does not set isolation to worktree. Every writing subagent works in its own worktree, never the session clone: the dispatcher opens and closes it, the agent stays in the path it is given, runs no git, and never commits. A premium-model authorisation grants a model tier, not an isolation exemption. Forks and the review class are the only carve-outs. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
        elif ($file_effort | has($type)) and ($routed_effort[$type] // "") != $file_effort[$type] then
          deny("Dispatch of \"" + $type + "\" under a fabric launch, but its agent file says effort \"" + $file_effort[$type] + "\" while this launch resolves " + $type + " to \"" + ($routed_effort[$type] // "none") + "\". Either another launch of this account (the other provider) has rewritten ~/.claude/agents/" + $type + ".md since this session started, or the fabric checkout moved under this session and now routes " + $type + " differently; either way the agent would think at a level nothing chose for this session. Re-run agent-fabric/bin/fabric-model apply from this session, or relaunch. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
        elif $type == "code-high" or $type == "code-plan" then
          ask("Agent dispatch names " + $type + ", a premium class (" + $alias + "). Per the subagent-dispatch skill, the premium tier is for a subagent only when you explicitly asked for it -- the task looking hard is not authorisation. Approve only if you did.")
        else empty end
    elif ($type | test("^(Explore|Plan|claude-code-guide)$")) then
      if ($model | length) == 0 then
        deny("Agent dispatch has no model set. Omitting it is not a neutral default - the subagent INHERITS the session model, so a premium session silently spawns premium agents. Set model explicitly: haiku for mechanical work (extraction, pattern-following edits, structured search), sonnet for judgement work (multi-file reasoning, convention-holding prose). See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif $iso == "worktree" then
        deny("Read-only dispatch (" + $type + ") sets isolation worktree. That type has no writing tool and its Bash is fenced in the clone (subagent-clone-guard.sh); a worktree protects nothing and hides the uncommitted work it is asked about (worktree.baseRef is head). Omit isolation. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
      elif ($model | test("opus|fable")) then
        ask("Agent dispatch requests the premium model \"" + ($t.model // "") + "\" for a read-only " + $type + ". Per the subagent-dispatch skill, opus/fable are forbidden for subagents unless you explicitly asked for that tier. Approve only if you did.")
      else empty end
    elif ($model | length) == 0 then
      deny("Agent dispatch has no model set. Omitting it is not a neutral default - the subagent INHERITS the session model, so a premium session silently spawns premium agents. Set model explicitly: haiku for mechanical work (extraction, pattern-following edits, structured search), sonnet for judgement work (multi-file reasoning, convention-holding prose). See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
    elif $iso != "worktree" then
      deny("Agent dispatch does not set isolation to worktree. Every writing subagent works in its own worktree, never the session clone: the dispatcher opens and closes it, the agent stays in the path it is given, runs no git, and never commits. A premium-model authorisation grants a model tier, not an isolation exemption. Forks and the review class are the only carve-outs. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).")
    elif ($model | test("opus|fable")) then
      ask("Agent dispatch requests the premium model \"" + ($t.model // "") + "\". Per the subagent-dispatch skill, opus/fable are forbidden for subagents unless you explicitly asked for that tier. Approve only if you did.")
    else empty end
'
