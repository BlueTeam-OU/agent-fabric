#!/usr/bin/env python3
"""A memory a correction replaced is told to its author (j174): the drain's `superseded_harvests` row names the owner and the
report records the same claim in `obsolete_memories`, which the next drain carries until the memory is read again changed, and
fabric-status lists an agent's own files that a committed report names — never another agent's, never one edited since, and
without touching any file in the agent's home.

Stdlib only; runnable as `python3 test_obsolete_memories.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "fabric"))
import test_assemble as ta  # noqa: E402
import status  # noqa: E402
import harvest_memory as harvest  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ORIGINAL = {"class": "solution", "topic": "t", "title": "Status v1 of the thing", "body": "Original text of the finding.", "evidence": ["h1"]}
CORRECTION = {"class": "solution", "topic": "fix-a", "title": "Status v2 of the thing", "body": "Text A, a longer correction.",
              "evidence": ["h2"], "merge_target": "Status v1 of the thing"}
OTHER = {"class": "solution", "topic": "other", "title": "Something unrelated", "body": "Nothing to do with it.", "evidence": ["h3"]}
OWNERS = {"h1": ("dev-01", "t"), "h2": ("dev-02", "fix-a"), "h3": ("dev-02", "other"), "h4": ("dev-01", "t"), "h5": ("dev-01", "t")}


ONLY_OTHER = {"h3": ("dev-02", "other")}   # a later drain's bundle that never read memory 't'


def observe(drain: str, rows: dict[str, tuple[str, str]] = OWNERS) -> None:
    """Observations as harvest_memory.py writes them: the memory's name is the row's `title`."""
    with open(os.path.join(drain, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for h, (agent, topic) in sorted(rows.items()):
            fh.write(json.dumps({"content_hash": h, "agent": agent, "host": "hostA", "title": topic}) + "\n")


def drain_of(tmp: str) -> tuple[str, str, str]:
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    observe(drain)
    return drain, claims_dir, out


def pass_of(drain: str, claims_dir: str, out: str, bundle: list[dict], stamp: str = "2026-01-01", rows: dict | None = None) -> dict:
    if rows is not None:
        observe(drain, rows)
    ta.set_claims(claims_dir, "alpha", bundle)
    proc = ta.run_assemble(drain, claims_dir, out, "--stamp", stamp)
    assert proc.returncode == 0, proc.stderr
    return json.loads(ta.read(ta.report_path(out)))


def replayed(tmp: str) -> tuple[str, str, str, dict]:
    """The original, its correction, then the original again: one drain whose report names memory 't' as obsolete."""
    drain, claims_dir, out = drain_of(tmp)
    pass_of(drain, claims_dir, out, [ORIGINAL])
    pass_of(drain, claims_dir, out, [CORRECTION])
    return drain, claims_dir, out, pass_of(drain, claims_dir, out, [ORIGINAL])


def test_a_row_names_its_owner_and_the_record_names_the_slice_and_heading(tmp: str) -> None:
    _d, _c, _o, report = replayed(tmp)
    (note,) = report["superseded_harvests"]
    assert "memory 't' (dev-01@hostA)" in note and "update or delete 't'" in note, note
    (row,) = report["obsolete_memories"]
    assert row == {"memory": "t", "agent": "dev-01", "host": "hostA", "content_hash": "h1", "slice": row["slice"],
                   "heading": "Status v1 of the thing"} and row["slice"].endswith(":t"), row


def test_a_same_run_predecessor_names_its_owner_too(tmp: str) -> None:
    drain, claims_dir, out = drain_of(tmp)
    pass_of(drain, claims_dir, out, [ORIGINAL])
    report = pass_of(drain, claims_dir, out, [ORIGINAL, CORRECTION], stamp="2026-01-02")
    (note,) = report["superseded_harvests"]
    assert "memory 't' (dev-01@hostA)" in note, note
    assert [(r["memory"], r["agent"], r["host"]) for r in report["obsolete_memories"]] == [("t", "dev-01", "hostA")]


def test_a_memory_nobody_unattributed_is_named_without_a_record(tmp: str) -> None:
    """An origin the harvest could not attribute has no agent to tell: the row says so and writes no record."""
    drain, claims_dir, out = drain_of(tmp)
    pass_of(drain, claims_dir, out, [ORIGINAL], rows={"h1": ("unresolved", "t"), "h2": ("dev-02", "fix-a")})
    pass_of(drain, claims_dir, out, [CORRECTION])
    report = pass_of(drain, claims_dir, out, [ORIGINAL])
    assert "owner unknown" in report["superseded_harvests"][0] and report["obsolete_memories"] == [], report


def test_a_row_survives_the_next_drain_that_does_not_read_the_memory(tmp: str) -> None:
    drain, claims_dir, out, first = replayed(tmp)
    later = pass_of(drain, claims_dir, out, [OTHER], stamp="2026-01-02", rows=ONLY_OTHER)
    assert later["superseded_harvests"] == [] and later["obsolete_memories"] == first["obsolete_memories"], later


def test_a_row_ends_when_the_memory_is_read_again_changed(tmp: str) -> None:
    drain, claims_dir, out, _first = replayed(tmp)
    rewritten = dict(ORIGINAL, body="Another account of the matter, rewritten by its author.", evidence=["h4"])
    later = pass_of(drain, claims_dir, out, [rewritten], stamp="2026-01-02", rows={"h4": ("dev-01", "t")})
    assert later["obsolete_memories"] == [], later["obsolete_memories"]


def test_a_row_stays_when_the_memory_is_read_again_unchanged_and_not_flagged(tmp: str) -> None:
    drain, claims_dir, out, first = replayed(tmp)
    later = pass_of(drain, claims_dir, out, [OTHER], stamp="2026-01-02")   # OWNERS still holds h1, the unchanged memory 't'
    assert later["obsolete_memories"] == first["obsolete_memories"], later["obsolete_memories"]


def test_a_held_slice_keeps_no_obsolete_record(tmp: str) -> None:
    drain, claims_dir, out, first = replayed(tmp)
    assert first["obsolete_memories"], "the control: the record is there before the hold"
    hold = os.path.join(tmp, "hold.json")
    with open(hold, "w", encoding="utf-8") as fh:
        json.dump(["alpha/solution:t"], fh)
    ta.set_claims(claims_dir, "alpha", [ORIGINAL])
    proc = ta.run_assemble(drain, claims_dir, out, "--hold", hold)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(ta.read(ta.report_path(out)))["obsolete_memories"] == []


def test_a_hold_under_a_later_stamp_keeps_the_carried_row(tmp: str) -> None:
    drain, claims_dir, out, first = replayed(tmp)
    hold = os.path.join(tmp, "hold.json")
    with open(hold, "w", encoding="utf-8") as fh:
        json.dump(["alpha/solution:t"], fh)
    ta.set_claims(claims_dir, "alpha", [dict(OTHER, topic="t", title="A newer claim to the slice")])   # a hold names a slice the drain has
    proc = ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02", "--hold", hold)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(ta.read(ta.report_path(out)))["obsolete_memories"] == first["obsolete_memories"]


def test_a_row_is_renewed_when_the_memory_is_read_again_unchanged(tmp: str) -> None:
    drain, claims_dir, out, first = replayed(tmp)
    later = pass_of(drain, claims_dir, out, [ORIGINAL], stamp="2026-01-02")
    assert later["obsolete_memories"] == first["obsolete_memories"] and len(later["superseded_harvests"]) == 1, later


def test_an_earlier_report_without_the_record_parses_and_a_malformed_row_is_dropped(tmp: str) -> None:
    drain, claims_dir, out, _first = replayed(tmp)
    path = ta.report_path(out)
    report = json.loads(ta.read(path))
    del report["obsolete_memories"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    assert pass_of(drain, claims_dir, out, [OTHER], stamp="2026-01-02", rows=ONLY_OTHER)["obsolete_memories"] == []
    report["obsolete_memories"] = ["junk", {"memory": "t"}, {"memory": "t", "agent": "dev-01", "host": "hostA", "content_hash": "h1",
                                                            "slice": "s", "heading": "h"}]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    rows = pass_of(drain, claims_dir, out, [OTHER], stamp="2026-01-03", rows=ONLY_OTHER)["obsolete_memories"]
    assert [r["content_hash"] for r in rows] == ["h1"], rows


# --- fabric-status --------------------------------------------------------

def memory_file(directory: str, name: str, body: str) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name + ".md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"---\nname: {name}\ndescription: d\nmetadata:\n  type: project\n  roles_class: solution\n---\n{body}\n")
    return path


def put_report(base: str, rows: object) -> str:
    path = os.path.join(base, ".agent-fabric", "memory", "last-drain-report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"obsolete_memories": rows} if rows is not None else {}, fh)
    return path


def row(name: str, body: str, agent: str = "me", host: str = "hostA") -> dict:
    return {"memory": name, "agent": agent, "host": host, "content_hash": harvest.content_hash(name, body),
            "slice": "alpha/solution:t", "heading": "Status v1"}


def world(tmp: str) -> tuple[dict, str, str, str]:
    home, wc, root = (os.path.join(tmp, d) for d in ("home", "wc", "root"))
    for d in (home, wc, os.path.join(root, "tools")):
        os.makedirs(d)
    os.symlink(os.path.join(os.path.dirname(HERE), "tools", "fabric"), os.path.join(root, "tools", "fabric"))   # status loads harvest_memory from the root
    ctx = {"agent": "me", "host": "hostA", "project": "p", "working_copy": wc}
    return ctx, os.path.join(home, ".claude", "projects", harvest.layout.memory_slug(wc), "memory"), root, home


def listed(ctx: dict, root: str, home: str) -> list[dict] | None:
    with mock.patch.dict(os.environ, {"HOME": home}):
        return status.obsolete_memories(ctx, root)


def test_status_lists_the_agents_own_obsolete_memory_with_the_action(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    path = memory_file(mem, "t", "Original text.")
    report = put_report(ctx["working_copy"], [row("t", "Original text.")])
    (hit,) = listed(ctx, root, home)
    assert hit == {"file": path, "memory": "t", "slice": "alpha/solution:t", "heading": "Status v1", "report": os.path.realpath(report),
                   "action": "update or delete"}, hit
    lines = status.render({"agent": "a", "host": "h", "role": None, "launched_role": None, "drift": None, "project": None, "working_copy": None,
                           "session": None, "binding_updated": None, "jobs": {"active": None, "queued": 0, "paused": 0, "blocked": 0, "delivered": 0},
                           "api": {"provider": "anthropic", "path": "x", "base_url_host": None, "session_model": "m", "launch_profile": None,
                                   "pins": "p", "credentials": "c", "claude_sign_in": "s"}, "capabilities": {}, "routing_check": "clean",
                           "undrained_memories": None, "obsolete_memories": [hit], "host_tools": {"moveto": {"installed": False}},
                           "control_plane": "/r"}, "")
    assert any(l.startswith("obsolete     ") and path in l and "update or delete" in l for l in lines), lines


def test_status_names_nobody_elses_memory(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    memory_file(mem, "t", "Original text.")
    put_report(ctx["working_copy"], [row("t", "Original text.", agent="someone-else"), row("t", "Original text.", host="hostB")])
    assert listed(ctx, root, home) == []


def test_a_memory_changed_since_the_drain_is_no_longer_listed(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    memory_file(mem, "t", "Original text.")
    put_report(ctx["working_copy"], [row("t", "Original text.")])
    assert len(listed(ctx, root, home)) == 1
    memory_file(mem, "t", "Original text, updated by its author.")
    assert listed(ctx, root, home) == []


def test_a_deleted_memory_is_no_longer_listed(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    os.makedirs(mem)
    put_report(ctx["working_copy"], [row("t", "Original text.")])
    assert listed(ctx, root, home) == []


def test_every_report_is_read(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    memory_file(mem, "a", "Body A.")
    memory_file(mem, "b", "Body B.")
    put_report(ctx["working_copy"], [row("a", "Body A.")])
    put_report(root, [row("b", "Body B.")])
    assert [h["memory"] for h in listed(ctx, root, home)] == ["a", "b"]


def test_a_report_without_the_record_or_unreadable_names_nothing_and_no_working_copy_is_none(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    memory_file(mem, "t", "Original text.")
    put_report(ctx["working_copy"], None)
    assert listed(ctx, root, home) == []
    with open(put_report(root, None), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert listed(ctx, root, home) is None, "an unreadable report is unknown, not 'nothing obsolete'"
    put_report(root, None)
    put_report(ctx["working_copy"], "not a list")
    assert listed(ctx, root, home) is None
    assert listed(dict(ctx, working_copy=None), root, home) is None


def test_status_changes_no_file_in_the_agents_home(tmp: str) -> None:
    ctx, mem, root, home = world(tmp)
    memory_file(mem, "t", "Original text.")
    put_report(ctx["working_copy"], [row("t", "Original text.")])

    def snapshot() -> dict:
        return {p: (os.stat(p).st_mtime_ns, open(p, "rb").read()) for d, _s, fs in os.walk(home) for f in fs for p in [os.path.join(d, f)]}
    before = snapshot()
    assert len(listed(ctx, root, home)) == 1 and snapshot() == before


def main() -> int:
    cases = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
