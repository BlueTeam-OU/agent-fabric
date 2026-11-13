#!/usr/bin/env python3
"""Tests for tools/fabric/adr.py: the real docs/adr/ is clean, and each
rule catches the one mutation it exists for — on a copy under TMPDIR, so
the run leaves nothing behind (run.sh's
leak check)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import adr  # noqa: E402
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import write_registry  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

ZERO = "docs/adr/ADR-000-the-enduring-organization.md"
ONE = "docs/adr/ADR-001-decision-records.md"


def fixture(tmp: str) -> str:
    root = os.path.join(tmp, "fabric")
    shutil.copytree(os.path.join(ROOT, "docs", "adr"), os.path.join(root, "docs", "adr"))
    # A record's Evidence paths must exist (adr.check), so the copy carries them.
    adrs, _ = adr.load(ROOT)
    for ev in {e.strip() for a in adrs for e in a["fields"].get("Evidence", "").split(",") if e.strip()}:
        src, dst = os.path.join(ROOT, ev), os.path.join(root, ev)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, dst)
    write_registry(os.path.join(root, "projects"))   # the fixture's, never the live one
    give_class(root)
    return root


def give_class(root: str) -> None:
    """A record without **Class:** gets `engine`, so the fixture stays clean
    whether or not the real records carry the header yet; the real tree's own
    headers are held by case_the_real_records_carry_a_class."""
    d = os.path.join(root, "docs", "adr")
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if adr.FILE_RE.fullmatch(f):
            s = open(p, encoding="utf-8").read()
            if "\n**Class:**" not in s:
                s = re.sub(r"(\n\*\*Pillar:\*\*[^\n]*)", r"\1\n**Class:** engine", s, count=1)
                open(p, "w", encoding="utf-8").write(s)
    adr.write_index(root)


def edit(root: str, rel: str, old: str, new: str, count: int = 1) -> None:
    p = os.path.join(root, rel)
    s = open(p, encoding="utf-8").read()
    assert old in s, f"fixture drifted: {old!r} not in {rel}"
    open(p, "w", encoding="utf-8").write(s.replace(old, new, count))


def only(root: str, needle: str) -> None:
    f = adr.check(root)
    assert any(needle in x for x in f), f"expected a finding with {needle!r}, got {f}"


def case_the_real_records_are_clean(tmp: str) -> None:
    # The real records, copied with their Evidence, checked against the
    # fixture registry rather than the live one (ADR-045 §5 rule 3).
    root = fixture(tmp)
    assert adr.check(root) == [], adr.check(root)


def case_index_is_generated_and_a_stale_one_fails(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, "docs/adr/index.json", '"Decision records"', '"Decision notes"')
    only(root, "index.json: stale")
    edit(root, "docs/adr/README.md", "| Decision records |", "| Decision notes |")
    only(root, "index table is stale")
    adr.write_index(root)
    assert adr.check(root) == [], "index --write repairs both"


def case_numbers_are_contiguous_and_unique(tmp: str) -> None:
    root = fixture(tmp)
    os.rename(os.path.join(root, ONE), os.path.join(root, "docs/adr/ADR-002-decision-records.md"))
    edit(root, "docs/adr/ADR-002-decision-records.md", "# ADR-001 —", "# ADR-002 —")
    only(root, "not contiguous")


def case_heading_and_file_agree(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "# ADR-001 — Decision records", "# ADR-007 — Decision records")
    only(root, "heading says ADR-007")


def case_header_fields_and_statuses(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Scope:** ", "**Scopes:** ")
    only(root, "**Scope:** missing")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "**Status:** Accepted", "**Status:** Approved")
    only(root, "not one of Proposed")
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "**Date:** 2026-09-27", "**Date:** 27 September")
    only(root, "is not a YYYY-MM-DD date")


def case_accepted_needs_the_owners_word(tmp: str) -> None:
    root = fixture(tmp)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    s = re.sub(r"^\*\*Ratified:\*\*.*\n", "", s, flags=re.M)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "Accepted without '**Ratified:** owner")


def case_sections_in_order(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "## 3. Alternatives Considered", "## 3. Options")
    only(root, "sections must be, in order")
    root = fixture(os.path.join(tmp, "b"))
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    a, b = s.split("## 4. Rationale", 1)
    r, rest = b.split("## 5. Binding Rules", 1)
    s = a + "## 5. Binding Rules" + rest.replace("## 6. Consequences", "## 4. Rationale" + r + "## 6. Consequences", 1)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "sections must be, in order")


def case_pillars_come_from_adr_000(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P9")
    only(root, "P9 is not in ADR-000 §5")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ZERO, "| P7 | Sustainable operation |", "| XX | Sustainable operation |")
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P7")
    only(root, "P7 is not in ADR-000 §5")


def case_evidence_must_exist(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P2\n**Evidence:** docs/live-checks/nowhere.md")
    only(root, "Evidence:** docs/live-checks/nowhere.md does not exist")


def case_citations_resolve_but_another_projects_are_not_ours(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSee ADR-944.\n")
    only(root, "cites ADR-944, which does not exist")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nLike gzapp's ADR-944 and gzapp ADR-059.\n")
    assert adr.check(root) == [], "a citation named with another registered project is that project's"
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nLike fixture-proj's ADR-944.\n")
    assert adr.check(root) == [], "the registry read is the fixture tree's: fixture-proj is in no live one"


# A date after every real amendment: the fixture copies the real records, whose DIGEST bullets must read in date order.
def amend(root: str, date: str = "2099-09-28", title: str = "a rule moved") -> None:
    adr.cmd_amend(root, "1", title, date)
    edit(root, "docs/adr/DIGEST.md", "- Keywords: ADR, amendment,", f"- A {date} — {title}.\n- Keywords: ADR, amendment,")
    adr.write_index(root)


def case_an_amendment_is_the_triple(tmp: str) -> None:
    root = fixture(tmp)
    amend(root)
    assert adr.check(root) == [], f"amend + DIGEST bullet + index is clean: {adr.check(root)}"
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s.replace("| 2099-09-28 | a rule moved |", "| 2099-09-29 | a rule moved |"))
    only(root, "amendment note(s) with no table row")
    only(root, "table row(s) with no history note")


def case_one_amendment_heading_form(tmp: str) -> None:
    root = fixture(tmp)
    amend(root)
    edit(root, "docs/adr/history/ADR-001-amendments.md", "### Amendment 2099-09-28 — a rule moved", "### Amendment (i) — 2099-09-28 — a rule moved")
    only(root, "is not '### Amendment YYYY-MM-DD — Title'")


def case_no_amendment_note_inside_the_record(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "### Amendment 2026-09-28 — inline\n\n## 6. Consequences")
    only(root, "an '### Amendment' heading in the ADR itself")


def case_orphan_history_files(tmp: str) -> None:
    root = fixture(tmp)
    os.makedirs(os.path.join(root, "docs/adr/history"), exist_ok=True)
    open(os.path.join(root, "docs/adr/history/ADR-999-amendments.md"), "w").write("# x\n\n### Amendment 2026-09-28 — y\n")
    only(root, "history/ADR-999-amendments.md: belongs to no ADR")


def case_superseded_needs_a_point_map_to_a_real_record(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Status:** Accepted", "**Status:** Superseded (→ ADR-000)")
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 — Decision records (Accepted)", "### ADR-001 — Decision records (Superseded)")
    adr.write_index(root)
    only(root, "Superseded without a point map")
    edit(root, ONE, "## 1. Context and Problem", "Point map: §5 rule 1 → ADR-000 §5 rule 4.\n\n## 1. Context and Problem")
    assert not any("point map" in x for x in adr.check(root)), adr.check(root)
    edit(root, ONE, "(→ ADR-000)", "(→ ADR-999)")
    only(root, "superseded by ADR-999, which does not exist")


def case_the_digest_follows_the_records(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 — Decision records (Accepted)", "### ADR-001 — Decision records (Proposed)")
    only(root, "DIGEST.md: ADR-001 reads 'Decision records' (Proposed)")
    root = fixture(os.path.join(tmp, "b"))
    s = open(os.path.join(root, "docs/adr/DIGEST.md"), encoding="utf-8").read()
    open(os.path.join(root, "docs/adr/DIGEST.md"), "w", encoding="utf-8").write(s.split("### ADR-001")[0])
    only(root, "no entry '### ADR-001")
    root = fixture(os.path.join(tmp, "c"))
    # A date no real amendment will carry, so the case follows the corpus:
    # the history gains it, the DIGEST bullets do not.
    adr.cmd_amend(root, "1", "a rule moved", "2099-01-02")
    adr.write_index(root)
    only(root, "'2099-01-02']")


def case_new_takes_the_next_number(tmp: str) -> None:
    root = fixture(tmp)
    nxt = f"ADR-{len(adr.load(root)[0]):03d}"
    path = adr.cmd_new(root, "a-new-thing", "A new thing")
    assert path.endswith(f"{nxt}-a-new-thing.md"), path
    assert open(path, encoding="utf-8").read().startswith(f"# {nxt} — A new thing")


def case_lookup_with_no_word_is_the_table_and_an_entry_has_a_budget(tmp: str) -> None:
    """ADR-001: a session looks the DIGEST up, never reads it whole. With no
    word, lookup answers only the table of which record answers what; a
    bullet over the word budget is a finding, so a lookup stays cheap."""
    table = adr.cmd_lookup(ROOT, [])
    assert len(table) == 1 and table[0].startswith("| Looking for") and "### ADR-" not in table[0], table[:1]
    assert len(table[0].split()) < len(open(os.path.join(ROOT, "docs/adr/DIGEST.md"), encoding="utf-8").read().split()) / 5, \
        "the table is a small part of the DIGEST"
    root = fixture(tmp)
    assert adr.check(root) == [], adr.check(root)
    # many short bullets are fine: the budget is per bullet, not per entry
    edit(root, "docs/adr/DIGEST.md", "- Keywords: ADR, amendment,", ("- " + "padding " * 10 + "\n") * 40 + "- Keywords: ADR, amendment,")
    assert adr.check(root) == [], adr.check(root)
    # a bullet over budget, its words on continuation lines, is refused
    edit(root, "docs/adr/DIGEST.md", "- Keywords: ADR, amendment,", "- long\n" + ("  " + "padding " * 10 + "\n") * 6 + "- Keywords: ADR, amendment,")
    only(root, f"DIGEST.md: ADR-001's bullet")


def case_every_digest_line_counts_and_amendments_read_in_order(tmp: str) -> None:
    """A line the per-bullet budget cannot attribute is never free text: an
    unbulleted or tab- or one-space-indented line counts against the bullet
    above it, and one before an entry's first bullet is a finding. An
    entry's amendment bullets read in date order."""
    keywords = "- Keywords: ADR, amendment,"
    for label, inserted in (("unbulleted", "- short\n" + "padding " * 70 + "\n"),
                            ("tab", "- long\n" + ("\t" + "padding " * 10 + "\n") * 7),
                            ("one space", "- long\n" + (" " + "padding " * 10 + "\n") * 7)):
        root = fixture(os.path.join(tmp, label.replace(" ", "-")))
        edit(root, "docs/adr/DIGEST.md", keywords, inserted + keywords)
        only(root, "DIGEST.md: ADR-001's bullet")
    root = fixture(os.path.join(tmp, "before"))
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 — Decision records (Accepted)\n\n",
         "### ADR-001 — Decision records (Accepted)\n\nA stray paragraph.\n")
    only(root, "DIGEST.md: ADR-001 has a line before its first bullet")
    root = fixture(os.path.join(tmp, "order"))
    amend(root, "2099-09-28", "an earlier rule")
    amend(root, "2099-09-30", "a later rule")
    assert adr.check(root) == [], adr.check(root)
    s = open(os.path.join(root, "docs/adr/DIGEST.md"), encoding="utf-8").read()
    early, late = "- A 2099-09-28 — an earlier rule.\n", "- A 2099-09-30 — a later rule.\n"
    open(os.path.join(root, "docs/adr/DIGEST.md"), "w", encoding="utf-8").write(s.replace(early + late, late + early))
    only(root, "DIGEST.md: ADR-001's amendment bullets are out of date order")


def case_lookup_reads_the_digest(tmp: str) -> None:
    hits = adr.cmd_lookup(ROOT, ["ratify"])
    assert hits and hits[0].startswith("### ADR-001"), hits


def case_lookup_refuses_an_exported_operator_without_a_digest(tmp: str) -> None:
    """Review of #572, F2: the engine's DIGEST alone answered, exit 0."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_FABRIC_")}
    env["AGENT_FABRIC_OPERATOR"] = os.path.join(tmp, "nonexistent")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "adr.py"), "lookup", "mechanism"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode != 0 and "nonexistent" in r.stderr and "### ADR-" not in r.stdout, (r.returncode, r.stderr)


def git(cwd: str, *a: str, msg: str | None = None) -> None:
    env = git_env()
    subprocess.run(["git", "-C", cwd, *a] + (["-m", msg] if msg else []), check=True, capture_output=True, env=env)


def case_range_check_refuses_an_unrecorded_body_edit(tmp: str) -> None:
    root = fixture(tmp)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    base = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, env=git_env()).stdout.strip()
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="reword")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "no new Amendments row" in f[0], f
    git(root, "commit", "-q", "--amend", msg="reword\n\nADR-Editorial: a word, nothing decided")
    assert adr.range_check(root, base) == [], "the trailer records an editorial edit"
    root2 = fixture(os.path.join(tmp, "b"))
    git(root2, "init", "-q", "-b", "main"); git(root2, "config", "core.hooksPath", "/dev/null")
    git(root2, "add", "-A"); git(root2, "commit", "-q", msg="base")
    base2 = subprocess.run(["git", "-C", root2, "rev-parse", "HEAD"], capture_output=True, text=True, env=git_env()).stdout.strip()
    amend(root2)
    edit(root2, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root2, "add", "-A"); git(root2, "commit", "-q", msg="amend ADR-001")
    assert adr.range_check(root2, base2) == [], "an amendment row records the body edit"
    edit(root2, ONE, "**Ratified:** owner, 2026-09-27", "**Ratified:** owner, 2026-09-28")
    git(root2, "commit", "-qa", msg="ratified")
    assert adr.range_check(root2, base2) == [], "a header-only change (ratification) is not a body edit"


def case_header_dates_keep_their_own_pattern(tmp: str) -> None:
    # The body's date scan must not replace the header's anchored pattern
    # (review thread on #53): any real calendar date is a valid header date,
    # and nothing may trail it.
    assert adr.real_date("2100-01-01") and adr.real_date("1999-12-31")
    assert not adr.real_date("2026-09-27-x") and not adr.real_date("2026-09-27 ")
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSince 2100-01-01, every record says so.\n")
    only(root, "§6 dates something (2100-01-01)")


def case_the_date_rules_hold_at_their_edges(tmp: str) -> None:
    # Review of #53: the anchor is the pattern's, not only fromisoformat's;
    # an amendment's date is a calendar date; an attribution may break
    # between "the" and "owner"; a dated path of any kind, bare or in a
    # fenced block, is not a dated sentence.
    assert adr.DATE_RE.match("2026-09-27-x") is None
    root = fixture(tmp)
    try:
        adr.main(["--root", root, "amend", "--date", "2026-02-30", "1", "x"])
        raise AssertionError("amend took an impossible date")
    except SystemExit as e:
        assert "YYYY-MM-DD" in str(e), e
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    h = os.path.join(root, "docs/adr/history/ADR-001-amendments.md")
    s = open(h, encoding="utf-8").read()
    open(h, "w", encoding="utf-8").write(s.replace("### Amendment ", "### Amendment 2026-02-30 — ghost\n\n### Amendment ", 1))
    assert any("2026-02-30" in f and "not a date" in f for f in adr.check(root)), adr.check(root)
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nKept as commit 04f4b1c (the\n  owner's rule).\n")
    only(root, "an inline attribution")
    root = fixture(os.path.join(tmp, "d"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nKept (The owner, 2026-09-13).\n")
    assert any("inline attribution" in f for f in adr.check(root)), adr.check(root)
    root = fixture(os.path.join(tmp, "e"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSee docs/live-checks/2026-09-25-x.md and\nruntime/state/2026-09-25-y.json.\n\n```text\nat 2026-09-25 the log said so\n```\n")
    assert adr.check(root) == [], adr.check(root)


def case_impossible_dates_and_escaping_evidence(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Date:** 2026-09-27", "**Date:** 2026-13-45")
    only(root, "'2026-13-45' is not a YYYY-MM-DD date")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P2\n**Evidence:** /etc/passwd, ../../outside.md")
    only(root, "/etc/passwd is not a path inside the repository")
    only(root, "../../outside.md is not a path inside the repository")


def case_duplicate_numbers(tmp: str) -> None:
    root = fixture(tmp)
    shutil.copy(os.path.join(root, ONE), os.path.join(root, "docs/adr/ADR-001-a-twin.md"))
    only(root, "number(s) used twice: ADR-001")


def case_amendments_bookkeeping_edges(tmp: str) -> None:
    root = fixture(tmp)
    amend(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    s = s.replace("\n## Amendments\n", "\n## Amendments-moved\n", 1)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "amended, but no '## Amendments' section")
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    head, amendments = s.split("\n## Amendments\n", 1)
    refs = head.index("\n## References")
    s = head[:refs] + "\n## Amendments\n" + amendments.rstrip("\n") + "\n" + head[refs:] + "\n"
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "'## Amendments' must be the last section")
    root = fixture(os.path.join(tmp, "c"))
    os.makedirs(os.path.join(root, "docs/adr/history"), exist_ok=True)
    open(os.path.join(root, "docs/adr/history/ADR-001-amendments.md"), "w").write("# ADR-001 — amendments\n")
    only(root, "no amendment in it — remove it")


def case_superseded_needs_an_arrow(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Status:** Accepted", "**Status:** Superseded")
    only(root, "Superseded without '(→ ADR-NNN)'")


def case_no_inline_attribution(tmp: str) -> None:
    # Who decided and when are the header's and the history's; the body
    # states the decision (the owner's rule for records).
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nKept apart (the owner,\n2026-09-13) on purpose.\n")
    only(root, "an inline attribution '(the owner,")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 —", "- Stray (the CEO) bullet.\n\n### ADR-001 —")
    only(root, "DIGEST.md: an inline attribution '(the CEO)")


def case_dates_only_in_the_context(tmp: str) -> None:
    # A record reads current: a date may date an incident in §1, and the
    # engine's markers and dated paths stay; the rules carry none.
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSince 2026-09-25, every record says so.\n")
    only(root, "§6 dates something (2026-09-25)")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSee `docs/live-checks/2026-09-25-x.md` and\n[the note](../2026-09-20-y.md); rule 3 (A 2026-09-26).\n")
    edit(root, ONE, "## 2. Decision", "## 2. Decision\n\n**§5 rule 9 — withdrawn** (Amendment 2026-09-26).\n")
    assert adr.check(root) == [], adr.check(root)
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "## 1. Context and Problem", "## 1. Context and Problem\n\nOn 2026-09-19 the disk filled.\n")
    assert adr.check(root) == [], adr.check(root)


def case_digest_orphan_and_readme_markers(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 —", "### ADR-999 — Ghost (Accepted)\n\n### ADR-001 —")
    only(root, "an entry for ADR-999, which does not exist")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, "docs/adr/README.md", adr.INDEX_START, "")
    only(root, "no <!-- adr-index:start -->")


def commit_base(root: str) -> str:
    git(root, "init", "-q", "-b", "main"); git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, env=git_env()).stdout.strip()


def case_range_check_takes_a_git_range_and_refuses_a_bad_one(tmp: str) -> None:
    """`range-check A..B` is how git spells a range: it once crashed git
    rev-list as "A..B..HEAD". Taken as base and head; a range git cannot
    read, or a range with a second head, is refused without a traceback."""
    root = fixture(tmp)
    git(root, "init", "-q", "-b", "main"); git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    base = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, env=git_env()).stdout.strip()
    tool = os.path.join(ROOT, "tools", "fabric", "adr.py")
    cli = lambda *a: subprocess.run([sys.executable, tool, "--root", root, "range-check", *a], capture_output=True, text=True)  # noqa: E731
    r = cli(f"{base}..HEAD")
    assert r.returncode == 0 and "clean" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr
    r = cli("nosuchref..HEAD")
    assert r.returncode == 2 and "could not read" in r.stderr and "Traceback" not in r.stderr, r.stderr
    r = cli(f"{base}..HEAD", "HEAD")
    assert r.returncode == 2 and "not both" in r.stderr, r.stderr
    r = cli("..HEAD")
    assert r.returncode == 2 and "no base" in r.stderr, r.stderr


def case_range_check_with_no_range_chooses_the_base_as_ci_does(tmp: str) -> None:
    """`fabric-adr range-check` with no range (ADR-040 rule 7: the command
    replaces policies/check_adr_amendment.sh): the GitHub event's own base
    and head first, then AGENT_FABRIC_ADR_BASE, origin/$GITHUB_BASE_REF,
    origin/main, main; with none, it says the check is not enforced."""
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "checkout", "-q", "-b", "feat")
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="an unrecorded body edit")
    tool = os.path.join(ROOT, "tools", "fabric", "adr.py")
    clean = {k: v for k, v in os.environ.items() if k not in ("GITHUB_EVENT_PATH", "GITHUB_BASE_REF", "AGENT_FABRIC_ADR_BASE")}

    def cli(**env: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, tool, "--root", root, "range-check"], capture_output=True, text=True,
                              env={**clean, **git_env(), **env})
    r = cli()
    assert r.returncode == 1 and "unrecorded" in r.stdout, f"main as the base: {r.stdout}{r.stderr}"
    git(root, "branch", "-q", "mark")
    r = cli(AGENT_FABRIC_ADR_BASE="mark")
    assert r.returncode == 0 and "clean" in r.stdout, f"AGENT_FABRIC_ADR_BASE ignored: {r.stdout}{r.stderr}"
    head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, env=git_env()).stdout.strip()
    event = os.path.join(tmp, "event.json")
    with open(event, "w", encoding="utf-8") as f:
        json.dump({"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}, f)
    r = cli(GITHUB_EVENT_PATH=event, AGENT_FABRIC_ADR_BASE="mark")
    assert r.returncode == 1 and "unrecorded" in r.stdout, f"the event's base did not win: {r.stdout}{r.stderr}"
    git(root, "branch", "-q", "-m", "main", "trunk")
    r = cli()
    assert r.returncode == 0 and "not enforced" in r.stdout, f"no base: {r.stdout}{r.stderr}"


def case_range_check_counts_only_new_amendment_rows(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    edit(root, ONE, "## 6. Consequences", "| 2026-09-19 | disk full | lease added |\n\n## 6. Consequences")
    git(root, "commit", "-qa", msg="a dated row inside the body is not an amendment")
    assert len(adr.range_check(root, base)) == 1, "a dated table row outside ## Amendments hid a body edit"
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    base = commit_base(root)
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    edit(root, ONE, "| (say which § and rule) |", "| §3 |")
    git(root, "commit", "-qa", msg="an edited Effect cell is not a new row")
    assert len(adr.range_check(root, base)) == 1, "an edited existing row counted as an amendment"


def case_range_check_follows_renames_and_passes_header_only(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "mv", ONE, "docs/adr/ADR-001-decision-records-renamed.md")
    edit(root, "docs/adr/ADR-001-decision-records-renamed.md", "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="rename and rewrite")
    assert len(adr.range_check(root, base)) == 1, "a rename carrying a body edit escaped"
    root = fixture(os.path.join(tmp, "b"))
    base = commit_base(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    s = s.replace("\n\n## 1.", "\n \n## 1.", 1)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    git(root, "commit", "-qa", msg="whitespace on the header's last line")
    assert adr.range_check(root, base) == [], "a header-only change was reported as a body edit"


def case_a_record_the_branch_adds_is_a_draft_until_merged(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    draft = os.path.relpath(adr.cmd_new(root, "a-draft", "A draft"), root)
    git(root, "add", "-A"); git(root, "commit", "-q", msg="add a draft record")
    edit(root, draft, "## 6. Consequences", "## 6. Consequences\n\nRevised before the merge.\n")
    git(root, "commit", "-qa", msg="revise the draft")
    assert adr.range_check(root, base) == [], "revising a record the branch adds is not an amendment"


def case_range_check_judges_a_renamed_record_by_its_number(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "mv", ONE, "docs/adr/ADR-001-renamed.md")
    git(root, "commit", "-q", msg="rename only")
    edit(root, "docs/adr/ADR-001-renamed.md", "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="then edit the body")
    assert len(adr.range_check(root, base)) == 1, "a body edit after a rename escaped as a new record"


def case_a_source_is_never_edited(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    edit(root, "docs/adr/sources/ADR-000-the-owners-statement.md", "I would broaden it", "I would widen it")
    git(root, "commit", "-qa", msg="touch the source")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "a verbatim source, which is never edited" in f[0], f


def case_range_check_on_a_base_without_records(tmp: str) -> None:
    root = os.path.join(tmp, "fresh")
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main"); git(root, "config", "core.hooksPath", "/dev/null")
    open(os.path.join(root, "README"), "w").write("x\n")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="before any record")
    base = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, env=git_env()).stdout.strip()
    shutil.copytree(os.path.join(ROOT, "docs", "adr"), os.path.join(root, "docs", "adr"))
    git(root, "add", "-A"); git(root, "commit", "-q", msg="the records arrive")
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="revise one before the merge")
    assert adr.range_check(root, base) == [], "a base with no docs/adr: every record is the branch's own"


def case_range_check_pairs_a_delete_and_add_of_one_record(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    body = open(os.path.join(root, ONE), encoding="utf-8").read()
    os.remove(os.path.join(root, ONE))
    head = body.split("## 1. Context and Problem", 1)[0]
    # Every section rewritten: far below -M's similarity threshold, so git
    # reports a delete and an add, never a rename.
    sections = "".join(f"## {name}\n\nRewritten {i}: " + "fresh wording " * 30 + "\n\n" for i, name in enumerate(adr.SECTIONS))
    open(os.path.join(root, "docs/adr/ADR-001-rewritten.md"), "w", encoding="utf-8").write(head + sections)
    # A source added in the same commit carries the record's number; it is
    # not the record's other half (review of #51).
    open(os.path.join(root, "docs/adr/sources/ADR-001-a-new-source.md"), "w", encoding="utf-8").write("new\n")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="rename and rewrite in one go")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "ADR-001-rewritten.md" in f[0] and "source" not in f[0], f


def case_a_source_is_never_removed(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "rm", "-q", "docs/adr/sources/ADR-000-the-owners-statement.md")
    git(root, "commit", "-q", msg="drop the source")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "never removed" in f[0], f
    # An editorial trailer excuses a record's body edit, never a source's
    # removal or edit (review of #51).
    root = fixture(os.path.join(tmp, "b"))
    base = commit_base(root)
    git(root, "rm", "-q", "docs/adr/sources/ADR-000-the-owners-statement.md")
    git(root, "commit", "-q", msg="drop the source\n\nADR-Editorial: tidy")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "never removed" in f[0], f
    root = fixture(os.path.join(tmp, "c"))
    base = commit_base(root)
    edit(root, "docs/adr/sources/ADR-000-the-owners-statement.md", "I would broaden it", "I would widen it")
    git(root, "commit", "-qa", msg="touch the source\n\nADR-Editorial: typo")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "never edited" in f[0], f
    # A rename out of sources/ is an edit of the source, trailer or not.
    for n, msg in enumerate(("move the source", "move the source\n\nADR-Editorial: tidy")):
        root = fixture(os.path.join(tmp, f"d{n}"))
        base = commit_base(root)
        git(root, "mv", "docs/adr/sources/ADR-000-the-owners-statement.md", "docs/adr/ADR-000-statement.txt")
        git(root, "commit", "-q", msg=msg)
        f = adr.range_check(root, base)
        assert len(f) == 1 and "never edited" in f[0], f


def case_staged_check_judges_the_commit_being_made(tmp: str) -> None:
    # The commit-time leg (job j261): the index against HEAD, excused only by the message being written.
    # Kills: judging HEAD's own commit instead of the index, reading a commented-out trailer, and judging a first commit.
    root = fixture(tmp)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.hooksPath", "/dev/null")
    assert adr.staged_check(root, "first\n") == [], "a repository with no HEAD has nothing to compare with"
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    assert adr.staged_check(root, "nothing staged\n") == []
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "add", "-A")
    f = adr.staged_check(root, "reword\n")
    assert len(f) == 1 and f[0].startswith("this commit: edits the body of docs/adr/ADR-001") and "no new Amendments row" in f[0], f
    assert adr.staged_check(root, "reword\n\nADR-Editorial: a word, nothing decided\n") == [], "the trailer excuses it"
    assert len(adr.staged_check(root, "reword\n# ADR-Editorial: a word\n")) == 1, "a comment line is no trailer"
    git(root, "commit", "-q", msg="reword\n\nADR-Editorial: a word")
    assert adr.staged_check(root, "after\n") == [], "the edit is committed; nothing is staged"
    amend(root)
    edit(root, ONE, "Cheaper, yet it keeps", "Cheaper, still it keeps")
    git(root, "add", "-A")
    assert adr.staged_check(root, "amend ADR-001\n") == [], "a new Amendments row records the body edit"
    tool = os.path.join(ROOT, "tools", "fabric", "adr.py")
    msgf = os.path.join(tmp, "MSG")
    with open(msgf, "w", encoding="utf-8") as fh:
        fh.write("reword\n")
    git(root, "commit", "-q", msg="amended")
    edit(root, ONE, "Cheaper, still it keeps", "Cheaper, and it keeps")
    git(root, "add", "-A")
    r = subprocess.run([sys.executable, tool, "--root", root, "staged-check", msgf], capture_output=True, text=True, env=git_env())
    assert r.returncode == 1 and "adr staged-check: this commit: edits the body" in r.stderr and not r.stdout, (r.returncode, r.stderr)


def case_staged_check_on_an_amend_and_with_no_base(tmp: str) -> None:
    # Review of #297, F2: an amend's parent is HEAD^; F3: with no base, range-check enforces nothing, and nor does this.
    # Kills: comparing an amend with HEAD, and judging when no base resolves.
    root = fixture(tmp)
    commit_base(root)
    amend(root)
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="amend ADR-001")
    edit(root, ONE, "Cheaper, yet it keeps", "Cheaper, still it keeps")
    git(root, "add", "-A")
    assert len(adr.staged_check(root, "amend ADR-001\n")) == 1, "against HEAD the row is no longer new"
    assert adr.staged_check(root, "amend ADR-001\n", against="HEAD^") == [], "against HEAD^ the amend adds the row"
    other = fixture(os.path.join(tmp, "nobase"))
    git(other, "init", "-q", "-b", "trunk"); git(other, "config", "core.hooksPath", "/dev/null")
    git(other, "add", "-A"); git(other, "commit", "-q", msg="base")
    edit(other, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(other, "add", "-A")
    env = {k: os.environ.pop(k) for k in ("AGENT_FABRIC_ADR_BASE", "GITHUB_BASE_REF", "GITHUB_EVENT_PATH") if k in os.environ}
    try:
        assert adr.default_range(other) is None and adr.staged_check(other, "reword\n") == [], "no base: not judged"
        msgf = os.path.join(tmp, "MSG")
        with open(msgf, "w", encoding="utf-8") as fh:
            fh.write("reword\n")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "adr.py"), "--root", other, "staged-check", msgf],
                           capture_output=True, text=True, env=git_env())
        assert r.returncode == 0 and "no base to compare with — not enforced" in r.stderr, (r.returncode, r.stderr)   # said, never silent
    finally:
        os.environ.update(env)


def case_the_real_records_carry_a_class(tmp: str) -> None:
    # Fails until every real record has its **Class:** header: held apart from
    # the fixture, which supplies the header itself.
    bad = [x for x in adr.check(ROOT) if "Class" in x]
    assert bad == [], bad[:3]


def case_class_is_required_and_one_of_two(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Class:** engine\n", "")
    only(root, "header field **Class:** missing")
    edit(root, ONE, "**Pillar:** P2\n", "**Pillar:** P2\n**Class:** mixed\n")
    only(root, "'mixed' is not one of engine, organisational")
    edit(root, ONE, "**Class:** mixed", "**Class:** organisational")
    assert not [x for x in adr.check(root) if "Class" in x]


def case_index_and_table_carry_the_class(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Class:** engine", "**Class:** organisational")
    adr.write_index(root)
    rows = {r["number"]: r for r in json.load(open(os.path.join(root, "docs/adr/index.json")))["adrs"]}
    assert rows["001"]["class"] == "organisational" and rows["000"]["class"] == "engine"
    assert "| Pillar | Class | Status |" in open(os.path.join(root, "docs/adr/README.md"), encoding="utf-8").read()
    assert adr.check(root) == []


def case_list_prints_the_numbers_of_a_class(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Class:** engine", "**Class:** organisational")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "adr.py"), "--root", root, "list", "--class", "organisational"],
                       capture_output=True, text=True, env=git_env())
    # The fixture copies the real records, whose own organisational ones list too.
    want = sorted(f"ADR-{a['number']}" for a in adr.load(root)[0] if a["fields"].get("Class") == "organisational")
    assert "ADR-001" in want and r.returncode == 0 and r.stdout.split() == want, (r.returncode, r.stdout, r.stderr)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "adr.py"), "--root", root, "list", "--class", "other"],
                       capture_output=True, text=True, env=git_env())
    assert r.returncode != 0


def reserve(root: str, **table: str) -> None:
    with open(os.path.join(root, "docs/adr/reserved.json"), "w", encoding="utf-8") as fh:
        json.dump({"$comment": "t", "reserved": {k.lstrip("n"): v for k, v in table.items()}}, fh)


def move_one_out(root: str) -> str:
    """ADR-001 leaves for an operator tree beside the engine's, its number reserved."""
    op = os.path.join(os.path.dirname(root), "operator")
    os.makedirs(os.path.join(op, "docs", "adr"))
    for sub in ("", "history"):
        os.makedirs(os.path.join(op, "docs", "adr", sub), exist_ok=True)
    for rel in (ONE, "docs/adr/history/ADR-001-amendments.md"):
        shutil.move(os.path.join(root, rel), os.path.join(op, rel))
    reserve(root, n001="moved to the operator")
    return op


def split_trees(root: str) -> str:
    """The move done properly: ADR-001 in an operator tree with its own
    README, DIGEST entry, index and registry, the engine's copies without it,
    so each tree is clean by itself and only the pair is the numbering."""
    op = move_one_out(root)
    eng_digest = os.path.join(root, "docs/adr/DIGEST.md")
    head, entries = open(eng_digest, encoding="utf-8").read().split("\n### ADR-000", 1)
    parts = ("### ADR-000" + entries).split("\n### ")
    first = [p for p in parts if p.startswith("ADR-001 ")][0]
    rest = [p for p in parts if not p.startswith("ADR-001 ")]
    def entry(p: str) -> str:
        return p if p.startswith("### ") else "### " + p
    with open(eng_digest, "w", encoding="utf-8") as fh:
        fh.write(head.rstrip("\n") + "\n\n" + "\n".join(entry(p) for p in rest))
    with open(os.path.join(op, "docs/adr/DIGEST.md"), "w", encoding="utf-8") as fh:
        fh.write(head.rstrip("\n") + "\n\n" + entry(first))
    shutil.copy(os.path.join(root, "docs/adr/README.md"), os.path.join(op, "docs/adr/README.md"))
    write_registry(os.path.join(op, "projects"))
    adr.write_index(op)
    adr.write_index(root)
    return op


def case_a_two_tree_check_is_clean_and_a_lone_root_is_only_itself(tmp: str) -> None:
    root = fixture(tmp)
    op = split_trees(root)
    assert adr.check(op, other=root) == [], adr.check(op, other=root)
    assert adr.check(root, other=op) == [], adr.check(root, other=op)
    assert adr.check(op), "a root handed alone is that tree only: the engine's numbers are missing"


def case_a_number_recorded_in_both_trees_is_a_finding(tmp: str) -> None:
    root = fixture(tmp)
    op = split_trees(root)
    shutil.copy(os.path.join(op, ONE), os.path.join(root, ONE))
    for tree_, other in ((op, root), (root, op)):
        got = [x for x in adr.check(tree_, other=other) if "record in both trees" in x]
        assert len(got) == 1 and "ADR-001" in got[0], got
        assert os.path.realpath(op) in got[0] and os.path.realpath(root) in got[0], got


def case_an_undivided_operator_copy_is_one_tree_not_a_pair(tmp: str) -> None:
    # Before step B an exported operator is the whole fabric copied: every
    # record in both trees. That is no duplicate; only a split tree (one
    # without ADR-000) is checked as a half of the numbering.
    root = fixture(tmp)
    op = os.path.join(os.path.dirname(root), "operator")
    shutil.copytree(root, op)
    for tree_, other in ((op, root), (root, op)):
        assert adr.check(tree_, other=other) == [], adr.check(tree_, other=other)
    assert not adr.divided(adr.adr_dir(op), adr.adr_dir(root))


def case_new_in_an_operator_tree_is_organisational(tmp: str) -> None:
    root = fixture(tmp)
    op = split_trees(root)
    saved = adr.ROOT
    adr.ROOT = root          # the engine, as new sees it: the fixture's, not the live checkout
    try:
        mine = open(adr.cmd_new(op, "op-thing", "Op thing"), encoding="utf-8").read()
        assert "**Class:** organisational" in mine and "**Class:** engine" not in mine
        theirs = open(adr.cmd_new(root, "eng-thing", "Eng thing"), encoding="utf-8").read()
        assert "**Class:** engine" in theirs
    finally:
        adr.ROOT = saved


def case_list_refuses_a_missing_or_empty_tree(tmp: str) -> None:
    for sub in (None, "docs/adr"):
        root = os.path.join(tmp, "bare" if sub is None else "empty")
        os.makedirs(os.path.join(root, sub or ""), exist_ok=True)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "adr.py"), "--root", root, "list", "--class", "organisational"],
                           capture_output=True, text=True, env=git_env())
        assert r.returncode != 0 and "no records to list" in r.stderr and r.stdout == "", (sub, r.returncode, r.stdout, r.stderr)


def case_a_reserved_number_keeps_the_numbering_contiguous(tmp: str) -> None:
    root = fixture(tmp)
    move_one_out(root)
    only(root, "DIGEST.md: an entry for ADR-001")   # the move's own step takes the entry out
    assert not [x for x in adr.check(root) if "contiguous" in x or "cites" in x], adr.check(root)
    os.remove(os.path.join(root, "docs/adr/reserved.json"))
    only(root, "missing ADR-001")


def case_reserved_and_recorded_is_a_finding_and_a_bad_number_too(tmp: str) -> None:
    root = fixture(tmp)
    reserve(root, n001="moved")
    only(root, "ADR-001 is reserved and has a record in this tree")
    reserve(root, **{"1": "short", "n002": ""})
    only(root, "is not a three-digit number with a reason")
    with open(os.path.join(root, "docs/adr/reserved.json"), "w", encoding="utf-8") as fh:
        fh.write("[]")
    only(root, "not a JSON object")


def case_the_index_lists_a_reserved_number_without_a_link(tmp: str) -> None:
    root = fixture(tmp)
    move_one_out(root)
    adr.write_index(root)
    rows = json.load(open(os.path.join(root, "docs/adr/index.json")))["adrs"]
    assert [r["number"] for r in rows][:3] == ["000", "001", "002"]
    assert rows[1] == {"number": "001", "file": None, "title": "moved to the operator", "status": "Reserved",
                       "date": "", "pillar": "", "class": "", "amendments": 0}, rows[1]
    readme = open(os.path.join(root, "docs/adr/README.md"), encoding="utf-8").read()
    assert "| ADR-001 | moved to the operator |" in readme and "](ADR-001-decision-records.md) |" not in readme


def case_new_never_takes_a_reserved_number(tmp: str) -> None:
    root = fixture(tmp)
    top = max(int(a["number"]) for a in adr.load(root)[0])
    reserve(root, **{f"n{top + 3:03d}": "moved"})
    assert os.path.basename(adr.cmd_new(root, "next", "Next")).startswith(f"ADR-{top + 4:03d}-")


def case_an_exported_operator_and_the_engine_count_each_others_numbers(tmp: str) -> None:
    root = fixture(tmp)
    op = move_one_out(root)
    adr.write_index(root)
    saved_root, saved_env = adr.ROOT, os.environ.get("AGENT_FABRIC_OPERATOR")
    adr.ROOT, os.environ["AGENT_FABRIC_OPERATOR"] = root, op
    try:
        write_registry(os.path.join(op, "projects"))
        found = adr.check(None)          # the operator's tree: ADR-001 alone, the rest the engine's
        assert not [x for x in found if "contiguous" in x or "cites" in x or "pillar" in x], found
        top = max(int(n) for n in adr.record_numbers(os.path.join(root, "docs", "adr")))
        assert os.path.basename(adr.cmd_new(None, "next", "Next")).startswith(f"ADR-{top + 1:03d}-")
        assert not [x for x in adr.check(root) if "contiguous" in x], "--root is the one tree, plus its reserved.json"
        os.remove(os.path.join(root, "docs/adr/reserved.json"))
        only(root, "missing ADR-001")
        assert [x for x in adr.check(None) if "contiguous" in x] == [], "the operator's tree is only its own plus the engine's"
    finally:
        adr.ROOT = saved_root
        if saved_env is None:
            os.environ.pop("AGENT_FABRIC_OPERATOR")
        else:
            os.environ["AGENT_FABRIC_OPERATOR"] = saved_env


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
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
