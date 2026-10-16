# The privacy notice at blueteam.ee/privacy.html

Opinion of `legal-expert-ee-eu`, 2026-10-15; section 6 revised
2026-10-16, before the merge, to record the owner's decision on it (the
#278 review). Not the advice of an attorney admitted to the bar. The redraft this opinion leads to is
`2026-10-15-privacy-notice-blueteam-ee-draft.md`.

## 1. Question

The owner asked whether the privacy notice published at
<https://blueteam.ee/privacy.html> ("Updated 22nd June 2026") meets the
law, and later asked for a clear account of the problem with running
client work on an Anthropic Max plan.

## 2. Facts assumed

Read from the page itself (downloaded 2026-10-15, with its three
scripts):

- The controller is BlueTeam OÜ, registry code 14454093, Narva mnt 5,
  10117 Tallinn; contact `info@blueteam.ee` (written into the page by a
  script).
- The page sets no cookie, loads nothing from another host, and its
  own scripts write no cookie. One `localStorage` call exists inside the
  bundled vendor library and was not seen in use. Only this page was
  checked, not the rest of the site.

Stated by the owner on 2026-10-15, not verified against contracts:

| Provider | What for | Where | GDPR role |
|---|---|---|---|
| Proton AG | email | Switzerland | processor |
| 1984 ehf | website hosting | Iceland (EEA) | processor |
| Smart Accounts OÜ (reg. 12041731) | accounting software | Estonia | processor |
| Wisor Accounts OÜ | accountant, payroll, VAT | Estonia | processor (bookkeeping); probably an independent controller for its own anti-money-laundering checks (*unverified*) |
| Holvi Payment Services Oy | payments | Finland (EEA) | independent controller (*unverified*) |
| OpenAI, business account | AI tools | Ireland contracting entity; US abuse-monitoring copies | processor under a data processing agreement (*unverified*, secondary sources) |
| Anthropic, Max plan, training setting off | AI tools | Anthropic Ireland as controller; US group | **independent controller, no processing agreement** |

- Most clients are in Switzerland and are not projects of the agent
  fleet. One client, Gzapi, is in Georgia and is a fleet project
  (`projects/clients.json`, `projects/registry.json`).
- BlueTeam has no Italian clients.

Not known: whether the fleet's broker route (DeepSeek, GLM;
agent-fabric ADR-005) or GitHub carries any client's personal data;
the log retention configured at the host; whether processing agreements
with Proton, 1984, Smart Accounts and Wisor have been accepted.

## 3. The law

Read from the official text in this session:

- Regulation (EU) 2016/679 (GDPR), OJ L 119, 4.5.2016, from the EU
  Publications Office: Articles 3(1), 6(1), 12(5), 13, 15(3), 21(4), 26,
  28(2), 28(4), 30(5), 33(1), 34(1), 44, 45(9). No amendment is in force: the Digital Omnibus
  proposal (procedure 2025/0360(COD)) had no Council position in October
  2026, per secondary sources.
- Commission Decision 2000/518/EC of 26 July 2000 (OJ L 215,
  25.8.2000), Article 1: Switzerland provides an adequate level of
  protection; kept in force by GDPR Article 45(9).
- Anthropic's Consumer Terms of Service (effective 8 October 2025) and
  Privacy Policy (effective 10 September 2026), from anthropic.com/legal,
  the pages themselves; the phrases quoted in section 4 are theirs.

*Unverified* in this session: the Accounting Act § 12 (seven-year
retention of source documents); the General Part of the Civil Code Act
§ 146 (limitation periods); CJEU C-210/16 *Wirtschaftsakademie*; the
WP29 position paper on Article 30(5) (2018); OpenAI's business terms and
data processing addendum; Anthropic's Commercial Terms of Service and
its data processing addendum (what section 4 says of the commercial
plans rests on them); the Swiss Federal Act on Data Protection
(outside this jurisdiction).

## 4. Reading

### The Anthropic Max plan

Anthropic sells two kinds of contract.

- **Commercial** (Team, Enterprise, the API; *unverified*, see section
  3): Anthropic processes what the customer sends on the customer's
  instructions. It is the
  customer's processor, under a data processing agreement, and does not
  train on the content.
- **Consumer** (Free, Pro, Max): Anthropic decides itself what it does
  with what the user sends, under its own privacy policy. For users in
  the EEA, the UK and Switzerland, that policy names "Anthropic Ireland,
  Limited" as the controller. There is no processing agreement for these
  plans. The policy also says that content processed "on behalf of
  customers of our business offerings" falls outside it, and Max is not
  one of those offerings.

Turning off the training setting narrows Anthropic's use but does not
end it. The policy keeps training use for conversations "flagged for
safety review" and for feedback the user sends explicitly, and it keeps
data "for as long as reasonably necessary".

That is the problem when **someone else's** personal data goes into
Max: a log with a client's customers in it, a client repository whose
commit history names its developers, a screenshot of a client's admin
screen. Then:

1. **As a processor for a client**, BlueTeam may hand the client's
   personal data only to a sub-processor the client has authorised in
   writing, bound by the same data protection obligations (Article
   28(2) and (4)). Anthropic on Max is neither: it is not bound to
   BlueTeam's instructions, and it uses the data for its own purposes.
   This holds for a client outside the EU too: GDPR binds BlueTeam as
   an EU processor (Article 3(1)), and Article 44 binds processors.
2. **As a controller** (BlueTeam's own contacts and correspondence),
   handing personal data to Anthropic needs a legal basis, and Anthropic
   has to be named in the notice as a recipient (Article 13(1)(e)).
3. **The promise in the current notice**, that personal data is never
   used "directly or indirectly" to train AI, cannot be guaranteed on
   Max, because of the safety and feedback exceptions.

What Max does **not** affect: work that carries no one's personal data,
such as writing new code, general questions, BlueTeam's own non-personal
documents. The same log in the OpenAI business account is covered by
OpenAI's processing agreement.

### The rest of the notice

1. **Recipients and transfers (Article 13(1)(e), (f)).** The notice names
   only accounting and legal services. Proton, 1984, Smart Accounts,
   Wisor, Holvi, OpenAI and Anthropic belong in it. Switzerland and
   Iceland are not a problem: Switzerland is covered by an adequacy
   decision, and Iceland is in the EEA. The sentence that data "as a
   standard practice" stays in the EEA or Switzerland is inaccurate for
   the AI providers.
2. **Two roles mixed.** Logs, screenshots and settings handled in client
   systems are processed on the client's behalf. That is the client's
   notice and the processing agreement with the client, not this notice
   as controller.
3. **The record of processing (Article 30(5)).** The exemption is lost
   when processing is "not occasional". Client records and contracts
   kept for the life of a business are not occasional. The published
   paragraph claiming the exemption should go, and the record should be
   kept.
4. **The website section contradicts itself.** It says nothing is
   collected from a visit, while the data list includes IP addresses and
   website activity, and the host keeps server logs.
5. **The right to object (Article 21(4))** must be presented "clearly and
   separately from any other information". It is one line in a list.
6. **Retention (Article 13(2)(a))** needs periods or criteria, not "it
   depends".
7. **Whether data must be provided (Article 13(2)(e))** is missing.
8. **LinkedIn.** A page operator is a joint controller with the platform
   for the page's visitor statistics (*Wirtschaftsakademie*,
   *unverified*); "at your own risk" does not discharge it. Article 26(2)
   asks that the essence of the arrangement be made available.
9. **Smaller points.** The breach section promises more than Articles
   33(1) and 34(1) require, and is not information Article 13 asks for. The
   contact person is not a data protection officer and should not read
   as one. "Privacy by default" is defined wrongly in the glossary.

## 5. Risk

The likely route to cost is a complaint to the supervisory authority,
or a client's own audit. Point 1 of the Max reading (client personal
data with no processing agreement) and finding 3 (the Article 30
exemption) are the ones that carry fines. The rest are cheap to fix
and unlikely to be pursued alone.

## 6. What to do

For the owner to decide; point 1 is decided.

1. **Client personal data and Max.** Decided: the owner chose (b),
   recorded as agent-fabric ADR-059 (2026-10-16). The fleet keeps the Max
   plan, and no personal data of a third party (clients, their people,
   visitors of Blueteam's sites) goes into it. ADR-059 governs the Max
   plan only: the OpenAI business account, with its processing
   agreement, is outside it, and client personal data goes there only as
   (a) describes, under a later record. The options as they were put:
   - (a) Run client work that touches personal data only on a plan
     with a processing agreement: the OpenAI business account, or an
     Anthropic commercial plan.
   - (b) Keep Max, and keep all third-party personal data out of it
     (cleaned logs, no client repositories with real commit history,
     no production access).
   - (c) Accept the risk. Not lawful for data processed for a client.

   Advised: (a) for client systems, (b) for everything else.
2. **Client contracts** carry a written authorisation of sub-processors,
   with the provider table attached (Article 28(2)).
3. **Processing agreements** with Proton, 1984, Smart Accounts and
   Wisor: confirm they are accepted, and keep copies.
4. **Adopt the redraft**, which is written on ADR-059, once the bracketed
   facts in it are filled in. It is true only while ADR-059's rules 1
   and 2 are kept.

Needs an attorney: the Swiss law questions (FADP, the clients' Swiss
contracts), for which a Swiss data protection attorney is the
instrument; and a client processing agreement template, if clients will
sign it as drafted.
