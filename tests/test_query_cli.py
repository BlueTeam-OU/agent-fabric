#!/usr/bin/env python3
"""The oracle for tools/fabric/query.sh: what the citation graph answers,
exactly, for every subcommand, over a scratch fabric root with crossref.json
files of the shape the assembler writes (tools/fabric/assemble.py:
{"role","generated_at","index":{kind:{value:{"observations":[…],"slices":[…]}}}}).

The CLI under test is the path in $QUERY_CLI, default tools/fabric/query.sh, so
one file runs against the shim and against the bash it replaced. The root
defaults to the script's own checkout, so a copy outside the repository needs
a memory/ beside its tools/.

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.environ.get("QUERY_CLI") or os.path.join(HERE, "tools", "fabric", "query.sh")
if not os.path.isfile(CLI):
    sys.exit(f"test: script under test not found at {CLI}")

T = tempfile.mkdtemp(prefix="test_query_cli.")
ROOT = f"{T}/root"      # basename "root" labels its own roles
WC_A = f"{T}/wc-a"      # AGENT_FABRIC_WORKING_COPY
WC_B = f"{T}/wc-b"      # AGENT_FABRIC_WORKING_COPIES
WC_C = f"{T}/wc-c"      # named by the binding
STATE = f"{T}/state"
HOME = f"{T}/home"
LOGIN = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()

fails = 0
rc = 0
out = ""
err = ""


def ok(label: str) -> None:
    print(f"  ok   {label}")


def fail(label: str, detail: str = "") -> None:
    global fails
    fails += 1
    print(f"  FAIL {label}")
    for line in detail.splitlines():
        print(f"      {line}")


def put(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def xref(path: str, role: str, index: str) -> None:
    put(path, json.dumps({"generated_at": "2026-09-27", "index": json.loads(index), "role": role}, indent=2) + "\n")


def clean_env() -> dict[str, str]:
    # The ordering of roles follows the locale; the oracle fixes it. The
    # caller's own AGENT_FABRIC_*, GITHUB_* and XDG_STATE_HOME never reach the CLI.
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("GITHUB_", "AGENT_FABRIC_")) and k != "XDG_STATE_HOME"}
    e.update(HOME=HOME, LC_ALL="C")
    return e


def run(*args: str, **env: str) -> None:
    """The CLI under a clean environment plus env; sets rc, out, err."""
    global rc, out, err
    e = clean_env()
    e.update(env)
    p = subprocess.run([CLI, *args], env=e, capture_output=True, timeout=60)
    rc = p.returncode
    out = p.stdout.decode("utf-8", "surrogateescape")
    err = p.stderr.decode("utf-8", "surrogateescape")


def full(**more: str) -> dict[str, str]:
    e = dict(AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_STATE_DIR=STATE, AGENT_FABRIC_WORKING_COPY=WC_A,
             AGENT_FABRIC_WORKING_COPIES=f"{WC_B}::{T}/nonexistent: :{WC_A}")
    e.update(more)
    return e


def expect(name: str, want_rc: int, want_out: str, want_err: str) -> None:
    """The last run, exactly."""
    problems = []
    if rc != want_rc:
        problems.append(f"exit {rc}, wanted {want_rc}")
    if out != want_out:
        problems.append(f"stdout: wanted {want_out!r}, got {out!r}")
    if err != want_err:
        problems.append(f"stderr: wanted {want_err!r}, got {err!r}")
    if problems:
        fail(name, "\n".join(problems))
    else:
        ok(name)


def expect_names(name: str, want_rc: int, file: str) -> None:
    """The last run refused the file: nothing on stdout, the exit status, and
    the file named on stderr. The bash said it in jq's words."""
    if rc == want_rc and not out and file in err:
        ok(name)
    else:
        fail(name, f"rc={rc}\n{out}{err}")


def check(name: str, good: bool, detail: str = "") -> None:
    ok(name) if good else fail(name, detail)


def head_(label: str) -> str:
    return f"\n{label}\n"


def hit(name: str, n: int, slices: str) -> str:
    return f"  {name:<44} {n} obs\n      slices: {slices}\n"


def cites(kind: str, value: str) -> str:
    return f"  {kind:<12} {value}\n"


def table(*rows: tuple) -> str:
    return "".join(f"{a:<28} {b:<8} {c:<8} {d}\n" for a, b, c, d in rows)


def fixtures() -> None:
    os.makedirs(STATE)
    os.makedirs(HOME)
    os.makedirs(f"{ROOT}/memory")
    put(f"{ROOT}/memory/domains/devrole/a.md", "a")
    put(f"{ROOT}/memory/domains/devrole/b.md", "b")
    put(f"{ROOT}/memory/domains/devrole/INDEX.md", "index")
    leg = f"{ROOT}/memory/projects/legacyproj/devrole"
    put(f"{leg}/s1.md", "built from deadbeef01 and 11112222")
    put(f"{leg}/sub/s2.md", "nothing")
    put(f"{leg}/INDEX.md", "deadbeef01 in an index is still a mention")
    xref(f"{leg}/crossref.json", "devrole", '''{
    "adrs": {
      "ADR-054": {"observations": ["11112222", "deadbeef01"], "slices": ["lesson:a", "solution:b"]},
      "ADR-0541": {"observations": [], "slices": ["lesson:c"]}
    },
    "archs": {"arch-1": {"observations": ["cafe0002"], "slices": ["lesson:a"]}},
    "commits": {"abc1234": {"observations": ["cafe0002"], "slices": ["lesson:a"]}},
    "contracts": {"CONTRACT-9": {"observations": [], "slices": ["lesson:a"]}},
    "error_codes": {"E_BAD": {"observations": ["cafe0002"], "slices": ["lesson:a"]}},
    "files": {
      "apps/status_web": {"observations": ["cafe0002"], "slices": ["lesson:a"]},
      "apps/status_web/lib/main.dart": {"observations": [], "slices": ["lesson:c"]},
      "weird.key[1]*": {"observations": [], "slices": ["lesson:a"]}
    },
    "migrations": {"migration-0007": {"observations": ["cafe0002"], "slices": ["lesson:a"]}},
    "prs": {"#428": {"observations": ["cafe0002", "11112222"], "slices": ["lesson:p"]}}
  }''')
    xref(f"{ROOT}/.agent-fabric/memory/fabric-coordinator/crossref.json", "fabric-coordinator", '''{
    "adrs": {"ADR-054": {"observations": ["deadbeef01", "cafe0002"], "slices": ["lesson:one"]}}
  }''')
    put(f"{WC_A}/.agent-fabric/memory/devrole/note.md", "evidence: deadbeef01")
    put(f"{WC_A}/.agent-fabric/memory/devrole/INDEX.md", "x")
    xref(f"{WC_A}/.agent-fabric/memory/devrole/crossref.json", "devrole", '''{
    "adrs": {"ADR-054": {"observations": ["deadbeef01"], "slices": ["lesson:z"]}},
    "prs": {"#428": {"observations": [], "slices": ["lesson:q"]}}
  }''')
    xref(f"{WC_B}/.agent-fabric/memory/qa/crossref.json", "qa", '''{
    "adrs": {"Ünï-1": {"observations": ["feed0003"], "slices": ["lesson:ü"]}},
    "files": {"apps/status_web": {"observations": [], "slices": ["lesson:w"]}}
  }''')
    # An artifact with an observation and no slice: pinned below. ADR-002 is
    # what the working-copy discovery cases ask for: an ordinary hit, so they
    # hold the bash to discovery alone, not to the empty-slice fix (review of
    # #73).
    xref(f"{WC_C}/.agent-fabric/memory/ops/crossref.json", "ops", '''{
    "adrs": {"ADR-001": {"observations": ["0abc"], "slices": []},
             "ADR-002": {"observations": ["0abd"], "slices": ["lesson:found"]}}
  }''')
    put(f"{STATE}/binding.json", json.dumps({"working_copy": WC_C, "role": "x"}) + "\n")


HELP = """Ask the corpus what it knows about an artifact.

  tools/fabric/query.sh adr ADR-054       # who learned from it, where it landed
  tools/fabric/query.sh pr 428
  tools/fabric/query.sh migration 0007
  tools/fabric/query.sh file apps/status_web
  tools/fabric/query.sh obs <content-hash>
  tools/fabric/query.sh roles             # what roles exist, per project, and how big they are

The citation graph is small — thousands of edges — so it lives in the
committed JSON the assembler writes (<working copy>/.agent-fabric/memory/
<role>/crossref.json in each project's repository; memory/projects/
<project>/ here while a project has not moved), and jq answers everything
in milliseconds. Which working copies are searched: this checkout (for
agent-fabric itself), $AGENT_FABRIC_WORKING_COPY, the working copy the
agent's binding names, and every entry of $AGENT_FABRIC_WORKING_COPIES
(colon-separated). A database
would buy nothing here and would cost the one property that matters
most: the graph is reviewable in a pull request, because it is a diff
like everything else.

If multi-hop queries ever become routine, the next step is a generated
SQLite edge cache rebuilt from these files — derived, never authoritative.
Git stays the source of truth.
"""

KINDS = "adr arch pr commit contract error migration file"


def main() -> int:
    fixtures()
    adr054_all = (head_("root/fabric-coordinator") + hit("ADR-054", 2, "lesson:one")
                  + head_("legacyproj/devrole") + hit("ADR-054", 2, "lesson:a, solution:b") + hit("ADR-0541", 0, "lesson:c")
                  + head_("wc-a/devrole") + hit("ADR-054", 1, "lesson:z"))
    nocorpus = f"query: no corpus at {T}/empty/memory\n"
    bare = dict(AGENT_FABRIC_ROOT=f"{T}/bare", AGENT_FABRIC_STATE_DIR=f"{T}/nostate")
    nothing = lambda what: f"nothing in the corpus cites {what}\n"  # noqa: E731

    print("query: the help")
    run(**full())
    expect("help (no argument)", 0, HELP, "")
    run("", **full())
    expect("help (an empty argument)", 0, HELP, "")
    for a in ("-h", "--help", "help"):
        run(a, **full())
        expect(f"help ({a})", 0, HELP, "")
    run("help", "roles", "ignored", "extra", **full())
    expect("help ignores what follows it", 0, HELP, "")

    print("query: a corpus that is missing")
    run("adr", "ADR-054", AGENT_FABRIC_ROOT=f"{T}/empty")
    expect("no corpus: exit 2, said", 2, "", nocorpus)
    # The corpus is checked before the command is read: even the help needs it.
    run("--help", AGENT_FABRIC_ROOT=f"{T}/empty")
    expect("no corpus: the help does not get past it", 2, "", nocorpus)
    os.makedirs(f"{T}/bare/memory")
    run("roles", **bare)
    expect("a corpus with no crossref: the header only", 0, "project/role                 project  domain   citations\n", "")
    run("adr", "ADR-054", **bare)
    expect("a corpus with no crossref: nothing cites it", 0, nothing("ADR-054"), "")

    print("query: the arguments")
    run("bogus", "x", **full())
    expect("an unknown kind", 2, "", f"query: unknown artifact kind 'bogus' ({KINDS})\n")
    run("bogus", **full())
    expect("an unknown kind alone: asks for an artifact first", 2, "", "query: need an artifact, e.g. 'adr ADR-054'\n")
    run("adr", **full())
    expect("a kind without an artifact", 2, "", "query: need an artifact, e.g. 'adr ADR-054'\n")
    run("obs", **full())
    expect("obs without a hash", 2, "", "query: obs needs a content hash\n")
    run("errors", "x", **full())
    expect("'errors' is not a kind", 2, "", f"query: unknown artifact kind 'errors' ({KINDS})\n")

    print("query: adr")
    run("adr", "ADR-054", **full())
    expect("adr, over every root: this checkout, legacy memory, the working copy; WORKING_COPY, WORKING_COPIES and the binding; wc-a once", 0, adr054_all, "")
    run("adrs", "ADR-054", **full())
    expect("adrs is adr", 0, adr054_all, "")
    run("adr", "adr-054", **full())
    expect("case-insensitive substring", 0, adr054_all, "")
    run("adr", "054", **full())
    expect("…of any part", 0, adr054_all, "")
    run("adr", "ADR-0541", **full())
    expect("an exact key only the one", 0, head_("legacyproj/devrole") + hit("ADR-0541", 0, "lesson:c"), "")
    run("adr", "ADR-999", **full())
    expect("no hit", 0, nothing("ADR-999"), "")
    run("adr", "ADR-054", AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_STATE_DIR=f"{T}/nostate")
    expect("this checkout and legacy memory alone, with no working copy and no binding", 0,
           head_("root/fabric-coordinator") + hit("ADR-054", 2, "lesson:one")
           + head_("legacyproj/devrole") + hit("ADR-054", 2, "lesson:a, solution:b") + hit("ADR-0541", 0, "lesson:c"), "")
    run("adr", "ADR-001", **full())
    # DEFECT, fixed in the port: the bash read the line with IFS=$'\t', a whitespace
    # separator, so the empty slices field collapsed and it printed the
    # observation count (1) as the slices and an empty count. The expected text is
    # what was meant: the real count, and "none".
    expect("an empty slice list (the count is its own, the slices are none)", 0, head_("wc-c/ops") + hit("ADR-001", 1, "none"), "")

    print("query: pr")
    pr428 = head_("legacyproj/devrole") + hit("#428", 2, "lesson:p") + head_("wc-a/devrole") + hit("#428", 0, "lesson:q")
    run("pr", "428", **full())
    expect("pr 428 is #428", 0, pr428, "")
    run("pr", "#428", **full())
    expect("pr '#428'", 0, pr428, "")
    run("prs", "42", **full())
    expect("prs, a part of the number", 0, pr428, "")
    run("pr", "999", **full())
    expect("pr with no hit names the # it searched for", 0, nothing("#999"), "")

    print("query: arch, commit, contract, error, migration, file")
    for kind, key, plural in (("arch", "arch-1", "archs"), ("commit", "abc1234", "commits"),
                              ("contract", "CONTRACT-9", "contracts"), ("error", "E_BAD", "error_codes")):
        want = head_("legacyproj/devrole") + hit(key, 0 if kind == "contract" else 1, "lesson:a")
        run(kind, key, **full())
        expect(f"{kind} {key}", 0, want, "")
        run(plural, key, **full())
        expect(f"{plural} is {kind}", 0, want, "")
    mig = head_("legacyproj/devrole") + hit("migration-0007", 1, "lesson:a")
    run("migration", "0007", **full())
    expect("migration 0007 (the number is a part of migration-0007: the needle is left as typed)", 0, mig, "")
    run("migrations", "migration-0007", **full())
    expect("migrations, the whole key", 0, mig, "")
    files = (head_("legacyproj/devrole") + hit("apps/status_web", 1, "lesson:a") + hit("apps/status_web/lib/main.dart", 0, "lesson:c")
             + head_("wc-b/qa") + hit("apps/status_web", 0, "lesson:w"))
    run("file", "apps/status_web", **full())
    expect("file, a prefix of two keys and an exact one in another root", 0, files, "")
    run("files", "APPS/STATUS_WEB/LIB", **full())
    expect("files, case-insensitive", 0, head_("legacyproj/devrole") + hit("apps/status_web/lib/main.dart", 0, "lesson:c"), "")
    run("file", "apps/status_web", "extra", "args", **full())
    expect("arguments after the needle are ignored", 0, files, "")

    print("query: keys with metacharacters are literal, and only ASCII folds")
    run("adr", "ADR-05.", **full())
    expect("a regex dot is a dot", 0, nothing("ADR-05."), "")
    run("adr", ".*", **full())
    expect("a regex star is a star", 0, nothing(".*"), "")
    weird = head_("legacyproj/devrole") + hit("weird.key[1]*", 0, "lesson:a")
    run("file", "weird.key[1]*", **full())
    expect("a key with brackets and a star, whole", 0, weird, "")
    run("file", "weird.key", **full())
    expect("…and a part of it", 0, weird, "")
    run("adr", 'a"b\\c$d|e', **full())
    expect("quotes, backslash, dollar, pipe", 0, nothing('a"b\\c$d|e'), "")
    run("adr", "Ünï", **full())
    # DEFECT, fixed in the port: the bash padded by bytes (printf), so the two-byte
    # letters narrowed the column; the width is 44 characters.
    expect("a non-ASCII key, padded by characters", 0, head_("wc-b/qa") + "  Ünï-1" + " " * 39 + " 1 obs\n      slices: lesson:ü\n", "")
    run("adr", "ünï", **full())
    expect("ascii_downcase leaves Ü alone: ünï is not Ünï", 0, nothing("ünï"), "")
    run("adr", "ÜNÏ", **full())
    expect("…and neither is ÜNÏ", 0, nothing("ÜNÏ"), "")

    print("query: obs")
    obs_dead = (head_("root/fabric-coordinator cites:") + cites("adrs", "ADR-054")
                + head_("legacyproj/devrole cites:") + cites("adrs", "ADR-054")
                + head_("wc-a/devrole cites:") + cites("adrs", "ADR-054")
                + f"\nevidence for:\n  {WC_A}/.agent-fabric/memory/devrole/note.md\n"
                + "  memory/projects/legacyproj/devrole/INDEX.md\n  memory/projects/legacyproj/devrole/s1.md\n")
    run("obs", "deadbeef01", **full())
    expect("obs: each root's citers, then the slices that mention the row (INDEX.md too; absolute outside the root, sorted before relative)", 0, obs_dead, "")
    run("obs", "cafe0002", **full())
    expect("obs: one row in many kinds, with no evidence file", 0,
           head_("root/fabric-coordinator cites:") + cites("adrs", "ADR-054")
           + head_("legacyproj/devrole cites:") + cites("archs", "arch-1") + cites("commits", "abc1234")
           + cites("error_codes", "E_BAD") + cites("files", "apps/status_web") + cites("migrations", "migration-0007")
           + cites("prs", "#428"), "")
    run("obs", "11112222", **full())
    expect("obs: cited by an artifact and by a note", 0,
           head_("legacyproj/devrole cites:") + cites("adrs", "ADR-054") + cites("prs", "#428")
           + "\nevidence for:\n  memory/projects/legacyproj/devrole/s1.md\n", "")
    run("obs", "zzzz", **full())
    expect("obs: not referenced", 0, "observation zzzz is not referenced in the corpus\n", "")
    run("obs", "deadbeef0.", **full())
    # DEFECT, fixed in the port: the bash passed the hash to grep as a BRE, so a
    # dot matched any letter; a content hash is hex, and it is searched as written.
    expect("obs: the hash is exact for the evidence too, a dot is a dot", 0, "observation deadbeef0. is not referenced in the corpus\n", "")
    run("obs", "feed0003", **full())
    expect("obs: a row cited in a working copy only", 0, head_("wc-b/qa cites:") + cites("adrs", "Ünï-1"), "")
    run("obs", "deadbeef01", "extra", **full())
    expect("obs: arguments after the hash are ignored", 0, obs_dead, "")

    print("query: roles")
    run("roles", **full())
    expect("roles: the table, in path order, with slices (no INDEX.md) per project, per domain, and the citations", 0,
           table(("project/role", "project", "domain", "citations"),
                 ("root/fabric-coordinator", 0, 0, 1), ("legacyproj/devrole", 2, 2, 11), ("wc-a/devrole", 1, 2, 2),
                 ("wc-b/qa", 0, 0, 2), ("wc-c/ops", 0, 0, 2)), "")

    print("query: crossrefs that cannot be read")
    bad = f"{T}/wc-bad"
    badfile = f"{bad}/.agent-fabric/memory/r/crossref.json"
    put(badfile, '{"index": {"adrs": ')
    run("adr", "ADR-054", **full(AGENT_FABRIC_WORKING_COPY=bad))
    check("a truncated crossref: exit 5", rc == 5, f"truncated crossref: exit {rc}, wanted 5")
    check("…the roots before it were already printed, none after", out.rstrip("\n") == adr054_all.rstrip("\n"), f"partial stdout\n{out}")
    check("…and the file is named, on stderr", badfile in err, f"file not named\n{err}")
    shutil.rmtree(bad)

    typed = f"{T}/wc-typed"
    typedfile = f"{typed}/.agent-fabric/memory/r/crossref.json"
    put(typedfile, '{"index": []}\n')
    run("adr", "x", **bare, AGENT_FABRIC_WORKING_COPY=typed)
    expect_names("an index that is a list: refused with the file named, exit 5", 5, typedfile)
    run("obs", "x", **bare, AGENT_FABRIC_WORKING_COPY=typed)
    expect("obs: the same list is read by to_entries: nothing cites it", 0, "observation x is not referenced in the corpus\n", "")
    run("roles", **bare, AGENT_FABRIC_WORKING_COPY=typed)
    expect("roles: counts what a list holds", 0,
           table(("project/role", "project", "domain", "citations"), ("wc-typed/r", 0, 0, 0)), "")
    shutil.rmtree(typed)

    noindex = f"{T}/wc-noindex"
    noindexfile = f"{noindex}/.agent-fabric/memory/r/crossref.json"
    put(noindexfile, '{"role": "r"}\n')
    run("adr", "x", **bare, AGENT_FABRIC_WORKING_COPY=noindex)
    expect("a crossref with no index: nothing cites it", 0, nothing("x"), "")
    run("obs", "x", **bare, AGENT_FABRIC_WORKING_COPY=noindex)
    expect_names("obs: …but obs reads .index as an object: refused with the file named, exit 5", 5, noindexfile)
    shutil.rmtree(noindex)

    print("query: the binding and the working copies")
    put(f"{STATE}/binding.json", '{"working_copy": ')
    run("adr", "ADR-054", **full())
    check("a malformed binding costs the binding, not the answer", rc == 0 and out == adr054_all, f"rc={rc} {out}")
    check("…and is said on stderr", bool(err), "malformed binding said nothing")
    put(f"{STATE}/binding.json", json.dumps({"working_copy": f"{T}/missing"}) + "\n")
    run("adr", "ADR-054", **full())
    expect("a binding naming a working copy that is not there: skipped, without a word", 0, adr054_all, "")
    put(f"{STATE}/binding.json", '{"role": "x"}\n')
    run("adr", "ADR-054", **full())
    expect("a binding with no working copy", 0, adr054_all, "")
    os.remove(f"{STATE}/binding.json")
    run("adr", "ADR-002", AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_STATE_DIR=STATE, AGENT_FABRIC_WORKING_COPIES="")
    expect("no binding file, no working copy: wc-c is not seen", 0, nothing("ADR-002"), "")
    # The state directory when AGENT_FABRIC_STATE_DIR is unset: XDG_STATE_HOME, then HOME.
    wc_c_ops = head_("wc-c/ops") + hit("ADR-002", 1, "lesson:found")
    binding = json.dumps({"working_copy": WC_C}) + "\n"
    put(f"{T}/xdg/agent-fabric/agents/{LOGIN}/binding.json", binding)
    run("adr", "ADR-002", AGENT_FABRIC_ROOT=ROOT, XDG_STATE_HOME=f"{T}/xdg")
    expect("the binding under XDG_STATE_HOME/agent-fabric/agents/<login>", 0, wc_c_ops, "")
    put(f"{HOME}/.local/state/agent-fabric/agents/{LOGIN}/binding.json", binding)
    run("adr", "ADR-002", AGENT_FABRIC_ROOT=ROOT)
    expect("…and under HOME/.local/state when that is unset too", 0, wc_c_ops, "")
    run("adr", "ADR-002", AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_WORKING_COPIES=WC_C, AGENT_FABRIC_STATE_DIR=f"{T}/nostate")
    expect("WORKING_COPIES alone", 0, wc_c_ops, "")
    run("adr", "ADR-002", AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_WORKING_COPY=WC_C, AGENT_FABRIC_STATE_DIR=f"{T}/nostate")
    expect("WORKING_COPY alone", 0, wc_c_ops, "")

    print("query: the root defaults to the script's own checkout")
    # A checkout the test builds: the CLI's own directory (so the default
    # root is the copy, wherever CLI came from) beside a memory/ of one
    # fixture role that no live corpus holds.
    cli_dir = os.path.dirname(CLI)
    copy_cli_dir = f"{T}/copy/tools/fabric"
    os.makedirs(copy_cli_dir)
    for name in os.listdir(cli_dir):
        if os.path.isfile(f"{cli_dir}/{name}"):
            shutil.copy2(f"{cli_dir}/{name}", copy_cli_dir)
    xref(f"{T}/copy/memory/projects/fixtureproj/fixturerole/crossref.json", "fixturerole",
         '{"adrs": {"ADR-001": {"observations": [], "slices": ["lesson:a"]}}}')
    cli = os.path.join(copy_cli_dir, os.path.basename(CLI))
    e = clean_env()
    e["AGENT_FABRIC_STATE_DIR"] = f"{T}/nostate"
    p = subprocess.run([cli, "roles"], env=e, capture_output=True, timeout=60)
    got, errs = p.stdout.decode("utf-8", "surrogateescape"), p.stderr.decode("utf-8", "surrogateescape")
    lines = got.split("\n")
    check("without AGENT_FABRIC_ROOT: the checkout's own memory/ is the corpus",
          p.returncode == 0 and lines[0] == "project/role                 project  domain   citations"
          and lines[1].startswith("fixtureproj/fixturerole") and lines[2:] == [""], f"rc={p.returncode} {got!r} {errs}")

    if fails:
        print(f"test_query_cli: {fails} FAILED")
        return 1
    print("test_query_cli: all assertions passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)
