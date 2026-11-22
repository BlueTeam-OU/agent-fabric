# Live check 2026-09-16 — OpenRouter presets through the API; the shim tool

Host `develop-qzapp`, agent `user`, role `fabric-coordinator`, the
account's own `OPENROUTER_API_KEY` from the environment. What was read
back before `tools/fabric/shim.py` was written, and what the tool then
did against the live account.

## 1. What a preset is, on the wire

`GET /api/v1/presets` lists the account's presets: `id`, `name`, `slug`,
`status` (`active` | `disabled`), `designated_version_id`, timestamps. Six
on this account: the two shims (`glm2claude-shim` v3, `deepseek2claude-
shim` v8) and four disabled experiments from 2026-09-13 (`code-low`,
`code-medium`, `code-high`, `code-strategic`).

`GET /api/v1/presets/{slug}` returns the preset with its
`designated_version` inline: `{version, system_prompt, config}`. The
config is what the dashboard's routing pane sets: `glm2claude-shim` v3
carries `{"provider": {"sort": {"by": "price"}, "allow_fallbacks":
true}}` (v1 and v2 carried `{}`); `deepseek2claude-shim` v8 carries
`{"provider": {"only": ["ionstream"], "order": ["ionstream"], "sort":
null, "allow_fallbacks": false}}`. Neither names a model: the composite
`<model>@preset/<slug>` supplies it, which is what makes one shim serve
a family.

`GET /api/v1/presets/{slug}/versions` lists every version, oldest first;
`…/versions/N` one of them (N the integer; the version's UUID is
refused with "Version must be a positive integer", and a preset is
addressed by slug only — its UUID gets "Preset not found").

## 2. Creating one

The OpenAPI spec (`https://openrouter.ai/openapi.json`) declares `POST
/api/v1/presets/{slug}/messages` (and `/chat/completions`, `/responses`
siblings): "Creates a preset (or a new version of an existing one) from
an inference request body. Only fields that overlap with the preset
config are persisted; other fields (e.g. `messages`, `stream`, `prompt`)
are silently ignored." So a messages-shaped body whose `system` is the
delta and whose `provider` is the routing becomes a version. There is no
documented update, rename or delete: a slug is created if absent, and a
`name` in the body is ignored (the name is the slug); `DELETE
/presets/{slug}` is 404. Retiring one is the dashboard's *disable*.

Exercised on a throwaway slug `zz-fabric-apitest`: the first push
created it (`status active`, version 1), the second added version 2
with the changed text as the designated version, and `shim.py diff`
read both back byte-identical to the sources. The slug stays on the
account, disabled by hand.

## 3. The check

`shim.py check z-ai/glm-5.3-flash --shim glm2claude-shim --quick` ran the
two-step task headless through `ori claude --model <composite>` with
`--output-format stream-json`, then read every generation back from
`/api/v1/generation?id=`: 3 turns, 2 reads, the answer with its
`CHECK-COMPLETE` line, no harness markup in assistant text — PASS;
served by GMICloud (first run) and StreamLake (second, through the test
preset with the same `sort: price` routing), $0.007 and $0.004 on the
bill against the harness's notional $0.14–0.17. Two things the first run
taught the judge: the stream emits one `assistant` event per content
block, so a turn's `requestId` repeats and counts once; and the newest
generation is indexed a few seconds after the response — a 404 on
`/generation` is retried, then reported as "not indexed yet", never as
a failure.

## What this decides

- A shim's source lives in git: `routing/shims/<slug>/system_prompt.md`
  and `config.json`; both existing shims were pulled in, byte-identical
  to their live designated versions. `tools/fabric/routing.py check`
  fails a `shims.json` entry with no source.
- The next shim is `shim.py push <slug>` from those files, `shim.py check
  <model> --shim <slug>` (the six-step task of the DeepSeek admission by
  default; `--quick` for the two-step one), its report in
  `docs/live-checks/`, then the `shims.json` family entry by hand — the
  note there is the admission record — and admission to a class stays
  architect-cto's under `routing/policies/review-grade.json`.
- A preset's `config` carries parameters beyond `provider`: version 3 of
  the throwaway slug was pushed with `temperature: 0.2`, `max_tokens:
  4096` and `top_p: 0.9` beside the routing, and `GET /presets/{slug}`
  returned all three in the designated version's `config`; `shim.py diff`
  read them back byte-identical to the source. So a shim's
  `config.json` may pin sampling as well as routing, and `push` sends
  every key it holds.
