# The FADP behind the two [SWISS COUNSEL] marks in the blueteam.ee privacy redraft

Opinion by `legal-expert-ch` (Swiss law), 2026-11-09, answered for that
date. It serves `2026-10-15-privacy-notice-blueteam-ee-draft.md`, which
`legal-expert-ee-eu` holds. It answers only for Swiss law: the GDPR and
Estonian conclusions in that draft are `legal-expert-ee-eu`'s and are not
repeated or checked here. It is not the advice of an attorney admitted
in Switzerland, and section 6 says what still needs one.

## 1. Question

Asked by `architect-cto` (REQUEST 01a1c232, 2026-11-09), about the two
marks in the redraft on `origin/main` (5b831166):

1. **Section 9, the FDPIC sentence.** What may a notice say about the
   Swiss authority a person in Switzerland may turn to, and in what words?
2. **Section 10.** Does BlueTeam OÜ, a controller seated abroad, have to
   designate a representative in Switzerland? What does the Federal Act
   on Data Protection add to this notice?

For each: what the act and its ordinance require, the sentence the
notice should carry, and what is left for an attorney.

## 2. Facts assumed

Supplied, not verified by me:

- BlueTeam OÜ is a private limited company seated in Tallinn, Estonia
  (registry code 14454093). Source: the redraft, section 1.
- It has no seat, branch or residence in Switzerland. The redraft
  implies this but does not say it. **Unverified, and it controls the
  answer**: Art. 14 binds only a controller "mit Sitz oder Wohnsitz im
  Ausland".
- Most of its clients are in Switzerland. Source: the opinion of
  `legal-expert-ee-eu`, `2026-10-15-privacy-notice-blueteam-ee.md`
  section 2.
- As controller, it processes the categories in the redraft's section 2:
  - contact and client data of business contacts;
  - invoices and payments;
  - web server logs.

  It uses no cookies or tracking, makes no automated decisions and does
  no profiling (redraft sections 2 and 5). Its recipients and their
  countries are those in the redraft's section 4.
- In client systems it acts on the client's behalf (redraft, section 2,
  "Work in your systems"). That is the client's processing as
  controller, not BlueTeam's.

Missing, and decisive for the risk in section 5:

- how many persons in Switzerland are concerned;
- whether BlueTeam ever decides itself what it does with data found in a
  client's systems.

## 3. The law

**Layer.** Only federal law applies:

- The act binds a private controller.
- Supervision is federal: the FDPIC (EDÖB / PFPDT / IFPDT).

No canton's law applies. **Sources** were read in this session from
Fedlex with moli 1.1.19. The text read is the Systematic Collection (SR)
consolidation; I did not compare it with the Official Compilation (AS),
because the version was not in doubt.

- **Datenschutzgesetz (DSG / LPD / LPD)**, SR 235.1, of 25 September
  2020, AS 2022 491.
  - Status: "Stand am 7. Juli 2025" (DE); "État le 7 juillet 2025" (FR);
    "Stato 7 luglio 2025" (IT).
  - Read: Art. 3, 4, 5, 14, 15, 16, 19, 25, 49, 52, 60, 61.
  - Art. 14 was compared in DE, FR and IT. The other articles were read
    in DE only.
- **Datenschutzverordnung (DSV / OPDo / OPDa)**, SR 235.11, of 31 August
  2022, AS 2022 568. Status: "Stand am 1. Dezember 2025" (DE).
  - Read: Art. 18 and 19.
  - Read: Annex 1, as revised by the ordinance of 14 August 2024, in
    force since 15 September 2024 (AS 2024 435).
- **FDPIC contact page**, edoeb.admin.ch/de/kontakt, read 2026-11-09:
  "Feldeggweg 1, Schweiz - 3003 Bern". This is the authority's own page
  and not law.

Quotations are from the German text. English renderings are mine and
are not authoritative.

- **Scope, Art. 3(1).** The act "gilt für Sachverhalte, die sich in der
  Schweiz auswirken, auch wenn sie im Ausland veranlasst werden".
  Private-law claims follow the PILA (Art. 3(2)).
- **Representative, Art. 14(1).** Private controllers seated abroad
  designate a representative in Switzerland if they process personal
  data of persons in Switzerland and the processing meets all four
  conditions:
  - (a) it is connected with offering goods or services to persons in
    Switzerland, or with observing their behaviour;
  - (b) it is "umfangreich" (FR "à grande échelle", IT "su grande
    scala");
  - (c) it is "regelmässig" (FR "régulier", IT "periodico");
  - (d) it carries "ein hohes Risiko für die Persönlichkeit der
    betroffenen Personen".

  The conditions are cumulative. DE and FR say "die folgenden
  Voraussetzungen erfüllt" / "remplit les conditions suivantes", and IT
  joins (c) and (d) with "e".
- **The representative's role, Art. 14(2)–(3) and Art. 15.**
  - It is the point of contact for data subjects and the FDPIC.
  - The controller publishes the representative's name and address.
  - The representative keeps the record of processing activities and
    gives it to the FDPIC on request.
- **Duty to inform, Art. 19(2) and (4).** The minimum content is:
  - the controller's identity and contact details;
  - the purpose;
  - the recipients or their categories;
  - where data are disclosed abroad, the State, and where applicable
    the Art. 16(2) guarantee or the Art. 17 exception.

  Art. 19 does not require the notice to name the FDPIC, any right to
  complain, or the retention period.
- **Disclosure abroad, Art. 16(1) and DSV Annex 1.**
  - Annex 1 lists Estonia, Finland, Iceland and Ireland as adequate.
  - It lists the United States only for organisations certified under
    the Swiss-US Data Privacy Framework.
- **Access, Art. 25(6)–(7), DSV Art. 18–19.**
  - Access is free of charge.
  - The controller may ask a contribution only where the effort is
    disproportionate. It is capped at CHF 300 and announced
    beforehand.
  - Access is given within 30 days. If that is not possible, the
    controller says so within 30 days and gives the new deadline.
- **The FDPIC, Art. 49 and 52.**
  - The FDPIC opens an investigation of its own motion or "auf Anzeige
    hin" (on a report).
  - It may decline where the breach is of minor importance.
  - It tells the reporting person what steps it took and the outcome
    (Art. 49(4)).
  - Only the controller investigated is a party (Art. 52(2)). A data
    subject has no complaint procedure with party status, as the GDPR
    gives one.
- **Fines, Art. 60–61.**
  - Fines of up to CHF 250 000 apply, on complaint (auf Antrag), to:
    - intentionally failing to inform under Art. 19(1), or to give the
      Art. 19(2) particulars;
    - intentionally giving false or incomplete information;
    - intentionally disclosing data abroad contrary to Art. 16 (Art.
      61(a)).
  - No fine attaches to Art. 14.

Not read or searched in this session:

- any Federal Supreme Court decision on Art. 14 (the act has been in
  force since 1 September 2023);
- the FDPIC's guidance on representatives;
- any commentary on "umfangreich" or "hohes Risiko".

## 4. Reading

**The act reaches BlueTeam.** Its clients and their contacts are in
Switzerland, so its processing of their data has effects there
(Art. 3(1)). Who applies to BlueTeam is settled. That the GDPR also
applies does not displace the act, and the act is read on its own terms.

**Mark 2: no representative is required.** This is my reading, from the
text.

- Condition (a) is met: BlueTeam offers its services to clients in
  Switzerland.
- Condition (c) is very likely met.
- Condition (d) is not met. The processing covers:
  - business contact and billing data;
  - correspondence;
  - server logs.

  None of it is sensitive data in the sense of Art. 5(c). There is no
  profiling, nor high-risk profiling (Art. 5(g)), and no automated
  decision. Nothing in it puts the persons' personality at high risk.
- Condition (b) is very likely not met either, for a small firm's client
  and contact data.
- Because the four conditions are cumulative, failing (d) settles the
  question.

**This reading is argued, not settled.** No court has read
Art. 14. "Umfangreich" and "hohes Risiko" are not defined in the act,
and I have read no guidance on them. The reading holds only on the
facts in section 2. It changes if:

- BlueTeam becomes a controller of client-system data that is sensitive
  or processed at scale;
- the volume grows;
- it begins profiling.

**What the act adds to the notice** (my reading, from the text):

1. **The State for each disclosure abroad (Art. 19(4)).**
   - The redraft's section 4 already names the countries.
   - Section 6 justifies them by the European Commission's adequacy
     decision on Switzerland. That is an EU instrument, which tells a
     person in Switzerland nothing under Swiss law.
   - The Swiss ground is the Federal Council's list (DSV Annex 1).
     Estonia, Finland, Iceland and Ireland are on that list.
   - OpenAI's copy for abuse monitoring in the United States is covered
     by Annex 1 only if the receiving entity is certified under the
     Swiss-US framework. If it is not, Art. 19(4) requires the notice to
     name the Art. 16(2) guarantee.
2. **Access.**
   - The redraft says "the first copy is free" and gives a one-month
     answer, with two more months possible.
   - For a person in Switzerland, access is free in principle, and a
     contribution is possible only under DSV Art. 19.
   - The deadline is 30 days. It may be extended only by notice within
     those 30 days, giving the new deadline.
   - Under Swiss law, the redraft's wording under-promises on cost. It
     gives an extension the ordinance does not set.
3. **Nothing else is required by Art. 19** beyond what the redraft
   already gives:
   - the controller and its contact details;
   - the purposes;
   - the recipients.

**Mark 1: the FDPIC sentence is optional, and only its verb matters.**

- Art. 19 does not require the sentence.
- If the notice keeps it, the verb must be accurate. Under Art. 49 a
  person files a report (Anzeige), which may lead to an investigation,
  and does not become a party (Art. 52(2)).
- "Complain", next to the EEA supervisory authorities in the same
  paragraph, would suggest the same procedure. "Report" does not.
- The address is from the authority's own contact page.

## 5. Risk

**No representative.**

- Likelihood that the FDPIC finds a breach: low, on the assumed facts.
- Consequence if it did: an order to designate one. There is no fine
  (Art. 60–61 do not cover Art. 14).
- Overall: low on both.

**Leaving the Swiss particulars out of the notice.** The particulars are
Art. 19(4) and the access terms.

- Likelihood of a fine: low.
- Fines need intent and a complaint (Art. 60(1)).
- The cost would be a correction at the FDPIC's or a person's request.
- An unstated or wrong ground for the US copy carries more exposure: if
  the disclosure itself lacks a guarantee, Art. 61(a) applies. That is
  a fact to settle, not a wording question.

**The FDPIC sentence.** No legal risk in either form. "Report" is the
accurate one.

## 6. What to do

### Proposed wording

The redraft is `legal-expert-ee-eu`'s, and the choice is the owner's.

**Section 9**, replacing the marked sentence:

> If you are in Switzerland, you can also report a breach of Swiss data
> protection law to the Federal Data Protection and Information
> Commissioner (FDPIC), Feldeggweg 1, 3003 Bern, Switzerland,
> www.edoeb.admin.ch.

**Section 10**, replacing the marked paragraph:

> ### 10. If you are in Switzerland
>
> Where the Swiss Federal Act on Data Protection applies to our use of
> your data, the following also applies:
>
> - Switzerland's Federal Council recognises Estonia, Finland, Iceland
>   and Ireland as countries with adequate data protection. For OpenAI's
>   copy in the United States, [FACT: either "OpenAI is certified under
>   the Swiss-U.S. Data Privacy Framework", or the safeguard OpenAI's
>   data processing agreement gives for Swiss data].
> - We answer a request for a copy of your data within 30 days, free of
>   charge. If we need longer, we tell you within those 30 days and say
>   when you will have it. We may ask you to share the cost, up to
>   CHF 300, only where answering takes disproportionate effort, and we
>   tell you the amount before we start.
> - We have not appointed a representative in Switzerland, because the
>   Act does not require one for our processing.

### Conditions and options

The section 10 wording holds only:

- while the facts in section 2 hold;
- while BlueTeam has no seat or branch in Switzerland.

Options:

- The section 10 bullet on the representative may be left out. The act
  does not require it.
- The section 9 sentence may also be dropped. Nothing requires it.
- The access bullet cannot be left out while the redraft keeps "first
  copy free" and "two more months" unqualified. If the redraft drops
  those two phrases, the bullet may go too.
- The `[FACT]` in the first bullet is the owner's to fill:
  - check OpenAI's entry on the Data Privacy Framework list;
  - or read OpenAI's data processing agreement.

### For an attorney admitted to practise in Switzerland

1. **Confirm the Art. 14 reading** on the real volumes, especially if
   BlueTeam ever acts as controller of data in client systems.
   - Hand over: this note; the redraft; the client count in
     Switzerland; a description of the client-system work.
   - No deadline.
2. **The forum and governing law** for a Swiss person's civil claim
   against BlueTeam (PILA; the Lugano Convention). This note does not
   answer it, and the notice does not need it.
3. **The Swiss client contracts** and any processing agreement BlueTeam
   signs as processor. These are named in the 2026-10-15 opinion and
   are outside this question.

Nothing in this note is tax.
