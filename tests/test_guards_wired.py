#!/usr/bin/env python3
"""tools/fabric/github/guards_wired.py, through the module. The behaviour's
oracle is two managed projects' tools/checks/test_check_guards_are_wired.sh,
run unchanged against the module, each with its project's guards.json
(ADR-040 §5 rule 5). This file pins what the union added or neither suite
reaches: a glob wires only the members of its own path, and a for-loop
over self-tests answers the runner rule as a whole while a literal
answers it per command; a self-test of any extension satisfies its
member and must be wired itself; exemptions by path or by name, for
members only, and per project whether one excuses wiring or the list may
be absent; the whole-tree rule and its exclusions; both report forms,
whole; the refusals. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [sys.executable, os.path.join(ROOT, "tools", "fabric", "github", "guards_wired.py")]
GZAPP = os.path.join(ROOT, "tests", "fixtures", "gzapp-gh", "guards.json")

LINES = {
    "dirs": [{"dir": "tools/checks", "role": "guard", "members": "\\.(sh|py)$"},
             {"dir": "tools/gh", "role": "script", "members": "\\.sh$"},
             {"dir": "tools/ci", "role": "ci", "members": "\\.sh$"}],
    "exempt_file": "tools/checks/selftest_exempt.txt", "exempt_required": False, "exempt_excuses_wiring": True,
    "runner": "tools/checks/run_suite.sh", "package_scripts": None,
    "tree_excludes": [".git", "node_modules", "target"], "report": "lines",
    "text": {"member_unwired": "{path}: unwired", "member_untested": "{path}: untested ({dir}/test_{stem}.sh)",
             "test_unwired": "{path}: suite unwired", "test_bare": "{path}: suite bare",
             "loop_bare": "bare loop: {loop}", "summary": "\nsummary {n}", "ok": "lines OK {guards} {exempt}"},
}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_"))}
        base.update(HOME=sandbox, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=sandbox)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
        lines_cfg = os.path.join(sandbox, "lines.json")
        with open(lines_cfg, "w", encoding="utf-8") as fh:
            json.dump(LINES, fh)
        n = [0]

        def tree(files: dict[str, str | bytes], workflow: str = "") -> str:
            n[0] += 1
            root = os.path.join(sandbox, f"t{n[0]}")
            os.makedirs(os.path.join(root, ".github", "workflows"))
            files = {"tools/checks/selftest_exempt.txt": "", **files}
            if workflow:
                files[".github/workflows/ci.yml"] = workflow
            for rel, body in files.items():
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(body.encode() if isinstance(body, str) else body)
            return root

        def run(root: str, config: str | None = GZAPP, *args: str, cwd: str = sandbox):
            e = dict(base)
            if config is not None:
                e["AGENT_FABRIC_GUARDS_CONFIG"] = config
            r = subprocess.run([*TOOL, "--root", root, *args] if root else [*TOOL, *args], env=e, cwd=cwd,
                               capture_output=True, timeout=60)
            return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

        GUARD = {"tools/checks/ban_a.sh": "", "tools/checks/test_ban_a.sh": ""}
        WIRED = "      - run: bash tools/checks/ban_a.sh\n      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh\n"

        print("guards_wired: globs and the runner")
        rc, out, err = run(tree({**GUARD, "tools/gh/x.sh": "", "tools/gh/test_x.sh": ""},
                                WIRED + "      - run: for t in tools/gh/test_*.sh; do bash tools/checks/run_suite.sh \"$t\"; done\n"))
        check("a glob in a wrapped loop wires its own directory's suites", rc == 0, out + err)
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/test_ban_a.sh": ""},
                                "      - run: bash tools/checks/ban_a.sh\n"
                                "      - run: for t in tools/gh/test_*.sh; do bash tools/checks/run_suite.sh \"$t\"; done\n"))
        check("but never another directory's: tools/gh/test_*.sh does not wire tools/checks",
              rc == 1 and "        test_ban_a.sh\n" in out, out)
        rc, out, err = run(tree({**GUARD, "tools/gh/x.sh": "", "tools/gh/test_x.sh": ""},
                                WIRED + "      - run: for t in $ROOT/tools/*/test_*.sh; do bash tools/checks/run_suite.sh \"$t\"; done\n"))
        check("a glob may carry a prefix, and match a directory level with *", rc == 0, out + err)
        rc, out, err = run(tree({**GUARD, "tools/gh/x.sh": "", "tools/gh/test_x.sh": ""},
                                WIRED + "      - run: for t in tools/*test_x.sh; do bash tools/checks/run_suite.sh \"$t\"; done\n"))
        check("but a * never crosses a /: tools/*test_x.sh is not tools/gh/test_x.sh",
              rc == 1 and "would still pass:\n        tools/gh/test_x.sh\n" in out, out)
        rc, out, err = run(tree({**GUARD, "tools/gh/x.sh": "", "tools/gh/test_x.sh": ""},
                                WIRED + "      - run: |\n          for t in ./tools/gh/test_*.sh; do\n"
                                        "            bash \"$t\"\n          done\n"))
        check("a loop over suites with no runner in it, read to its done: the head named in the bare block",
              rc == 1 and "FAIL: 1 self-test(s) are run without tools/checks/run_suite.sh" in out
              and "        for t in ./tools/gh/test_*.sh; do\n" in out and "Two ways to green" not in out, out)
        rc, out, err = run(tree({**GUARD, "tools/gh/x.sh": "", "tools/gh/test_x.sh": ""},
                                WIRED + "      - run: bash tools/gh/test_*.sh\n"))
        check("a glob outside a loop answers per command: bare", rc == 1 and "        tools/gh/test_x.sh\n" in out, out)
        rc, out, err = run(tree(GUARD, WIRED + "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh"
                                               " | tee log\n"))
        check("a literal through the runner, piped onward, is still wrapped", rc == 0, out + err)

        rc, out, err = run(tree(GUARD, "      - run: |\n          echo bash tools/checks/ban_a.sh\n"
                                       "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh\n"))
        check("an echo inside a run: block runs nothing", rc == 1 and "whatever they contain:\n        ban_a.sh\n" in out, out)

        rc, out, err = run(tree(GUARD, "      - run: true # bash tools/checks/ban_a.sh\n"
                                       "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh\n"))
        check("a path after a command's # comment runs nothing", rc == 1 and "whatever they contain:\n        ban_a.sh\n" in out,
              out)
        rc, out, err = run(tree(GUARD, "      - run: true; echo bash tools/checks/ban_a.sh\n"
                                       "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh\n"))
        check("nor does one an echo prints mid-line", rc == 1 and "whatever they contain:\n        ban_a.sh\n" in out, out)
        for line in ("if true; then echo bash tools/checks/ban_a.sh; fi", "for x in a; do echo tools/checks/ban_a.sh; done",
                     "true \\\" ; true # bash tools/checks/ban_a.sh", "X=\"a b\" echo bash tools/checks/ban_a.sh",
                     "env echo tools/checks/ban_a.sh", "/usr/bin/env echo tools/checks/ban_a.sh",
                     "env -u X echo tools/checks/ban_a.sh", "env -u X bash tools/checks/ban_a.sh",
                     "timeout -s KILL 60 echo tools/checks/ban_a.sh"):
            rc, out, err = run(tree(GUARD, f"      - run: {line}\n"
                                           "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh\n"))
            check(f"not run: {line}", rc == 1 and "whatever they contain:\n        ban_a.sh\n" in out, out)
        rc, out, err = run(tree(GUARD, "      - run: X=\"a #b\" Y=c#d bash tools/checks/ban_a.sh # x\n"
                                       "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_a.sh\n"))
        check("a # inside quotes, or one that does not start a word, cuts nothing", rc == 0, out + err)
        loop = "      - run: |\n          for t in tools/gh/test_*.sh; do\n{body}          done{after}\n"
        gh = {**GUARD, "tools/gh/x.sh": "", "tools/gh/test_x.sh": ""}
        rc, out, err = run(tree(gh, WIRED + loop.format(body="            bash \"$t\"\n            bash tools/checks/run_suite.sh"
                                                                 " other.sh\n", after="")))
        check("a loop whose runner runs some other suite still runs its own bare",
              rc == 1 and "        for t in tools/gh/test_*.sh; do\n" in out, out)
        rc, out, err = run(tree(gh, WIRED + "      - run: for t in tools/gh/test_*.sh; do bash \"$t\"; done; "
                                            "bash tools/checks/run_suite.sh \"$t\"\n"))
        check("…and a runner after the done, handed the last $t, is not in the loop", rc == 1 and "bare" not in err and
              "run without tools/checks/run_suite.sh" in out, out)
        rc, out, err = run(tree(gh, WIRED + loop.format(body="            bash \"$t\"\n            bash tools/checks/run_suite.sh"
                                                                 " \"$t\"\n", after="")))
        check("a loop that also runs $t bare is bare, however it wraps it too",
              rc == 1 and "        for t in tools/gh/test_*.sh; do\n" in out, out)
        for bare in ('"$t"', './"$t"', 'bash -e "${t}"', 'bash -o pipefail "$t"', '/usr/bin/env bash "$t"',
                     'env -u X bash "$t"', 'timeout 60 "$t"', 'timeout -s KILL 60 "$t"', 'timeout -k 5 60 "$t"'):
            rc, out, err = run(tree(gh, WIRED + loop.format(body=f"            {bare}\n            bash tools/checks/run_suite.sh"
                                                                 " \"$t\"\n", after="")))
            check(f"…so is one that runs {bare} beside it", rc == 1 and "        for t in tools/gh/test_*.sh; do\n" in out,
                  out)
        rc, out, err = run(tree(gh, WIRED + loop.format(body="            PATH=x bash tools/checks/run_suite.sh \"${t}\"\n",
                                                        after="")))
        check("a loop handing ${t} to the runner is wrapped", rc == 0, out + err)
        rc, out, err = run(tree(gh, WIRED + loop.format(body="            printf '%s\\n' \"$t\"\n            env bash"
                                                             " tools/checks/run_suite.sh \"$t\"\n", after="")))
        check("…and so is one that only prints $t beside a runner reached through env", rc == 0, out + err)

        print("guards_wired: self-tests of any extension")
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/test_ban_a.py": ""},
                                "      - run: bash tools/checks/ban_a.sh\n"))
        check("a .py self-test satisfies its guard, and no workflow running it is reported",
              rc == 1 and "        test_ban_a.py\n" in out and "have no test_" not in out, out)
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/test_ban_a.py": ""},
                                "      - run: bash tools/checks/ban_a.sh\n      - run: python3 tools/checks/test_ban_a.py\n"))
        check("wired, it passes: the runner rule is a bash suite's only", rc == 0, out + err)

        print("guards_wired: exemptions")
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/selftest_exempt.txt":
                                 "# why\nban_a.sh   # a reason on the line\n"}, "      - run: bash tools/checks/ban_a.sh\n"))
        check("by name, a trailing comment cut; counted in the OK line", (rc, out) == (0, "check_guards_are_wired: OK — 1"
              " guard(s) wired into a workflow; 1 awaiting a self-test (exempt, must shrink).\n"), out + err)
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/selftest_exempt.txt": "tools/checks/ban_a.sh\n"},
                                "      - run: bash tools/checks/ban_a.sh\n"))
        check("by repository-relative path", rc == 0, out + err)
        rc, out, err = run(tree({**GUARD, "tools/checks/selftest_exempt.txt": "test_ban_a.sh\n"},
                                "      - run: bash tools/checks/ban_a.sh\n"))
        check("never for a self-test", rc == 1 and "        test_ban_a.sh\n" in out, out)
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/selftest_exempt.txt": "ban_a.sh\n"}, "\n"))
        check("gzapp: an exemption does not excuse wiring", rc == 1 and "referenced by no workflow" in out, out)
        rc, out, err = run(tree({"tools/checks/a.sh": "", "tools/checks/selftest_exempt.txt": "a.sh\n"}, "\n"), lines_cfg)
        check("excuses_wiring: it does", (rc, out) == (0, "lines OK 1 1\n"), out + err)
        root = tree(GUARD, WIRED)
        os.remove(os.path.join(root, "tools/checks/selftest_exempt.txt"))
        rc, out, err = run(root)
        check("a required list missing is exit 2, named", (rc, out) == (2, "") and err ==
              f"check_guards_are_wired: exemption list not found at {root}/tools/checks/selftest_exempt.txt\n", err)
        rc, out, err = run(root, lines_cfg)
        check("one not required may be absent", (rc, out) == (0, "lines OK 1 0\n"), out + err)

        print("guards_wired: the whole tree")
        rc, out, err = run(tree({**GUARD, "apps/x/test_y.sh": "", "node_modules/p/test_z.sh": "",
                                 ".hidden/test_h.sh": "", "tools/checks/sub/test_s.sh": ""}, WIRED))
        check("a test_*.sh elsewhere, unwired, is reported by path, one under a checked directory's subdirectory"
              " too; node_modules and hidden dirs are not walked",
              rc == 1 and "        apps/x/test_y.sh\n" in out and "        tools/checks/sub/test_s.sh\n" in out
              and "test_z" not in out and "test_h" not in out, out)
        rc, out, err = run(tree({"tools/checks/a.sh": "", "tools/checks/test_a.sh": "", "target/c/test_v.sh": ""},
                                "      - run: bash tools/checks/a.sh\n      - run: bash tools/checks/run_suite.sh"
                                " tools/checks/test_a.sh\n"), lines_cfg)
        check("a project's own exclusion (target) is honoured", rc == 0, out + err)

        print("guards_wired: the two forms, whole")
        rc, out, err = run(tree({"tools/checks/ban_a.sh": "", "tools/checks/check_b.sh": "", "tools/checks/test_check_b.sh": "",
                                 "tools/gh/p.sh": "", "tools/gh/test_p.sh": ""},
                                "      - run: bash tools/checks/check_b.sh\n      - run: bash tools/gh/test_p.sh\n"))
        want = ("FAIL: 1 guard(s) are referenced by no workflow —\n"
                "      they can never fail a build, whatever they contain:\n        ban_a.sh\n\n"
                "FAIL: 1 self-test(s) are referenced by no workflow —\n"
                "      the guard is checked in CI but its self-test is not, so a\n"
                "      guard that silently stopped detecting anything would still pass:\n        test_check_b.sh\n\n"
                "FAIL: 1 self-test(s) are run without tools/checks/run_suite.sh —\n"
                "      run bare, an assertion calling an undefined helper passes\n"
                "      silently. Invoke them as: bash tools/checks/run_suite.sh <suite>\n        tools/gh/test_p.sh\n\n"
                "FAIL: 1 guard(s) have no test_<name>.sh and are not\n"
                "      listed in selftest_exempt.txt:\n        ban_a.sh\n\n"
                "Two ways to green: (a) wire it up — add a step to the relevant\n"
                "workflow (guard AND self-test are separate steps), and write the\n"
                "missing test_<name>.sh covering the clean case plus each failure\n"
                "mode the guard's header claims; or (b) the guard is obsolete —\n"
                "then DELETE it, do not leave it in the tree unreferenced. Adding\n"
                "a name to selftest_exempt.txt is a loosening, not a fix:\n"
                "that list exists for four historical guards and must only shrink.\n")
        check("grouped: the blocks in order, names as the directory says, the footer", (rc, out, err) == (1, want, ""),
              out + err)
        rc, out, err = run(tree({"tools/checks/a.sh": "", "tools/ci/w.sh": "", "tools/ci/test_w.sh": "",
                                 "tools/gh/test_q.sh": ""},
                                "      - run: bash tools/gh/test_q.sh\n"
                                "      - run: for t in tools/ci/test_*.sh; do bash \"$t\"; done\n"), lines_cfg)
        check("lines: one per finding, directory by directory, then the loops; the summary on stderr",
              (rc, out, err) == (1, "tools/checks/a.sh: untested (tools/checks/test_a.sh)\ntools/checks/a.sh: unwired\n"
                                    "tools/gh/test_q.sh: suite bare\ntools/ci/w.sh: unwired\n"
                                    "bare loop: for t in tools/ci/test_*.sh; do bash \"$t\"; done\n",
                                 "\nsummary 5\n"), f"{out}|{err}")

        print("guards_wired: refusals")
        root = tree(GUARD, WIRED)
        os.makedirs(os.path.join(root, ".github", "workflows", "deep"))
        with open(os.path.join(root, ".github", "workflows", "deep", "x.yml"), "wb") as fh:
            fh.write(b"      - run: bash \xff\n")
        rc, out, err = run(root)
        check("a workflow that is not UTF-8 is exit 2, named, never a verdict",
              rc == 2 and out == "" and err.startswith("check_guards_are_wired: could not read the workflow run commands: "
                                                       f"{root}/.github/workflows/deep/x.yml: "), out + err)
        os.remove(os.path.join(root, ".github", "workflows", "deep", "x.yml"))
        locked = os.path.join(root, ".github", "workflows", "ci.yml")
        os.chmod(locked, 0)
        try:
            rc, out, err = run(root)
        finally:
            os.chmod(locked, 0o644)
        check("one that cannot be opened likewise: its guards are never reported unwired",
              rc == 2 and out == "" and err == "check_guards_are_wired: could not read the workflow run commands: "
                                                f"{locked}: Permission denied\n", out + err)
        os.chmod(locked, 0)
        try:
            rc, out, err = run(root, lines_cfg)
        finally:
            os.chmod(locked, 0o644)
        check("…with no package-script hop to read it a second time, too",
              rc == 2 and out == "" and err == "check_guards_are_wired: could not read the workflow run commands: "
                                                f"{locked}: Permission denied\n", out + err)
        os.makedirs(os.path.join(root, "apps", "p"))
        with open(os.path.join(root, "apps", "p", "package.json"), "w") as fh:
            fh.write("{ not json")
        rc, out, err = run(root)
        check("a package.json that does not parse, with the pnpm hop on, is exit 2, named",
              rc == 2 and out == "" and err.startswith(f"check_guards_are_wired: could not read package scripts: {root}/apps/p/"
                                                       "package.json: "), out + err)
        with open(os.path.join(root, "apps", "p", "package.json"), "w") as fh:
            fh.write("[]")
        rc, out, err = run(root)
        check("…and one that parses but is no object, likewise, never a traceback",
              (rc, out, err) == (2, "", f"check_guards_are_wired: could not read package scripts: {root}/apps/p/package.json:"
                                        " not a JSON object\n"), out + err)
        rc, out, err = run(tree(GUARD, WIRED + "      - run: ls tools/[z-a]* tools/checks/[\\]x\n"))
        check("a bracket no shell could expand wires nothing and raises nothing", rc == 0 and "Traceback" not in err,
              out + err)
        empty = os.path.join(sandbox, "empty")
        os.makedirs(empty)
        rc, out, err = run(empty)
        check("no workflows directory: exit 2, named",
              (rc, err) == (2, f"check_guards_are_wired: workflows directory not found at {empty}/.github/workflows\n"), err)
        rc, out, err = run(empty, None)
        check("no config: exit 2", rc == 2 and err.startswith(f"check_guards_are_wired: no guards config for {empty} "), err)
        bad = os.path.join(sandbox, "bad.json")
        for label, change in (("an unknown role", {"dirs": [{"dir": "x", "role": "boss", "members": "."}]}),
                              ("an unknown report form", {"report": "fancy"}),
                              ("an unknown package manager", {"package_scripts": "yarn"})):
            with open(bad, "w", encoding="utf-8") as fh:
                json.dump({**LINES, **change}, fh)
            rc, out, err = run(empty, bad)
            check(f"{label} in the config is refused", rc == 2 and err.startswith(f"check_guards_are_wired: cannot read {bad}:"),
                  err)
        # The operator a working copy's project is found in: a fixture registry
        # holding gzapp's remote, and gzapp's guards.json at its place (instance data).
        operator = os.path.join(sandbox, "operator")
        os.makedirs(os.path.join(operator, "projects", "gzapp", "integration", "gh"))
        with open(os.path.join(operator, "projects", "registry.json"), "w", encoding="utf-8") as fh:
            json.dump({"projects": {"gzapp": {"remotes": ["git@github.com:gzapi-org/gzapp.git"]}}}, fh)
        shutil.copy(GZAPP, os.path.join(operator, "projects", "gzapp", "integration", "gh", "guards.json"))
        gz = tree(GUARD, WIRED)
        for args in (["init", "-q", gz], ["-C", gz, "remote", "add", "origin", "git@github.com:gzapi-org/gzapp.git"]):
            subprocess.run(["git", *args], env=base, check=True, capture_output=True, timeout=30)
        base["AGENT_FABRIC_OPERATOR"] = operator
        rc, out, err = run("", None, cwd=gz)
        del base["AGENT_FABRIC_OPERATOR"]
        check("a gzapp working copy, no --root: its toplevel, gzapp's guards.json", rc == 0 and "1 guard(s) wired" in out,
              out + err)
        rc, out, err = run("", GZAPP, "-h")
        check("--help is the module's text", rc == 0 and "passes silently-green" in out and not err)

    print("ok" if not fails else f"{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
