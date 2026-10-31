---
role: "fabric-coordinator"
class: domain
topic: edgextract
description: "raphaelmansuy/edgextract: markdown -> knowledge graph with a user ontology; a local decision model answers closed yes/no per candidate (probability + cutoff: keep / review / drop); not adopted (needs Ollama + a decision model); borrow…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 06509847aa49830e
---

## raphaelmansuy/edgextract: markdown -> knowledge graph with a user ontology; a local decision model answers closed yes/no per candidate (probability + cutoff: keep / review / drop); not adopted (needs Ollama + a decision model); borrow closed decisions with a review queue and ontology-gated typed links

https://github.com/raphaelmansuy/edgextract, read 2026-10-15 (Apache-2.0, 115 stars, 11 forks, 17 commits: young). Python library (`uv`, `extract_text`, `write_report`), a Rust crate (`cargo add edgextract`) that compiles to WASM for an in-browser demo (Tev1 0.8B on WebGPU). Output is EdgeQuake-shaped JSON (entities `UPPER_SNAKE`, relationships with their evidence sentence, a `review` list and a `rejected` list), plus Cypher and an interactive HTML graph.

**How it works:** split into sentences with offsets; candidate names come from code (the ontology's gazetteer, markdown cues, optionally GLiNER), never from the model; each unknown span gets a closed question ("is this a name?"), then a pick from the ontology's kinds; pairs the ontology does not allow are never asked; one yes/no per legal link type, so two link types can both hold; a probability per answer (Ollama `POST /v1/systemone`, 0.35+), and the caller's cutoffs decide keep / send to a person / drop. A decision cache makes moving the cutoffs free.

**Measured, honestly stated:** CoNLL04 zero-shot names F1 0.690, links 0.388 (Mistral JSON per sentence: 0.643 / 0.330; SpERT trained on it: 0.889 / 0.715). Limits it says itself: cutoffs uncalibrated until `edgextract calibrate` on your labels, no coreference, no cross-sentence links, link direction can flip, `weight` is the raw probability.

**For the fabric (judgement, 2026-10-15): not adopted.** It needs a local decision model served by Ollama on each host, which the fabric does not run (ADR-040's stdlib-first Python, no model hosting on the fleet's logins); and it extracts from prose, while the corpus's slices are already structured claims with provenance.

**Borrow the ideas, not the code:**
- A closed yes/no with a probability and a cutoff that sends the uncertain middle to a person beats asking for free-form JSON. It fits the drain and lint judgements: "is this slice a duplicate of X?", "does this correction supersede that section?". Keep / review / drop, with the review list visible, in place of a silent guess.
- An ontology that makes illegal links unaskable: typed links between memory slices (supersedes, corrects, depends-on) with allowed endpoints by class, not free `[[links]]`.
- Every link carries its evidence sentence, as our slices carry provenance.

**How to apply:** if the drain or lint ever gets model-judged decisions, shape them as closed questions with a cutoff and a review queue (the ADR-058 reflection pass and the drain report are the places). Related: [[edgequake]], [[helix-foundry]], [[overgraph]], [[agent-memory-tigerless]].

*References: agent-memory-tigerless, edgequake, helix-foundry, links, overgraph*

*Observed 2026-10-15 (fabric-coordinator)*
