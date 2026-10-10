# ADR-027 — Language-and-culture specialists shape the work, not only translate it; the bridge

**Date:** 2026-09-17
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the `language-culture` role (identities/roles/language-culture/charter.md, brief.md, and each locale under identities/roles/language-culture/locale/); the locale worker (locale/<suffix>/worker.md, runtime/claude-code/install-agent-files.sh, runtime/claude-code/hooks/agent-dispatch-guard.sh); the prompt in the locale (tools/fabric/launch_prompt.py, runtime/openrouter/launch, runtime/claude-code/harness/); the locale search (tools/fabric/websearch_locale.py, runtime/mcp/websearch-locale/install.py); the measurement (tools/fabric/control/ops/activity.py `script`); the memory rendering (tools/fabric/harvest_memory.py); the translation checks in tools/fabric/lint.py and bin/fabric-locale
**Pillar:** P4
**Evidence:** docs/live-checks/2026-09-17-language-culture-bridge.md, docs/live-checks/2026-09-18-language-culture-prompt-replacement.md

## 1. Context and Problem

The role that became `language-culture` began on 2026-08-10 as
`product-i18n`: the product's dictionaries and nothing else. A role that
only translates what others have finished meets a text at the end, when
its meaning is fixed and a market's expectations can no longer change
it; ADR-000's P4 asks for the opposite — a specialist who can say that a
solution does not suit the people it is for. On 2026-09-17 the role was
widened to language, translation, localization and local culture, and
renamed.

Its holder must reason in the language it answers for, because a
translation judged in English is judged wrong: read after its source, a
text shows every error that is present and none of what a native writer
would have written and did not. Two days of asking a holder to reason in
the locale showed the harness cannot see whether it happens — thinking
blocks are stored empty or as short summaries (one session with a
hundred thousand thinking tokens had none on disk). The only artifact
was what the holder writes by rule, and the first holder found its own
disposition had not survived one session. A rule with no artifact is a
wish; a disposition with no construction behind it is not a rule.

## 2. Decision

**The language-and-culture role shapes the work.** Its remit is the
words and the guarantees wherever a project publishes in a language, and
what a market's culture makes different wherever a product is deployed —
forms of address, names, calendars, units, imagery, how a public service
is expected to speak — stated so the surface's owner can decide. It says
when a language cannot carry a meaning as written, reads a text in its
locale before it reads the source, and hands a finding in another role's
surface to that role with the correction as the artifact. It does not
own the surfaces; it owns whether their words are right for their reader.

**Reasoning in the locale is a construction, not a disposition.** The
fabric installs it, measures it and drains through it:

- **One role, a holder per locale.** A holder's login is named for its
  locale (`language-culture-ge`, `language-culture-ru`); the locale is a
  directory, `identities/roles/language-culture/locale/<suffix>/`, whose
  `locale.json` names the BCP-47 tag (`ge` is `ka-GE`, Georgian).
- **The bridge and the worker.** On a holder's login, and no other,
  `install-agent-files.sh` installs a subagent, `locale-worker`, whose
  system prompt is written in the locale and which has one tool that
  reads and writes nothing. The holder is its bridge: it translates each
  request into the locale, dispatches the worker with the locale text
  alone, and renders the worker's answer — the same text, never a second
  composition. The worker composes; the bridge carries.
- **The prompt in the locale.** Every piece of the holder's launch prompt
  — the identity header, the charter, the brief, the shared sections and
  the harness's own text — may carry a translation in the locale
  directory, rendered for the login of that suffix. With the harness text
  translated the whole system prompt is replaced (the mechanics are
  ADR-002's exception); without it the fabric's part is appended as for
  every other login.
- **Search in the locale.** The holder searches as a reader of its locale
  would, through an MCP server configured from `locale.json`, and the
  harness's own US-only `WebSearch` is removed from its session.
- **Measured.** The holder's notes, its visible text and the worker's
  input and answers are counted by script on the account
  (`fabric-ctl <login> script`); a Latin paragraph in the worker's input
  is the bridge leaking.
- **Memory in the locale.** The holder's memory is written in the locale;
  a memory meant for the fleet carries its own rendering, which the drain
  takes as the claim.
- **The source locale.** A holder of the fleet's own language, English
  (`en-US`), translates nothing: its locale carries `locale.json` alone,
  no worker is installed, nothing is rendered, and its notes are not
  measured by script. It writes English for readers of English as a
  second language (A 2026-10-07).

What reaches the fleet — a message, a commit, a slice, a report — is the
English rendering. What the GZCoord tools print *around* a message on a
holder's login is in the holder's language; that decision, and the shape
of the dictionaries, is ADR-028.

## 3. Alternatives Considered

- **A translator at the end of the work.** The role as it was. Rejected:
  it cannot change what the text says or what the product does for a
  market, only how the finished thing reads.
- **Asking the holder to think in the locale.** Tried for two days.
  Rejected as the mechanism: it leaves no trace the harness keeps, and it
  did not survive one session. It stays as the charter's rule, and the
  notes are its artifact; the bridge is what forces it.
- **A role per country.** Rejected: the culture knowledge is the role's,
  in one domain slice per culture that every holder reads; a request
  names the locale it is about.
- **A worker with no tools.** Not possible on this harness: read back
  (`docs/live-checks/2026-09-17-language-culture-bridge.md`), an empty
  `tools:` line inherits every tool, and a list that
  resolves to none is refused at spawn. One inert tool (`TaskStop`) is
  the nearest to none.
- **Prepending the charter to the harness's English.** The harness has no
  prepend; `--system-prompt-file` replaces the default text, so "the
  charter before the harness text" is one file the fabric assembles in
  that order.
- **Google's own search API for the locale.** Closed to new customers,
  and a plain fetch of Google's results page answers an
  empty JavaScript shell. A results proxy (SerpAPI) reaches Google's
  index; Brave is kept as a second index. Brave alone has no Georgian
  locale (each parameter refused with HTTP 422), so for `ge` it runs as a
  global search steered by the query's language.

## 4. Rationale

A specialist can only shape work it meets while the work can still
change, and in the language its reader will meet it. Everything the
fabric controls around the holder — its prompt, its worker, its search,
its memory, its tools' lines — is moved into the locale, and what the
fabric does not control is named rather than hidden (§6). Measuring the
notes proves what a holder wrote, not what it reasoned in; the worker,
which never sees English, is the part that forces it, and its input is
counted so a leak is visible.

The costs are accepted for this role and stated: a second model call per
request, a prompt that must be re-translated whenever the harness text is
re-captured, and a holder who writes every answer twice.

## 5. Binding Rules

1. A holder of `language-culture` is a login named `language-culture-<suffix>`;
   its locale is `identities/roles/language-culture/locale/<suffix>/`, and
   the locale's BCP-47 tag is that directory's `locale.json` `tag` — never
   inferred from the suffix.
2. The role reports what a market's culture changes in a product so the
   surface's owner can decide, and says when a language cannot carry a
   meaning as written. A language finding in another role's surface is an
   `OBSERVATION` to that role with the correction as the artifact; the
   holder commits to a project's files only where that project's remit
   for the role binds it to them.
3. A review of a text in the locale runs in two passes: the target alone
   first, then against the source. Every finding names its pass
   (`first-pass` or `second-pass`); a first-pass finding withdrawn on the
   second pass is recorded as withdrawn, not deleted.
4. The holder translates every request into its locale before acting on
   it. Every answer is one text composed in the locale and its rendering:
   to a person at the terminal both, the locale first; to the fleet the
   English rendering only. The translated request and the original answer
   are kept in the holder's notes.
5. The notes are written in the locale, one file a day under
   `<fabric state>/agents/<login>/notes/YYYY-MM-DD.md`, never committed.
   `fabric-ctl <login> script` reports counts only — paragraphs by script,
   languages — and no text leaves the account. A holder with no notes is
   unmeasured, not clean.
6. The worker is `identities/roles/language-culture/locale/<suffix>/worker.md`:
   `name: locale-worker`, a one-line description in the locale carrying
   the `agent-fabric` marker, a model, and exactly `tools: TaskStop`
   (`tools/fabric/lint.py` holds the shape). `install-agent-files.sh`
   installs it as `~/.claude/agents/locale-worker.md` only on a login
   bound to `language-culture` whose suffix has a `worker.md`, and removes
   a copy carrying the marker from any other login. It carries no routed
   model pin and no routed effort: it is not a capability class.
7. The dispatch guard admits a `locale-worker` dispatch only with a model
   set — any alias, never asked — and with no isolation.
8. The bridge sends the worker text in the locale only, and renders the
   worker's answer without recomposing it. `fabric-ctl <login> script`
   counts the worker's input (less the harness's injected
   `<system-reminder>` spans) and answers per paragraph by script, and any
   tool use besides the hand-back.
9. A translation of a prompt piece is
   `identities/roles/<role>/locale/<suffix>/<piece>.md`, naming its source
   and the source body's digest, and `launch_prompt.py` renders it for the
   login whose name ends in `<suffix>`. When `locale/<suffix>/harness.md`
   exists on a `language-culture` login, the launcher passes the rendered
   prompt with `--system-prompt-file`; the absence of that file is the
   kill switch, and the absence of any other piece serves that piece's
   English.
10. Lint holds every translation to its source: every protected
    identifier (backticked span, path, slash command, flag, placeholder,
    fenced block and the rest `bin/fabric-locale tokens <source>` prints)
    appears the same number of times. A translation whose source digest
    no longer matches is a warning that names it, and is still served —
    a launch never fails on a lag. A localized launch prompt's character
    ceiling is `LOCALE_CHARS_FACTOR` (1.35) times the English one.
11. A locale's translations have no author but that locale's holder,
    through the carve-out of ADR-018 §5 rule 5. fabric-coordinator commits
    the English sources, the machinery and the tests, authors no
    translation, and merges the holder's pull request.
12. The holder's memory is written in the locale. A memory with a
    `roles_class` carries its rendering under `## English`, and a
    description in the locale carries `description_en` beside it; the
    harvester takes the rendering as the claim, records the language, and
    names a memory lacking either under `needs_rendering` in every drain
    report until its holder renders it; the coordinator sends those
    names to the holder as a `REQUEST` and drains after the holder
    answers. Nothing renders a memory but its holder.
13. On a holder's login whose locale has a `locale.json`,
    `install-agent-files.sh` writes the `websearch-locale` MCP server into
    the user-scope configuration and a `WebSearch` deny into the user
    settings, and the launcher passes `--disallowedTools WebSearch`; on
    every other login it removes both. The deny is marked as the
    fabric's and never touches one the login wrote itself. `web_search` tries SerpAPI, located
    by the locale file, then falls through to Brave on any refusal; its
    last line names the engine that answered by the locale file's label,
    and why it fell back. `web_search_global` is Brave. Tool descriptions
    are in the locale and name no vendor. Secrets are read at call time
    and never appear in a log line or a result; SerpAPI's key travels
    only as its `api_key` query parameter, built per call, the one request
    whose URL carries a secret. The keys' fingerprints show in
    `fabric-ctl <login> keys`. The worker has no search.

## 6. Consequences

- **What stays English, named.** In the worker: the harness's base
  prompt and its hand-back reminder. In the holder's session under the
  replaced prompt, as its first session read it back: the project layer from the
  session-start hook (the remit `.agent-fabric/roles/<role>.md` and the
  `INDEX.md` pointer), the `CLAUDE.md` files, the harness's Environment
  block and attribution reminder, the tool, agent and skill listings and
  MCP instructions — except `locale-worker` and the search tools, whose
  descriptions are in the locale — and the messages the inbox carries,
  which are the wire. Of these only the remit is the role's own prompt
  layer with no locale copy.
- **Tokens, measured.** One-turn calls as the `ge` holder
  (`docs/live-checks/2026-09-18-language-culture-prompt-replacement.md`):
  the default English prompt 26 180 input tokens; the older flow (English
  harness text, Georgian charter appended) 38 438; the whole prompt
  replaced in Georgian 31 935. The earlier per-body estimate (a
  Georgian body 2.9× its English tokens) overstated the total, because
  the harness's own additions dominate both flows.
- **The harness text is a moving source.** It changes with the CLI build;
  the capture in `runtime/claude-code/harness/en.md` is a live-check duty
  (ADR-008), and every re-capture is a re-translation by each holder. The
  launcher stamps the running build beside the capture's so a drift is
  visible; it is never a gate.
- **A lag is a warning.** When an English source moves, its translations
  lag until their holders re-render; lint names each and still passes,
  because the source has to land before a holder can translate it.
- **Two locales exist**, `ge` and `ru`; a third is a
  `locale/<suffix>/` directory drafted from the English sources and owned
  by its holder from the first session.
- **SerpAPI's free plan** is 250 searches a month; past it, `web_search`
  answers from Brave and says so.

## 7. Future Evolution

- Whether the project remit (`.agent-fabric/roles/language-culture.md`)
  gets a locale copy is the owner's call, not yet made.
- P4's direction — the specialist shaping the experience rather than
  reviewing it — has no mechanism beyond the charter's remit and the
  findings it hands to surface owners. Where the role is brought in
  before a surface is built, and how that is recorded, is open.
- A live read-back of an interactive relaunch under the replaced prompt
  — the worker dispatched, a skill invoked, the `script` op after it —
  was asked of the holder and is not recorded.

## 8. Decision Status

Accepted. The widened role, the bridge, the worker, the locale search and
the whole prompt in the locale are in use.

## References

- `identities/roles/language-culture/charter.md`, `brief.md`,
  `locale/ge/`, `locale/ru/` (each: the translated pieces, `harness.md`,
  `worker.md`, `locale.json`).
- `runtime/claude-code/install-agent-files.sh`,
  `runtime/claude-code/hooks/agent-dispatch-guard.sh`,
  `policies/subagent-dispatch/SKILL.md` §"The locale worker".
- `tools/fabric/launch_prompt.py` (`LOCALE_CHARS_FACTOR`, `render_harness`),
  `runtime/openrouter/launch` ("THE PROMPT IN THE LOCALE", the
  `--disallowedTools WebSearch` line), `runtime/claude-code/harness/`.
- `tools/fabric/lint.py` (`locale_translation_findings`,
  `locale_worker_findings`, `locale_file_findings`), `bin/fabric-locale`.
- `tools/fabric/websearch_locale.py` and `bin/fabric-websearch-locale` (the
  server), `runtime/mcp/websearch-locale/install.py` (its registration).
- `tools/fabric/control/ops/activity.py` (`script`, `worker_transcripts`),
  `tools/fabric/control/ctl.py`; `tools/fabric/harvest_memory.py`
  (`needs_rendering`).
- `policies/AUTHORITY.md` §"The one carve-out", `policies/githooks/locale-carve-out.sh`.
- ADR-000 (P4), ADR-002 (the launch prompt and its locale exception),
  ADR-008 (the harness capture), ADR-013 (the drain), ADR-018 (the
  carve-out).
- The live checks in Evidence.

## Amendments

The body above reads current; each change's full note is in [history/ADR-027-amendments.md](history/ADR-027-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-07 | The source locale has no bridge | §2: an en-US holder's locale carries locale.json alone; no worker, no rendering, notes unmeasured; global English |
