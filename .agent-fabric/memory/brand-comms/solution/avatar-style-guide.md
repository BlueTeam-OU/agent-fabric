---
role: "brand-comms"
class: solution
topic: "avatar-style-guide"
description: "ADR-056 avatar generation — where the style guide is, the fixed prompt template, and what gpt-image-1 does with framing words"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - adfa55726d7aff89
---

## ADR-056 avatar generation — where the style guide is, the fixed prompt template, and what gpt-image-1 does with framing words

The avatar style guide (brand-comms's, committed by fabric-coordinator as identities/personas/avatar-style.md) was delivered 2026-10-13 by REPLY 01a135aa-4819-762d-a4e3-28cfc67cd381; the source was /usr/local/share/agent-fabric/avatars/avatar-style.md (sha256 40aedfbd…). Sample: avatars/01a0a6a1-…/2.png (AI Clara Merian), approved by the owner 2026-10-13, accepted by me; my hand commit 21f92fe was rolled back and the persona recommitted through settings-put as 15eb346 (2026-10-13, after #236 merged). The other agents (job j19) wait on fabric-coordinator's "start"; their draw list (agent id, login, first name, surname, sex) is REPLY 01a135ad-96ac-7ac4-8ba5-d2fd64cd6380, relay seq 148529 (`gzcoord-inbox --replay 148529`); skip db-admin until its first name arrives. The schema is identities/schemas/persona-profile.schema.json. Each agent commits its own persona; brand-comms only draws.

gpt-image-1 lessons from the sample: naming a "central circle" as framing makes the model paint a ring — name it only as a negative; without explicit maturity cues ("about 35, mature adult face, natural adult eye size, defined jaw") the anime style reads too young; it does not hold a headroom percentage (hair lands ~3% from the top), so the guide checks "hair never touches the top edge" instead. Cost: about 4160 output tokens per 1024 high draw, about $0.17 at $40/M (rate assumed, not checked).

Fleet draw 2026-10-13: 22 candidates in /usr/local/share/agent-fabric/avatars/<id>/, offered.tsv names the one offered, <n>.prompt.txt each prompt, <n>.txt each brand-comms rejection; 20 of 22 passed first time. Read as too young: a pixie cut on a woman (read as a teenage boy, twice) and a straight fringe with a round face; a chin-length bob and "slim face with defined cheekbones, fine smile lines" fixed both. Waiting on fabric-coordinator to say who offers them to the agents (REPLY 01a135bc-e716-7bcd-ad07-119a04d896cf).

Mouths: gpt-image-1 draws an anime smile line plus a lower-lip tone; on a long thin line it reads as two mouths (language-culture-ru rejected it, and "no separate lower lip" did not fix it). What worked: "the closed lips drawn as one small softly coloured shape with a gentle upturn; no line drawn across the mouth and no separate stroke below it". Judge mouths on a full-size crop, never on a contact sheet. On 2026-10-15 (legal-expert-ee-eu, job j22) that wording still gave a separate dash under the lip in two draws out of three. What finally worked on the third draw was naming the chin as well: "below the mouth the skin is plain and smooth down to a softly rounded, unmarked chin, with no dimple, no dash, no shadow stroke and no line of any kind". Expect up to three draws (about $0.50) for a woman's portrait until the guide's template carries that line. The guide's candidate check should gain "the mouth reads as one"; that is a guide change for the owner.

Related: [[avatar-appearance-follows-surname-culture]].

2026-10-16 (j23, legal-expert-ch and legal-expert-ge): six more draws with even stronger mouth/chin wording ("lips painted only as flat colour, no outline… between the lips and the chin only plain smooth skin… completely blank") still produced the dash under the lower lip in all six. Re-prompting does not fix it. What works and is cheaper: draw once or twice, take the best one, and paint out the dash with `~/work/avatars/retouch.py <in> <out> x0 y0 x1 y1`. The box goes under the lip and must not include lip pixels: the fill is the skin of the box's bottom row plus paper grain. Record the retouch and its box in `<n>.prompt.txt`, and check a full-size crop before and after.

2026-10-16 (j24): I described 3.png to ux-designer-01 from its prompt ("hazel eyes"), but the model drew brown and the agent noticed. Describe an offered candidate from the image, never from the prompt. Also: agents do not know that `settings-put` is a subcommand of `fabric-secrets store`. Give the full command and the profile.json fields in the offer itself.

*References: avatar-appearance-follows-surname-culture*

*Observed 2026-10-13 (brand-comms)*
