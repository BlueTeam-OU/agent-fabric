#!/usr/bin/env python3
"""Behavioural tests for tools/fabric/harvest_memory.py.

Stdlib only; run as `python3 test_harvest_memory.py`. NOT pytest-collectable:
every case takes a `tmp: str`, which pytest would try to resolve as a fixture.

Each case builds a throwaway memory directory and runs the REAL script over
it. The cases that matter most are the REFUSALS: this writes into a shared
repository, so a memory it cannot classify must stop the drain rather than
land somewhere plausible.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tools", "fabric", "harvest_memory.py")
# The claim classes come from the schema the assembler validates against,
# never from a copy in this file: a copy is what drifted and let `index`
# through.
with open(os.path.join(ROOT, "identities", "schemas", "claims.schema.json"), encoding="utf-8") as _fh:
    SCHEMA_CLASSES = tuple(
        json.load(_fh)["properties"]["claims"]["items"]["properties"]["class"]["enum"])


def write_memory(d: str, name: str, mtype: str, body: str = "the fact",
                 roles_class: str | None = None, description: str = "d") -> None:
    extra = f"\n  roles_class: {roles_class}" if roles_class else ""
    with open(os.path.join(d, f"{name}.md"), "w", encoding="utf-8") as fh:
        fh.write(f"---\nname: {name}\ndescription: {description}\n"
                 f"metadata:\n  type: {mtype}{extra}\n---\n\n{body}\n")


def run(mem: str, out: str, *extra: str):
    # A case that names no working copy gets an empty one of its own: the
    # default is this checkout, whose committed drain report carries a real
    # watermark once agent-fabric has been drained, and a fixture memory
    # older than it was silently out of scope (the drain of 2026-09-25).
    if "--working-copy" not in extra:
        wc = out.rstrip(os.sep) + "-wc"
        os.makedirs(os.path.join(wc, ".agent-fabric", "memory"), exist_ok=True)
        extra = ("--working-copy", wc, "--project", "demo", *extra)
    return subprocess.run(
        [sys.executable, TOOL, "--role", "architect-cto", "--memory", mem,
         "--out", out, *extra],
        capture_output=True, text=True)


def claims_of(out: str) -> list[dict]:
    with open(os.path.join(out, "claims", "architect-cto.json"), encoding="utf-8") as fh:
        return json.load(fh)["claims"]


def test_a_memory_in_another_language_drains_through_its_rendering(tmp: str) -> None:
    """A Georgian memory with a `## English` section yields the English as
    the claim and records the language on the observation; one without
    is named under needs_rendering and yields no claim; an English memory
    is untouched. Kills: taking the body verbatim, or dropping the list."""
    mem, out = os.path.join(tmp, "m-ka"), os.path.join(tmp, "o-ka")
    os.makedirs(mem)
    ka = "ქართული ფაქტი: ხაზების აღნიშვნა ქართულია და ეს ავთენტურია.\n\n## English\n\nThe fact in English: the line labels are Georgian and that is authentic."
    write_memory(mem, "rendered", "project", body=ka, roles_class="solution")
    write_memory(mem, "unrendered", "project", body="მხოლოდ ქართული ტექსტი, თარგმანის გარეშე.", roles_class="solution")
    write_memory(mem, "plain", "project", body="An English fact.", roles_class="solution")
    r = run(mem, out)
    assert r.returncode == 0, r.stderr
    got = {c["topic"]: c["body"] for c in claims_of(out)}
    assert got["rendered"].startswith("The fact in English"), got
    assert "ქართული" not in got["rendered"], "the original leaked into the claim"
    assert "unrendered" not in got and got["plain"] == "An English fact.", got
    with open(os.path.join(out, "harvest-report.json"), encoding="utf-8") as fh:
        report = json.load(fh)
    assert report["needs_rendering"] == ["unrendered.md"], report   # filenames, like the skipped list
    with open(os.path.join(out, "observations.jsonl"), encoding="utf-8") as fh:
        obs = {o["title"]: o for o in (json.loads(l) for l in fh if l.strip())}
    assert obs["rendered"]["language"] == "ka" and "language" not in obs["plain"], obs


def test_a_claim_carries_the_date_the_memory_was_written(tmp: str) -> None:
    """The memory's own `modified` stamp, else the file's mtime: the section
    rendered from it carries the date, so two divergent sections on one
    topic read in time order."""
    mem, out = os.path.join(tmp, "m0"), os.path.join(tmp, "o0")
    os.makedirs(mem)
    with open(os.path.join(mem, "stamped.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: stamped\ndescription: d\nmetadata:\n  type: project\n  roles_class: workflow\n"
                 "  modified: 2026-09-12T08:15:00.000Z\n---\n\nthe fact\n")
    write_memory(mem, "unstamped", "project", roles_class="workflow")
    os.utime(os.path.join(mem, "unstamped.md"), (1789113600, 1789113600))   # 2026-09-11 08:00 UTC
    assert run(mem, out).returncode == 0
    got = {c["topic"]: c["observed_at"] for c in claims_of(out)}
    assert got == {"stamped": "2026-09-12", "unstamped": "2026-09-11"}, got


def test_a_quoted_description_is_read_as_yaml_reads_it(tmp: str) -> None:
    """A double-quoted value is unescaped and a single-quoted one undoubled:
    stripping the quotes alone carried the backslash of `\\"` into the
    claim, its heading and the index (gzapi.ge #18). Kills: strip-only."""
    mem, out = os.path.join(tmp, "mq"), os.path.join(tmp, "oq")
    os.makedirs(mem)
    write_memory(mem, "dq", "project", roles_class="workflow", description='"a trailing `echo \\"exit $?\\"` hides it"')
    write_memory(mem, "sq", "project", roles_class="workflow", description="'it''s the last command'")
    assert run(mem, out).returncode == 0
    got = {c["topic"]: c["title"] for c in claims_of(out)}
    assert got == {"dq": 'a trailing `echo "exit $?"` hides it', "sq": "it's the last command"}, got
    # A YAML escape JSON rejects (\\x, a raw tab) must not bring the quotes'
    # backslashes back with it (the review of the fix, 2026-09-26).
    mem2, out2 = os.path.join(tmp, "mq2"), os.path.join(tmp, "oq2")
    os.makedirs(mem2)
    write_memory(mem2, "yx", "project", roles_class="workflow", description='"caf\\xe9 \\"x\\"\tthere"')
    assert run(mem2, out2).returncode == 0
    title = claims_of(out2)[0]["title"]
    assert '\\"' not in title and '"x"' in title, repr(title)


def test_a_cue_in_another_script_needs_its_english(tmp: str) -> None:
    """The index line and the heading are read by every holder of the role
    in every project, so they are English like the body: a non-Latin
    description travels under `description_en`, and without one the memory
    waits under needs_rendering (gzapp #938, F1). Kills: the original
    description as the title."""
    mem, out = os.path.join(tmp, "mc"), os.path.join(tmp, "oc")
    os.makedirs(mem)
    ru = "Русский факт о слиянии веток.\n\n## English\n\nThe fact in English."
    for name, extra in (("cued", '\n  description_en: "Merge is rendered with vlivat"'), ("uncued", "")):
        with open(os.path.join(mem, f"{name}.md"), "w", encoding="utf-8") as fh:
            fh.write(f"---\nname: {name}\ndescription: По-русски merge — вливать\n"
                     f"metadata:\n  type: project\n  roles_class: domain{extra}\n---\n\n{ru}\n")
    assert run(mem, out).returncode == 0
    got = {c["topic"]: c["title"] for c in claims_of(out)}
    assert got == {"cued": "Merge is rendered with vlivat"}, got
    with open(os.path.join(out, "harvest-report.json"), encoding="utf-8") as fh:
        assert json.load(fh)["needs_rendering"] == ["uncued.md"]


def test_merge_target_travels_from_the_memory_to_the_claim(tmp: str) -> None:
    """`merge_target: "<heading>"` in a memory's metadata is the author's own
    supersession; the README promised it and the harvest dropped it. It
    reaches the claim as written; a memory without it carries no key."""
    mem, out = os.path.join(tmp, "mt"), os.path.join(tmp, "ot")
    os.makedirs(mem)
    with open(os.path.join(mem, "newer.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: newer\ndescription: d\nmetadata:\n  type: project\n  roles_class: solution\n"
                 "  merge_target: \"The dictionary has never had a native pass\"\n---\n\nIt has, since the native pass merged.\n")
    write_memory(mem, "plain", "project", roles_class="solution")
    assert run(mem, out).returncode == 0
    got = {c["topic"]: c.get("merge_target") for c in claims_of(out)}
    assert got == {"newer": "The dictionary has never had a native pass", "plain": None}, got


def test_role_knowledge_is_opt_in(tmp: str) -> None:
    """A memory reaches the shared corpus only if it says so. Nothing is
    inferred from `type`: memory has four types, .roles/ has nine classes,
    and `project` alone covers both live threads and durable constraints."""
    mem, out = os.path.join(tmp, "m1"), os.path.join(tmp, "o1")
    os.makedirs(mem)
    write_memory(mem, "opted-in", "feedback", roles_class="workflow")
    write_memory(mem, "not-opted-in", "feedback")
    assert run(mem, out).returncode == 0
    got = {c["topic"]: c["class"] for c in claims_of(out)}
    assert got == {"opted-in": "workflow"}, got


def test_the_class_is_taken_verbatim_not_mapped(tmp: str) -> None:
    """Every class a claim may take must survive, or the vocabulary is
    silently narrower than .roles/ actually uses. The set is the schema's,
    read from it rather than restated, because a restated copy drifted."""
    mem, out = os.path.join(tmp, "m1b"), os.path.join(tmp, "o1b")
    os.makedirs(mem)
    for klass in SCHEMA_CLASSES:
        write_memory(mem, f"m-{klass}", "project", roles_class=klass)
    assert run(mem, out).returncode == 0
    got = {c["class"] for c in claims_of(out)}
    assert got == set(SCHEMA_CLASSES), got


def test_a_generated_class_is_refused(tmp: str) -> None:
    """`index` is produced BY the assembler from the other slices, so it is
    not a class a claim can take: accepting one aborts assembly with
    KeyError: 'index' after slices have already been written. The schema
    enum is the authority, and it does not list it."""
    assert "index" not in SCHEMA_CLASSES, SCHEMA_CLASSES
    mem, out = os.path.join(tmp, "m1gen"), os.path.join(tmp, "o1gen")
    os.makedirs(mem)
    write_memory(mem, "m-index", "project", roles_class="index")
    r = run(mem, out)
    assert r.returncode == 1, r.returncode
    assert "index" in r.stderr, r.stderr


def test_a_skipped_memory_is_named_not_counted(tmp: str) -> None:
    """An omission you can see beats a wrong filing you cannot. A count
    tells you something was left out; the name tells you whether it should
    have been."""
    mem, out = os.path.join(tmp, "m1c"), os.path.join(tmp, "o1c")
    os.makedirs(mem)
    write_memory(mem, "forgot-to-say", "feedback")
    r = run(mem, out)
    assert r.returncode == 0
    assert "forgot-to-say.md" in r.stdout, r.stdout


def test_an_unfamiliar_type_is_not_an_obstacle(tmp: str) -> None:
    """Types are not consulted, so a memory type invented after this was
    written costs nothing. The old design refused the whole drain on one."""
    mem, out = os.path.join(tmp, "m3"), os.path.join(tmp, "o3")
    os.makedirs(mem)
    write_memory(mem, "novel", "some-future-type", roles_class="workflow")
    r = run(mem, out)
    assert r.returncode == 0, r.stderr
    assert [c["topic"] for c in claims_of(out)] == ["novel"]


def test_a_user_memory_needs_no_special_case(tmp: str) -> None:
    """User memories describe the PERSON and this writes into a shared
    repo. Under opt-in they are excluded by simply not opting in — no
    type-specific rule, and nothing of them reaches the output."""
    mem, out = os.path.join(tmp, "m3b"), os.path.join(tmp, "o3b")
    os.makedirs(mem)
    write_memory(mem, "who-they-are", "user", body="prefers terse answers")
    write_memory(mem, "real", "feedback", roles_class="workflow")
    assert run(mem, out).returncode == 0
    assert [c["topic"] for c in claims_of(out)] == ["real"]
    dumped = open(os.path.join(out, "observations.jsonl"), encoding="utf-8").read()
    assert "prefers terse answers" not in dumped, \
        "a user memory reached the observations file"


def test_hand_authored_classes_are_refused(tmp: str) -> None:
    """lint.py exempts charter, brief and recall from derived_from, which is
    what marks them hand-authored. A derived claim must not enter there."""
    for klass in ("charter", "brief", "recall"):
        mem = os.path.join(tmp, f"m5{klass}")
        out = os.path.join(tmp, f"o5{klass}")
        os.makedirs(mem)
        write_memory(mem, "x", "feedback", roles_class=klass)
        r = run(mem, out)
        assert r.returncode == 1, f"{klass} was accepted"
        assert "hand-authored" in r.stderr, r.stderr


def test_unknown_override_class_is_refused(tmp: str) -> None:
    mem, out = os.path.join(tmp, "m6"), os.path.join(tmp, "o6")
    os.makedirs(mem)
    write_memory(mem, "x", "feedback", roles_class="not-a-class")
    r = run(mem, out)
    assert r.returncode == 1
    assert "not-a-class" in r.stderr


def test_index_file_is_not_a_memory(tmp: str) -> None:
    """MEMORY.md is the index and has no frontmatter. Treating it as a
    memory would file the whole table of contents as a claim."""
    mem, out = os.path.join(tmp, "m7"), os.path.join(tmp, "o7")
    os.makedirs(mem)
    with open(os.path.join(mem, "MEMORY.md"), "w", encoding="utf-8") as fh:
        fh.write("- [A](a.md) — hook\n- [B](b.md) — hook\n")
    write_memory(mem, "real", "feedback", roles_class="workflow")
    assert run(mem, out).returncode == 0
    assert [c["topic"] for c in claims_of(out)] == ["real"]


def test_content_hash_follows_the_fact_not_the_file(tmp: str) -> None:
    """Evidence ids must be stable across a rename and must change when the
    fact changes, or a re-drain either duplicates a claim or silently keeps
    a stale one."""
    mem, out = os.path.join(tmp, "m8"), os.path.join(tmp, "o8")
    os.makedirs(mem)
    write_memory(mem, "one", "feedback", body="the original fact", roles_class="workflow")
    assert run(mem, out).returncode == 0
    first = claims_of(out)[0]["evidence"][0]

    # Same name and body, different filename: same evidence.
    os.rename(os.path.join(mem, "one.md"), os.path.join(mem, "renamed.md"))
    out2 = os.path.join(tmp, "o8b")
    assert run(mem, out2).returncode == 0
    assert claims_of(out2)[0]["evidence"][0] == first, "a rename changed the id"

    # Same name, rewritten body: different evidence.
    write_memory(mem, "one", "feedback", body="a rewritten fact", roles_class="workflow")
    os.remove(os.path.join(mem, "renamed.md"))
    out3 = os.path.join(tmp, "o8c")
    assert run(mem, out3).returncode == 0
    assert claims_of(out3)[0]["evidence"][0] != first, "a rewrite kept the id"


def test_wikilinks_become_citations(tmp: str) -> None:
    mem, out = os.path.join(tmp, "m9"), os.path.join(tmp, "o9")
    os.makedirs(mem)
    write_memory(mem, "linked", "feedback", roles_class="workflow",
                 body="see [[other-fact]] and [[third-fact]] and [[other-fact]]")
    assert run(mem, out).returncode == 0
    # An OBJECT keyed by kind, because assemble.py calls .values() on this
    # field; a bare list aborts the run part-way through writing slices.
    # The kind is `memories`: a memory slug is not an artifact reference.
    assert claims_of(out)[0]["citations"] == {
        "memories": ["other-fact", "third-fact"]}, \
        "citations are not an object of deduplicated, sorted wikilinks"


def test_a_memory_without_links_omits_citations(tmp: str) -> None:
    """An empty object, never an empty list: assemble.py's `or {}` hides a
    list only while it is empty, so the list shape would survive here and
    fail on the first memory that actually links to something."""
    mem, out = os.path.join(tmp, "m9b"), os.path.join(tmp, "o9b")
    os.makedirs(mem)
    write_memory(mem, "lonely", "feedback", roles_class="workflow",
                 body="no links here")
    assert run(mem, out).returncode == 0
    assert claims_of(out)[0]["citations"] == {}, claims_of(out)[0]["citations"]


def test_dry_run_writes_nothing(tmp: str) -> None:
    mem, out = os.path.join(tmp, "m10"), os.path.join(tmp, "o10")
    os.makedirs(mem)
    write_memory(mem, "a", "feedback", roles_class="workflow")
    r = run(mem, out, "--dry-run")
    assert r.returncode == 0
    assert not os.path.exists(out), "--dry-run created the output directory"


def test_missing_memory_dir_exits_two(tmp: str) -> None:
    r = run(os.path.join(tmp, "nope"), os.path.join(tmp, "o11"))
    assert r.returncode == 2, r.returncode
    assert "no memory directory" in r.stderr


def test_assemble_gets_the_files_it_requires(tmp: str) -> None:
    """assemble.py opens references.json unconditionally and reads
    observations for provenance; a drain missing either is unusable."""
    mem, out = os.path.join(tmp, "m12"), os.path.join(tmp, "o12")
    os.makedirs(mem)
    write_memory(mem, "a", "feedback", roles_class="workflow")
    assert run(mem, out).returncode == 0
    for required in ("references.json", "observations.jsonl",
                     os.path.join("claims", "architect-cto.json")):
        assert os.path.exists(os.path.join(out, required)), required
    obs = [json.loads(l) for l in
           open(os.path.join(out, "observations.jsonl"), encoding="utf-8") if l.strip()]
    assert obs and {"content_hash", "agent", "host", "project", "working_copy"} <= set(obs[0]), obs[:1]
    # Who learned it is the login, stamped by the resolver; where is a label.
    login = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    assert obs[0]["agent"] == login, obs[0]
    assert "clone_id" not in obs[0]
    # The claim's evidence must point AT an observation, or the slice's
    # derived_from cites nothing that exists.
    assert claims_of(out)[0]["evidence"][0] == obs[0]["content_hash"]


def test_the_assembler_actually_consumes_the_drain(tmp: str) -> None:
    """The one assertion that would have caught three separate defects.
    Every earlier check here looks at filenames and shapes; none ran the
    consumer, and the consumer aborted on this output in three different
    ways -- a references.json read as a role payload, a citations list
    where an object was required, and a class with no slice file."""
    assemble = os.path.join(os.path.dirname(TOOL), "assemble.py")
    if not os.path.exists(assemble):
        return                                   # not a harvester failure
    mem, out = os.path.join(tmp, "m13"), os.path.join(tmp, "o13")
    os.makedirs(mem)
    # A memory of every class, and one carrying a wikilink: the citation
    # shape is only exercised when the list is non-empty.
    for klass in SCHEMA_CLASSES:
        write_memory(mem, f"c-{klass}", "project", roles_class=klass)
    write_memory(mem, "z-linked", "project", roles_class="workflow",
                 body="See [[c-workflow]] for the rest.")
    assert run(mem, out).returncode == 0
    r = subprocess.run(
        [sys.executable, assemble,
         "--claims", os.path.join(out, "claims"), "--drain", out,
         "--fabric", os.path.join(tmp, "assembled13"), "--project", "demo",
         "--working-copy", os.path.join(tmp, "wc-demo"), "--stamp", "2026-01-01"],
        capture_output=True, text=True)
    assert r.returncode == 0, f"assemble failed: {r.stdout}\n{r.stderr}"
    # and the declared telemetry reached it, rather than printing "?"
    assert "admitted=" in r.stdout and "admitted=?" not in r.stdout, r.stdout


def test_an_author_s_merge_target_supersedes_without_a_question(tmp: str) -> None:
    """End to end, from the memory: an author writes a newer memory that
    names the section it replaces; the drain lands it in the section's
    place and asks the owner nothing — the case the README promised and a
    hand-written claims file had been standing in for."""
    assemble = os.path.join(os.path.dirname(TOOL), "assemble.py")
    if not os.path.exists(assemble):
        return
    wc = os.path.join(tmp, "wc-mt"); os.makedirs(os.path.join(wc, ".agent-fabric", "memory"))
    mem = os.path.join(tmp, "m-mt"); os.makedirs(mem)
    write_memory(mem, "dictionary", "project", roles_class="solution", description="The dictionary has never had a native pass",
                 body="Machine-filled, never reviewed by a native speaker.")
    out1 = os.path.join(tmp, "o-mt1")
    assert run(mem, out1, "--working-copy", wc, "--project", "demo", "--host", "hostA").returncode == 0
    fabric = os.path.join(tmp, "assembled-mt")
    r = subprocess.run([sys.executable, assemble, "--claims", os.path.join(out1, "claims"), "--drain", out1,
                        "--fabric", fabric, "--project", "demo", "--working-copy", wc, "--stamp", "2026-01-01"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    slice_path = os.path.join(wc, ".agent-fabric", "memory", "architect-cto", "solution.md")
    assert "never reviewed by a native speaker" in open(slice_path, encoding="utf-8").read()
    # The author retires the old memory and writes the newer one, naming
    # the section it supersedes.
    os.remove(os.path.join(mem, "dictionary.md"))
    with open(os.path.join(mem, "dictionary-native-pass.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: dictionary-native-pass\ndescription: The dictionary has had its native pass\n"
                 "metadata:\n  type: project\n  roles_class: solution\n"
                 "  merge_target: \"The dictionary has never had a native pass\"\n---\n\n"
                 "Reviewed by a native speaker; the machine fill is gone.\n")
    out2 = os.path.join(tmp, "o-mt2")
    assert run(mem, out2, "--working-copy", wc, "--project", "demo", "--host", "hostA", "--all").returncode == 0
    r = subprocess.run([sys.executable, assemble, "--claims", os.path.join(out2, "claims"), "--drain", out2,
                        "--fabric", fabric, "--project", "demo", "--working-copy", wc, "--stamp", "2026-01-02"],
                       capture_output=True, text=True)
    assert r.returncode == 0, "no question asked when the author named the section: " + r.stderr
    assert "SUPERSEDING?" not in r.stderr
    text = open(slice_path, encoding="utf-8").read()
    assert "Reviewed by a native speaker" in text and "never reviewed" not in text, text
    assert text.count("## The dictionary has") == 1 and "(2)" not in text, text


def test_the_watermark_round_trips_through_the_committed_report(tmp: str) -> None:
    """A drain reads only what is newer than the watermark the project's
    last report recorded for this host, writes harvest-report.json with
    the next one, and the assembler carries it into the committed report
    -- so the next drain starts where this one stopped, and an already
    drained memory is not re-read. --all ignores the watermark."""
    assemble = os.path.join(os.path.dirname(TOOL), "assemble.py")
    if not os.path.exists(assemble):
        return
    wc = os.path.join(tmp, "wc-wm"); os.makedirs(os.path.join(wc, ".agent-fabric", "memory"))
    mem = os.path.join(tmp, "m14"); os.makedirs(mem)
    write_memory(mem, "old-fact", "project", roles_class="solution")
    os.utime(os.path.join(mem, "old-fact.md"), (1_000_000, 1_000_000))       # 1970: older than any watermark
    write_memory(mem, "new-fact", "project", roles_class="workflow")
    new_ms = int(os.path.getmtime(os.path.join(mem, "new-fact.md")) * 1000)
    # First drain: no report yet, everything in scope, the watermark is the newest memory read.
    out1 = os.path.join(tmp, "o14a")
    r = run(mem, out1, "--working-copy", wc, "--project", "demo", "--host", "hostA")
    assert r.returncode == 0, r.stderr
    hr = json.load(open(os.path.join(out1, "harvest-report.json"), encoding="utf-8"))
    assert hr["since_watermark"] == 0 and hr["next_watermark"] == new_ms, hr
    assert hr["counts"] == {"in_scope": 2, "total": 2, "before_watermark": 0, "provisional_agent": 0}, hr
    assert "memory_dir" not in hr, "an absolute home path reached the report the assembler carries"
    assert len(claims_of(out1)) == 2
    r = subprocess.run([sys.executable, assemble, "--claims", os.path.join(out1, "claims"), "--drain", out1,
                        "--fabric", os.path.join(tmp, "assembled14"), "--project", "demo",
                        "--working-copy", wc, "--stamp", "2026-01-01"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    committed = json.load(open(os.path.join(wc, ".agent-fabric", "memory", "last-drain-report.json"), encoding="utf-8"))
    me = json.load(open(os.path.join(out1, "harvest-report.json"), encoding="utf-8"))["agent"]
    assert committed["watermarks"] == {f"{me}@hostA": new_ms}, committed.get("watermarks")
    assert committed["harvest"]["next_watermark"] == new_ms and committed["harvest"]["in_scope"] == 2, committed["harvest"]
    # Second drain, nothing new: an empty delta, and the watermark holds.
    out2 = os.path.join(tmp, "o14b")
    r = run(mem, out2, "--working-copy", wc, "--project", "demo", "--host", "hostA")
    assert r.returncode == 0, r.stderr
    hr = json.load(open(os.path.join(out2, "harvest-report.json"), encoding="utf-8"))
    assert hr["since_watermark"] == new_ms and hr["next_watermark"] == new_ms, hr
    assert hr["counts"]["in_scope"] == 0 and hr["counts"]["before_watermark"] == 2, hr
    assert claims_of(out2) == [], "a drained memory was read again"
    # Another host has its own watermark: everything is in scope for it.
    out3 = os.path.join(tmp, "o14c")
    assert run(mem, out3, "--working-copy", wc, "--project", "demo", "--host", "hostB").returncode == 0
    assert len(claims_of(out3)) == 2, "the watermark is per host"
    # --all reads everything regardless.
    out4 = os.path.join(tmp, "o14d")
    assert run(mem, out4, "--working-copy", wc, "--project", "demo", "--host", "hostA", "--all").returncode == 0
    hr = json.load(open(os.path.join(out4, "harvest-report.json"), encoding="utf-8"))
    assert hr["since_watermark"] == 0 and len(claims_of(out4)) == 2, hr


def test_a_bundle_round_trips_and_a_damaged_one_is_refused_by_file(tmp: str) -> None:
    """The bundle is the drain that crosses a host: harvest writes one tar
    with a manifest naming every file and its digest; assemble verifies it
    before reading anything, and names the file when it refuses."""
    import io, tarfile
    assemble = os.path.join(os.path.dirname(TOOL), "assemble.py")
    if not os.path.exists(assemble):
        return
    mem = os.path.join(tmp, "m15"); os.makedirs(mem)
    for klass in SCHEMA_CLASSES:
        write_memory(mem, f"b-{klass}", "project", roles_class=klass)
    bundle = os.path.join(tmp, "drain.tar")
    r = subprocess.run([sys.executable, TOOL, "--role", "architect-cto", "--memory", mem, "--bundle", bundle],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "", "with --bundle FILE nothing but the report may reach stdout (stdout may be the tar)"
    assert '"claims"' in r.stderr, "the report goes to stderr"
    with tarfile.open(bundle) as tar:
        names = tar.getnames()
        assert names[0] == "manifest.json" and "harvest-report.json" in names and "claims/architect-cto.json" in names, names
        manifest = json.load(tar.extractfile("manifest.json"))
    assert manifest["format"] == "agent-fabric-drain/1" and manifest["agent"] and manifest["host"] and manifest["role"] == "architect-cto"
    assert set(manifest["files"]) == set(names) - {"manifest.json"}, manifest["files"]
    # streamed to stdout, byte-identical (deterministic tar)
    r2 = subprocess.run([sys.executable, TOOL, "--role", "architect-cto", "--memory", mem, "--bundle", "-"], capture_output=True)
    assert r2.returncode == 0 and r2.stdout == open(bundle, "rb").read(), "the stdout bundle differs from the file one"
    # the assembler consumes it, from a file and from stdin
    def assemble_bundle(src):
        return subprocess.run([sys.executable, assemble, "--bundle", src, "--fabric", os.path.join(tmp, "assembled15"),
                               "--project", "demo", "--working-copy", os.path.join(tmp, "wc-demo15"), "--stamp", "2026-01-01"],
                              capture_output=True, text=True)
    r = assemble_bundle(bundle)
    assert r.returncode == 0 and "file(s) verified" in r.stdout and "admitted=" in r.stdout, r.stdout + r.stderr
    r = subprocess.run([sys.executable, assemble, "--bundle", "-", "--fabric", os.path.join(tmp, "assembled15b"),
                        "--project", "demo", "--working-copy", os.path.join(tmp, "wc-demo15b"), "--stamp", "2026-01-01"],
                       capture_output=True, input=open(bundle, "rb").read())
    assert r.returncode == 0 and b"file(s) verified" in r.stdout, r.stdout + r.stderr
    # damaged in three ways: a tampered file, a missing file, an extra unnamed file — each refused by name
    def rewrite(mutate):
        out = io.BytesIO()
        with tarfile.open(bundle) as src, tarfile.open(fileobj=out, mode="w") as dst:
            for info in src:
                data = src.extractfile(info).read()
                keep, data = mutate(info.name, data)
                if not keep:
                    continue
                info.size = len(data); dst.addfile(info, io.BytesIO(data))
            extra = mutate("__extra__", b"")
            if extra[0]:
                i = tarfile.TarInfo("claims/stray.json"); i.size = len(extra[1]); dst.addfile(i, io.BytesIO(extra[1]))
        path = os.path.join(tmp, "damaged.tar"); open(path, "wb").write(out.getvalue()); return path
    r = assemble_bundle(rewrite(lambda n, d: (n != "__extra__", d.replace(b"the fact", b"a lie") if n == "claims/architect-cto.json" else d)))
    assert r.returncode != 0 and "claims/architect-cto.json does not match its manifest digest" in r.stderr, r.stderr
    r = assemble_bundle(rewrite(lambda n, d: (n not in ("observations.jsonl", "__extra__"), d)))
    assert r.returncode != 0 and "observations.jsonl is named in the manifest but missing" in r.stderr, r.stderr
    r = assemble_bundle(rewrite(lambda n, d: (True, b"{}" if n == "__extra__" else d)))
    assert r.returncode != 0 and "claims/stray.json is in the tar but not in the manifest" in r.stderr, r.stderr
    # an agent mismatch between manifest and report
    def forge(n, d):
        if n == "manifest.json":
            m = json.loads(d); m["agent"] = "someone-else"; return True, json.dumps(m).encode()
        return n != "__extra__", d
    r = assemble_bundle(rewrite(forge))
    assert r.returncode != 0 and "manifest says agent='someone-else'" in r.stderr, r.stderr
    # not a bundle at all
    open(os.path.join(tmp, "empty.tar"), "wb").write(b"")
    r = assemble_bundle(os.path.join(tmp, "empty.tar"))
    assert r.returncode != 0 and ("no manifest.json" in r.stderr or "bundle" in r.stderr), r.stderr
    # --out and --bundle are one choice
    r = subprocess.run([sys.executable, TOOL, "--role", "architect-cto", "--memory", mem], capture_output=True, text=True)
    assert r.returncode == 2 and "exactly one of --out" in r.stderr


def test_the_memory_slug_is_the_harness_s_spelling(tmp: str) -> None:
    """Claude Code names a launch directory by turning every character
    that is not a letter or a digit into `-` — a dot as much as a slash
    (read back 2026-09-17). Kills: mapping `/` alone, which left every
    dotted working copy (gzapp.decks, gzapi.ge) without its memory."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("harvest", os.path.join(ROOT, "tools", "fabric", "harvest_memory.py"))
    harvest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harvest)
    assert harvest.memory_slug("/home/x/projects/gzapp") == "-home-x-projects-gzapp"
    assert harvest.memory_slug("/home/x/projects/gzapp.decks") == "-home-x-projects-gzapp-decks", harvest.memory_slug("/home/x/projects/gzapp.decks")
    assert harvest.memory_slug("/home/x/.claude-mem") == "-home-x--claude-mem"
    assert harvest.default_memory_dir("/home/x/projects/gzapi.ge").endswith("/.claude/projects/-home-x-projects-gzapi-ge/memory")


def test_a_credential_refuses_the_whole_drain_at_the_harvester(tmp: str) -> None:
    """A memory whose body carries a credential by shape refuses the WHOLE
    drain and is named, before any claim is built — the bundle travels
    over the control channel, so the fence is here, not at the assembler.
    Kills: harvesting the memory and leaving hygiene to assemble.py."""
    mem = os.path.join(tmp, "cred-mem"); out = os.path.join(tmp, "cred-out")
    os.makedirs(mem)
    write_memory(mem, "clean", "project", "a fact", roles_class="solution")
    write_memory(mem, "leaky", "project", "use GH_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 for it", roles_class="solution")
    r = run(mem, out, "--all")
    assert r.returncode == 1, (r.returncode, r.stderr)
    assert "leaky.md: carries a credential" in r.stderr and "nothing of it leaves the account" in r.stderr, r.stderr
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in r.stderr + r.stdout, "the value must not be echoed"
    assert not os.path.exists(os.path.join(out, "claims")), "no partial claims file"
    b = subprocess.run([sys.executable, TOOL, "--role", "architect-cto", "--memory", mem, "--bundle", os.path.join(tmp, "cred.tar"), "--all"],
                       capture_output=True, text=True)
    assert b.returncode == 1 and not os.path.exists(os.path.join(tmp, "cred.tar")), f"no bundle either: {b.returncode} {b.stderr}"
    # A memory without roles_class is the agent's own: not a claim, not inspected here, and named as skipped.
    os.remove(os.path.join(mem, "leaky.md"))
    write_memory(mem, "private", "user", "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    r = run(mem, out, "--all", "--dry-run")
    assert r.returncode == 0 and json.loads(r.stdout)["skipped_no_roles_class"] == ["private.md"], r.stderr + r.stdout


def test_the_watermark_never_passes_an_unrendered_memory(tmp: str) -> None:
    """A non-Latin memory without its English rendering yields no claim and
    is named under needs_rendering; the next watermark stays below it, so
    the next drain without --all names it again (the charter: named in
    every report until rendered, never dropped). Kills: advancing next_ms
    before the rendering check."""
    mem = os.path.join(tmp, "wm-mem"); out = os.path.join(tmp, "wm-out")
    os.makedirs(mem)
    write_memory(mem, "older", "project", "an English fact", roles_class="solution")
    write_memory(mem, "georgian", "project", "ქართული ფაქტი ინგლისური გადმოცემის გარეშე", roles_class="solution")
    old = os.path.join(mem, "older.md"); ka = os.path.join(mem, "georgian.md")
    os.utime(old, (1_700_000_000, 1_700_000_000)); os.utime(ka, (1_700_000_100, 1_700_000_100))
    r = run(mem, out, "--all", "--dry-run")
    rep = json.loads(r.stdout)
    assert rep["needs_rendering"] == ["georgian.md"] and rep["claims"] == 1, rep
    assert rep["next_watermark"] == 1_700_000_000_000, f"the watermark stops at the last memory that drained: {rep['next_watermark']}"
    # The unrendered memory older than one that drains: the watermark stops below it, not at the newer one.
    os.utime(ka, (1_699_999_900, 1_699_999_900))
    rep = json.loads(run(mem, out, "--all", "--dry-run").stdout)
    assert rep["needs_rendering"] == ["georgian.md"] and rep["claims"] == 1, rep
    assert rep["next_watermark"] == 1_699_999_900_000 - 1, f"below the oldest unrendered memory: {rep['next_watermark']}"


def test_co_owners_named_in_the_memory_reach_the_claim(tmp: str) -> None:
    """`metadata.shared_with` is how a memory says other roles own the fact;
    the assembler routes a claim with two or more owners to shared/, and
    without the field on the claim that route is unreachable from a drain."""
    mem, out = os.path.join(tmp, "m16"), os.path.join(tmp, "o16")
    os.makedirs(mem)
    with open(os.path.join(mem, "shared.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: shared\ndescription: d\nmetadata:\n  type: project\n"
                 "  roles_class: domain\n  shared_with: web-dev, backend-dev web-dev\n---\n\nthe fact\n")
    write_memory(mem, "own", "project", roles_class="domain")
    assert run(mem, out).returncode == 0
    by_topic = {c["topic"]: c for c in claims_of(out)}
    assert by_topic["shared"]["shared_with"] == ["backend-dev", "web-dev"], by_topic["shared"]
    assert "shared_with" not in by_topic["own"], "a memory with no co-owners carries no field"


def test_a_co_owner_that_is_not_a_slug_refuses_the_drain(tmp: str) -> None:
    mem, out = os.path.join(tmp, "m17"), os.path.join(tmp, "o17")
    os.makedirs(mem)
    with open(os.path.join(mem, "bad.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: bad\ndescription: d\nmetadata:\n  type: project\n"
                 "  roles_class: domain\n  shared_with: Web Dev\n---\n\nthe fact\n")
    r = run(mem, out)
    assert r.returncode != 0 and "shared_with" in r.stderr, r.stderr


def main() -> int:
    cases = [
        test_an_author_s_merge_target_supersedes_without_a_question,
        test_the_watermark_round_trips_through_the_committed_report,
        test_a_bundle_round_trips_and_a_damaged_one_is_refused_by_file,
        test_a_claim_carries_the_date_the_memory_was_written,
        test_a_quoted_description_is_read_as_yaml_reads_it,
        test_a_cue_in_another_script_needs_its_english,
        test_merge_target_travels_from_the_memory_to_the_claim,
        test_role_knowledge_is_opt_in,
        test_a_memory_in_another_language_drains_through_its_rendering,
        test_the_class_is_taken_verbatim_not_mapped,
        test_a_generated_class_is_refused,
        test_a_skipped_memory_is_named_not_counted,
        test_an_unfamiliar_type_is_not_an_obstacle,
        test_a_user_memory_needs_no_special_case,
        test_hand_authored_classes_are_refused,
        test_unknown_override_class_is_refused,
        test_index_file_is_not_a_memory,
        test_content_hash_follows_the_fact_not_the_file,
        test_wikilinks_become_citations,
        test_a_memory_without_links_omits_citations,
        test_dry_run_writes_nothing,
        test_missing_memory_dir_exits_two,
        test_assemble_gets_the_files_it_requires,
        test_the_assembler_actually_consumes_the_drain,
        test_the_memory_slug_is_the_harness_s_spelling,
        test_a_credential_refuses_the_whole_drain_at_the_harvester,
        test_the_watermark_never_passes_an_unrendered_memory,
        test_co_owners_named_in_the_memory_reach_the_claim,
        test_a_co_owner_that_is_not_a_slug_refuses_the_drain,
    ]
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            try:
                case(tmp)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                print(f"  FAIL {case.__name__}: {exc}", file=sys.stderr)
                failures += 1
    print()
    print(f"{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
