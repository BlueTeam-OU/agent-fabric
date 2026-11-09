#!/usr/bin/env python3
"""Four defects of the 2026-11-08 drain in tools/fabric/assemble.py (j120): a resolving anchor lost to one that does not
resolve, a `[[link]]` in a code span cited, a description read two ways, and a slice written for a role the project's
taxonomy does not bind. One case per defect with the control that shows the fixture could see it; the fixtures are
test_assemble.py's own, imported.

Stdlib only; runnable as `python3 test_assemble_drain_defects.py`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_assemble as ta  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "fabric"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()


def bind(out: str, *roles: str) -> None:
    """The demo project's taxonomy binds exactly `roles`."""
    os.makedirs(os.path.join(ta.working_copy(out), ".agent-fabric"), exist_ok=True)
    with open(os.path.join(ta.working_copy(out), ".agent-fabric", "taxonomy.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "project": ta.PROJECT, "roles": [{"id": r} for r in roles]}, fh)


def report(out: str) -> dict:
    return json.loads(ta.read(ta.report_path(out)))


def test_a_slice_of_a_role_the_taxonomy_does_not_bind_is_held_and_named(tmp: str) -> None:
    """Drain of 2026-11-08: a bundle wrote a new fabric-coordinator corpus into a project that binds other roles. The
    project-scoped slice is held (written nowhere, listed nowhere), the bound role's slice is written, and the
    report names the held one with its role, project and source. A domain slice of the same role is not the project's."""
    items = [{"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"]}]
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", items), "beta": ta.claims("beta", [
        {**items[0], "topic": "held", "evidence": ["h2"]},
        {"class": "domain", "topic": "field", "title": "F", "body": "Field knowledge.", "evidence": ["h2"]}])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-02", "h3": "dev-02"})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(ta.proj(out, "alpha", "workflow.md")), "positive control: the bound role's slice is written"
    assert not os.path.exists(ta.proj(out, "beta", "workflow.md")) and "beta/workflow" not in ta.read(ta.proj(out, "beta", "INDEX.md")), \
        "the unbound role has no project slice, and its index (it lists the domain slice) names none: " + str(sorted(ta.tree(out)))
    assert os.path.isfile(ta.dom(out, "beta", "domain.md")), \
        "a domain slice belongs to the fabric, not to the project's roles"
    rep = report(out)
    assert rep["held_back"] == ["beta/workflow:held"], rep["held_back"]
    assert rep["held_unbound_role"] == [{"slice": "beta/workflow:held", "role": "beta", "project": ta.PROJECT, "class": "workflow",
                                         "topic": "held", "source": ["dev-02@hostA"]}], rep["held_unbound_role"]
    assert "beta/workflow:held" in proc.stderr, proc.stderr
    # Once the role is bound the same bundle writes the slice, and the hold leaves the report.
    bind(out, "alpha", "beta")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(ta.proj(out, "beta", "workflow.md")), "bound now: written"
    assert report(out)["held_back"] == [] and report(out)["held_unbound_role"] == [], report(out)


def test_a_role_whose_every_slice_is_held_gets_no_project_corpus(tmp: str) -> None:
    """Review round 1, F1: the hold wrote nothing of the slice but the role still got an INDEX and a crossref in the
    project, which every later run re-indexed. A role with a domain claim keeps its index (the first case above)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"]}]),
        "beta": ta.claims("beta", [{"class": "workflow", "topic": "held", "title": "T", "body": "Held.", "evidence": ["h2"]}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert not os.path.exists(ta.proj(out, "beta")), sorted(ta.tree(out))
    rep = report(out)
    assert rep["held_back"] == ["beta/workflow:held"] and rep["roles"] == ["alpha"], (rep["held_back"], rep["roles"])
    assert "memory/beta" not in proc.stdout + proc.stderr, proc.stdout + proc.stderr


def test_an_unbound_author_of_a_shared_slice_gets_no_project_corpus(tmp: str) -> None:
    """Re-review round 2, F1: the unbound role is the AUTHOR of a slice it shares with a bound role, so it is in the
    drain's claims files though it has no per-role slice. The hold wrote nothing, and so does the role's index."""
    drain, claims_dir, out = ta.build(tmp, {"beta": ta.claims("beta", [
        {"class": "workflow", "topic": "s", "title": "T", "body": "Shared.", "evidence": ["h1"], "shared_with": ["alpha"]}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert report(out)["held_back"] == ["shared/workflow:s"], report(out)["held_back"]
    assert not os.path.exists(ta.proj(out, "beta")), sorted(ta.tree(out))
    assert report(out)["roles"] == [], report(out)["roles"]


def test_an_unbound_hold_keeps_the_stores_mark_below_its_memory(tmp: str) -> None:
    """Review round 1, F2: a hold is not a drop. The mark stays below the oldest memory the held slice stands on, so the
    harvest brings it again once the role is bound."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["k1"]}]),
        "beta": ta.claims("beta", [{"class": "workflow", "topic": "held", "title": "T", "body": "Held.", "evidence": ["w1"]}])})
    with open(os.path.join(drain, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for cid, epoch in (("k1", 1), ("w1", 4)):
            fh.write(json.dumps({"content_hash": cid, "agent": "dev-01", "host": "hostA", "created_at_epoch": epoch}) + "\n")
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": "dev-01", "host": "hostA", "since_watermark": 0, "next_watermark": 9000, "counts": {"in_scope": 2}}, fh)
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert report(out)["watermarks"] == {"dev-01@hostA": 3999}, report(out)["watermarks"]
    bind(out, "alpha", "beta")
    proc = ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02")
    assert proc.returncode == 0, proc.stderr
    assert report(out)["watermarks"] == {"dev-01@hostA": 9000}, ("nothing held now: the mark moves on", report(out)["watermarks"])


def test_the_fabrics_own_project_is_not_judged_by_its_taxonomy(tmp: str) -> None:
    """Control: agent-fabric's taxonomy binds the roles that own the control plane's paths, while its project memory is
    every role's (the drain of 2026-11-08 wrote backend-dev's workflow there)."""
    drain, claims_dir, out = ta.build(tmp, {"beta": ta.claims("beta", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"]}])})
    wc = os.path.join(out, "wc-fabric")
    os.makedirs(os.path.join(wc, ".agent-fabric"))
    with open(os.path.join(wc, ".agent-fabric", "taxonomy.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "project": "agent-fabric", "roles": [{"id": "alpha"}]}, fh)
    proc = subprocess.run([sys.executable, ta.ASSEMBLE, "--claims", claims_dir, "--drain", drain, "--fabric", out,
                           "--project", "agent-fabric", "--working-copy", wc, "--stamp", "2026-01-01"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(os.path.join(wc, ".agent-fabric", "memory", "beta", "workflow.md")), sorted(ta.tree(out))


def test_a_project_with_no_taxonomy_binds_every_role(tmp: str) -> None:
    """Control: nothing says which roles the project binds, so nothing is held."""
    drain, claims_dir, out = ta.build(tmp, {"beta": ta.claims("beta", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"]}])})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(ta.proj(out, "beta", "workflow.md")) and report(out).get("held_unbound_role", []) == []


def test_a_shared_slice_with_an_unbound_owner_is_held(tmp: str) -> None:
    """A shared slice is listed by every owner's index; an unbound owner would be indexed in the project."""
    sw = {"shared_with": ["beta"]}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"], **sw}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert report(out)["held_back"] == ["shared/workflow:w"], report(out)["held_back"]
    assert not os.path.exists(ta.proj(out, "beta")) and not os.path.exists(os.path.join(ta.proj(out, "shared"))), sorted(ta.tree(out))
    bind(out, "alpha", "beta")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0 and os.path.isdir(ta.proj(out, "shared")), proc.stderr


def anchored(anchor_list: list[str], **extra) -> dict:
    return {"class": "solution", "topic": "one", "title": "T", "body": "The body.", "evidence": ["h1"],
            "observed_at": "2026-11-01", "anchors": anchor_list, **extra}


def seed_file(root: str, rel: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def test_an_anchor_that_resolves_is_not_replaced_by_one_that_does_not(tmp: str) -> None:
    """Drain of 2026-11-08 (j663): the corpus's `gzapp:src/b.py::marker` was repaired from `src/b.py::marker`; the
    memory still says the old one, which names nothing in this project's tree, and the harvest wrote it back. The
    corpus's anchor stays and the report names the dropped one with its author."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [anchored(["gzapp:src/b.py::marker"])])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-01", "h3": "dev-01"})
    seed_file(out, "gzapp/src/b.py", "a marker\n")
    ta.write_registry(out)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    written = ta.read(ta.proj(out, "alpha", "solution.md"))
    assert "*Anchors: `gzapp:src/b.py::marker`*" in written, written
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(ta.claims("alpha", [anchored(["src/b.py::marker"])]), fh)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    kept = ta.read(ta.proj(out, "alpha", "solution.md"))
    assert "*Anchors: `gzapp:src/b.py::marker`*" in kept and "`src/b.py::marker`" not in kept, kept
    assert report(out)["anchors_kept"] == [{"slice": "alpha/solution:one", "heading": "T", "dropped": "src/b.py::marker",
                                            "kept": "gzapp:src/b.py::marker", "agent": "dev-01", "host": "hostA", "memory": "one"}], \
        report(out)["anchors_kept"]
    assert "src/b.py::marker -> gzapp:src/b.py::marker" in proc.stderr, proc.stderr


def test_an_incoming_anchor_that_resolves_stands_and_so_does_one_that_cannot_be_judged(tmp: str) -> None:
    """The controls of the case above: the guard replaces only an anchor that is GONE, by one that is THERE. An incoming
    anchor that resolves is the author's newer text; one in a checkout that is not here is unknown, not gone."""
    for corpus_anchor, incoming, has_file, other_checkout in (
            ("gzapp:src/b.py::marker", "src/b.py::marker", True, True),        # both resolve: the claim is the newer text
            ("gzapp:src/b.py::marker", "src/b.py::marker", False, False),      # the corpus's cannot be looked at: unknown, not there
            ("gzapp:src/b.py::marker", "gzapp:src/b.py::other", False, True),  # another string is another anchor
            ("gzapp:src/b.py::marker", "src/b.py::marker", False, "lacks"),    # the corpus's is gone too: nothing to keep
    ):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out = ta.build(sub, {"alpha": ta.claims("alpha", [anchored([corpus_anchor])])})
            ta.with_agents(drain, {"h1": "dev-01"})
            if other_checkout:
                seed_file(out, "gzapp/src/b.py", "a marker\n")   # present while the corpus is written
            ta.write_registry(out)
            if has_file:
                seed_file(ta.working_copy(out), "src/b.py", "a marker\n")
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, (corpus_anchor, proc.stderr)
            if other_checkout == "lacks":
                seed_file(out, "gzapp/src/b.py", "nothing\n")
            with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
                json.dump(ta.claims("alpha", [anchored([incoming])]), fh)
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, (corpus_anchor, incoming, proc.stderr)
            text = ta.read(ta.proj(out, "alpha", "solution.md"))
            assert f"*Anchors: `{incoming}`*" in text, (corpus_anchor, incoming, text)
            assert report(out).get("anchors_kept", []) == [], report(out)


def test_a_link_in_a_code_span_is_not_cited(tmp: str) -> None:
    """Drain of 2026-11-08 (j663): the harvest cites every `[[x]]` of a body, code or not, and the section carried it in
    its References line. A code span is literal text. The link written outside code is still cited (the control), and
    the report lists only that one as unresolved."""
    body = "Write `[[example-topic]]` literally, and see [[real-topic]]; ``[[also-code]]`` too.\n\n```\n[[fenced]]\n```"
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": body, "evidence": ["h1"],
         "citations": {"memories": ["also-code", "example-topic", "fenced", "real-topic"]}}])})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = ta.read(ta.dom(out, "alpha", "domain.md"))
    assert "*References: real-topic*" in text, text
    targets = [row["target"] for row in report(out)["unresolved_links"]]
    assert targets == ["real-topic"], targets


def test_a_toml_array_header_in_a_code_span_is_not_cited(tmp: str) -> None:
    """The cases fleetdeck #63's review (F2) found in the drain: a plugin manifest's `[[events]]` and `[[panes]] title`,
    written in code beside a link that is one (`[[real-topic]]`), must not reach the References line."""
    body = ("herdr emits events (socket or a plugin `[[events]]` hook), and the pane's `label` = its `[[panes]] title`.\n"
            "See [[real-topic]].")
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": body, "evidence": ["h1"],
         "citations": {"memories": ["events", "panes", "real-topic"]}}])})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "*References: real-topic*" in ta.read(ta.dom(out, "alpha", "domain.md"))
    assert [row["target"] for row in report(out)["unresolved_links"]] == ["real-topic"], report(out)["unresolved_links"]


def test_a_break_in_a_title_does_not_split_the_heading_or_cut_the_index_entry(tmp: str) -> None:
    """Drain of 2026-11-08 (j670): a memory's description with a YAML `\\n` escape reaches the claim as a title with a
    line break, which split the section's heading and cut the INDEX entry at the break, so lint judged the entry
    mis-described. The title is one line wherever it is written, and lint agrees with the index."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Compose the sections\nof a message", "body": "The body.", "evidence": ["h1"]},
        {"class": "domain", "topic": "two", "title": "Double  space stays", "body": "Other.", "evidence": ["h1"]}])})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = ta.read(ta.dom(out, "alpha", "domain", "one.md"))
    assert "\n## Compose the sections of a message\n" in text, text
    assert "\n## Double  space stays\n" in ta.read(ta.dom(out, "alpha", "domain", "two.md")), "only breaks are touched"
    assert "description: Compose the sections of a message\n" in text, text
    ta.lint_inputs(out)
    os.makedirs(os.path.join(out, "identities", "roles"), exist_ok=True)
    with open(os.path.join(out, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "roles": [{"id": "alpha", "title": "Alpha"}]}, fh)
    with open(ta.ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\ntier: 1\ndistilled_at: 2026-01-01\n---\n\n# alpha\n")
    proc = ta.run_assemble(drain, claims_dir, out)      # re-index with the charter present
    assert proc.returncode == 0, proc.stderr
    index = ta.read(ta.proj(out, "alpha", "INDEX.md"))
    assert "— Compose the sections of a message\n" in index, index
    lint = subprocess.run([sys.executable, ta.LINT, "--fabric", out, "--working-copy", f"{ta.PROJECT}={ta.working_copy(out)}"],
                          capture_output=True, text=True)
    assert lint.returncode == 0 and "describes it as" not in lint.stderr, lint.stderr

    # A slice written before titles were made one line holds the break in its frontmatter: its entry is one line too.
    old = ta.dom(out, "alpha", "domain", "two.md")
    edited = ta.read(old)
    with open(old, "w", encoding="utf-8") as fh:
        fh.write(edited.replace("description: Double  space stays", 'description: "Older\\nbreak"'))
    from assembler.writer import described
    assert described(old, "fallback") == "Older break", described(old, "fallback")


def main() -> int:
    cases = [
        test_a_slice_of_a_role_the_taxonomy_does_not_bind_is_held_and_named,
        test_a_role_whose_every_slice_is_held_gets_no_project_corpus,
        test_an_unbound_author_of_a_shared_slice_gets_no_project_corpus,
        test_an_unbound_hold_keeps_the_stores_mark_below_its_memory,
        test_the_fabrics_own_project_is_not_judged_by_its_taxonomy,
        test_a_project_with_no_taxonomy_binds_every_role,
        test_a_shared_slice_with_an_unbound_owner_is_held,
        test_an_anchor_that_resolves_is_not_replaced_by_one_that_does_not,
        test_an_incoming_anchor_that_resolves_stands_and_so_does_one_that_cannot_be_judged,
        test_a_link_in_a_code_span_is_not_cited,
        test_a_toml_array_header_in_a_code_span_is_not_cited,
        test_a_break_in_a_title_does_not_split_the_heading_or_cut_the_index_entry,
    ]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
