#!/usr/bin/env python3
"""tools/fabric/guards/dispatch_guard.py — the dispatch guard (ADR-040 Wave 2;
runtime/claude-code/hooks/agent-dispatch-guard.sh is its shim, run by the
PreToolUse hook for the Agent tool in runtime/claude-code/workspace/settings.json).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  stdin     the PreToolUse call, JSON
  env       AGENT_FABRIC_LAUNCH_PROVIDER (a fabric launch; routing.py reads
            AGENT_FABRIC_ROOT and AGENT_FABRIC_STATE_DIR), CLAUDE_CONFIG_DIR
  stdout    nothing to allow as written; else one hookSpecificOutput object,
            compact: deny, ask, or allow with updatedInput
  exit      0, always: exit 2 is the one code the harness reads as a
            blocking error, and any other failure it reads as an allow

Where the bash stopped (a call that was not JSON, a field of the wrong
type, an empty call) jq printed nothing and the dispatch ran; here it
asks, with the reason.

What follows is the bash's header, the rules and their incidents:

Claude Code PreToolUse hook for the Agent tool: the dispatch guard.

Reads the tool call on stdin, prints a hookSpecificOutput JSON object
to deny or ask, or prints nothing to allow. The rules it enforces, and
the incidents behind each one, are in the subagent-dispatch skill
(policies/subagent-dispatch/SKILL.md); agent-fabric ADR-005 and ADR-020
are the decisions. This file exists so the program can be
READ and TESTED (.claude/test_agent-dispatch-guard.sh) -- it used to
be a one-line jq string inside settings.json, which nothing exercised.

TWO CLASSES OF DISPATCH, decided in this order:

  fork            -> allowed; a fork continues the session.
  REVIEW class    -> subagent_type "code-review" AND description
                     beginning "review" / "re-review" (any word
                     form: Reviewing, Re-review of ...) AND model
                     "fable" AND NO isolation. All four, or denied --
                     never asked. Standing authorisation for the
                     class: a review's failure mode is not a retry,
                     it is a green PR that merges, so no per-dispatch
                     prompt and no dropping to a cheaper tier because
                     a review looks small. No worktree, because a
                     review writes nothing and worktree.baseRef=head
                     would hide uncommitted work from the one agent
                     that must see it; the tree is read-only for it.
                     WHY fable and not opus: the Agent tool's model
                     field accepts only the tier aliases, and on the
                     broker path one alias carries one exported
                     model. code-high rides opus, so a reviewer on
                     opus IS code-high's model -- on 2026-09-13 that
                     was GLM 5.3. fable is the alias nothing else
                     rides; the launcher exports the review-grade
                     model under it and gates exactly that export.
  CODING class   -> subagent_type code-low / code-medium / code-high:
                     the class DECIDES the tier. `model` must be the
                     alias runtime/claude-code/aliases.json binds to
                     that class (haiku / sonnet / opus); anything
                     else is denied, unset included. A class whose
                     alias could be overridden per call is decorative:
                     code-high on sonnet is "high" work on the cheap
                     tier with nothing to say so. The alias stays on
                     the call rather than being inferred, because it
                     is what the harness resolves and what the broker
                     launcher exports per session; the class is the
                     vocabulary, the alias its binding, and the two
                     must agree. code-high asks (premium).
  READ-ONLY types -> Explore, Plan, claude-code-guide: no writing
                     tool in their definition, and the clone guard
                     (subagent-clone-guard.sh) fences their Bash in
                     the session clone. Model required (the tier is
                     still a choice); isolation NOT required — a
                     worktree at baseRef=head would hide the
                     uncommitted work a search or a plan is asked
                     about, as it would for a review. Found
                     2026-09-16: every Explore dispatch was denied
                     and the research was done by hand.
  locale-worker   -> the language-culture role's worker: a one-inert-tool
                     subagent whose system prompt and every input are
                     the locale's language, so its reasoning cannot
                     start from English it never saw (the CEO,
                     2026-09-17; docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).
                     Model required; isolation must be ABSENT (it
                     writes nothing, a worktree protects nothing);
                     any alias allowed and never asked — language
                     judgement is premium by design. The dispatcher's
                     role is not checked here (no branch checks it):
                     the agent file exists only on a language-culture
                     login (install-agent-files.sh), and an unknown
                     type fails in the harness before this hook runs.
  everything else -> model required; isolation "worktree" required;
                     opus/fable ask (per-dispatch authorisation).

WHY the description prefix is a condition and not a substitute for
the type: a hook that granted the exemption on review-ish WORDS would
be satisfiable by phrasing. Here the words can only NARROW -- the type
is a file in the repo, and the prefix stops a writing dispatch
("Address review feedback") from wearing the review type and running
unisolated in the clone. Another project learned exactly that the
hard way: a guard that matched "review" anywhere let it through.

WHY the model condition sits inside the review branch: keyed on the
type alone, a sonnet or haiku dispatch would take the exemption and
evade the rule beside it. Both halves, or neither.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# Self-contained on purpose: the hook runs before every Agent dispatch, so
# it imports nothing of the fabric's (start-up is the cost ADR-040 §6
# names), and a copy of this file alone still decides — without the
# aliases beside it, by denying every class dispatch.
HERE = os.path.dirname(os.path.realpath(__file__))
FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SKILL = "See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md)."
ADR027 = "See docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md."
CLASSES = ("code-low", "code-medium", "code-high", "code-plan", "code-review")
PROBE_TIMEOUT_S = 20
# Whitespace as jq's Oniguruma reads `\s`: Python's also takes the four
# separators U+001C-U+001F, and with them "\u001freview: write the fix"
# wore the review type past this rule (review of #72). Measured over every
# character Python calls a space: those four are the only difference.
REVIEW_DESC = re.compile(r"^(?:(?![\x1c-\x1f])\s)*(re-)?review")
CODING_CLASS = re.compile(r"^code-(low|medium|high|plan)$")
READ_ONLY = re.compile(r"^(Explore|Plan|claude-code-guide)$")
PREMIUM = re.compile(r"opus|fable")
CANNOT_RUN = ("The dispatch guard could not run ({why}). Approve only if you have checked model and isolation "
              "yourself. " + SKILL)


class Malformed(Exception):
    pass


def decision(kind: str, reason: str, **extra) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind,
                                   "permissionDecisionReason": reason, **extra}}


def deny(reason: str) -> dict:
    return decision("deny", reason)


def ask(reason: str) -> dict:
    return decision("ask", reason)


def alt(value, default):
    """jq's `value // default`: null and false are absent."""
    return default if value is None or value is False else value


def text(value, what: str) -> str:
    """A field the rules read as text. jq stopped with an error on any other
    type, and a stopped guard was an allow; here it is a question."""
    if isinstance(value, str):
        return value
    raise Malformed(f"{what} is not text")


def ascii_lower(s: str) -> str:
    return s.translate({c: c + 32 for c in range(ord("A"), ord("Z") + 1)})


def first_value(path: str, key: str) -> str:
    """The first `<key>: ` line's value in an agent file (sed's
    `0,/^key: /s/^key: //p`), or ""."""
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as f:
            for line in f:
                if line.startswith(f"{key}: "):
                    return line[len(key) + 2:].rstrip("\n")
    except OSError:
        pass
    return ""


def routing_map(provider: str, what: str, column: int) -> dict:
    """`routing.py <what> --me --provider <p>`: its first word and the
    word at `column`, a map; "-" values dropped for efforts, as the awk
    did. Anything unreadable is the empty map."""
    # -E -s: no PYTHON* variable or user site reaches the probe whose
    # answer the gate compares (review of #72). Not -I: that also drops
    # routing.py's own directory, which it imports its siblings from.
    try:
        r = subprocess.run([sys.executable, "-E", "-s", os.path.join(FABRIC, "tools", "fabric", "routing.py"), what, "--me",
                            "--provider", provider], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out = {}
    for line in r.stdout.split("\n")[:-1] if r.stdout.endswith("\n") else r.stdout.split("\n") if r.stdout else []:
        words = line.split()
        key, value = (words[0] if words else ""), (words[column] if len(words) > column else "")
        # As the awk read it: every line an entry, a short one an empty
        # value; an effort of "-" (no effort for that model) no entry.
        if not (what == "efforts" and value == "-"):
            out[key] = value
    return out


def launch_pins(review: bool) -> tuple[dict, str, dict, dict]:
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
    provider = os.environ.get("AGENT_FABRIC_LAUNCH_PROVIDER", "")
    if not provider:
        return {}, "", {}, {}
    agents = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"),
                          "agents")
    # The review pin is asked only when a review is being judged: a routing
    # call costs a Python start on every dispatch.
    pinned = routing_map(provider, "pins", 2) if review else {}
    file_model = first_value(os.path.join(agents, "code-review.md"), "model") if review else ""
    # THE SAME CHECK, FOR THE OTHER ROUTED DIMENSION. install-agent-files.sh
    # writes an `effort:` into EVERY class file, not just the reviewer's
    # `model:`, so the cross-provider rewrite this guard already catches for
    # the review model can strand any class at the other provider's level —
    # an openrouter launch leaves GLM's clamp in code-medium.md and an
    # anthropic session dispatches at it. Both maps are built here, for all
    # five classes: the dispatched class need not be known before the rules,
    # so nothing reads the call first.
    # Compared FILE-first and only when the file carries a line: a missing
    # one is an install that predates effort, not another launch's value,
    # and denying on absence would block every dispatch on every account
    # until it relaunched. A cross-provider rewrite always WRITES a line,
    # so the direction that matters is still caught.
    routed_effort = routing_map(provider, "efforts", 1)
    file_effort = {}
    for k in CLASSES:
        v = first_value(os.path.join(agents, f"{k}.md"), "effort")
        # The awk kept only the first word of the line, and a line of
        # spaces as an empty value.
        if v:
            file_effort[k] = (v.split() or [""])[0]
    return pinned, file_model, routed_effort, file_effort


def aliases() -> dict:
    # The class->alias binding, from the file the launcher exports from. A
    # missing or unreadable file must not silently loosen the check: the
    # class branch then denies with a message that says so.
    try:
        with open(os.path.join(FABRIC, "runtime", "claude-code", "aliases.json"), encoding="utf-8") as f:
            found = alt(json.load(f).get("aliases"), {})
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def decide(call) -> dict | None:
    """The decision for one PreToolUse call, or None to allow as written."""
    t = alt(call.get("tool_input"), {}) if isinstance(call, dict) else None
    if not isinstance(t, dict):
        raise Malformed("the call carries no tool_input object")
    kind = text(alt(t.get("subagent_type"), ""), "subagent_type")
    raw_model = alt(t.get("model"), None)
    model = ascii_lower(text(alt(raw_model, ""), "model"))
    iso = alt(t.get("isolation"), "")
    review_desc = bool(REVIEW_DESC.search(ascii_lower(text(alt(t.get("description"), ""), "description"))))
    shown_model = raw_model if raw_model is not None else "unset"

    if kind == "fork":
        return None
    if kind == "blind-reviewer":
        return deny('subagent_type "blind-reviewer" is the retired name of the review class; dispatch it as '
                    "subagent_type: code-review (the capability class, like code-low/medium/high/plan), everything "
                    "else unchanged. " + SKILL)
    if kind == "code-review":
        if not review_desc:
            return deny("code-review dispatch whose description does not BEGIN with review or re-review. The review "
                        "class is read-only and unisolated; a writing task under this type would run in the session "
                        "clone. Describe a review as one, or dispatch a normal agent with isolation worktree. " + SKILL)
        if model != "fable":
            return deny(f'Review dispatch with model "{shown_model}". The review class rides the fable alias, always: '
                        "set model: fable. Not opus -- code-high rides opus, and one alias carries one exported "
                        "model, so a reviewer on opus is whatever code-high resolves to (on the broker, whatever the "
                        "column pins there). Not unset -- the review is not a retryable step, its failure mode is a "
                        "green PR that merges. The Agent tool accepts no full model id; under a fabric launch this "
                        "guard drops the alias after checking it and the agent file of the reviewer carries the model "
                        "routing resolved for code-review. That capability is gated by agent-fabric "
                        "routing/policies/review-grade.json, and the launcher (runtime/openrouter/launch) refuses a "
                        "profile that resolves it to anything else, so policy stays here and vendor plumbing stays in "
                        "routing/. " + SKILL)
        if iso != "":
            return deny("Review dispatch sets isolation. A review writes nothing, so isolation protects nothing, and "
                        "it hurts: worktree.baseRef is head, so a reviewer in a worktree cannot see uncommitted work. "
                        "Omit isolation, pass the repository path, and tell the agent the tree is read-only and it "
                        "runs no git writes. " + SKILL)
        pinned, file_model, routed_effort, file_effort = launch_pins(review=True)
        pin = alt(pinned.get("code-review"), "")
        if pin != "" and file_model != pin:
            return deny(f'Review dispatch under a fabric launch, but the agent file of the reviewer says model '
                        f'"{file_model}" while this launch resolves code-review to "{pin}". Either another launch of '
                        "this account (the other provider) has rewritten ~/.claude/agents/code-review.md since this "
                        "session started, or the fabric checkout moved under this session and now routes the review "
                        "class to a different model; either way a reviewer would run on a model nothing chose for "
                        "this session. Re-run agent-fabric/bin/fabric-model apply from this session, or relaunch. "
                        + SKILL)
        if "code-review" in file_effort and alt(routed_effort.get("code-review"), "") != file_effort["code-review"]:
            return deny(f'Review dispatch under a fabric launch, but the agent file of the reviewer says effort '
                        f'"{file_effort["code-review"]}" while this launch resolves code-review to '
                        f'"{alt(routed_effort.get("code-review"), "none")}". Either another launch of this account has '
                        "rewritten it since this session started, or the fabric checkout moved under this session and "
                        "now routes the review class differently. Re-run agent-fabric/bin/fabric-model apply from "
                        "this session, or relaunch. " + SKILL)
        if pin != "":
            # The rules held; under a fabric launch the reviewer file carries the pin.
            return decision("allow", "Review dispatch under a fabric launch: model fable checked, then removed so "
                            f"the reviewer runs on its pinned model {pin} (the agent file, from routing) while fable "
                            "itself stays the tier of code-plan.",
                            updatedInput={k: v for k, v in t.items() if k != "model"})
        return None
    if kind == "locale-worker":
        # Before the review-description branch: reviewing a text in the locale
        # is the job of the worker itself, and its description is in the locale;
        # a description that begins with review names no reviewer class here.
        if not model:
            return deny("locale-worker dispatch has no model set. The worker reads nothing, but its tier is still a "
                        "choice, and unset means the session model by accident. Set model explicitly (opus is the "
                        "design: language judgement is premium work). " + ADR027)
        if iso != "":
            return deny("locale-worker dispatch sets isolation. The worker writes nothing anywhere — its one tool "
                        "reads and writes no file — so isolation protects nothing; omit it. " + ADR027)
        return None
    if review_desc:
        return deny(f'Description begins with review but subagent_type is "{kind}". A code review is the code-review '
                    "class (fable, no isolation, no session context) -- not a general agent on a cheaper tier. If this "
                    "is not a code review, re-word the description (Audit ..., Check ..., Inspect ...). " + SKILL)
    if CODING_CLASS.search(kind):
        alias = alt(aliases().get(kind), "")
        if alias == "":
            return deny(f'Dispatch names the class "{kind}" but runtime/claude-code/aliases.json binds no alias to it '
                        "(file missing, unreadable, or the class is not in it). The class decides the tier and this "
                        "guard cannot tell which; nothing is inferred. Fix the binding, or set model to the alias the "
                        "class is documented to ride. " + SKILL)
        if model != alias:
            return deny(f'Dispatch names the class "{kind}" with model "{shown_model}"; that class rides the {alias} '
                        "alias (runtime/claude-code/aliases.json), and the two must agree -- a class whose tier a call "
                        f"can override is a label, and {kind} on another tier is that work on a model nothing chose "
                        f"for it. Set model: {alias}, or name the class that rides the tier you mean. " + SKILL)
        if iso != "worktree":
            return deny(WORKTREE)
        _, _, routed_effort, file_effort = launch_pins(review=False)
        if kind in file_effort and alt(routed_effort.get(kind), "") != file_effort[kind]:
            return deny(f'Dispatch of "{kind}" under a fabric launch, but its agent file says effort '
                        f'"{file_effort[kind]}" while this launch resolves {kind} to '
                        f'"{alt(routed_effort.get(kind), "none")}". Either another launch of this account (the other '
                        f"provider) has rewritten ~/.claude/agents/{kind}.md since this session started, or the fabric "
                        f"checkout moved under this session and now routes {kind} differently; either way the agent "
                        "would think at a level nothing chose for this session. Re-run agent-fabric/bin/fabric-model "
                        "apply from this session, or relaunch. " + SKILL)
        if kind in ("code-high", "code-plan"):
            return ask(f"Agent dispatch names {kind}, a premium class ({alias}). Per the subagent-dispatch skill, the "
                       "premium tier is for a subagent only when you explicitly asked for it -- the task looking hard "
                       "is not authorisation. Approve only if you did.")
        return None
    if READ_ONLY.search(kind):
        if not model:
            return deny(NO_MODEL)
        if iso == "worktree":
            return deny(f"Read-only dispatch ({kind}) sets isolation worktree. That type has no writing tool and its "
                        "Bash is fenced in the clone (subagent-clone-guard.sh); a worktree protects nothing and hides "
                        "the uncommitted work it is asked about (worktree.baseRef is head). Omit isolation. " + SKILL)
        if PREMIUM.search(model):
            return ask(f'Agent dispatch requests the premium model "{alt(raw_model, "")}" for a read-only {kind}. Per '
                       "the subagent-dispatch skill, opus/fable are forbidden for subagents unless you explicitly "
                       "asked for that tier. Approve only if you did.")
        return None
    if not model:
        return deny(NO_MODEL)
    if iso != "worktree":
        return deny(WORKTREE)
    if PREMIUM.search(model):
        return ask(f'Agent dispatch requests the premium model "{alt(raw_model, "")}". Per the subagent-dispatch '
                   "skill, opus/fable are forbidden for subagents unless you explicitly asked for that tier. Approve "
                   "only if you did.")
    return None


NO_MODEL = ("Agent dispatch has no model set. Omitting it is not a neutral default - the subagent INHERITS the session "
            "model, so a premium session silently spawns premium agents. Set model explicitly: haiku for mechanical "
            "work (extraction, pattern-following edits, structured search), sonnet for judgement work (multi-file "
            "reasoning, convention-holding prose). " + SKILL)
WORKTREE = ("Agent dispatch does not set isolation to worktree. Every writing subagent works in its own worktree, "
            "never the session clone: the dispatcher opens and closes it, the agent stays in the path it is given, "
            "runs no git, and never commits. A premium-model authorisation grants a model tier, not an isolation "
            "exemption. Forks and the review class are the only carve-outs. " + SKILL)


def main() -> int:
    # A permission gate that cannot run must not vanish into an allow: the
    # harness reads a failed hook as no objection. Whatever stops the rules
    # — a call that is not JSON, a field of the wrong type, a fault in here
    # — is a question to the person at the keyboard, with the reason.
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        try:
            if not raw.strip():
                raise Malformed("the call is empty")
            call = json.loads(raw)
        except ValueError:
            raise Malformed("the call is not JSON") from None
        out = decide(call)
        # UTF-8 bytes, whatever the locale: print() would encode the
        # reasons' dashes in a non-UTF-8 locale and raise, turning a deny
        # into the shim's ask (review of #72).
        if out is not None:
            sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
    except Malformed as e:
        write_ask(CANNOT_RUN.format(why=str(e)))
    except Exception as e:  # noqa: BLE001 — a guard's own fault must ask, never allow
        write_ask(CANNOT_RUN.format(why=f"{type(e).__name__} in the guard"))
    return 0


def write_ask(reason: str) -> None:
    sys.stdout.buffer.write(json.dumps(ask(reason), separators=(",", ":")).encode() + b"\n")


if __name__ == "__main__":
    sys.exit(main())
