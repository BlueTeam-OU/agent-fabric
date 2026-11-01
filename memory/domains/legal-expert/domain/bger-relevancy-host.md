---
role: "legal-expert"
class: domain
topic: "bger-relevancy-host"
description: "Reading Federal Supreme Court decisions (BGE) from source; www.bger.ch fails TLS verification, so use relevancy.bger.ch with curl and decode the page as latin-1"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0c08f537e362d930
---

## Reading Federal Supreme Court decisions (BGE) from source; www.bger.ch fails TLS verification, so use relevancy.bger.ch with curl and decode the page as latin-1

Tested 2026-10-20. www.bger.ch serves its leaf certificate without the DigiCert intermediate (`openssl s_client`: "unable to verify the first certificate"). So curl, moli and WebFetch all refuse it. Never work around that by disabling verification. The court's own host relevancy.bger.ch verifies, and it serves the same published decisions as plain HTML:

`curl -sSL "https://relevancy.bger.ch/php/clir/http/index.php?highlight_docid=atf://142-II-35:de&lang=de&type=show_document"`

The docid form is `atf://<vol>-<part>-<page>:<lang>`, with the part in upper case (`99-IB-39`). The page is latin-1: decode with that, strip the tags, and grep for the Erwägung. Never print the whole page. This counts as an official channel; record the retrieval date. An Italian or French decision is read in its language of decision. Related: [[fedlex-needs-js-browser]].

*References: fedlex-needs-js-browser*

*Observed 2026-10-20 (legal-expert)*
