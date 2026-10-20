#!/usr/bin/env python3
"""Linked sections and the opt-in `expand: 1` of memory_find (agent-fabric ADR-049 follow-up, a spike): the keys a section
derives, the edges between sections that share one, the one-hop neighbours of the strong hits, and the find that shows them
after the hits and not in place of one. Built on sections made in memory, so each case says what links what. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "runtime"))
import memory_index as mi  # noqa: E402
from memory_mcp import tools  # noqa: E402


def section(name: str, text: str, heading: str = "a cue", role: str = "dev", topic: str = "topic", directory: str = "memory/domains/dev/domain",
            position: int = 1) -> mi.Section:
    return mi.Section(slice_id=f"{directory}/{name}.md", heading=heading, cue="", kind="domain", scope="field", role=role,
                      title=topic, position=position, shared_with=(), projects=(), observed="2026-10-10", text=text)


def index_of(*sections: mi.Section) -> mi.Index:
    return mi.Index(sections=list(sections))


def hit(s: mi.Section, band: str = "strong") -> mi.Hit:
    return mi.Hit(s, 10.0, 1.0, band)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + str(detail).replace("\n", "\n      "))
        fails += not good

    print("the keys of a section")
    s = section("a-slice", "Text.\n*Anchors: `tools/fabric/launch.py::Launcher.run` `docs/x.md`*\nSee `tests/run.sh:42` and [[Other-Memory]] and [[a-slice]].\n"
                "Not a path: `just/a/dir` and `no_slash.py`.")
    keys = mi.section_keys(s)
    check("an anchor gives its path and its symbol", {"path:tools/fabric/launch.py", "symbol:launcher.run", "path:docs/x.md"} <= keys, sorted(keys))
    check("a path cited in backticks gives its path, a line number dropped", "path:tests/run.sh" in keys, sorted(keys))
    check("a backticked word with no slash or no extension is no path", not {"path:just/a/dir", "path:no_slash.py"} & keys, sorted(keys))
    check("a [[link]] is lower-cased and kept", "link:other-memory" in keys, sorted(keys))
    check("a section's own file name is a name, never a link to itself", "name:a-slice" in keys and "link:a-slice" not in keys, sorted(keys))
    check("its role and topic make the topic key", "topic:dev/topic" in keys, sorted(keys))
    prefixed = mi.section_keys(section("workflow-run-suites", "x", directory=".agent-fabric/memory/shared"))
    check("a project slice's file name loses its class prefix as a second name", {"name:workflow-run-suites", "name:run-suites"} <= prefixed, sorted(prefixed))
    check("a section with no role has no topic key", not any(k.startswith("topic:") for k in mi.section_keys(section("n", "x", role=""))))
    traversal = mi.section_keys(section("n", "*Anchors: `/etc/passwd` `../../outside.py`*"))
    check("an anchor that leaves the tree is no key (the same rule the checker reads by)", not any(k.startswith("path:") for k in traversal), sorted(traversal))

    print("the edges")
    cited = section("cited-memory", "The memory others cite.", topic="alpha")
    citer = section("citer-one", "Related: [[cited-memory]].", topic="beta")
    citer2 = section("citer-two", "Also [[cited-memory]].", topic="gamma")
    lonely = section("lonely", "Nothing links here.", topic="delta")
    ix = index_of(cited, citer, citer2, lonely)
    edges = ix._edges()
    kinds = lambda a, b: sorted(k for k, _key, _n in edges.get(a, {}).get(b, []))  # noqa: E731
    check("a section that cites a memory is directly linked to the one named for it, from both sides",
          kinds(0, 1) == ["direct"] and kinds(1, 0) == ["direct"] and kinds(0, 2) == ["direct"])
    check("two sections that cite the same third are co-cited", kinds(1, 2) == ["cocite"])
    check("a section nothing shares a key with has no edge", 3 not in edges)
    crowd = [section(f"crowd-{n}", "See `tests/shared.sh`.", topic=f"t{n}") for n in range(mi.KEY_DF_CAP + 1)]
    check("a path held by more sections than KEY_DF_CAP links nothing", not index_of(*crowd)._edges())
    cite_crowd = [section(f"cite-crowd-{n}", "See [[a-popular-memory]].", topic=f"c{n}") for n in range(mi.KEY_DF_CAP + 1)]
    check("a memory cited by more sections than KEY_DF_CAP co-cites none of them", not index_of(*cite_crowd)._edges())
    pop = section("a-popular-memory", "The memory everyone cites.", topic="pop")
    check("a memory cited by more sections than KEY_DF_CAP is directly linked to none of them", not index_of(pop, *cite_crowd)._edges())
    pop_edges = index_of(pop, *cite_crowd[:mi.KEY_DF_CAP])._edges()
    check("…and cited by exactly KEY_DF_CAP, to all of them (and they co-cite each other)", len(pop_edges.get(0, {})) == mi.KEY_DF_CAP and len(pop_edges) == mi.KEY_DF_CAP + 1)
    named_twice = index_of(*(section("a-popular-memory", f"x{n}", heading=f"cue {n}", position=n + 1, topic="pop") for n in range(mi.KEY_DF_CAP + 2)),
                           section("one-citer", "See [[a-popular-memory]]."))
    check("a name held by more sections than KEY_DF_CAP (a slice of many sections) is linked to a citer by KEY_DF_CAP of them at most",
          len(named_twice._edges().get(mi.KEY_DF_CAP + 2, {})) == mi.KEY_DF_CAP, len(named_twice._edges().get(mi.KEY_DF_CAP + 2, {})))
    cite_fits = [section(f"cite-fit-{n}", "See [[a-popular-memory]].", topic=f"c{n}") for n in range(mi.KEY_DF_CAP)]
    check("…and by exactly KEY_DF_CAP co-cites them all", len(index_of(*cite_fits)._edges()) == mi.KEY_DF_CAP)
    fits = [section(f"fit-{n}", "See `tests/shared.sh`.", topic=f"t{n}") for n in range(mi.KEY_DF_CAP)]
    check("…and by exactly KEY_DF_CAP links them all", len(index_of(*fits)._edges()) == mi.KEY_DF_CAP)
    same = index_of(section("one", "[[two]]", position=1), section("one", "x", heading="other cue", position=2), section("two", "y"))
    check("a second section of the same slice is linked like any other (the find, not the graph, keeps one per slice)", 2 in same._edges().get(0, {}))

    print("a named anchor and the same file anchored unnamed (ADR-050 rule 1, 2026-10-20)")
    import dataclasses
    named = dataclasses.replace(section("fabric-note", "*Anchors: `gzapp:lib/a.dart::Widget`*", topic="tn", directory="memory/domains/dev/domain"), home_project="agent-fabric")
    unnamed = dataclasses.replace(section("gzapp-note", "*Anchors: `lib/a.dart::Widget`*", topic="tu", directory=".agent-fabric/memory/dev"), projects=("gzapp",))
    homed = dataclasses.replace(section("gzapp-home", "See `lib/a.py`.", topic="th", directory=".agent-fabric/memory/dev"), home_project="gzapp")
    other = dataclasses.replace(section("other-note", "*Anchors: `lib/a.dart::Widget`*", topic="to", directory=".agent-fabric/memory/dev"), projects=("blueteam.ee",))
    same_project = dataclasses.replace(section("fabric-own", "*Anchors: `agent-fabric:lib/a.dart::Widget`*", topic="tf"), home_project="agent-fabric")
    check("a named anchor and an unnamed one of a slice from that project hold one path key",
          mi.section_keys(named) & mi.section_keys(unnamed) >= {"path:gzapp:lib/a.dart"}, (sorted(mi.section_keys(named)), sorted(mi.section_keys(unnamed))))
    check("a path cited in backticks takes the slice's home project when it has no origin", "path:gzapp:lib/a.py" in mi.section_keys(homed), sorted(mi.section_keys(homed)))
    check("an unnamed anchor in a slice with no origin and no home project keeps the bare path, which no named anchor shares",
          mi.section_keys(section("n", "*Anchors: `lib/a.dart`*")) & {"path:lib/a.dart"} and not mi.section_keys(named) & {"path:lib/a.dart"})
    check("a named anchor of the slice's own project is the unnamed one", mi.section_keys(same_project) >= {"path:agent-fabric:lib/a.dart"})
    pair = index_of(named, unnamed)
    got = pair.neighbours([hit(named)], kinds=("path",))
    check("from the slice naming the project, the slice of that project is a neighbour by the shared path",
          [mi.section_id(n.section) for n in got] == [mi.section_id(unnamed)] and got[0].via == ("path:gzapp:lib/a.dart",), got)
    back = pair.neighbours([hit(unnamed)], kinds=("path",))
    check("…and the other way round", [mi.section_id(n.section) for n in back] == [mi.section_id(named)], back)
    apart = index_of(named, other)
    check("the same relative path in two different projects stays two nodes: no path edge (the shared symbol still links them)",
          apart.neighbours([hit(named)], kinds=("path",)) == [] and [n.via for n in apart.neighbours([hit(named)], kinds=mi.KEY_KINDS)] == [("symbol:widget",)])
    check("memory_find's default expansion follows direct links only, so it does not add a path-linked section (DEFAULT_KINDS, measured)",
          pair.neighbours([hit(named)]) == [])

    loaded = mi.Index()
    files = {"dev/domain/x.md": b"---\nrole: dev\nclass: domain\ntopic: x\n---\n\n## a cue\n\nBody.\n\n*Anchors: `lib/a.py::Widget`*\n"}
    mi._load_root(loaded, files, "memory", "agent-fabric")
    mi._load_root(loaded, files, ".agent-fabric/memory")
    check("a slice loaded from the fabric's memory/ is the fabric's project; one from a working copy of unknown project is none",
          [s.home_project for s in loaded.sections] == ["agent-fabric", ""] and "path:agent-fabric:lib/a.py" in mi.section_keys(loaded.sections[0])
          and "path:lib/a.py" in mi.section_keys(loaded.sections[1]), [(s.home_project, sorted(mi.section_keys(s))) for s in loaded.sections])
    import shutil
    import subprocess
    import tempfile
    repo = tempfile.mkdtemp(prefix="memexp-")
    try:
        os.makedirs(os.path.join(repo, "memory", "dev", "domain"))
        with open(os.path.join(repo, "memory", "dev", "domain", "x.md"), "wb") as fh:
            fh.write(files["dev/domain/x.md"])
        genv = {"PATH": "/usr/bin:/bin", "HOME": repo, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        for argv in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@example.test", "-c", "commit.gpgsign=false", "-c", "gc.auto=0",
                                                     "-c", "maintenance.auto=false", "commit", "-q", "-m", "x"]):
            subprocess.run(["git", "-C", repo, *argv], env=genv, check=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        built = mi.build(os.path.join(repo, "memory"), None)
        check("build() gives the fabric's memory/ slices the fabric's project, so their unnamed paths resolve",
              [s.home_project for s in built.sections] == ["agent-fabric"] and "path:agent-fabric:lib/a.py" in mi.section_keys(built.sections[0]),
              [(s.home_project, sorted(mi.section_keys(s))) for s in built.sections])
    finally:
        shutil.rmtree(repo, True)
    check("a checkout the registry cannot place is no project, never a guess", mi._project_of("/nonexistent/for/this/test") == "")

    print("the neighbours of the hits")
    seed = hit(cited)
    got = ix.neighbours([seed])
    check("the sections linked to a strong hit come back, naming the hit and the kind of link",
          {mi.section_id(n.section) for n in got} == {mi.section_id(citer), mi.section_id(citer2)}
          and all(n.seed is cited and n.via[0].startswith("direct:") for n in got), got)
    check("a weak hit is no seed", ix.neighbours([hit(cited, "weak")]) == [] and ix.neighbours([hit(cited, "none")]) == [])
    check("…unless the caller asks for its band", len(ix.neighbours([hit(cited, "weak")], seed_bands=("strong", "weak"))) == 2)
    check("a section that is itself a hit is not a neighbour", [mi.section_id(n.section) for n in ix.neighbours([seed, hit(citer)])] == [mi.section_id(citer2)])
    check("at most per_hit neighbours of a hit, and total in all", len(ix.neighbours([seed], per_hit=1)) == 1 and len(ix.neighbours([seed], total=1)) == 1)
    many = [section("many-seed", "x", topic="s")] + [section(f"a-fairly-long-slice-name-for-a-citer-number-{n}", "[[many-seed]]", heading="a heading long enough to be clipped at sixty characters, " * 2, topic=f"m{n}") for n in range(5)]
    wide = index_of(*many)
    check("per_hit, from_top and total each bound the neighbours (2 a hit by default, 4 in all)", len(wide.neighbours([hit(many[0])])) == mi.PER_HIT == 2
          and len(wide.neighbours([hit(many[0])], per_hit=5)) == mi.MAX_NEIGHBOURS == 4, len(wide.neighbours([hit(many[0])], per_hit=5)))
    check("only the top from_top hits seed", ix.neighbours([hit(lonely), seed], from_top=1) == [])
    shared = index_of(section("p", "`x/y.py`", topic="tp"), section("q", "`x/y.py`", topic="tq"))
    check("by default only direct links are followed: a section sharing only a path is no neighbour",
          shared.neighbours([hit(shared.sections[0])]) == [] and len(shared.neighbours([hit(shared.sections[0])], kinds=mi.KEY_KINDS)) == 1)
    check("by default a co-citer is no neighbour either: citer2 is reached from citer only with cocite asked for",
          [mi.section_id(n.section) for n in ix.neighbours([hit(citer)])] == [mi.section_id(cited)]
          and mi.section_id(citer2) in [mi.section_id(n.section) for n in ix.neighbours([hit(citer)], kinds=("direct", "cocite"))])
    check("a kind left out of kinds gives no edge of it", ix.neighbours([seed], kinds=("cocite",)) == [])
    two_ways = index_of(section("a", "[[b]] `x/y.py`", topic="ta"), section("b", "`x/y.py`", topic="tb"), section("c", "[[a]]", topic="tc"))
    ranked = two_ways.neighbours([hit(two_ways.sections[0])], kinds=mi.KEY_KINDS)
    check("two kinds of edge outweigh one: the section linked twice comes first", [mi.section_id(n.section) for n in ranked][0] == mi.section_id(two_ways.sections[1])
          and len(ranked[0].via) == 2, ranked)
    same_slice = index_of(section("only", "[[only]] x"), section("only", "y", heading="second", position=2))
    check("the other sections of a hit's own slice are not its neighbours", same_slice.neighbours([hit(same_slice.sections[0])]) == [])

    print("memory_find with and without expand")
    docs = [section(f"doc{n}", f"quartz {'[[cited-memory]]' if n == 1 else ''} widget{n}", heading=f"quartz widget {n}", topic=f"t{n}") for n in range(1, 4)]
    corpus = index_of(*docs, cited, citer2)
    # A corpus this small never scores a strong band by the real thresholds: lowered here, for the seeds, and put back.
    real_strong = mi.STRONG_SCORE
    mi.STRONG_SCORE = 0.5
    try:
        session = tools.Session()
        text0, ids0 = tools.find(corpus, session, {"query": "quartz widget"})
        session1 = tools.Session()
        text1, ids1 = tools.find(corpus, session1, {"query": "quartz widget", "expand": 1})
        tight0, _ = tools.find(corpus, tools.Session(), {"query": "quartz widget", "max_tokens": tools.MIN_TOKENS})
        tight1, _ = tools.find(corpus, tools.Session(), {"query": "quartz widget", "max_tokens": tools.MIN_TOKENS, "expand": 1})
    finally:
        mi.STRONG_SCORE = real_strong
    check("without expand nothing is linked and no line says so", "linked to" not in text0, text0)
    check("with expand the hits are the same lines in the same order, then the linked ones",
          [ln for ln in text1.splitlines() if "linked to" not in ln] == text0.splitlines() and text1.splitlines()[len(text0.splitlines())].startswith(mi.section_id(cited)), text1)
    check("…each linked line names the hit and the kind and has no score or band", any(ln.startswith(mi.section_id(cited)) and "linked to " in ln and "by direct" in ln and "strong" not in ln for ln in text1.splitlines()), text1)
    check("…the ids returned and shown include the neighbour, so a mark or a read may name it",
          mi.section_id(cited) in ids1 and mi.section_id(cited) in session1.shown and mi.section_id(cited) not in ids0, (ids0, ids1))
    check("…the neighbours cost no more than the allowance, whatever the budget", sum(max(1, round(len(ln) * tools.TOKENS_PER_CHAR)) for ln in text1.splitlines() if "linked to" in ln) <= tools.NEIGHBOUR_TOKENS)
    check("a tight budget keeps the same hits with expand, in the same order", [ln for ln in tight1.splitlines() if "linked to" not in ln] == tight0.splitlines(), (tight0, tight1))
    real_strong = mi.STRONG_SCORE
    mi.STRONG_SCORE = 0.05
    try:
        seeds = [section(f"marigold-seed-{k}", "marigold", heading=f"marigold seed {k}", topic=f"s{k}") for k in range(3)]
        citers = [section(f"a-fairly-long-slice-name-for-a-citer-number-{k}-{n}", f"[[marigold-seed-{k}]]", heading="a heading long enough to be clipped at sixty characters, " * 2,
                          topic=f"m{k}{n}") for k in range(3) for n in range(2)]
        for_allowance = seeds + citers
        allowed, _ = tools.find(index_of(*for_allowance), tools.Session(), {"query": "marigold", "expand": 1})
    finally:
        mi.STRONG_SCORE = real_strong
    spent = [max(1, round(len(ln) * tools.TOKENS_PER_CHAR)) for ln in allowed.splitlines() if "linked to" in ln]
    check("the neighbours stop at the allowance, though more are linked", 1 <= len(spent) < mi.MAX_NEIGHBOURS and sum(spent) <= tools.NEIGHBOUR_TOKENS, (spent, allowed))
    for bad in (2, -1, "1", True, 1.5):
        try:
            tools.find(corpus, tools.Session(), {"query": "quartz widget", "expand": bad})
            check(f"expand {bad!r} is refused or clamped", bad in (2, -1), bad)
        except tools.ToolError as e:
            check(f"expand {bad!r} is refused in one line", "expand must be an integer" in str(e), str(e))
    schema = tools.TOOLS["memory_find"][2]
    check("the tool schema offers expand 0 or 1", schema["expand"]["minimum"] == 0 and schema["expand"]["maximum"] == 1, schema)

    print("test_memory_expand:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
