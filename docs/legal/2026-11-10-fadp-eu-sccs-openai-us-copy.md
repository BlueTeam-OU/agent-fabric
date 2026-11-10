# Do the EU SCCs in OpenAI's DPA carry Swiss data to the United States under the FADP?

Opinion by `legal-expert-ch` (Swiss law), 2026-11-10, answered for that
date. It serves section 10 of `2026-10-15-privacy-notice-blueteam-ee-draft.md`,
which `legal-expert-ee-eu` holds (branch
`develop-qzapp/legal-expert-ee-eu/for/user/j20-privacy-notice-owner-facts`,
commit 81b34bc3). It follows `2026-11-09-fadp-swiss-marks-blueteam-ee-notice.md`
and replaces nothing in it. It answers only for Swiss law; whether the
GDPR governs OpenAI Ireland's transfer, and what it then requires, is
`legal-expert-ee-eu`'s. It is not the advice of an attorney admitted in
Switzerland.

## 1. Question

Asked by `legal-expert-ee-eu` (QUESTION 01a1c6d0, 2026-11-10):

1. Under the FADP, Art. 16(2)(d), do the European Commission's 2021
   standard contractual clauses (SCCs), as OpenAI's data processing
   addendum (DPA) provides them, carry Swiss personal data to the United
   States? Does that turn on Swiss adaptations being in the DPA?
2. What sentence replaces the `[SWISS]` mark in section 10, or does the
   bullet need another shape?

## 2. Facts

Supplied by `legal-expert-ee-eu`, on the owner's word of 2026-11-10; not
verified by me:

- BlueTeam OÜ (Estonia) is the controller. OpenAI Ireland Ltd is its
  processor under a business account, with the DPA accepted and training
  turned off.
- OpenAI keeps copies for abuse monitoring in the United States.
- BlueTeam has no seat or branch in Switzerland.

Verified by me, 2026-11-10:

- **The DPA**, openai.com/policies/data-processing-addendum, "Updated:
  December 1, 2025", "Effective: January 1, 2026" (read with moli
  1.1.19):
  - **Preamble.** A customer based in the EEA or Switzerland contracts
    with OpenAI Ireland Ltd.
  - **§ 4.1 "EEA and Swiss Data".** Where OpenAI Ireland transfers
    such data to OpenAI affiliates or third parties outside the EEA or
    Switzerland, "it will do so on the basis of agreements containing
    SCCs … or an adequacy decision issued by the European Commission
    under Article 45 GDPR".
  - **The SCCs.** They are defined as the clauses "adopted by the EU
    Commission on June 4, 2021 (as may be amended, updated or
    replaced from time to time)".
  - **Schedule 1 § 8.** It completes the SCCs (governing law, forum,
    competent authority = the ICO) only "for the transfer of UK Data
    under Section 4.2".
  - **No Swiss adaptations.** The DPA has no Swiss annex. It names
    neither the FDPIC, nor a Swiss forum, nor any reading of GDPR
    references as references to the FADP.
- **The SCCs themselves.** The agreements that carry them, between
  OpenAI Ireland and its affiliates or sub-processors, are not part of
  the DPA. I have not seen them.

Not verified, and decisive:

- **(F1) Swiss Data Privacy Framework certification.** I could not
  verify whether the OpenAI entity that holds the US copy is certified
  under the Swiss-US Data Privacy Framework. The DPF list
  (dataprivacyframework.gov/list) loaded, but its participant search
  could not be queried from here: the API refused both direct calls and
  calls from inside the page.
- **(F2) Swiss adaptations in the intra-group SCCs.** Whether the
  intra-group SCCs carry the Swiss adaptations described in section 3.
- **(F3) Swiss data in the US copy.** Whether personal data of persons
  in Switzerland reach OpenAI at all through BlueTeam's use. If they do
  not, the bullet is moot for the US copy.

## 3. The law

**Layer.** Federal law only; no cantonal law applies to a private
controller's disclosure abroad.

**Federal acts**, read on Fedlex (SR consolidation) in this session:

- **DSG / LPD / LPD**, SR 235.1, AS 2022 491, "Stand am 7. Juli 2025".
  - Read: Art. 9, 16, 17, 19, 51, 60, 61.
  - Art. 16(2)(d) compared in DE, FR and IT.
- **DSV / OPDo / OPDa**, SR 235.11, AS 2022 568, "Stand am 1. Dezember
  2025".
  - Read: Art. 8, 9, 10 and Annex 1.
  - Art. 8(3) was amended in force 1 December 2025 (AS 2025 694).
  - Annex 1 was last amended in force 15 September 2024 (AS 2024 435).
    Its status is therefore unchanged since my note of 2026-11-09.

**The FDPIC's own texts.** These are not law. They show how the FDPIC
applies the act, and set the scope of what it "recognises":

- **Notice of 27 August 2021**, edoeb.admin.ch/de/27082021-…, read
  2026-11-10.
- **Guidance PDF**, "Die Übermittlung von Personendaten in ein Land ohne
  angemessenes Datenschutzniveau gestützt auf Standarddatenschutzklauseln
  nach Art. 16 Abs. 2 lit. d DSG": "veröffentlicht 27. August 2021;
  zuletzt angepasst am 12.02.2025". Read in full, German.
- **The FDPIC page "Bekanntgabe von Personendaten ins Ausland"**, read
  2026-11-10.

German quotations follow; the English is mine and not authoritative.

**Art. 16(1) DSG: adequacy.** Data may go abroad where the Federal
Council has found the State's legislation adequate.

- DSV Annex 1 lists Ireland.
- It lists the United States only for data processed by organisations
  certified under the Swiss-US Data Privacy Framework.
- A European Commission adequacy decision is not a Federal Council
  finding, and has no effect under Art. 16(1).

**Art. 16(2)(d) DSG: standard clauses.** Without such a finding, data may
go abroad where suitable protection is ensured by standard data
protection clauses that the FDPIC approved, issued or recognised
beforehand. The three language versions agree:

- DE: "Standarddatenschutzklauseln, die der EDÖB vorgängig genehmigt,
  ausgestellt oder anerkannt hat";
- FR: "clauses type de protection des données préalablement
  approuvées, établies ou reconnues par le PFPDT";
- IT: "clausole tipo di protezione dei dati previamente approvate,
  stabilite o riconosciute dall'IFPDT".

**DSV Art. 10.** Whoever discloses under such clauses, controller or
processor, takes adequate measures to ensure that the recipient complies
with them (para. 1). The FDPIC publishes a list of the clauses it has
recognised (para. 2). Since 1 September 2023 their use need not be
notified (FDPIC guidance, § 1).

**The FDPIC's recognition is conditional.** The 2021 SCCs are recognised
"sofern die für eine Verwendung unter Schweizer Datenschutzrecht
notwendigen Anpassungen und Ergänzungen vorgenommen werden" (notice of
27 August 2021): provided the adjustments and additions needed for use
under Swiss law are made. The guidance (§ 2.3.1–2.3.5) names them:

1. **FDPIC as authority.** Annex I.C must name the FDPIC as supervisory
   authority, at least for transfers under the DSG, beside an EU
   authority where the GDPR also applies. Naming an EU authority alone
   "würde den tatsächlichen Verhältnissen nicht entsprechen".
2. **Swiss forum.** An annex must state that "Mitgliedstaat" in Clause
   18(c) does not exclude data subjects habitually resident in
   Switzerland from suing there. The guidance calls this "zwingend".
3. **References to the GDPR.** An annex must say that they are to be
   read as references to the DSG, for transfers under the DSG. This is
   not needed where the parties subject every transfer to the GDPR
   standard (the guidance's "Option 2").
4. **Governing law (Clause 17).** Swiss law, or another law that grants
   third-party-beneficiary rights. Under Option 2, the law of an EU
   member state.

**Art. 17 DSG: exceptions.** Consent, contract performance with or for
the data subject, and the like. None fits a processor's standing copy
kept for abuse monitoring.

**Art. 9 DSG: processors.** Processing may be entrusted to a processor
only where it processes the data "so …, wie der Verantwortliche selbst
es tun dürfte" (para. 1(a)): as the controller itself would be allowed
to.

**Art. 19(4) DSG: duty to inform.** Where data are disclosed abroad, the
controller tells the data subject the State and, "gegebenenfalls"
(where applicable), the Art. 16(2) guarantee or the Art. 17 exception.

**Fines.** Each is up to CHF 250 000, on complaint, against private
persons who act intentionally:

- Art. 61(a): disclosing abroad contrary to Art. 16(1)–(2) without an
  Art. 17 ground;
- Art. 61(b): entrusting processing without the conditions of
  Art. 9(1)–(2);
- Art. 60(1)(a): intentionally giving false or incomplete information
  under Art. 19.

**Not read or searched in this session:**

- the FDPIC's published list under DSV Art. 10(2), beyond the 2021
  notice and its guidance;
- any Federal Supreme Court or Federal Administrative Court decision on
  Art. 16(2)(d) DSG;
- commentary;
- the agreements between OpenAI Ireland and its affiliates.

## 4. Reading

**Two disclosures, and BlueTeam's own is covered.**

- BlueTeam discloses to OpenAI Ireland. Ireland is on Annex 1, so
  Art. 16(1) covers that step. This is settled, from the text.
- The US copy is OpenAI Ireland's onward disclosure, as BlueTeam's
  processor. Art. 16 is not limited to controllers (DSV Art. 10(1) names
  the processor).
- BlueTeam answers for that onward step through Art. 9(1)(a): the
  processor may only do what BlueTeam itself could do, and BlueTeam
  could not send the data to the US without an Art. 16 or 17 ground.
  This is my reading from the text, not decided by a court that I have
  read.

**Q1: the 2021 SCCs carry Swiss data only with the Swiss adaptations.**

- Art. 16(2)(d) admits clauses that the FDPIC has recognised, and only
  as far as the FDPIC has recognised them. The FDPIC recognised the 2021
  SCCs under the proviso quoted in section 3.
- Unadapted SCCs therefore fall outside the recognition. They are not,
  by themselves, a guarantee under Art. 16(2)(d).
- This reading is the FDPIC's practice, read from its own texts. The
  guidance is not law. But here it does more than interpret: the statute
  makes the FDPIC's recognition the condition, so the recognition's
  scope sets the guarantee's scope.
- I know of no decision against this reading. I searched for none, so
  it stands as strongly argued, not settled.

**What the DPA shows.**

- **No Swiss completion.** The DPA promises SCCs for "EEA and Swiss
  Data", but completes them only for UK data. It contains none of the
  four adaptations.
- **The real question is elsewhere.** The SCCs that would carry the US
  copy are in OpenAI Ireland's own agreements with its affiliates. So
  the real question is whether those agreements carry the Swiss
  adaptations (F2). The DPA cannot answer it.
- **The alternative ground does not reach Swiss data.** The DPA's other
  ground, "an adequacy decision issued by the European Commission under
  Article 45 GDPR", has no effect for Swiss data.
- **Only F1 can substitute.** A Swiss-law equivalent exists only if the
  US recipient is Swiss-US DPF certified, in which case DSV Annex 1
  covers it under Art. 16(1).

**So, on today's evidence:**

- The Swiss leg of the US copy rests on a guarantee that is not shown.
- It is covered if F1 or F2 turns out yes. Otherwise there is a gap,
  and it is OpenAI's to close; BlueTeam answers for it through Art. 9.
- All of this applies only if F3 is yes: if no data of persons in
  Switzerland reach OpenAI through BlueTeam, the US copy raises no Swiss
  question.

**Q2: the bullet cannot be finished by wording.**

- Art. 19(4) requires the guarantee to be named, and a named guarantee
  must be true.
- "OpenAI's data processing agreement provides Standard Contractual
  Clauses adopted by the European Commission", left unqualified, would
  tell a person in Switzerland that the Art. 16(2)(d) guarantee is in
  place, and that is not shown.
- The sentence therefore depends on F1 or F2. Section 6 gives one
  sentence for each answer.

## 5. Risk

**The notice.** Wrong if the bullet names the unadapted SCCs as the
Swiss guarantee.

- Likelihood of a fine: low, because Art. 60(1)(a) needs intent and a
  complaint.
- Intent becomes harder to deny once this note exists.
- The likelier cost is a correction asked by the FDPIC or by a person.

**The transfer itself, if F1 and F2 are both no.**

- Likelihood that the FDPIC acts: low for a small controller, on a
  report.
- Consequence: an FDPIC order suspending or prohibiting the
  disclosure (Art. 51(2)), or adapting the processing (Art. 51(1)).
- A fine under Art. 61(a) or (b) requires intent and a complaint.
- That exposure rises with the volume of Swiss data sent to OpenAI (F3).

## 6. What to do

### The facts to get first (the owner's, through OpenAI)

- **F1.** Is OpenAI OpCo, LLC (or whichever entity keeps the US copy)
  listed as active under the Swiss-US DPF? The list is public.
- **F2.** Do OpenAI Ireland's SCCs with its US affiliates carry the
  Swiss adaptations? Ask OpenAI for written confirmation or the Swiss
  annex. I contact no counterparty.
- **F3.** Do personal data of persons in Switzerland reach OpenAI
  through BlueTeam's use at all? If not, the US copy needs no Swiss
  bullet.

### Proposed sentences

The draft is `legal-expert-ee-eu`'s, and the choice is the owner's. In
section 10, the first bullet's second sentence becomes one of these:

- **If F1 is yes:**

  > For OpenAI's copy in the United States, [ENTITY: the OpenAI company
  > that keeps it] is certified under the Swiss-U.S. Data Privacy
  > Framework, which the Federal Council recognises as adequate.

- **If F2 is yes:**

  > For OpenAI's copy in the United States, OpenAI uses the European
  > Commission's standard contractual clauses with the adaptations that
  > the Swiss Federal Data Protection and Information Commissioner
  > requires for their recognition under Swiss law.

- **If F3 is no:** delete the second sentence for Swiss purposes. Keep
  the EU sentence wherever `legal-expert-ee-eu` places it.
- **If F3 is yes and F1 and F2 are both no:** no sentence makes the
  notice both true and compliant. What follows is the owner's decision,
  not a wording one:
  - get the Swiss annex from OpenAI;
  - keep Swiss persons' data out of OpenAI;
  - or proceed knowing of the gap.

  A true but uncomfortable interim sentence would be: "OpenAI's data
  processing agreement provides the European Commission's standard
  contractual clauses; it does not state the adaptations that Swiss law
  requires for them." I do not recommend publishing it as the end
  state.

### For an attorney admitted to practise in Switzerland

- Only if F1 and F2 are both no, F3 is yes, and the owner chooses to
  proceed. The attorney confirms the Art. 9 / Art. 16 exposure on the
  real volumes.
- Hand over: this note; the DPA (version of 1 December 2025); OpenAI's
  answers to F1 and F2; the volume of Swiss data.
- No deadline runs.

Nothing in this note is tax.
