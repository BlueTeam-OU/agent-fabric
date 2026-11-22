---
role: "legal-expert"
class: domain
topic: "fadp-art14-representative-reading"
description: "Whether a controller abroad needs a Swiss representative (DSG Art. 14), and how a notice names the FDPIC (a report, not a complaint) — read from Fedlex 2026-11-09"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d265d840223b16b4
---

## Whether a controller abroad needs a Swiss representative (DSG Art. 14), and how a notice names the FDPIC (a report, not a complaint) — read from Fedlex 2026-11-09

Read on Fedlex 2026-11-09: DSG SR 235.1, "Stand am 7. Juli 2025"; DSV SR 235.11, "Stand am 1. Dezember 2025". Applied in docs/legal/2026-11-09-fadp-swiss-marks-blueteam-ee-notice.md (d0060b2e).

**The representative (DSG Art. 14(1)).** A private controller seated abroad must designate a representative in Switzerland only if four conditions all hold:
- (a) the processing is connected with offering goods or services in Switzerland, or with observing behaviour there;
- (b) it is large-scale ("umfangreich");
- (c) it is regular ("regelmässig");
- (d) it carries a high risk to the persons' personality ("hohes Risiko für die Persönlichkeit").

The conditions are cumulative. DE and FR say "die folgenden Voraussetzungen" / "les conditions suivantes", and IT joins (c) and (d) with "e". So for B2B contact and billing data without profiling, (d) fails, and no representative is needed.

Where a representative is designated, the controller publishes its name and address (Art. 14(3)). The representative keeps the record of processing (Art. 15).

No fine attaches to Art. 14: the fine provisions, Art. 60–61, do not list it. I found no case law on Art. 14 and did not read the FDPIC's guidance on it, so this reading is mine, not settled.

**The FDPIC in a notice.** Art. 19 does not require a notice to name the FDPIC. If it does, the person "reports" (Anzeige, Art. 49(1)). The FDPIC tells the reporting person what steps it took (Art. 49(4)). Only the controller investigated is a party (Art. 52(2)), so "complain" in the GDPR sense is wrong. The address is Feldeggweg 1, 3003 Bern (edoeb.admin.ch/de/kontakt).

**Two places where GDPR-shaped notices go wrong for Swiss persons:**
- **Disclosure abroad.** Under Art. 19(4), the Swiss ground for a disclosure abroad is the Federal Council's list in DSV Annex 1, not the EU's adequacy decision. Annex 1 covers the US only for organisations certified under the Swiss-US Data Privacy Framework.
- **Access.** Access is free (Art. 25(6)). A contribution of at most CHF 300 is allowed only for disproportionate effort (DSV Art. 19). The deadline is 30 days, extendable only by notice within those 30 days (DSV Art. 18). The GDPR's "first copy free" and "plus two months" do not carry over.

Related: [[workflow-carried-2026-10-18]], [[second-pass-before-proposing-words]].

**EU SCCs for Swiss data (read 2026-11-10).** DSG Art. 16(2)(d) admits clauses the FDPIC has recognised. The FDPIC recognised the 2021 EU SCCs "mit dem Vorbehalt" that they are adapted. Its document of 27 August 2021, last adjusted 12 February 2025, is linked from edoeb.admin.ch/de/bekanntgabe-von-personendaten-ins-ausland. It requires three adaptations:
- the FDPIC is named in Annex I.C;
- clause 18(c) lets persons resident in Switzerland sue there;
- an annex reads references to the GDPR as references to the FADP (not needed under "Option 2", where everything is put under the GDPR standard).

A European Commission adequacy decision has no force under DSG Art. 16(1). OpenAI's DPA (effective 2026-01-01) §4.1 relies on SCCs placed in its onward agreements, and on EU adequacy decisions. It has no Swiss addendum, though it has a UK one. dataprivacyframework.gov/list returned an empty page to moli.

*References: second-pass-before-proposing-words, workflow-carried-2026-10-18*

*Observed 2026-11-09 (legal-expert)*
