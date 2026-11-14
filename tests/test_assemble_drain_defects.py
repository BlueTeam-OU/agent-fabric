#!/usr/bin/env python3
"""Four defects of the 2026-11-08 drain in tools/fabric/assemble.py (j120): a resolving anchor lost to one that does not
resolve, a `[[link]]` in a code span cited, a description read two ways, and a claim of a role the project's
taxonomy does not bind (since j227: re-homed for fabric-coordinator, refused for any other role). One case per defect with the control that shows the fixture could see it; the fixtures are
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


COORD = "fabric-coordinator"
WF = {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"]}


def fabric_proj(out: str, role: str, *rest: str) -> str:
    """The control plane's own project corpus in the throwaway fabric root."""
    return os.path.join(out, ".agent-fabric", "memory", role, *rest)


def test_a_coordinator_claim_of_a_project_that_does_not_bind_it_lands_in_the_control_plane(tmp: str) -> None:
    """Drain of 2026-11-08, replayed: fabric-coordinator workflow claims drained with --project of a project that binds
    other roles. Not admitted there; filed under the control plane's own project memory, and the report counts and
    names each. The bound role's claim and the coordinator's domain claim are untouched (controls)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [
        {**WF, "topic": "moved", "title": "Moved", "evidence": ["h2"]},
        {"class": "domain", "topic": "field", "title": "F", "body": "Field knowledge.", "evidence": ["h2"]}])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-02"})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(ta.proj(out, "alpha", "workflow.md")), "positive control: the bound role's slice is written"
    assert os.path.isfile(ta.dom(out, COORD, "domain.md")), "a domain slice belongs to the fabric, not to the project's roles"
    assert os.path.isfile(fabric_proj(out, COORD, "workflow.md")), "re-homed: " + str(sorted(ta.tree(out)))
    assert "Moved" in ta.read(fabric_proj(out, COORD, "workflow.md"))
    assert os.path.isfile(fabric_proj(out, COORD, "INDEX.md")), "the re-homed role is indexed where it was written"
    assert not os.path.exists(ta.proj(out, COORD, "workflow.md")) and "Moved" not in ta.read(ta.proj(out, COORD, "INDEX.md")), \
        "no project slice of the unbound role, and its index (it lists the domain slice) names none: " + str(sorted(ta.tree(out)))
    rep = report(out)
    assert rep["rehomed"] == [{"slice": f"{COORD}/workflow:moved", "role": COORD, "class": "workflow", "topic": "moved", "title": "Moved",
                               "from_project": ta.PROJECT, "to_project": "agent-fabric", "source": ["dev-02@hostA"]}], rep["rehomed"]
    assert any(f.endswith(f"{COORD}/workflow.md") for f in rep["rehomed_files"]), rep["rehomed_files"]
    assert rep["roles"] == ["alpha", COORD] and rep["held_back"] == [], (rep["roles"], rep["held_back"])
    assert f"{COORD}/workflow:moved" in proc.stderr and "RE-HOMED (1" in proc.stderr, proc.stderr
    # Control: bound, the same claim is the project's and nothing is re-homed.
    bind(out, "alpha", COORD)
    proc = ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02")
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(ta.proj(out, COORD, "workflow.md")), "bound now: written in the project"
    assert report(out)["rehomed"] == [], report(out)["rehomed"]


def test_a_rehomed_claim_is_screened_by_the_control_planes_hygiene_view(tmp: str) -> None:
    """The claim leaves the project's pass, so the project's own-name allowance does not follow it: a name the project
    keeps to itself (scope "others") stays in its bound role's slice and is redacted in the re-homed one; and the pass
    over the project afterwards is judged by the project's view again, not the control plane's."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [{**WF, "body": "The acme habit."}]), COORD: ta.claims(COORD, [
        {**WF, "topic": "moved", "body": "The acme habit.", "evidence": ["h2"]}])})
    bind(out, "alpha")
    with open(os.path.join(ta.working_copy(out), ".agent-fabric", "hygiene.json"), "w", encoding="utf-8") as fh:
        json.dump({"patterns": [{"pattern": "\\bacme\\b", "flags": "i", "label": "own name", "scope": "others"}]}, fh)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "acme" in ta.read(ta.proj(out, "alpha", "workflow.md")), "control: the project's own slice keeps its own name"
    assert "acme" not in ta.read(fabric_proj(out, COORD, "workflow.md")), "the control plane's view bans it"


def test_a_refusal_of_the_control_planes_pass_stops_the_run_with_the_projects_corpus_untouched(tmp: str) -> None:
    """Two re-homed claims under one heading are a collision the owner decides (the control plane's pass refuses): the run
    exits 1 and, the control plane's pass going first, nothing of the project's is written. Control: one claim writes."""
    two = [{**WF, "topic": "moved", "body": "One.", "evidence": ["h2"]}, {**WF, "topic": "moved", "body": "Two.", "evidence": ["h2"]}]
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, two)})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert not os.path.exists(ta.proj(out, "alpha", "workflow.md")), sorted(ta.tree(out))
    drain, claims_dir, out = ta.build(os.path.join(tmp, "one"), {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, two[:1])})
    bind(out, "alpha")
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0


def test_a_claim_of_another_unbound_role_refuses_the_run_before_anything_is_written(tmp: str) -> None:
    """Any role but fabric-coordinator: refused, exit 1, naming the claim, the role and the project, with the bound role's
    claim not written either (nothing is written before the refusal). Control: bound, the same bundle writes."""
    items = [{"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"]}]
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", items), "beta": ta.claims("beta", [
        {**items[0], "topic": "held", "evidence": ["h2"]},
        {"class": "domain", "topic": "field", "title": "F", "body": "Field knowledge.", "evidence": ["h2"]}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert "workflow:held" in proc.stderr and "role beta" in proc.stderr and f"project {ta.PROJECT}" in proc.stderr, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
    assert not os.path.exists(ta.proj(out, "alpha")) and not os.path.exists(ta.dom(out, "beta")), sorted(ta.tree(out))
    bind(out, "alpha", "beta")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(ta.proj(out, "beta", "workflow.md")), "bound now: written"


def test_a_coordinator_claim_shared_with_another_unbound_role_is_refused(tmp: str) -> None:
    """The re-home is for a claim only the coordinator owns: one it shares with another role that the project does not
    bind is that role's too, and is refused naming both."""
    drain, claims_dir, out = ta.build(tmp, {COORD: ta.claims(COORD, [{**WF, "shared_with": ["beta"]}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and COORD in proc.stderr and "shared with beta" in proc.stderr, (proc.returncode, proc.stderr)
    assert not os.path.exists(fabric_proj(out, COORD)), sorted(ta.tree(out))


def test_a_rehomed_role_with_nothing_left_gets_no_project_corpus_and_its_evidence_is_not_held(tmp: str) -> None:
    """The role has no project directory, index or crossref in the project; and the store's mark moves past its memory,
    since the claim was written (in the control plane's corpus), not held."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["k1"]}]),
        COORD: ta.claims(COORD, [{"class": "workflow", "topic": "moved", "title": "T", "body": "Moved.", "evidence": ["w1"]}])})
    with open(os.path.join(drain, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for cid, epoch in (("k1", 1), ("w1", 4)):
            fh.write(json.dumps({"content_hash": cid, "agent": "dev-01", "host": "hostA", "created_at_epoch": epoch}) + "\n")
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": "dev-01", "host": "hostA", "since_watermark": 0, "next_watermark": 9000, "counts": {"in_scope": 2}}, fh)
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert not os.path.exists(ta.proj(out, COORD)), sorted(ta.tree(out))
    assert report(out)["watermarks"] == {"dev-01@hostA": 9000}, report(out)["watermarks"]


def test_an_unbound_author_of_a_shared_slice_gets_no_project_corpus(tmp: str) -> None:
    """Re-review round 2, F1: the unbound role is the AUTHOR of a slice it shares with a bound role, so it is in the
    drain's claims files though it has no per-role slice. The slice is the bound owner's and is written (drain of
    2026-11-08, replay defect 1); the unbound author gets no index of its own."""
    drain, claims_dir, out = ta.build(tmp, {"beta": ta.claims("beta", [
        {"class": "workflow", "topic": "s", "title": "T", "body": "Shared.", "evidence": ["h1"], "shared_with": ["alpha"]}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert report(out)["held_back"] == [], report(out)["held_back"]
    assert os.path.isdir(ta.proj(out, "shared")), sorted(ta.tree(out))
    assert not os.path.exists(ta.proj(out, "beta")), sorted(ta.tree(out))
    assert report(out)["roles"] == ["alpha"], report(out)["roles"]


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
    assert os.path.isfile(ta.proj(out, "beta", "workflow.md")) and report(out).get("rehomed", []) == []


def test_a_shared_slice_is_refused_when_no_owner_is_bound(tmp: str) -> None:
    """A shared slice is listed by every owner's index. With a bound owner it is written, and the unbound owner is left
    out of the indexes (drain of 2026-11-08: a slice shared by an unbound and a bound role); with none
    bound the run is refused, naming the owners, and writes when the taxonomy binds one."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"], "shared_with": ["beta"]}])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert report(out)["held_back"] == [] and os.path.isdir(ta.proj(out, "shared")), sorted(ta.tree(out))
    assert not os.path.exists(ta.proj(out, "beta")), sorted(ta.tree(out))
    shared = ta.read(os.path.join(ta.proj(out, "shared"), "workflow-w.md"))
    head = shared.split("\n---\n")[0]
    # The owner list is a corpus fact kept as recorded: dropping the unbound owner left a one-owner intersection, which lint
    # refuses (replay of #519 at 96595a24).
    assert "alpha" in head and "beta" in head, "the written slice keeps both owners in shared_with:\n" + shared
    assert "workflow-w.md" in "".join(ta.read(os.path.join(d, f)) for d, _, fs in os.walk(ta.proj(out, "alpha")) for f in fs if f.startswith("INDEX")), \
        "positive control: the bound owner's index lists the slice"

    drain, claims_dir, out = ta.build(os.path.join(tmp, "none"), {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"], "shared_with": ["beta"]}])})
    bind(out, "gamma")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "workflow:w" in proc.stderr and "role alpha shared with beta" in proc.stderr, (proc.returncode, proc.stderr)
    assert not os.path.exists(os.path.join(ta.proj(out, "shared"))), sorted(ta.tree(out))
    bind(out, "alpha", "beta")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0 and os.path.isdir(ta.proj(out, "shared")), proc.stderr


def test_an_unbound_owner_with_a_directory_already_is_reindexed_from_shared_with(tmp: str) -> None:
    """Replay of #531 at d1e1f1f8 (herdr): python-dev is unbound but has its directory from before the binding. This run
    writes it no entry (unindexed_owners), yet the re-index of an existing directory lists every shared slice on disk whose
    shared_with names the role, so the entry stays, as it does in the repository. Pinned so it is a decision, not a
    surprise; the control is the same bundle with no directory, where beta gets none."""
    for existing in (True, False):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out = ta.build(sub, {"alpha": ta.claims("alpha", [
                {"class": "workflow", "topic": "w", "title": "T", "body": "The body.", "evidence": ["h1"], "shared_with": ["beta"]}])})
            bind(out, "alpha")
            if existing:
                os.makedirs(ta.proj(out, "beta"))
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, proc.stderr
            index = os.path.join(ta.proj(out, "beta"), "INDEX.md")
            listed = os.path.isfile(index) and "workflow-w.md" in ta.read(index)
            assert listed == existing, (existing, sorted(ta.tree(out)))


def test_an_unbound_owner_of_a_claim_moved_by_merge_target_is_not_indexed(tmp: str) -> None:
    """Review of #531 at aa300433, F1: the claim shared with the unbound beta names a section another shared topic holds, so it
    moves there and carries its owners; beta must still get no index and no project directory (the control: gamma, bound, does)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "h", "title": "Old", "body": "Old body.", "evidence": ["h1"], "shared_with": ["gamma"]}])})
    bind(out, "alpha", "gamma")
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(ta.claims("alpha", [
            {"class": "workflow", "topic": "t", "title": "New", "body": "New body.", "evidence": ["h1"],
             "shared_with": ["beta", "gamma"], "merge_target": "Old"}]), fh)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "New body." in ta.read(os.path.join(ta.proj(out, "shared"), "workflow-h.md")), "positive control: the claim moved"
    assert os.path.isdir(ta.proj(out, "gamma")), "positive control: the bound owner is indexed"
    assert not os.path.exists(ta.proj(out, "beta")), sorted(ta.tree(out))


def test_an_unbound_owner_keeps_its_index_entry_for_a_shared_domain_slice(tmp: str) -> None:
    """Re-review of #531, F3: the unbound beta is a co-owner of a project-class shared slice (left out of the indexes) and of a
    shared domain slice, which the taxonomy never judges; the domain slice stays in beta's index. The control: with no
    project-class claim beta is indexed as before."""
    for with_project_claim in (True, False):
        with tempfile.TemporaryDirectory() as sub:
            items = [{"class": "domain", "topic": "field", "title": "F", "body": "Field.", "evidence": ["h1"], "shared_with": ["alpha"]}]
            if with_project_claim:
                items.append({"class": "workflow", "topic": "s", "title": "S", "body": "Shared.", "evidence": ["h1"], "shared_with": ["alpha"]})
            drain, claims_dir, out = ta.build(sub, {"beta": ta.claims("beta", items)})
            bind(out, "alpha")
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, proc.stderr
            index = os.path.join(ta.proj(out, "beta"), "INDEX.md")
            assert os.path.isfile(index) and "domain-field.md" in ta.read(index), (with_project_claim, sorted(ta.tree(out)))


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
    proc = ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene")
    assert proc.returncode == 0, proc.stderr
    written = ta.read(ta.proj(out, "alpha", "solution.md"))
    assert "*Anchors: `gzapp:src/b.py::marker`*" in written, written
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(ta.claims("alpha", [anchored(["src/b.py::marker"])]), fh)
    proc = ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene")
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
            proc = ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene")
            assert proc.returncode == 0, (corpus_anchor, proc.stderr)
            if other_checkout == "lacks":
                seed_file(out, "gzapp/src/b.py", "nothing\n")
            with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
                json.dump(ta.claims("alpha", [anchored([incoming])]), fh)
            proc = ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene")
            assert proc.returncode == 0, (corpus_anchor, incoming, proc.stderr)
            text = ta.read(ta.proj(out, "alpha", "solution.md"))
            assert f"*Anchors: `{incoming}`*" in text, (corpus_anchor, incoming, text)
            assert report(out).get("anchors_kept", []) == [], report(out)


def test_a_resolving_corpus_anchor_replaced_by_one_that_is_gone_is_reported_not_changed(tmp: str) -> None:
    """Drain of 2026-11-08 replay (b): the memory's newer anchor names another file, or another string of the same file,
    and names nothing, over the corpus's anchor that resolves. Nothing pairs the two safely, so the claim is written as it
    stands and the report names both with the author. The controls: a new anchor that resolves, and a corpus anchor that
    was gone already, tell nothing."""
    cases = (
        ("path", "gzapp:src/b.py::marker", "gzapp:src/c.py::marker", True, True),
        ("literal", "gzapp:src/b.py::a marker", "gzapp:src/b.py::a marker's", True, True),
        ("control: the new anchor resolves", "gzapp:src/b.py::marker", "gzapp:src/c.py::marker", True, False),
        ("control: the old one is gone too", "gzapp:src/b.py::marker", "gzapp:src/c.py::marker", False, True),
    )
    for name, corpus_anchor, incoming, old_there, new_is_gone in cases:
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out = ta.build(sub, {"alpha": ta.claims("alpha", [anchored([corpus_anchor])])})
            ta.with_agents(drain, {"h1": "dev-01"})
            seed_file(out, "gzapp/src/b.py", "a marker\n")
            ta.write_registry(out)
            assert ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene").returncode == 0
            seed_file(out, "gzapp/src/b.py", "a marker\n" if old_there else "nothing\n")
            if not new_is_gone:
                seed_file(out, "gzapp/src/c.py", "a marker\n")
            with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
                json.dump(ta.claims("alpha", [anchored([incoming])]), fh)
            proc = ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene")
            assert proc.returncode == 0, (name, proc.stderr)
            assert f"*Anchors: `{incoming}`*" in ta.read(ta.proj(out, "alpha", "solution.md")), name
            assert report(out)["anchors_kept"] == [], name
            want = [{"slice": "alpha/solution:one", "heading": "T", "lost": corpus_anchor, "gained": incoming, "agent": "dev-01",
                     "host": "hostA", "memory": "one"}] if name in ("path", "literal") else []
            assert report(out)["anchors_lost"] == want, (name, report(out)["anchors_lost"])
            assert (f"{corpus_anchor} -> {incoming}" in proc.stderr) == bool(want), (name, proc.stderr)


def test_a_checkout_given_by_working_copy_project_dir_is_where_the_guard_judges(tmp: str) -> None:
    """Drain of 2026-11-08 replay (a): the drain's checkouts sat under its own directory, beside nothing, and lint was told
    where with `--working-copy PROJECT=DIR`; the guard looked only beside the tree, found nothing, read the corpus's
    anchor as unknown and let the harvest's old one replace it. Given by the flag, the checkout is the one the guard
    judges in. The control: a project the map does not name stays unknown, and unknown is never swapped."""
    for name, mapped in (("given", True), ("control: not given", False)):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out = ta.build(sub, {"alpha": ta.claims("alpha", [anchored(["gzapp:src/b.py::marker"])])})
            ta.with_agents(drain, {"h1": "dev-01"})
            ta.write_registry(out)
            elsewhere = os.path.join(sub, "drain-wt", "gzapp")          # beside no tree of this run
            seed_file(elsewhere, "src/b.py", "a marker\n")
            flag = ("--working-copy", f"gzapp={elsewhere}") if mapped else ()
            # The corpus is written with the anchor in place: the first run has no standing anchor to compare with.
            assert ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene", *flag).returncode == 0
            with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
                json.dump(ta.claims("alpha", [anchored(["src/b.py::marker"])]), fh)
            proc = ta.run_assemble(drain, claims_dir, out, "--allow-missing-hygiene", *flag)
            assert proc.returncode == 0, (name, proc.stderr)
            text = ta.read(ta.proj(out, "alpha", "solution.md"))
            if mapped:
                # incoming `src/b.py::marker` is judged in the demo project's own tree (gone) and the corpus's in the mapped one
                assert "*Anchors: `gzapp:src/b.py::marker`*" in text and "`src/b.py::marker`" not in text, text
                assert [r["kept"] for r in report(out)["anchors_kept"]] == ["gzapp:src/b.py::marker"], report(out)
            else:
                assert "*Anchors: `src/b.py::marker`*" in text, text
                assert report(out)["anchors_kept"] == [], report(out)


def test_a_working_copy_project_dir_that_is_no_directory_is_refused_with_its_name(tmp: str) -> None:
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [anchored(["a.py"])])})
    missing = os.path.join(tmp, "no-such-checkout")
    proc = ta.run_assemble(drain, claims_dir, out, "--working-copy", f"gzapp={missing}")
    assert proc.returncode == 2 and f"gzapp={missing}" in proc.stderr, (proc.returncode, proc.stderr)
    assert not os.path.exists(ta.proj(out, "alpha", "solution.md"))


def test_the_own_project_form_and_the_malformed_working_copy_arguments(tmp: str) -> None:
    """lint's `--working-copy PROJECT=DIR` for the run's own project is the checkout the corpus is written in, as the bare
    flag is (it was parsed and dropped); two different checkouts for it, two bare flags and `=DIR` are refused."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [anchored(["a.py"])])})
    wc = ta.working_copy(out)
    os.makedirs(os.path.join(wc, ".agent-fabric"), exist_ok=True)
    base = [sys.executable, ta.ASSEMBLE, "--claims", claims_dir, "--drain", drain, "--fabric", out, "--project", ta.PROJECT,
            "--stamp", "2026-01-01"]
    other = os.path.join(tmp, "other")
    os.makedirs(other)
    for name, flags, want in (
            ("own form alone", [f"{ta.PROJECT}={wc}"], 0),
            ("own form beside the same bare", [wc, f"{ta.PROJECT}={wc}"], 0),
            ("own form beside another bare", [other, f"{ta.PROJECT}={wc}"], 2),
            ("two bare", [wc, other], 2),
            ("no project", [f"={wc}"], 2)):
        argv = base + [a for f in flags for a in ("--working-copy", f)]
        proc = subprocess.run(argv, capture_output=True, text=True)
        assert proc.returncode == want, (name, proc.returncode, proc.stderr)
        if want == 2:
            assert "--working-copy" in proc.stderr, (name, proc.stderr)
    assert os.path.exists(ta.proj(out, "alpha", "solution.md")), "positive control: the own form wrote the corpus in the checkout"
    assert not os.path.exists(os.path.join(other, ".agent-fabric")), "nothing was written to the checkout that was refused"


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


def test_a_title_made_one_line_is_told_for_a_slice_written_with_an_unbound_co_owner(tmp: str) -> None:
    """Replay review F1: the entry is named by the slice the claim is filed under, "shared/" for a shared one."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "w", "title": "A\nB", "body": "Shared.", "evidence": ["h1"], "shared_with": ["beta"]},
        {"class": "workflow", "topic": "own", "title": "C\nD", "body": "Own.", "evidence": ["h1"]}])})
    bind(out, "alpha")      # alpha owns "own" and shares "w" with the unbound beta: both are written
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert sorted(r["slice"] for r in report(out)["titles_one_lined"]) == ["alpha/workflow:own", "shared/workflow:w"], report(out)["titles_one_lined"]
    assert "TITLES MADE ONE LINE" in proc.stderr, proc.stderr


def test_a_title_made_one_line_is_told_as_hygiene_leaves_it_and_not_for_a_refused_claim(tmp: str) -> None:
    """Round 7-8: the report is committed, so it carries the title hygiene screened and never the text before the break
    was made a space (a lookbehind that needs the space does not match across the break), and a claim hygiene refuses
    gets no entry for a slice that received nothing."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "kept", "title": "Springfield\nnotes", "body": "Fine.", "evidence": ["h1"]},
        {"class": "workflow", "topic": "handle", "title": "Fork with clone\nsomeuser/tool", "body": "Fine.", "evidence": ["h1"]},
        {"class": "workflow", "topic": "runs", "title": "A\nB\r\n\nC", "body": "Fine.", "evidence": ["h1"]},
        {"class": "workflow", "topic": "refused", "title": "E\nF", "body": "Questo \u00e8 molto importante, sono qui.", "evidence": ["h1"]}])})
    os.makedirs(os.path.join(ta.working_copy(out), ".agent-fabric"), exist_ok=True)
    with open(os.path.join(ta.working_copy(out), ".agent-fabric", "hygiene.json"), "w", encoding="utf-8") as fh:
        json.dump({"patterns": [{"pattern": "\\bspringfield\\b", "flags": "i", "label": "city name"},
                                {"pattern": "(?<=clone )\\S+", "label": "handle"}]}, fh)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "alpha/workflow:refused: reads as non-English" in proc.stderr, proc.stderr   # the refusal is the run's exit
    rows = report(out)["titles_one_lined"]
    assert [r["slice"] for r in rows] == ["alpha/workflow:kept", "alpha/workflow:handle", "alpha/workflow:runs"], rows
    assert [r["title"] for r in rows] == ["[redacted] notes", "Fork with clone [redacted]", "A B C"], rows
    assert [r["breaks"] for r in rows] == [1, 1, 2], rows      # runs of breaks, not breaks: "\r\n\n" is one
    assert "springfield" not in json.dumps(rows).lower() + proc.stderr.lower() and "someuser" not in json.dumps(rows) + proc.stderr, (rows, proc.stderr)


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
    assert report(out)["titles_one_lined"] == [{"slice": "alpha/domain:one", "breaks": 1,
                                                "title": "Compose the sections of a message"}], report(out)["titles_one_lined"]
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
    # And lint reads that entry as the writer wrote it, not as drift from the decoded break.
    index_path = ta.proj(out, "alpha", "INDEX.md")
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(index.replace("— Double  space stays\n", "— Older break\n"))
    lint = subprocess.run([sys.executable, ta.LINT, "--fabric", out, "--working-copy", f"{ta.PROJECT}={ta.working_copy(out)}"],
                          capture_output=True, text=True)
    assert lint.returncode == 0 and "describes it as" not in lint.stderr, lint.stderr
    import lint as lint_module
    from assembler.core import LINE_BREAK_RE
    assert lint_module.LINE_BREAK_RE.pattern == LINE_BREAK_RE.pattern, "lint reads a break as the INDEX writer makes it"


def refusal(tmp: str, files: dict[str, dict]) -> subprocess.CompletedProcess:
    drain, claims_dir, out = ta.build(tmp, files)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    return proc


def never_named(proc: subprocess.CompletedProcess) -> None:
    """The fixture project bans "Springfield" (test_assemble.HYGIENE): neither stream may carry it, in any case."""
    assert "springfield" not in (proc.stdout + proc.stderr).lower(), proc.stdout + proc.stderr


def test_a_refusal_before_the_hygiene_screen_does_not_print_a_banned_name_from_a_claim(tmp: str) -> None:
    """Round 2-3 of #589: the scope and anchor refusals printed the claim's title, topic, class and anchor as written, to
    the operator's terminal and any log, before screen_hygiene ran. Each still names the file, the claim's index and the
    title as screened, so the operator finds it. The positive control is the same claim with a title that is not banned."""
    def domain_only(title: str) -> dict:
        return {"class": "solution", "topic": "t", "title": title, "body": "B.", "evidence": ["h1"], "knowledge_scope": "domain-only"}
    ok = refusal(os.path.join(tmp, "a"), {"alpha": ta.claims("alpha", [domain_only("Plain notes")])})
    assert "'alpha.json': claim 0 'Plain notes' is domain-only" in ok.stderr, ok.stderr
    proc = refusal(os.path.join(tmp, "b"), {"alpha": ta.claims("alpha", [domain_only("Springfield notes")])})
    never_named(proc)
    assert "'alpha.json': claim 0 '[redacted] notes' is domain-only" in proc.stderr, proc.stderr
    no_title = domain_only("x")
    del no_title["title"]
    no_title["topic"] = "springfield-topic"
    proc = refusal(os.path.join(tmp, "c"), {"alpha": ta.claims("alpha", [no_title])})
    never_named(proc)
    assert "'alpha.json': claim 0" in proc.stderr, proc.stderr
    proc = refusal(os.path.join(tmp, "d"), {"alpha": ta.claims("alpha", [domain_only("T")])} | {"springfield-file": ta.claims("beta", [domain_only("T")])})
    never_named(proc)
    assert "'[redacted]-file.json': claim 0" in proc.stderr, proc.stderr
    proc = refusal(os.path.join(tmp, "e"), {"alpha": ta.claims("alpha", [{**domain_only("T"), "class": "Springfield"}])})
    never_named(proc)


def test_a_banned_text_that_repr_would_escape_is_screened_before_it_is_quoted(tmp: str) -> None:
    """Review F1: screening repr(title) missed a hit whose text repr rewrites (a quote beside a double quote, a tab). The
    credential pattern is the built-in one; the project's own city is the control that a plain title is still screened."""
    def refused_title(title: str, sub: str) -> str:
        claim = {"class": "solution", "topic": "t", "title": title, "body": "B.", "evidence": ["h1"], "knowledge_scope": "domain-only"}
        return refusal(os.path.join(tmp, sub), {"alpha": ta.claims("alpha", [claim])}).stderr
    err = refused_title("password='hunter2secret' said \"x\"", "a")
    assert "hunter2secret" not in err and "claim 0" in err, err
    err = refused_title("Bearer\tabcdefghijklmnopqrstuvwxyz0123", "b")
    assert "abcdefghijklmnopqrstuvwxyz0123" not in err and "claim 0" in err, err
    err = refused_title("it's Springfield \"x\"", "c")
    assert "pringfield" not in err and "claim 0" in err, err


def test_the_rehome_refusal_does_not_print_a_banned_role_or_owner(tmp: str) -> None:
    """Review, pre-existing: a role id the regex admits can be a banned word, and the refusal for an unbound role named it."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), "springfield": ta.claims("springfield", [WF])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode != 0 and "not admitted" in proc.stderr, proc.stderr
    never_named(proc)
    assert "of role [redacted]" in proc.stderr, proc.stderr
    owned = {**WF, "topic": "o", "shared_with": ["springfield"]}
    drain, claims_dir, out = ta.build(os.path.join(tmp, "o"), {"alpha": ta.claims("alpha", [WF]), "beta": ta.claims("beta", [owned])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode != 0 and "not admitted" in proc.stderr, proc.stderr
    never_named(proc)
    assert "shared with [redacted]" in proc.stderr, proc.stderr


def test_an_anchor_refusal_does_not_print_a_banned_name_from_a_claim(tmp: str) -> None:
    ok = refusal(os.path.join(tmp, "a"), {"alpha": ta.claims("alpha", [anchored("not a list", title="Plain notes")])})
    assert "'alpha': claim 0 'Plain notes': anchors is not a list of strings" in ok.stderr, ok.stderr
    cut = "docs/" + "x" * 30 + " Bearer abcdefghijklmnopqrstuvwxyz0123"   # a 60-character cut leaves 17 of the token, under the pattern's 20
    proc = refusal(os.path.join(tmp, "cut"), {"alpha": ta.claims("alpha", [anchored([cut])])})
    assert "abcdefghijklmnopq" not in proc.stderr and "claim 0" in proc.stderr, proc.stderr
    for n, extra in enumerate([{"title": "Springfield notes"}, {"title": "T", "anchors": ["springfield:src/a.py"]},
                               {"title": "T", "class": "Springfield"}, {"title": "T", "anchors": ["x"] * 99 + ["Springfield"]}]):
        claim = anchored("not a list") | extra
        proc = refusal(os.path.join(tmp, f"b{n}"), {"alpha": ta.claims("alpha", [claim])})
        never_named(proc)
        assert "'alpha': claim 0" in proc.stderr, proc.stderr


def test_a_valid_role_id_that_is_a_banned_name_is_screened_in_an_anchor_refusal(tmp: str) -> None:
    """A role id the regex admits can still be a banned word (the project's own city)."""
    proc = refusal(tmp, {"alpha": ta.claims("springfield", [anchored("not a list")])})
    never_named(proc)
    assert "'[redacted]': claim 0" in proc.stderr, proc.stderr


def test_a_role_id_refusal_does_not_print_a_banned_name(tmp: str) -> None:
    """The claims file's role and a claim's shared_with are echoed by role_id_error before they are known to be role ids."""
    ok = refusal(os.path.join(tmp, "a"), {"alpha": ta.claims("Plain Role", [])})
    assert "'Plain Role' is not a role id" in ok.stderr, ok.stderr
    proc = refusal(os.path.join(tmp, "b"), {"alpha": ta.claims("Springfield", [])})
    never_named(proc)
    assert "'[redacted]' is not a role id" in proc.stderr, proc.stderr
    claim = {"class": "domain", "topic": "t", "title": "T", "body": "B.", "evidence": ["h1"], "shared_with": ["Springfield"]}
    proc = refusal(os.path.join(tmp, "c"), {"alpha": ta.claims("alpha", [claim])})
    never_named(proc)
    assert "shared_with names '[redacted]' is not a role id" in proc.stderr, proc.stderr


def set_hygiene(out: str, *patterns: dict) -> None:
    with open(os.path.join(ta.working_copy(out), ".agent-fabric", "hygiene.json"), "w", encoding="utf-8") as fh:
        json.dump({"patterns": list(patterns)}, fh)


ZORG = {"pattern": "\\bzorg\\b", "flags": "i", "label": "a name the corpus must not carry"}


def test_f1_a_banned_topic_or_title_reaches_neither_the_report_nor_the_commit_body_nor_stderr(tmp: str) -> None:
    """j227 review round 1 F1: the re-homed rows were built before hygiene screened the claim, so a banned name in the topic
    or title was carried to last-drain-report.json, the commit body and stderr, though the slice itself was redacted.
    Control: with no hygiene list the same claim is named there (the fixture can see the text), and so is a refusal."""
    claim = {**WF, "topic": "zorg-habit", "title": "The zorg habit", "body": "Plain body.", "evidence": ["h2"]}
    msg = os.path.join(tmp, "msg.txt")
    drain, claims_dir, out = ta.build(os.path.join(tmp, "control"), {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [claim])})
    bind(out, "alpha")
    set_hygiene(out)
    proc = ta.run_assemble(drain, claims_dir, out, "--commit-message", msg)
    assert proc.returncode == 0, proc.stderr
    seen = [ta.read(ta.report_path(out)), ta.read(msg), proc.stderr]
    assert all("zorg" in text.lower() for text in seen), "positive control: unscreened, every channel names it"
    drain, claims_dir, out = ta.build(os.path.join(tmp, "screened"), {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [claim])})
    bind(out, "alpha")
    set_hygiene(out, ZORG)
    proc = ta.run_assemble(drain, claims_dir, out, "--commit-message", msg)
    assert proc.returncode == 0, proc.stderr
    assert "redacted" in ta.read(fabric_proj(out, COORD, "workflow.md")).lower()
    rep = report(out)
    assert [r["slice"] for r in rep["rehomed"]] == [f"{COORD}/workflow:redacted-habit"], rep["rehomed"]
    for name, text in (("report", ta.read(ta.report_path(out))), ("commit body", ta.read(msg)), ("stderr", proc.stderr)):
        assert "zorg" not in text.lower(), (name, text)
    # The refusal line of another role's claim is screened the same way.
    drain, claims_dir, out = ta.build(os.path.join(tmp, "refuse"), {"alpha": ta.claims("alpha", [WF]), "beta": ta.claims("beta", [claim])})
    bind(out, "alpha")
    set_hygiene(out)
    assert "zorg" in ta.run_assemble(drain, claims_dir, out).stderr.lower(), "positive control: the refusal names the claim"
    set_hygiene(out, ZORG)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "role beta" in proc.stderr and "zorg" not in proc.stderr.lower(), proc.stderr


def test_f2_a_collision_in_the_rehome_pass_is_decided_by_the_owner_and_the_rerun_carries_it(tmp: str) -> None:
    """F2: --collision-decisions was cleared for the control plane's pass, so its collision could never be decided and the
    drain was stuck. The decision file serves both passes; the decision is recorded in the project's report."""
    two = [{**WF, "topic": "moved", "body": "One.", "evidence": ["h2"]}, {**WF, "topic": "moved", "body": "Two.", "evidence": ["h2"]}]
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, two)})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and f"{COORD}/workflow:moved#T" in proc.stderr, proc.stderr
    proc = ta.run_assemble(drain, claims_dir, out, *ta.keep_both(tmp, f"{COORD}/workflow:moved#T"))
    assert proc.returncode == 0, proc.stderr
    text = ta.read(fabric_proj(out, COORD, "workflow.md"))
    assert "One." in text and "Two." in text, text
    assert [d["key"] for d in report(out)["collision_decisions"]] == [f"{COORD}/workflow:moved#T"], report(out)["collision_decisions"]


def fabric_report(out: str) -> dict:
    with open(os.path.join(out, ".agent-fabric", "memory", "last-drain-report.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_f3_what_the_rehome_pass_replaced_is_recorded_in_the_control_planes_report_and_a_replay_keeps_it(tmp: str) -> None:
    """F3: a correction applied in the re-home pass was recorded nowhere, so a replay of the old bundle wrote the replaced text
    back into agent-fabric's corpus."""
    old = {**WF, "topic": "one", "title": "The finding", "body": "The old fact.", "evidence": ["h2"]}
    fix = {**WF, "topic": "fix-one", "title": "The finding, corrected", "merge_target": "The finding", "body": "The new fact.",
           "evidence": ["h3"]}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [old])})
    ta.with_agents(drain, {"h2": "dev-01", "h3": "dev-02"})
    bind(out, "alpha")
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    with open(os.path.join(claims_dir, f"{COORD}.json"), "w", encoding="utf-8") as fh:
        json.dump(ta.claims(COORD, [fix]), fh)
    assert ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02").returncode == 0
    rep = fabric_report(out)
    assert [e["replaced"] for e in rep["applied_corrections"]] == ["The finding"], rep["applied_corrections"]
    assert [e["heading"] for e in rep["replaced_sections"]] == ["The finding"], rep["replaced_sections"]
    assert any("The finding, corrected" in k for k in rep["section_writers"]), rep["section_writers"]
    def corpus() -> str:
        """Every slice of the coordinator's re-homed workflow corpus (flat or one file per topic), without its index."""
        root = fabric_proj(out, COORD)
        return "".join(ta.read(os.path.join(d, n)) for d, _ds, fs in sorted(os.walk(root)) for n in sorted(fs)
                       if n.endswith(".md") and n != "INDEX.md")
    corrected = corpus()
    assert "The new fact." in corrected and "The old fact." not in corrected, corrected
    # The old bundle again, a later pass of the same drain.
    with open(os.path.join(claims_dir, f"{COORD}.json"), "w", encoding="utf-8") as fh:
        json.dump(ta.claims(COORD, [old]), fh)
    proc = ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02")
    assert proc.returncode == 0, proc.stderr
    assert corpus() == corrected, corpus()


def test_f4_the_notes_of_the_rehome_pass_reach_the_projects_report_and_its_files_are_checked_for_links(tmp: str) -> None:
    """F4: titles made one line and the pass's links were dropped; the pass's notes are the run's."""
    claim = {**WF, "topic": "moved", "title": "Line one\nline two", "body": "See [[no-such-topic-anywhere]].", "evidence": ["h2"]}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [claim])})
    bind(out, "alpha")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    rep = report(out)
    assert [r["slice"] for r in rep["titles_one_lined"]] == [f"{COORD}/workflow:moved"], rep["titles_one_lined"]
    assert "TITLES MADE ONE LINE" in proc.stderr, proc.stderr
    assert [r["target"] for r in rep["unresolved_links"] if r["slice"].endswith(f"{COORD}/workflow.md")] == ["no-such-topic-anywhere"], \
        rep["unresolved_links"]


def test_f6_the_rehome_pass_updates_the_control_planes_report_in_its_record_keys_only(tmp: str) -> None:
    """F6: agent-fabric's report at another stamp than the project's drain (the ordinary case) was replaced by the pass's, so
    its harvest, memory marks, horizons, held-back claims and telemetry went and the project's roles entered its telemetry.
    Control: the record keys the pass wrote are in it."""
    kept = {"stamp": "2025-12-01", "project": "agent-fabric", "roles": ["fabric-coordinator"], "files": [], "files_written": 0,
            "harvest": {"read": 3}, "harvest_sources": {"a@h": {"read": 3}}, "memory_marks": {"s1": [["h", 1]]},
            "memory_use": {"x": 1}, "review_horizons": {"r": "2026-01-01"}, "held_back": [{"slice": "k"}],
            "title_collisions": [{"t": "u"}], "unresolved_links": [{"slice": "k", "target": "t"}], "memory_flags": [{"f": 1}],
            "telemetry": {"fabric-coordinator": {"n": 5}}, "telemetry_sources": {"a@h": {"fabric-coordinator": {"n": 5}}},
            "watermarks": {"h": 7},
            "collision_decisions": [{"key": "k#T", "decision": "keep-both"}], "retitles": [{"key": "k#U", "to": "V"}]}
    claim = {**WF, "topic": "moved", "title": "Moved", "evidence": ["h2"]}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [claim])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-02"})
    bind(out, "alpha")
    path = os.path.join(out, ".agent-fabric", "memory", "last-drain-report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kept, fh)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    rep = fabric_report(out)
    assert {k: v for k, v in rep.items() if k in kept} == kept, {k: v for k, v in rep.items() if k in kept}
    assert any(COORD in k for k in rep["section_writers"]), "control: the pass's record is there: " + str(rep["section_writers"])
    assert rep["stamp"] == "2025-12-01" and set(rep["telemetry"]) == {"fabric-coordinator"}, (rep["stamp"], rep["telemetry"])


def rehome_fixture(tmp: str) -> tuple[str, str, str, str]:
    claim = {**WF, "topic": "moved", "title": "Moved", "evidence": ["h2"]}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [claim])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-02"})
    bind(out, "alpha")
    path = os.path.join(out, ".agent-fabric", "memory", "last-drain-report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return drain, claims_dir, out, path


def test_f6_with_no_report_of_its_own_the_rehome_pass_writes_only_its_record_keys(tmp: str) -> None:
    """F6 path 2: the drained project's stamp and its roles' telemetry were written as agent-fabric's own. Control: the pass's
    record is written."""
    drain, claims_dir, out, _path = rehome_fixture(tmp)
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    rep = fabric_report(out)
    assert any(COORD in k for k in rep["section_writers"]), "control: " + str(rep)
    assert set(rep) == {"project", "section_writers", "applied_corrections", "replaced_sections", "collision_decisions", "retitles"}, sorted(rep)
    assert rep["project"] == "agent-fabric", rep["project"]


def test_f6_an_unreadable_control_plane_report_is_refused_and_left_as_it_is(tmp: str) -> None:
    """F6 path 2: a report that is no JSON, or no object, took the 'none' path and was overwritten. Control: absent, the same
    run writes."""
    for text in ("{not json", "[1, 2]"):
        drain, claims_dir, out, path = rehome_fixture(os.path.join(tmp, str(len(text))))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = ta.run_assemble(drain, claims_dir, out)
        assert proc.returncode == 1 and "not replaced" in proc.stderr and "Traceback" not in proc.stderr, (proc.returncode, proc.stderr)
        assert ta.read(path) == text, "left as it is"
        assert not os.path.exists(fabric_proj(out, COORD, "workflow.md")), "refused before the pass writes"
        assert not os.path.exists(ta.proj(out, "alpha", "workflow.md")), "nor the project's own"


def test_a_rehome_collision_decision_reaches_the_control_planes_own_report(tmp: str) -> None:
    """The decision of the re-home pass's collision is in agent-fabric's report (record_rehomed), not only the project's: the
    next run forgot a decision the owner had given when the pass's own record was dropped. Control: the project's report has it."""
    two = [{**WF, "topic": "moved", "body": "One.", "evidence": ["h2"]}, {**WF, "topic": "moved", "body": "Two.", "evidence": ["h2"]}]
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, two)})
    bind(out, "alpha")
    key = f"{COORD}/workflow:moved#T"
    proc = ta.run_assemble(drain, claims_dir, out, *ta.keep_both(tmp, key))
    assert proc.returncode == 0, proc.stderr
    assert [d["key"] for d in report(out)["collision_decisions"]] == [key], "control: " + str(report(out)["collision_decisions"])
    assert [d["key"] for d in fabric_report(out)["collision_decisions"]] == [key], fabric_report(out)


def test_an_unreadable_report_of_the_drained_project_is_refused_and_left_as_it_is(tmp: str) -> None:
    """The project's own report was taken for absent and overwritten when it was no JSON or no object, while the re-home pass
    refuses the same input. Control: absent, the same run writes it."""
    for text in ("{not json", "[1, 2]"):
        drain, claims_dir, out = ta.build(os.path.join(tmp, str(len(text))), {"alpha": ta.claims("alpha", [WF])})
        bind(out, "alpha")
        path = ta.report_path(out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        proc = ta.run_assemble(drain, claims_dir, out)
        assert proc.returncode == 1 and path in proc.stderr and "not replaced" in proc.stderr and "Traceback" not in proc.stderr, \
            (proc.returncode, proc.stderr)
        assert ta.read(path) == text, "left as it is"
        assert not os.path.exists(ta.proj(out, "alpha", "workflow.md")), "refused before anything is written"
        assert proc.stderr.strip().count("\n") == 0, "one line: " + proc.stderr
    drain, claims_dir, out = ta.build(os.path.join(tmp, "absent"), {"alpha": ta.claims("alpha", [WF])})
    bind(out, "alpha")
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0, "control"
    assert report(out)["project"] == ta.PROJECT


def test_the_commit_body_counts_what_was_rehomed(tmp: str) -> None:
    """A line the report gives reason for: removing it from commit_message passed every suite (the review's risks)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [{**WF, "topic": "moved", "evidence": ["h2"]}])})
    bind(out, "alpha")
    msg = os.path.join(tmp, "msg.txt")
    assert ta.run_assemble(drain, claims_dir, out, "--commit-message", msg).returncode == 0
    assert f"Re-homed to the control plane's corpus: 1 ({COORD}/workflow:moved)." in ta.read(msg), ta.read(msg)
    bind(out, "alpha", COORD)
    assert ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02", "--commit-message", msg).returncode == 0
    assert "Re-homed" not in ta.read(msg), "control: bound, nothing re-homed, no line"


def test_a_rehomed_claim_the_control_planes_pass_rejects_is_no_rehomed_row(tmp: str) -> None:
    """F1's other half: the rows are of what the control plane's pass kept. A claim it rejected (non-English prose) was not
    re-homed, and the report, the commit body and stderr must not say it was. Control: the English claim beside it is."""
    bad = {**WF, "topic": "bad", "body": "Perche questo quindi anche quello, e questa quella cosa.", "evidence": ["h2"]}
    good = {**WF, "topic": "good", "evidence": ["h2"]}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [WF]), COORD: ta.claims(COORD, [bad, good])})
    bind(out, "alpha")
    msg = os.path.join(tmp, "msg.txt")
    proc = ta.run_assemble(drain, claims_dir, out, "--commit-message", msg)
    assert proc.returncode == 1 and "REJECTED" in proc.stderr, (proc.returncode, proc.stderr)
    assert not os.path.exists(msg), "a failed drain writes no commit message"
    assert "RE-HOMED (1" in proc.stderr, proc.stderr
    assert [r["slice"] for r in report(out)["rehomed"]] == [f"{COORD}/workflow:good"], report(out)["rehomed"]


def main() -> int:
    cases = [
        test_a_coordinator_claim_of_a_project_that_does_not_bind_it_lands_in_the_control_plane,
        test_a_rehomed_claim_is_screened_by_the_control_planes_hygiene_view,
        test_a_refusal_of_the_control_planes_pass_stops_the_run_with_the_projects_corpus_untouched,
        test_a_claim_of_another_unbound_role_refuses_the_run_before_anything_is_written,
        test_a_coordinator_claim_shared_with_another_unbound_role_is_refused,
        test_a_rehomed_role_with_nothing_left_gets_no_project_corpus_and_its_evidence_is_not_held,
        test_an_unbound_author_of_a_shared_slice_gets_no_project_corpus,
        test_the_fabrics_own_project_is_not_judged_by_its_taxonomy,
        test_a_project_with_no_taxonomy_binds_every_role,
        test_a_shared_slice_is_refused_when_no_owner_is_bound,
        test_an_unbound_owner_with_a_directory_already_is_reindexed_from_shared_with,
        test_an_unbound_owner_of_a_claim_moved_by_merge_target_is_not_indexed,
        test_an_unbound_owner_keeps_its_index_entry_for_a_shared_domain_slice,
        test_an_anchor_that_resolves_is_not_replaced_by_one_that_does_not,
        test_an_incoming_anchor_that_resolves_stands_and_so_does_one_that_cannot_be_judged,
        test_a_resolving_corpus_anchor_replaced_by_one_that_is_gone_is_reported_not_changed,
        test_a_checkout_given_by_working_copy_project_dir_is_where_the_guard_judges,
        test_a_working_copy_project_dir_that_is_no_directory_is_refused_with_its_name,
        test_the_own_project_form_and_the_malformed_working_copy_arguments,
        test_a_link_in_a_code_span_is_not_cited,
        test_a_toml_array_header_in_a_code_span_is_not_cited,
        test_a_title_made_one_line_is_told_for_a_slice_written_with_an_unbound_co_owner,
        test_a_title_made_one_line_is_told_as_hygiene_leaves_it_and_not_for_a_refused_claim,
        test_a_break_in_a_title_does_not_split_the_heading_or_cut_the_index_entry,
        test_a_refusal_before_the_hygiene_screen_does_not_print_a_banned_name_from_a_claim,
        test_a_banned_text_that_repr_would_escape_is_screened_before_it_is_quoted,
        test_the_rehome_refusal_does_not_print_a_banned_role_or_owner,
        test_an_anchor_refusal_does_not_print_a_banned_name_from_a_claim,
        test_a_valid_role_id_that_is_a_banned_name_is_screened_in_an_anchor_refusal,
        test_a_role_id_refusal_does_not_print_a_banned_name,
        test_f1_a_banned_topic_or_title_reaches_neither_the_report_nor_the_commit_body_nor_stderr,
        test_f2_a_collision_in_the_rehome_pass_is_decided_by_the_owner_and_the_rerun_carries_it,
        test_f6_the_rehome_pass_updates_the_control_planes_report_in_its_record_keys_only,
        test_f6_with_no_report_of_its_own_the_rehome_pass_writes_only_its_record_keys,
        test_f6_an_unreadable_control_plane_report_is_refused_and_left_as_it_is,
        test_f3_what_the_rehome_pass_replaced_is_recorded_in_the_control_planes_report_and_a_replay_keeps_it,
        test_f4_the_notes_of_the_rehome_pass_reach_the_projects_report_and_its_files_are_checked_for_links,
        test_a_rehome_collision_decision_reaches_the_control_planes_own_report,
        test_an_unreadable_report_of_the_drained_project_is_refused_and_left_as_it_is,
        test_the_commit_body_counts_what_was_rehomed,
        test_a_rehomed_claim_the_control_planes_pass_rejects_is_no_rehomed_row,
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
