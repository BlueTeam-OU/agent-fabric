#!/usr/bin/env python3
"""tools/fabric/cli/ and bin/fabric: the `fabric <noun> <verb>` command (ADR-068 §5 rules 1, 2, 3, 5, 7).

Stdlib only; runnable as `python3 tests/test_fabric_cli.py`. The table is a fixture of the shape the record gives, so the
suite does not depend on the real commands.json; the guards' two-spelling cases are tests/test_fabric_spellings.py.
**Each case names the mutation it kills**:

  every_form_resolves            <- resolve's verb lookup, or the noun's own command, dropped or swapped
  unlisted_verb_goes_to_command  <- resolve refusing a word the noun does not list although the noun has its own command
  noun_without_command_refuses   <- an unlisted verb of a command-less noun passed on, or a bare such noun run
  refusals_exit_2                <- USAGE changed, a refusal printed on stdout, or an option before the noun accepted
  help_is_not_an_error           <- help / --help refused, or listed on stderr, or given an argument
  listing_names_every_form       <- forms() dropping a verb or the own command
  exec_is_the_same_process       <- a child process (subprocess) in place of os.execv: pid differs
  argv_is_passed_unchanged       <- a word dropped, split, reordered, or "" lost on the way
  argv0_is_the_checkout_path     <- argv[0] left as `fabric` or the table's command name
  no_path_lookup                 <- the target found on PATH before the checkout
  same_output_as_direct_call     <- stdout, stderr or the exit status changed on the way
  checkout_is_where_the_file_is  <- the root taken from the cwd or the environment, not the module's own place
  missing_target_is_127          <- FileNotFoundError read as 126 or 70
  unrunnable_target_is_126       <- PermissionError read as 127
  broken_table_is_70             <- a malformed or missing table read as a refusal (2) or run
  table_naming_stranger_is_70    <- a command not in `commands` exec'd by path anyway
  canonical_*                    <- see each: the spellings, the path forms, the prefixes, and None for the rest
  table_*                        <- each fault of table_findings, with its passing control
  literal_*                      <- each way a command name is recognised in a hook, with its passing control
"""
from __future__ import annotations

import atexit
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from cli import canonical as canon, checks, table  # noqa: E402

TMP = tempfile.mkdtemp(prefix="fabric-cli-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

DOC = {
    "commands": {"fabric": "bin/fabric", "fabric-jobs": "bin/fabric-jobs", "fabric-review": "bin/fabric-review",
                 "fabric-review-mcp": "bin/fabric-review-mcp", "fabric-memory-check": "bin/fabric-memory-check",
                 "fabric-memory-mcp": "bin/fabric-memory-mcp", "gzcoord-inbox": "bin/gzcoord-inbox", "gzmsg": "bin/gzmsg",
                 "fabric-pr": "bin/fabric-pr", "fabric-secret-run": "bin/fabric-secret-run"},
    "fabric": {"_comment": "fixture", "nouns": {
        "jobs": {"command": "fabric-jobs"},
        "pr": {"command": "fabric-pr"},
        "review": {"command": "fabric-review", "verbs": {"mcp": "fabric-review-mcp"}},
        "memory": {"verbs": {"check": "fabric-memory-check", "mcp": "fabric-memory-mcp"}},
        "gzcoord": {"verbs": {"inbox": "gzcoord-inbox", "msg": "gzmsg"}},
        "secret-run": {"command": "fabric-secret-run"}}},
}
FORMS = {
    ("jobs", "list"): ("fabric-jobs", ("list",)), ("jobs",): ("fabric-jobs", ()),
    ("pr", "post-review", "5"): ("fabric-pr", ("post-review", "5")),
    ("review", "mcp"): ("fabric-review-mcp", ()), ("review", "mcp", "--x"): ("fabric-review-mcp", ("--x",)),
    ("review", "brief", "a"): ("fabric-review", ("brief", "a")),
    ("memory", "check"): ("fabric-memory-check", ()), ("memory", "mcp", "q"): ("fabric-memory-mcp", ("q",)),
    ("gzcoord", "inbox", "--until-delivery"): ("gzcoord-inbox", ("--until-delivery",)), ("gzcoord", "msg"): ("gzmsg", ()),
    ("secret-run", "--", "x"): ("fabric-secret-run", ("--", "x")),
}


def nouns() -> dict:
    return table.nouns_of(DOC)


def write(path: str, text: str, mode: int = 0o755) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)


TARGET = """#!/bin/sh
echo "pid=$$ argv0=$0 n=$#"
for a in "$@"; do echo "arg=[$a]"; done
echo "to-stderr" >&2
exit 7
"""


def checkout(doc: dict | str | None = None, targets: bool = True) -> str:
    """A tree of its own: bin/fabric, the package, a commands.json and one fake target per command."""
    root = tempfile.mkdtemp(dir=TMP)
    shutil.copy(os.path.join(ROOT, "bin", "fabric"), os.path.join(root, "bin-fabric-tmp"))
    os.makedirs(os.path.join(root, "bin"))
    os.rename(os.path.join(root, "bin-fabric-tmp"), os.path.join(root, "bin", "fabric"))
    shutil.copytree(os.path.join(ROOT, "tools", "fabric", "cli"), os.path.join(root, "tools", "fabric", "cli"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    d = DOC if doc is None else doc
    write(os.path.join(root, table.COMMANDS_FILE), d if isinstance(d, str) else json.dumps(d), 0o644)
    if targets and isinstance(d, dict):
        for cmd, rel in d["commands"].items():
            if cmd != "fabric":
                write(os.path.join(root, rel), TARGET)
    return root


def env(**extra: str) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": TMP, "LC_ALL": "C", "AGENT_FABRIC_PYTHON": sys.executable, **extra}


def run(prog: str, *args: str, environment: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([prog, *args], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                          env=environment or env(), check=False)


# ---- resolution ------------------------------------------------------------------------------------------------------

def case_every_form_resolves() -> None:
    for words, (command, args) in FORMS.items():
        got = table.resolve(nouns(), list(words))
        assert got == table.Run(command, args), (words, got)


def case_unlisted_verb_goes_to_command() -> None:
    assert table.resolve(nouns(), ["jobs", "frobnicate", "x"]) == table.Run("fabric-jobs", ("frobnicate", "x"))
    assert table.resolve(nouns(), ["review", "mcpx"]) == table.Run("fabric-review", ("mcpx",))   # not a prefix match
    assert table.resolve(nouns(), ["jobs", "help"]) == table.Run("fabric-jobs", ("help",))       # the command's own help


def case_noun_without_command_refuses() -> None:
    for words in (["memory", "nope"], ["memory", "check-it"], ["gzcoord", "send"], ["memory"], ["memory", "check", "x"][:1]):
        got = table.resolve(nouns(), words)
        assert isinstance(got, table.Say) and got.status == 2 and got.stream == "err", (words, got)
    assert table.resolve(nouns(), ["memory", "check"]) == table.Run("fabric-memory-check", ())   # positive control


def case_refusals_exit_2() -> None:
    for words in ([], ["nope"], ["-x", "jobs", "list"], ["--version"], ["-h"], ["--", "jobs"], ["JOBS"], ["jo"], ["help", "jobs"],
                  ["--help", "x"]):
        got = table.resolve(nouns(), words)
        assert isinstance(got, table.Say) and got.status == 2 and got.stream == "err", (words, got)
        assert "fabric jobs [args…]" in got.text, (words, got.text)   # the listing rides every refusal
    assert "not accepted before the noun" in table.resolve(nouns(), ["-x", "jobs"]).text   # said as what it is, not as an unknown noun
    assert table.resolve(nouns(), ["jobs", "-x"]) == table.Run("fabric-jobs", ("-x",))   # options after the noun are the command's


def case_help_is_not_an_error() -> None:
    for words in (["help"], ["--help"], ["memory", "help"], ["memory", "--help"]):
        got = table.resolve(nouns(), words)
        assert isinstance(got, table.Say) and got.status == 0 and got.stream == "out", (words, got)
    assert "fabric memory check [args…]" in table.resolve(nouns(), ["memory", "help"]).text
    assert "fabric jobs" not in table.resolve(nouns(), ["memory", "help"]).text   # the noun's own forms only


def case_listing_names_every_form() -> None:
    text = table.listing(nouns())
    for f, c in table.forms(nouns()):
        assert f in text and c in text, (f, c)
    assert len(table.forms(nouns())) == 9, table.forms(nouns())


# ---- the process -----------------------------------------------------------------------------------------------------

def case_exec_is_the_same_process() -> None:
    root = checkout()
    p = subprocess.Popen([os.path.join(root, "bin", "fabric"), "jobs", "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=env(), stdin=subprocess.DEVNULL)
    out, _ = p.communicate(timeout=60)
    assert out.startswith(f"pid={p.pid} "), (p.pid, out)


def case_argv_is_passed_unchanged() -> None:
    root = checkout()
    odd = ["a b", "", "--", "-x", "*", "$HOME", "é\u00a0", "line\nbreak"]
    r = run(os.path.join(root, "bin", "fabric"), "jobs", *odd)
    assert r.stdout.startswith("pid=") and f"n={len(odd)}" in r.stdout.split("\n")[0], r.stdout
    assert [ln for ln in r.stdout.split("\n") if ln.startswith("arg=[")][:4] == ["arg=[a b]", "arg=[]", "arg=[--]", "arg=[-x]"], r.stdout
    r2 = run(os.path.join(root, "bin", "fabric"), "review", "mcp", "--", "mcp")
    assert "arg=[--]" in r2.stdout and "arg=[mcp]" in r2.stdout and r2.stdout.count("arg=[") == 2, r2.stdout


def case_argv0_is_the_checkout_path() -> None:
    # A script's $0 is the kernel's path whatever argv[0] was, so the call itself is what is recorded.
    import importlib.util
    here = os.path.join(ROOT, "tools", "fabric", "cli")
    spec = importlib.util.spec_from_file_location("fabric_cli_script", os.path.join(here, "fabric.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = checkout()
    calls = []
    mod.main(["review", "mcp", "--x"], root=root, execv=lambda path, argv: calls.append((path, argv)))
    target = os.path.join(root, "bin", "fabric-review-mcp")
    assert calls == [(target, [target, "--x"])], calls
    r = run(os.path.join(root, "bin", "fabric"), "review", "mcp")
    assert f"argv0={os.path.realpath(root)}/bin/fabric-review-mcp " in r.stdout, r.stdout


def case_no_path_lookup() -> None:
    root = checkout()
    decoy = tempfile.mkdtemp(dir=TMP)
    write(os.path.join(decoy, "fabric-jobs"), "#!/bin/sh\necho DECOY\n")
    r = run(os.path.join(root, "bin", "fabric"), "jobs", "list", environment=env(PATH=f"{decoy}:/usr/bin:/bin"))
    assert "DECOY" not in r.stdout and "argv0=" in r.stdout, r.stdout


def case_same_output_as_direct_call() -> None:
    root = checkout()
    via = run(os.path.join(root, "bin", "fabric"), "jobs", "list", "--all")
    direct = run(os.path.join(root, "bin", "fabric-jobs"), "list", "--all")
    norm = lambda s: "\n".join(ln for ln in s.split("\n") if not ln.startswith("pid="))   # noqa: E731  the pid is the one thing that differs
    assert (norm(via.stdout), via.stderr, via.returncode) == (norm(direct.stdout), direct.stderr, direct.returncode) \
        and via.returncode == 7 and via.stderr == "to-stderr\n", (via, direct)


def case_checkout_is_where_the_file_is() -> None:
    mine, other = checkout(), checkout()
    write(os.path.join(other, "bin", "fabric-jobs"), "#!/bin/sh\necho OTHER\n")
    link_dir = tempfile.mkdtemp(dir=TMP)
    link = os.path.join(link_dir, "fabric")
    os.symlink(os.path.join(mine, "bin", "fabric"), link)           # ~/.local/bin/fabric
    r = subprocess.run([link, "jobs"], capture_output=True, text=True, timeout=60, cwd=other,
                       env=env(AGENT_FABRIC_ROOT=other), stdin=subprocess.DEVNULL, check=False)
    assert "OTHER" not in r.stdout and f"argv0={os.path.realpath(mine)}/bin/fabric-jobs " in r.stdout, r.stdout


def case_missing_target_is_127() -> None:
    root = checkout()
    os.unlink(os.path.join(root, "bin", "fabric-jobs"))
    r = run(os.path.join(root, "bin", "fabric"), "jobs", "list")
    assert r.returncode == 127 and r.stdout == "" and r.stderr.count("\n") == 1 and "fabric-jobs" in r.stderr, (r.returncode, r.stderr)
    assert run(os.path.join(root, "bin", "fabric"), "pr", "x").returncode == 7   # positive control: a present target runs


def case_unrunnable_target_is_126() -> None:
    root = checkout()
    os.chmod(os.path.join(root, "bin", "fabric-jobs"), 0o644)
    r = run(os.path.join(root, "bin", "fabric"), "jobs")
    assert r.returncode == 126 and "cannot execute" in r.stderr, (r.returncode, r.stderr)


def case_broken_table_is_70() -> None:
    bad = copy.deepcopy(DOC)
    del bad["fabric"]
    noun_shape = copy.deepcopy(DOC)
    noun_shape["fabric"]["nouns"]["jobs"] = {"verbs": "x"}
    for label, doc in (("not json", "{"), ("no fabric table", bad), ("bad noun", noun_shape), ("not an object", "[]")):
        root = checkout(doc, targets=False)
        r = run(os.path.join(root, "bin", "fabric"), "help")
        assert r.returncode == 70 and r.stdout == "" and r.stderr.startswith("fabric: ") and "Traceback" not in r.stderr, (label, r)
    shutil.rmtree(os.path.join(root, "runtime"))
    r = run(os.path.join(root, "bin", "fabric"), "help")
    assert r.returncode == 70, r


def case_table_naming_stranger_is_70() -> None:
    doc = copy.deepcopy(DOC)
    doc["fabric"]["nouns"]["jobs"] = {"command": "not-a-command"}
    root = checkout(doc)
    write(os.path.join(root, "bin", "not-a-command"), "#!/bin/sh\necho RAN\n")
    r = run(os.path.join(root, "bin", "fabric"), "jobs")
    assert r.returncode == 70 and "RAN" not in r.stdout, r


def case_real_entry_shape() -> None:
    root = checkout()
    r = run(os.path.join(root, "bin", "fabric"), "help")
    assert r.returncode == 0 and r.stderr == "" and "fabric gzcoord msg [args…]" in r.stdout, r
    r = run(os.path.join(root, "bin", "fabric"))
    assert r.returncode == 2 and r.stdout == "" and "no noun given" in r.stderr, r
    r = run(os.path.join(root, "bin", "fabric"), "--debug", "jobs")
    assert r.returncode == 2 and r.stdout == "", r
    r = run(os.path.join(root, "bin", "fabric"), "memory", "nope")
    assert r.returncode == 2 and "unknown verb 'nope'" in r.stderr, r
    r = run(os.path.join(root, "bin", "fabric"), environment=env(AGENT_FABRIC_PYTHON="/nonexistent/python"))
    assert r.returncode == 127 and "pinned Python" in r.stderr, r


# ---- canonical() -----------------------------------------------------------------------------------------------------

def canonical(*words: str):
    return canon.canonical(list(words), DOC)


def case_canonical_both_spellings() -> None:
    assert canonical("fabric-pr", "post-review", "5") == ("fabric-pr", ["post-review", "5"])
    assert canonical("fabric", "pr", "post-review", "5") == ("fabric-pr", ["post-review", "5"])
    assert canonical("fabric", "memory", "check") == ("fabric-memory-check", [])
    assert canonical("fabric", "gzcoord", "msg", "x") == ("gzmsg", ["x"])
    assert canonical("fabric", "review", "mcp") == ("fabric-review-mcp", [])
    assert canonical("fabric", "review", "brief") == ("fabric-review", ["brief"])
    for words, (command, args) in FORMS.items():
        assert canonical("fabric", *words) == (command, list(args)), words
        assert canonical(command, *args) == (command, list(args)), words


def case_canonical_path_forms() -> None:
    for w in ("bin/fabric-pr", "./bin/fabric-pr", "/home/x/projects/agent-fabric/bin/fabric-pr", "~/.local/bin/fabric-pr",
              "../bin/fabric-pr"):
        assert canonical(w, "arm") == ("fabric-pr", ["arm"]), w
    assert canonical("~/.local/bin/fabric", "pr", "arm") == ("fabric-pr", ["arm"])
    assert canonical("/x/bin/fabric", "jobs", "list") == ("fabric-jobs", ["list"])
    for w in ("/tmp/fabric-pr", "tools/fabric-pr", "/x/bin/fabric-pr/x", "bin/fabric-prx", "$HOME/.local/bin/fabric-pr", "./fabric-pr",
              "fabric-p*", "fabric-pr\\", "`x`/bin/fabric-pr"):
        assert canonical(w, "arm") is None, w


def case_canonical_prefixes() -> None:
    want = ("fabric-pr", ["post-review", "5"])
    for pre in ([], ["FOO=bar"], ["A=1", "B="], ["env"], ["env", "-i"], ["env", "-"], ["env", "-u", "X"], ["env", "-uX"],
                ["env", "--unset=X"], ["env", "-C", "/tmp"], ["env", "--chdir=/tmp"], ["env", "--"], ["env", "A=1", "-i", "B=2"],
                ["command"], ["command", "-p"], ["command", "--"], ["FOO=1", "env", "A=2", "command"], ["env", "-0"]):
        assert canonical(*pre, "fabric-pr", "post-review", "5") == want, pre
        assert canonical(*pre, "fabric", "pr", "post-review", "5") == want, pre
    for pre in (["env", "-S", "x"], ["command", "-v"], ["command", "-V"], ["env", "-x"], ["env", "--split-string=x"]):
        assert canonical(*pre, "fabric-pr", "x") is None, pre           # runs something else, or nothing
    for pre in (["env"], ["FOO=1"], ["command"], [], ["env", "-u"]):
        assert canonical(*pre) is None, pre                             # no command after the prefix
    for launcher in ("time", "sudo", "timeout", "nice"):
        assert canonical(launcher, "5", "fabric-pr", "x") is None, launcher   # the guards' other launchers are theirs to unwrap


def case_canonical_none_for_the_rest() -> None:
    for words in ([], [""], ["ls", "-l"], ["fabric-op", "x"], ["fabric-nothing"], ["git", "fabric-pr"], ["echo", "fabric-pr"],
                  ["FABRIC-PR"], ["fabric"], ["fabric", "help"], ["fabric", "--help"], ["fabric", "nope", "x"], ["fabric", "-x", "pr"],
                  ["fabric", "memory"], ["fabric", "memory", "nope"], ["fabric", "fabric"], ["bin/"]):
        assert canonical(*words) is None, words


def case_canonical_unknown_stays_unknown() -> None:
    without_table = {"commands": DOC["commands"]}
    assert canon.canonical(["fabric", "pr", "arm"], without_table) is None       # the dispatcher spelling, no table: nothing known
    assert canon.canonical(["fabric-pr", "arm"], without_table) == ("fabric-pr", ["arm"])   # the direct spelling still read
    try:
        canon.canonical(["fabric-pr"], {"commands": "x"})
    except table.TableError:
        pass
    else:
        raise AssertionError("an unreadable commands.json read as 'not a fabric command'")
    stranger = copy.deepcopy(DOC)
    stranger["fabric"]["nouns"]["jobs"] = {"command": "elsewhere"}
    assert canon.canonical(["fabric", "jobs"], stranger) is None                 # a table naming a stranger resolves to nothing


def case_canonical_reads_the_checkout_by_default() -> None:
    root = checkout()
    got = canon.canonical(["fabric", "review", "mcp"], root=root)
    assert got == ("fabric-review-mcp", []), got
    canon._cache.clear()


# ---- table_findings --------------------------------------------------------------------------------------------------

def findings(doc, own=None):
    return [f for f in checks.table_findings(doc, own if own is not None else {}) if not f.startswith("note:")]


def mutated(fn) -> dict:
    d = copy.deepcopy(DOC)
    fn(d)
    return d


def case_table_passes() -> None:
    d = copy.deepcopy(DOC)
    d["fabric"]["nouns"]["sr"] = {"command": "fabric-secret-run"}
    del d["fabric"]["nouns"]["secret-run"]
    assert findings(DOC) == [], findings(DOC)
    assert findings(d) == []
    assert findings(DOC, {"fabric-review": {"brief", "post"}}) == []   # a verb the command does not take


def case_table_missing_command() -> None:
    got = findings(mutated(lambda d: d["fabric"]["nouns"].pop("jobs")))
    assert got == ["fabric-jobs: in `commands` and reached by no `fabric` form"], got


def case_table_names_stranger() -> None:
    got = findings(mutated(lambda d: d["fabric"]["nouns"]["jobs"].update(command="fabric-nothing")))
    assert any("fabric-nothing" in g and "not in `commands`" in g for g in got), got
    got = findings(mutated(lambda d: d["fabric"]["nouns"]["memory"]["verbs"].update(zz="fabric-nothing")))
    assert any("fabric memory zz" in g for g in got), got


def case_table_reaches_twice() -> None:
    got = findings(mutated(lambda d: d["fabric"]["nouns"]["jobs"].update(verbs={"again": "fabric-jobs"})))
    assert len(got) == 1 and "fabric-jobs is reached by 2 forms" in got[0], got


def case_table_names_the_dispatcher() -> None:
    got = findings(mutated(lambda d: d["fabric"]["nouns"].update(loop={"command": "fabric"})))
    assert any("names the dispatcher itself" in g for g in got), got


def case_table_dispatcher_must_be_linked() -> None:
    got = findings(mutated(lambda d: d["commands"].pop("fabric")))
    assert any("`fabric` is not in `commands`" in g for g in got), got


def case_table_verb_the_command_takes() -> None:
    own = {"fabric-review": {"mcp", "brief"}}
    got = findings(DOC, own)
    assert len(got) == 1 and "fabric.nouns.review.verbs.mcp" in got[0] and "takes `mcp`" in got[0], got
    notes = checks.table_findings(DOC)          # not supplied: said, not silently passed
    assert any(n.startswith("note: own_verbs not supplied") for n in notes), notes


def case_table_malformed() -> None:
    for doc in ([], {}, {"commands": {}}, {"commands": {"a": "bin/a"}, "fabric": {"nouns": {"x": {"verbs": {}}}}},
                {"commands": {"a": "bin/a"}, "fabric": {"nouns": {"x": {"command": "a", "extra": 1}}}},
                {"commands": {"a": 1}, "fabric": {"nouns": {}}}):
        got = checks.table_findings(doc)
        assert len(got) == 1 and "Traceback" not in got[0], (doc, got)


# ---- the mechanism's checker -----------------------------------------------------------------------------------------

NAMES = sorted(DOC["commands"])


def lit(src: str, allowed: dict | None = None, rel: str = "runtime/claude-code/hooks/g.py") -> list[str]:
    return checks.literal_findings(rel, src, NAMES, allowed or {})


def case_literal_each_way_is_found() -> None:
    for src in ('if name == "fabric-pr":\n    pass\n', 'if "fabric-pr" != name:\n    pass\n', 'if name in ("gh", "fabric-pr"):\n    pass\n',
                'if name in {"fabric-pr"}:\n    pass\n', 'if "fabric-pr" in cmd:\n    pass\n',
                'import re\nBARE = re.compile(r"fabric-pr\\s+post-review")\n', 'import re\nre.search(r"\\bfabric-pr\\b", c)\n',
                'x.startswith("fabric-pr ")\n', 'x.startswith(("gh ", "fabric-pr "))\n', 'c.find("gzmsg")\n', 'c.count("fabric-jobs")\n',
                'if w == "bin/fabric-pr":\n    pass\n', 'if w == "~/.local/bin/gzmsg":\n    pass\n',
                'if f"fabric-pr {verb}" == a:\n    pass\n'):
        got = lit(src)
        assert len(got) == 1 and "ask tools/fabric/cli canonical()" in got[0], (src, got)


def case_literal_what_is_not_a_name() -> None:
    for src in ('x = "fabric-pr"\n', '"""fabric-pr post-review is the command"""\n', 'print("run fabric-pr post-review")\n',
                'if name == "fabric-prx":\n    pass\n', 'if p == "tools/fabric/":\n    pass\n', 'if p == "agent-fabric":\n    pass\n',
                'if p == "fabric.py":\n    pass\n', 'if p.endswith("fabric/x.py"):\n    pass\n', 'if name == "gh":\n    pass\n',
                'if x == "my-gzmsg-thing":\n    pass\n', 'if x == 3:\n    pass\n', 'ok = FOO == BAR\n', 'x = (\n',
                'import re\nre.compile(r"gh\\s+pr")\n', 'foo("fabric-pr")\n'):
        assert lit(src) == [], (src, lit(src))


def case_literal_listed_module_is_admitted() -> None:
    src = 'if name == "fabric-pr":\n    pass\n'
    assert len(lit(src)) == 1
    assert lit(src, {"runtime/claude-code/hooks/g.py": "why"}) == []


def case_literal_policy_and_tree() -> None:
    good = 'def f(w):\n    return canonical(w)\n'
    bad = 'def f(w):\n    return w == "fabric-pr"\n'
    root = tempfile.mkdtemp(dir=TMP)
    files = {"runtime/claude-code/hooks/good.py": good, "runtime/claude-code/hooks/bad.py": bad,
             "tools/fabric/guards/bad2.py": bad, "tools/fabric/cli/own.py": bad, "tests/test_x.py": bad, "tools/fabric/other.py": bad,
             "runtime/claude-code/hooks/testdata/t.py": bad}
    for rel, text in files.items():
        write(os.path.join(root, rel), text, 0o644)
    tracked = sorted(files)
    got = checks.tree_findings(root, tracked, None, DOC)
    assert [g.split(":")[0] for g in got] == ["runtime/claude-code/hooks/bad.py", "tools/fabric/guards/bad2.py"], got
    policy = json.dumps({"recognisers": {"runtime/claude-code/hooks/bad.py": "reads a transcript", "tools/fabric/guards/bad2.py": "why"}})
    assert checks.tree_findings(root, tracked, policy, DOC) == []
    stale = json.dumps({"recognisers": {"runtime/claude-code/hooks/good.py": "no longer", "tools/fabric/other.py": "not judged",
                                        "tools/fabric/guards/gone.py": "moved", "tools/fabric/guards/bad2.py": "why",
                                        "runtime/claude-code/hooks/bad.py": ["not a string"]}})
    got = checks.tree_findings(root, tracked, stale, DOC)
    assert sum("admits nothing" in g for g in got) == 3 and any(g.startswith("runtime/claude-code/hooks/bad.py:") for g in got), got
    got = checks.tree_findings(root, tracked, "{", DOC)
    assert len(got) == 1 and "cannot be read as JSON" in got[0], got
    got = checks.tree_findings(root, tracked, None, {"commands": 3})
    assert len(got) == 1 and "not judged" in got[0], got


def case_literal_unparseable_and_escapes() -> None:
    assert lit("def (\n") == []
    src = 'import re\nre.compile("\\d fabric-pr")\n'    # an invalid escape beside a hit must not hide it under -W error
    assert len(lit(src)) == 1


def case_checker_main_is_red_then_green() -> None:
    root = tempfile.mkdtemp(dir=TMP)
    for rel, text in {"runtime/claude-code/hooks/b.py": 'x = 1 if w == "fabric-pr" else 2\n'}.items():
        write(os.path.join(root, rel), text, 0o644)
    write(os.path.join(root, table.COMMANDS_FILE), json.dumps(DOC), 0o644)
    git_env = {"PATH": "/usr/bin:/bin", "HOME": root, "GIT_CONFIG_NOSYSTEM": "1"}
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", root, *cmd], check=True, env=git_env, stdin=subprocess.DEVNULL, timeout=30)
    pkg = os.path.join(ROOT, "tools", "fabric")
    code = ("import sys, importlib.util as u\n"
            f"s = u.spec_from_file_location('cli', {pkg + '/cli/__init__.py'!r}, submodule_search_locations=[{pkg + '/cli'!r}])\n"
            "m = u.module_from_spec(s); sys.modules['cli'] = m; s.loader.exec_module(m)\n"
            "from cli import checks\n"
            "sys.exit(checks.main(['--root', sys.argv[1]]))\n")
    r = subprocess.run([sys.executable, "-I", "-c", code, root], capture_output=True, text=True, timeout=60,
                       stdin=subprocess.DEVNULL, env=git_env, check=False)
    assert r.returncode == 1 and "b.py:1: comparison names the command `fabric-pr`" in r.stdout, (r.returncode, r.stdout, r.stderr)
    write(os.path.join(root, "policies/command-names.json"), json.dumps({"recognisers": {"runtime/claude-code/hooks/b.py": "why"}}), 0o644)
    r = subprocess.run([sys.executable, "-I", "-c", code, root], capture_output=True, text=True, timeout=60,
                       stdin=subprocess.DEVNULL, env=git_env, check=False)
    assert (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout)


def main() -> int:
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("case_") and callable(f)):
        fn()
        print(f"  ok   {name[5:].replace('_', ' ')}")
    print("test_fabric_cli.py: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
