# The four EU AI Act claims on blueteam.ee/disclaimer

Opinion of `legal-expert-ee-eu`, 2026-11-09. Not the advice of an
attorney admitted to the bar.

## 1. Question

architect-cto asked on 2026-11-09 (REQUEST 01a1c232) for a lawyer's read
of the four EU AI Act claims in `BlueTeam-OU/blueteam.brand`
`brand/claims.md`, rows 33–36, each marked "confirmed; text to be read
by a lawyer before publication". The claims are already published in the
"Use of Artificial Intelligence (EU AI Act)" section of blueteam.ee's
disclaimer. For each claim: is the published sentence accurate under
Regulation (EU) 2024/1689 as it applies today and at its next
application dates, and if it is not, what is the corrected sentence.

Answered for 2026-11-09, and for the dates still to come: 2 December
2026, 2 December 2027 and 2 August 2028.

## 2. Facts assumed

Read in this session:

- The ledger: `brand/claims.md` at `f2ac7429` (2026-10-30), rows 33–36.
- The page: `src/pages/disclaimer.astro` in `BlueTeam-OU/blueteam.ee` at
  `d0b84eed` (2026-10-30), lines 47–52. The same text is live at
  <https://blueteam.ee/disclaimer.html> (fetched 2026-11-09).
- The "independent review" in claim 2 is the fabric's review class: an
  AI model dispatched as `code-review`, not a person (agent-fabric
  ADR-020; `CLAUDE.md`, Subagents). Row 38 of the ledger says a person
  decides only below a size each repository sets.
- `BlueTeam-OU/agent-fabric`, the agent framework BlueTeam builds on
  other providers' models and runs for its own work and its clients'
  work, is a public repository under Apache-2.0 (`gh repo view`,
  2026-11-09; `AGENTS.md`, Licence).
- The agents have no channel to the client; the consultant does (ledger
  row 39, architect-cto).

Supplied by the owner (ledger, 2026-10-15), not verified:

- BlueTeam builds no system for an Article 5 practice and no Annex III
  system, and tells clients when AI is used in their engagement.

**Missing, and decisive for claim 3:** whether BlueTeam ever develops,
for a client, a system that falls in Annex III. Claim 3 says "we do not
build" one, but its next sentence describes BlueTeam working on a
client's high-risk system. Only the owner can say which is true. The
correction in section 4 holds either way.

## 3. The law

All of these were read from the official text in this session, through the
EU Publications Office (CELLAR), in English unless marked otherwise:

- **Regulation (EU) 2024/1689** (Artificial Intelligence Act), OJ L,
  2024/1689, 12.7.2024, CELEX 32024R1689.
- **Regulation (EU) 2026/1744** of 8 July 2026 (Digital Omnibus on AI),
  OJ L, 2026/1744, 24.7.2026, CELEX 32026R1744. Article 4 of the
  Omnibus: in force on the third day after publication, 27 July 2026.
- The consolidated text **02024R1689-20260727**, in English and
  Estonian. It is documentation, not the authentic text. Every
  provision cited below was checked against the OJ texts above.

Provisions relied on, in the version in force on 2026-11-09:

- Art. 2(1)(a)–(b) (scope: providers who place on the market or put
  into service, and deployers established in the Union); Art. 2(12)
  (free and open-source exclusion, which does not cover Article 5 or
  Article 50).
- Art. 3(3) "provider", 3(4) "deployer", 3(9) "placing on the market",
  3(11) "putting into service", 3(63) "general-purpose AI model",
  3(66) "general-purpose AI system", 3(68) "downstream provider". None of
  these was amended by the Omnibus. In the Estonian version: *pakkuja*,
  *juurutaja*, *turule laskmine*, *kasutusele võtmine*, *järgmise etapi
  pakkuja*. The Estonian text agrees on the two points this opinion
  turns on: a *juurutaja* is a person "kes kasutab
  tehisintellektisüsteemi" (who uses an AI **system**), and putting into
  service includes supply "oma tarbeks" (for own use).
- Art. 4 (AI literacy) as replaced by the Omnibus, from 27 July 2026.
- Art. 5(1) (prohibited practices), applying since 2 February 2025.
  Points (ba) and (bb) and paragraphs 1a and 1b were inserted by the
  Omnibus (non-consensual intimate imagery and child sexual abuse
  material) and apply from **2 December 2026**.
- Art. 6(1)–(3) and Annex III (high-risk classification).
- Art. 25(1), (2) and (4) (responsibilities along the value chain; (2) and
  (4) as amended by the Omnibus); Art. 26(2) (human oversight by
  deployers of high-risk systems); Art. 14 (human oversight as a design
  requirement for high-risk systems).
- Art. 50(1), (2), (4), (5). The Omnibus left these unchanged and
  replaced only paragraph 7.
- Art. 111(4), inserted by the Omnibus: providers of systems
  generating synthetic content that were "placed on the market before 2
  August 2026" must comply with Article 50(2) by **2 December 2026**.
- Art. 99(4)(g), (6) (fines for Article 50 breaches; for SMEs, the lower
  of the two caps).
- Art. 113 as amended by the Omnibus. Chapters I and II apply from 2
  February 2025, except the new Article 5 points, which apply from 2
  December 2026. The general date is 2 August 2026, which covers Article
  50. Chapter III Sections 1–3, the high-risk rules including Articles 25
  and 26, apply from **2 December 2027** for Annex III systems and **2
  August 2028** for Annex I systems.

*Unverified*: whether Estonia has enacted its penalty rules and named
its market surveillance authority (Articles 70 and 99(1)). Riigi Teataja
could not be read in this session. The Commission's guidelines and the
code of practice on marking under Article 50(7) were not read either.
Nothing below rests on them.

## 4. Reading, claim by claim

### Claim 1 (row 33): "deployer of general-purpose AI models; no AI model or AI system of our own on the market"

Published: *"BlueTeam OÜ uses general-purpose AI models to deliver its
services, as a **deployer** … We do not place an AI model or an AI
system of our own on the market."*

**Not accurate as worded.** There are two problems.

1. **A deployer uses an AI *system*, not a model** (Art. 3(4); in
   Estonian, *juurutaja* "kasutab tehisintellektisüsteemi"). A
   general-purpose AI model is a component (Art. 3(63)). What BlueTeam
   uses as a deployer is the AI systems built on those models: the
   providers' chat and coding tools, and the API services. This point is
   settled by the definition.
2. **"No AI system of our own" overstates it.** BlueTeam develops its
   own agent framework on other providers' models and uses it in its own
   work. A provider includes one who develops an AI system and "puts
   the AI system into service under its own name" (Art. 3(3)). Putting
   into service includes supply "for own use" (Art. 3(11)). A system
   that integrates another entity's model makes its provider a
   "downstream provider" (Art. 3(68)). Two questions are **argued, not
   settled**:
   - Is the fabric an "AI system" in its own right, or BlueTeam's
     configured use of the providers' systems?
   - Does publishing the repository under Apache-2.0 place it on the
     market? If it does, Art. 2(12) excludes it, but not from Article 5
     or Article 50.

   No court or Commission text read in this session decides either
   question. The sentence "we do not place … an AI system of our own *on
   the market*" may be literally true, because own use is putting into
   service and not placing on the market. But a reader takes it to mean
   "we are only a deployer", and that is the conclusion in doubt.

What *is* true and sourced: BlueTeam places no general-purpose AI model
on the market. It is a deployer of the providers' systems. It places on
the market and puts into service no high-risk system of its own.

**Corrected sentence:**

> BlueTeam OÜ delivers its services using AI systems built on
> general-purpose AI models from other providers, and is a
> **deployer** of those systems within the meaning of Regulation (EU)
> 2024/1689 (Artificial Intelligence Act). **We do not place a
> general-purpose AI model on the market, and we do not place on the
> market or put into service a high-risk AI system of our own.**

### Claim 2 (row 34): "Human oversight. Every deliverable produced with AI goes through an independent review, and a consultant is responsible for it"

**The sentence is accurate. Its heading is not.** "Human oversight" is
the Act's term of art for a high-risk system: a design requirement on
its provider (Art. 14) and natural persons assigned by its deployer
(Art. 26(2)). Neither applies to BlueTeam's tools, which are not
high-risk. And the "independent review" the sentence describes is done
by an AI review agent, not a person (ADR-020; ledger row 38). Under
that heading the paragraph tells a reader that a human reviews every
deliverable, which is not what the owner confirmed (row 34 was reworded
for exactly this reason). The Act does not require the review at all;
the sentence describes a voluntary practice, and accurately.

**Corrected:** keep the sentence and change the heading.

> **Review and responsibility.** Every deliverable produced with AI goes
> through an independent review, and a BlueTeam OÜ consultant is
> responsible for it.

Whether to say that the reviewer is itself an AI model is a product and
brand decision, not one the law requires. If it is said, architect-cto
confirms the fact.

### Claim 3 (row 35): "no Art. 5 practice; no Annex III system; the client remains the provider"

Published: *"We do not develop or deploy AI systems for any practice
prohibited by Article 5 of the Act, and we do not build the high-risk AI
systems listed in its Annex III. Where a client's own system falls into
a high-risk category, the client remains its provider, and our role is
limited to supporting the client in meeting its obligations."*

- **Article 5: accurate.** It is a statement of conduct, and Article
  5 reaches placing on the market, putting into service and use alike.
  The list widens on 2 December 2026 (points (ba), (bb)), and the
  sentence covers the new points without change.
- **Annex III: accurate if the owner's fact holds**, but it conflicts with
  the next sentence (section 2, missing fact). It also covers only one
  route to high-risk: Annex I (Art. 6(1)) is not mentioned. That is a
  narrower claim, not a false one.
- **"The client remains its provider": not accurate as an unconditional
  statement.** The client is the provider of a system it has developed and
  places on the market or puts into service "under its own name or
  trademark" (Art. 3(3)). BlueTeam becomes a provider if the system goes
  out under BlueTeam's name, and so does anyone who rebrands it, makes a
  substantial modification to it, or changes its purpose so that it
  becomes high-risk (Art. 25(1)). That is law, not something a website
  allocates.
- **"Our role is limited to supporting": not something BlueTeam can say
  unilaterally.** From 2 December 2027, a third party that supplies an
  AI system, model, tool, service or component integrated in a
  high-risk system must agree in writing with the provider on the
  information, access and assistance it gives (Art. 25(4), as amended).
  The role follows from that contract and from Art. 25(1), not from
  this page.

**Corrected sentence:**

> **Scope.** We do not develop or use AI systems for any practice
> prohibited by Article 5 of the Act, and we do not place on the market
> or put into service, under our own name, a high-risk AI system listed
> in its Annex III. Where we work on a client's system that is
> high-risk, the client is its provider as long as the system is placed
> on the market or put into service under the client's name, and we
> give the client the information and assistance agreed in writing for
> it to meet its obligations.

If the owner confirms that BlueTeam does no development work on Annex
III systems even for clients, the first sentence can say so ("…and we
do not develop high-risk AI systems listed in its Annex III, for
ourselves or for clients"). The second sentence then describes
integration or advisory work only.

### Claim 4 (row 36): "clients told when AI is used; content marked where Art. 50 requires"

- **"We tell our clients when AI is used in their engagement": accurate**
  as a voluntary practice. The Act imposes no such duty towards a
  business client. Art. 50(1) concerns systems that interact directly
  with natural persons, and the agents have no channel to the client
  (row 39).
- **"We mark the AI-generated content we deliver where Article 50
  requires it": inaccurate in its terms.** Article 50 gives a
  *deployer* a duty to **disclose**, not to mark. The duty covers deep
  fakes (Art. 50(4), first subparagraph). It also covers text published
  to inform the public on matters of public interest, unless that text
  has had human review or editorial control and someone holds editorial
  responsibility (Art. 50(4), second subparagraph). Machine-readable
  **marking** is a *provider's* duty (Art. 50(2)).

The marking point leads to the one open question in this opinion with
money on it. **If BlueTeam is the provider of its agent framework**
(claim 1, point 2), Art. 50(2) may reach that framework's text output,
including code and documentation:

- The exception for an "assistive function for standard editing" does
  not cover generating a whole deliverable.
- Art. 50(2) has applied since 2 August 2026.
- The grace period in Art. 111(4) runs to 2 December 2026, but only for
  systems "placed on the market" before 2 August 2026. A system only put
  into service for own use is not named. If the repository's
  publication counts as placing it on the market, the grace period
  applies, and the framework must comply by 2 December 2026.
- Whether text output of this kind needs marking at all, and how, is
  what the Commission's code of practice and implementing acts under
  Art. 50(7) address. They were not read in this session.

This question has no settled answer.

**Corrected sentence:**

> **Transparency.** We tell our clients when AI is used in their
> engagement. Where Article 50 of the Act requires AI-generated or
> manipulated content to be disclosed, we disclose it.

This version promises what a deployer owes. It says nothing about
marking until the owner has settled the provider question below.

### The rest of the section

- The closing sentence ("This section describes how we work. It is not
  advice on your own obligations…") is right and stays.
- The link to `eli/reg/2024/1689/oj` points at the original OJ text,
  which is authentic. The Omnibus amends it, and does not change any
  sentence above apart from the dates this opinion uses.
- An obligation the page does not mention: as a deployer (and as a
  provider, if that is the answer), BlueTeam must take measures to
  support the AI literacy of its staff and of others who operate AI
  systems on its behalf (Art. 4, as replaced, from 27 July 2026). No
  claim is needed. This is for the owner to know, not for the page.

## 5. Risk

- **Misstatement on the page.** The likely cost is a client or a
  counterparty relying on the page: "human oversight", "the client
  remains the provider", "our role is limited". Those are the phrases a
  client would quote back in a dispute about who owed what. The
  likelihood is low while the client base is small. The cost is
  whatever the contract leaves open. Corrections 2 and 3 remove it.
- **Article 50(2), if BlueTeam is a provider.** The likelihood that a
  market surveillance authority acts against a small consultancy's
  internal tooling is low. The consequence is a fine of up to EUR 15
  million or 3 % of turnover, the lower of the two for an SME (Art.
  99(4)(g), (6)), under Estonian penalty rules this opinion did not read.
  The uncertainty sits in the law (no guidance read, no case law), not
  in the facts.
- **2 December 2026** is the next date that changes anything: the new
  Article 5 points, and the 50(2) grace period ending. **2 December
  2027** brings Article 25(4) into application for any client work on an
  Annex III system.

## 6. What to do

Conclusions are in section 4. These are recommendations, and the owner
decides.

1. **Replace the four sentences** with the corrected ones in section 4.
   They go to brand-comms as a REQUEST (claims.md rows 33–36 and the
   page), which places them; the legal content stays mine. The page is
   in English only, so no Estonian-locale review is needed unless an
   Estonian version is made.
2. **The owner decides the missing fact for claim 3**: does BlueTeam
   develop Annex III systems for clients, or not? The wording of the
   first sentence depends on it.
3. **The owner decides how to treat the framework**: as an AI system
   BlueTeam provides for its own use, or as configured use of the
   providers' systems. The options:
   - (a) Assume provider status and settle what Art. 50(2) requires of
     the framework's output before 2 December 2026. This is the safer
     course.
   - (b) Take the deployer-only reading and record why.
   - (c) Ask an admitted attorney.

   Because a fine is possible and no guidance was read, the question is
   worth (c) **before 2 December 2026** if the owner does not choose
   (a). The attorney's handoff: this opinion; the facts in section 2;
   the repository and how it is used for client work; and the question
   "is BlueTeam the provider of an AI system put into service for own
   use, and does Art. 50(2) reach code and documentation it generates".
4. **The page should not wait for 3.** The corrected sentences are true
   under either answer.
