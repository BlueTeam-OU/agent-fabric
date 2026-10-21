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
whole; the refusals; rule 1's one hop through a wired shell member, each
reading that counts and each that does not. Plain script: prints ok/FAIL, exit 1 on any failure."""
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
        print("guards_wired: the runner rule over the whole tree")
        elsewhere = {**GUARD, "apps/x/test_y.sh": ""}
        rc, out, err = run(tree(elsewhere, WIRED + "      - run: bash apps/x/test_y.sh\n"))
        check("a test_*.sh outside the configured directories, run bare, is bare",
              rc == 1 and "FAIL: 1 self-test(s) are run without tools/checks/run_suite.sh" in out and "        apps/x/test_y.sh\n" in out, out)
        rc, out, err = run(tree(elsewhere, WIRED + "      - run: bash tools/checks/run_suite.sh apps/x/test_y.sh\n"))
        check("…the same run through the runner passes (the positive control)", rc == 0, out + err)
        rc, out, err = run(tree(elsewhere, WIRED + "      - run: bash tools/checks/run_suite.sh apps/x/test_y.sh\n      - run: bash apps/x/test_y.sh\n"))
        check("…and a wrapped run elsewhere does not excuse a bare one", rc == 1 and "        apps/x/test_y.sh\n" in out, out)
        rc, out, err = run(tree(elsewhere, WIRED + "      - run: for t in apps/x/test_*.sh; do bash \"$t\"; done\n"))
        check("a bare for-loop over such suites is bare, the head named", rc == 1 and "        for t in apps/x/test_*.sh; do bash \"$t\"; done\n" in out, out)
        rc, out, err = run(tree(elsewhere, WIRED + "      - run: for t in apps/x/test_*.sh; do bash tools/checks/run_suite.sh \"$t\"; done\n"))
        check("…and one that hands its variable to the runner passes", rc == 0, out + err)
        pkg = {"apps/admin_web/package.json": json.dumps({"name": "admin_web", "scripts": {"lint": "bash scripts/test_c.sh"}}),
               "apps/admin_web/scripts/test_c.sh": ""}
        flow = WIRED + "      - run: pnpm --filter admin_web lint\n"
        rc, out, err = run(tree({**GUARD, **pkg}, flow))
        check("a bare one reached through a pnpm package script is bare, by its path from the root",
              rc == 1 and "        apps/admin_web/scripts/test_c.sh\n" in out, out)
        pkg["apps/admin_web/package.json"] = json.dumps({"name": "admin_web", "scripts": {
            "lint": "bash ../../tools/checks/run_suite.sh scripts/test_c.sh"}})
        rc, out, err = run(tree({**GUARD, **pkg}, flow))
        check("…and the same script handing it to the runner passes", rc == 0, out + err)
        rc, out, err = run(tree({**GUARD, "node_modules/p/test_z.sh": "", ".hidden/test_h.sh": ""},
                                WIRED + "      - run: bash node_modules/p/test_z.sh\n      - run: bash .hidden/test_h.sh\n"))
        check("a bare one under a tree_excludes path or a hidden directory is not reported", rc == 0, out + err)
        rc, out, err = run(tree({**GUARD, "tools/gh/test_q.sh": "", "tools/gh/x.sh": ""}, WIRED + "      - run: bash tools/gh/test_q.sh\n"), lines_cfg)
        check("the configured directories answer as before", rc == 1 and "tools/gh/test_q.sh: suite bare" in out, out)
        rc, out, err = run(tree(elsewhere, WIRED + "      - run: bash apps/x/test_y.sh\n"), lines_cfg)
        check("in the lines form too: the path and the summary", rc == 1 and "apps/x/test_y.sh: suite bare" in out, out)

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
        print("guards_wired: rule 1's one hop through a wired shell member")
        HERE = 'here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        SUITES = ("      - run: bash tools/ci/main.sh\n"
                  "      - run: for t in tools/ci/test_*.sh; do bash tools/checks/run_suite.sh \"$t\"; done\n")

        def hop(main: str, extra: dict | None = None, workflow: str = SUITES):
            files = {"tools/ci/main.sh": main, "tools/ci/test_main.sh": "",
                     "tools/ci/helper.sh": "", "tools/ci/test_helper.sh": "", **(extra or {})}
            return run(tree(files, workflow), lines_cfg)

        for label, main in (
                ("under a variable set to the script's own directory", HERE + 'python3 "$here/helper.sh" a b\n'),
                ("under ${var}, after cd -- and dirname --",
                 'HERE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"\nbash "${HERE}/helper.sh"\n'),
                ("as \"$(dirname \"$0\")/<name>\"", 'bash "$(dirname "$0")/helper.sh" x\n'),
                ("by its repository-relative path", 'bash tools/ci/helper.sh\n'),
                ("on a continuation line", HERE + 'python3 \\\n    "$here/helper.sh"\n'),
                ("under an unquoted $(cd … && pwd)",
                 'here=$(cd "$(dirname "$0")" && pwd)\nbash "$here/helper.sh"\n'),
                ("with its output redirected", HERE + 'bash "$here/helper.sh" >&2 2>&1\n'),
                ("behind a leading redirect and its target", '2> log bash tools/ci/helper.sh\n'),
                ("after a << and a backtick that are single-quoted", "echo 'a << b' '`x`'\nbash tools/ci/helper.sh\n"),
                ("behind a keyword", 'if true; then bash tools/ci/helper.sh; fi\n'),
                ("after an array appended in a loop", 'for p in a b; do args+=(-p "$p"); done\nbash tools/ci/helper.sh\n'),
                ("after a subshell closed against a ;", '(true); bash tools/ci/helper.sh\n'),
                ("after a quoted ( on a line of its own", 'grep "(" f\nbash tools/ci/helper.sh\n'),
                ("after a case closed past ;; on its arm's line", 'case "$1" in\n  -h) exit 0 ;; esac\nbash tools/ci/helper.sh\n'),
                ("after a nested $( ) and quotes that close", 'x="$(cd "$(dirname "$0")" && echo "(")"\nbash tools/ci/helper.sh\n'),
                ("after a case whose last arm ends in ;& then esac", 'case "$1" in\n  a) : ;&\n  b) : ;;\nesac\nbash tools/ci/helper.sh\n'),
                ("after a quoted # and a ;", 'echo "#"; bash tools/ci/helper.sh\n'),
                ("after a quoted word opening with #", 'echo "a" "#b"; tools/ci/helper.sh\n'),
                ("after a ;# inside quotes", 'echo "a;#" ; bash tools/ci/helper.sh\n'),
                ("after an escaped ; before a #", 'echo a\\;#b; bash tools/ci/helper.sh\n'),
                ("after an escaped ; that follows a ;, before a #", 'true;\\;#x 2>/dev/null; bash tools/ci/helper.sh\n'),
                ("after a comment ending in a backslash, which continues nothing", '# note \\\nbash tools/ci/helper.sh\n'),
                ("after a case closed by esac;", 'case "$1" in\n  a) : ;;\nesac;\nbash tools/ci/helper.sh\n'),
                ("after a case closed on a line holding ${ }", 'case "$1" in a) y=${x} ;; esac\nbash tools/ci/helper.sh\n'),
                ("after a case closed past ;;& on its arm's line", 'case "$1" in a) : ;;& esac\nbash tools/ci/helper.sh\n'),
                ("after a case closed past ;& on its arm's line", 'case "$1" in a) : ;& esac\nbash tools/ci/helper.sh\n'),
                ("after a case whose empty arm's ;; touches its )", 'case "$1" in a);; esac\nbash tools/ci/helper.sh\n'),
                ("after a case that ends", 'case "$1" in -h) exit 0 ;; esac\nbash tools/ci/helper.sh\n'),
                ("after a case block that ends", 'case "$1" in\n  -h) exit 0 ;;\nesac\nbash tools/ci/helper.sh\n'),
                ("behind a leading assignment", 'X=1 bash tools/ci/helper.sh\n'),
                ("behind a redirect to a file", '> log bash tools/ci/helper.sh\n'),
                ("past the interpreter's options", 'bash -e -u tools/ci/helper.sh\n'),
                ("after a <<< here-string", 'tr a b <<< hello\nbash tools/ci/helper.sh\n'),
                ("as a later command of a line", HERE + 'true && bash "$here/helper.sh" | tee log\n')):
            rc, out, err = hop(main)
            check(f"a helper the wired member runs is wired: {label}", rc == 0, out + err)
        for label, main in (
                ("in a comment", HERE + '# bash "$here/helper.sh"\n'),
                ("after a command's comment", HERE + 'true # bash "$here/helper.sh"\n'),
                ("in an echo", HERE + 'echo bash "$here/helper.sh"\n'),
                ("inside a longer string", HERE + 'printf "%s\\n" "run $here/helper.sh"\n'),
                ("in an assignment", HERE + 'h="$here/helper.sh"\n'),
                ("under a variable naming another directory",
                 'here="$(cd "$(dirname "$0")/.." && pwd)"\nbash "$here/helper.sh"\n'),
                ("under a variable assigned twice", HERE + 'here=/tmp\nbash "$here/helper.sh"\n'),
                ("under a variable never assigned", 'bash "$X/helper.sh"\n'),
                ("by a bare name", 'cd tools/ci && bash helper.sh\n'),
                ("echoed after a separator", HERE + 'true && echo "$here/helper.sh"\n'),
                ("echoed across a continuation", HERE + 'echo \\\n    "$here/helper.sh"\n'),
                ("after a ; inside an echo's string", 'echo "skipped; tools/ci/helper.sh is not run"\n'),
                ("after a ; inside a printf's string", 'printf "%s\\n" "done; tools/ci/helper.sh next"\n'),
                ("on a line of a string that spans lines", 'msg="usage:\ntools/ci/helper.sh\n"\n'),
                ("in a heredoc's body", 'cat <<EOF\ntools/ci/helper.sh\nEOF\n'),
                ("in a quoted heredoc's body", "cat <<-'END'\n\ttools/ci/helper.sh\n\tEND\n"),
                ("under a variable reassigned after a ;", HERE + 'true; here=/var\nbash "$here/helper.sh"\n'),
                ("under a variable reassigned after &&", HERE + '[ -n "$X" ] && here=/var\nbash "$here/helper.sh"\n'),
                ("under a variable appended to", HERE + 'here+="/.."\nbash "$here/helper.sh"\n'),
                ("under a for loop's variable", HERE + 'for here in /a; do :; done\nbash "$here/helper.sh"\n'),
                ("under a variable read", HERE + 'read -r here\nbash "$here/helper.sh"\n'),
                ("under a variable defaulted", HERE + ': "${here:=/var}"\nbash "$here/helper.sh"\n'),
                ("under a variable a second assignment of a line sets", HERE + 'local x=1 here=/var\nbash "$here/helper.sh"\n'),
                ("under a variable appended its own directory to", HERE + 'here+="$(dirname "$0")"\nbash "$here/helper.sh"\n'),
                ("in a command shlex cannot read", 'bash tools/ci/helper.sh "unclosed\n'),
                ("echoed to stderr", HERE + 'echo >&2 usage: "$here/helper.sh"\n'),
                ("echoed with 2>&1", 'echo missing 2>&1 tools/ci/helper.sh\n'),
                ("echoed behind a redirect and its target", '2> log echo tools/ci/helper.sh\n'),
                ("echoed after a leading redirect", '>&2 echo tools/ci/helper.sh\n'),
                ("in a heredoc inside $( )", 'msg=$(cat <<EOF\nusage: tools/ci/helper.sh\nEOF\n)\n'),
                ("in a heredoc whose delimiter is backslash-quoted", 'cat <<\\EOF\ntools/ci/helper.sh\nEOF\n'),
                ("in a script with a heredoc delimiter it cannot read", 'cat <<"$X"\nx\n$X\nbash tools/ci/helper.sh\n'),
                ("under a variable while read sets", HERE + 'while read -r here; do bash "$here/helper.sh"; done\n'),
                ("under a variable IFS= read sets", HERE + 'IFS= read -r here\nbash "$here/helper.sh"\n'),
                ("under an inner for's variable", HERE + 'for x in 1; do for here in /a; do bash "$here/helper.sh"; done; done\n'),
                ("under a variable getopts sets", HERE + 'while getopts ab here; do :; done\nbash "$here/helper.sh"\n'),
                ("handed to printf", 'printf "%s\\n" tools/ci/helper.sh\n'),
                ("handed to test", HERE + '[ -x "$here/helper.sh" ]\n'),
                ("handed to cat", 'cat tools/ci/helper.sh\n'),
                ("echoed past >|", 'echo usage >| log tools/ci/helper.sh\n'),
                ("in a comment inside $( )", 'n=$(\n  # see tools/ci/helper.sh\n  wc -l x\n)\n'),
                ("under a variable a case arm reads", HERE + 'case x in a) read -r here ;; esac\nbash "$here/helper.sh"\n'),
                ("under a variable (( )) sets", HERE + '(( here = 1 ))\nbash "$here/helper.sh"\n'),
                ("under a variable let sets", HERE + 'let "here=1"\nbash "$here/helper.sh"\n'),
                ("under a variable eval sets", HERE + 'eval "here=/tmp"\nbash "$here/helper.sh"\n'),
                ("under a variable a redirected read sets", HERE + '<in read -r here\nbash "$here/helper.sh"\n'),
                ("as a case pattern", 'case "$1" in\n  tools/ci/helper.sh) echo hi ;;\nesac\n'),
                ("as an array element", 'files=(tools/ci/helper.sh tools/ci/x.sh)\n'),
                ("as an array element after the (", 'files=(x tools/ci/helper.sh) && true\n'),
                ("as an echo's argument after a $( )", 'echo $(date) tools/ci/helper.sh\n'),
                ("in an arm of a case after a quoted #", 'echo "#"; case "$1" in\n  a)\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("as a function's name", 'tools/ci/helper.sh() { :; }\n'),
                ("in an arm of a case behind then", 'if true; then case "$1" in\n  a)\n    bash tools/ci/helper.sh ;;\n  esac\nfi\n'),
                ("in a later arm, after a pattern a|esac", 'case "$1" in\n  a|esac) echo ;;\n  b)\n    tools/ci/helper.sh ;;\nesac\n'),
                ("in a later arm, after a pattern \"esac\"", 'case "$1" in\n  "esac") echo ;;\n  b)\n    tools/ci/helper.sh ;;\nesac\n'),
                ("in a later arm, after a pattern (esac)", 'case "$1" in\n  (esac) echo ;;\n  b)\n    tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm of a case in a function", 'function f { case "$1" in\n  b)\n    tools/ci/helper.sh ;;\n  esac\n}\n'),
                ("in an arm of a case in a () function", 'f() { case "$1" in\n  b)\n    tools/ci/helper.sh ;;\n  esac\n}\n'),
                ("in an arm after a quoted ;; esac", 'case "$1" in\n  a) echo \'x ;; esac;\'\n     bash tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm after a double-quoted ;; esac", 'case "$1" in\n  a) msg=";; esac}"\n     bash tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm after a fallthrough ;& closes nothing early", 'case "$1" in\n  a) : ;&\n  b)\n    tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm after 'esac' run as a command", "case $1 in\n  a)\n    'esac' 2>/dev/null\n    bash tools/ci/helper.sh\n    ;;\nesac\n"),
                ("in an arm after \\esac run as a command", 'case $1 in\n  a) true; \\esac 2>/dev/null\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm after \"esac\" run as a command", 'case $1 in\n  a) true; "esac" 2>/dev/null\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm after echo esac; 'esac'", "case $1 in\n  a) echo esac; 'esac' 2>/dev/null\n    bash tools/ci/helper.sh ;;\nesac\n"),
                ("in an arm after echo esac; \\esac", 'case $1 in\n  a) echo esac; \\esac 2>/dev/null\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("in an arm after a double-quoted esac and 'esac'", 'case "$1" in\n  a)\n    echo "a esac b"; \'esac\'\n    bash tools/ci/helper.sh\n    ;;\nesac\n'),
                ("in an arm after esac nested in \"$( )\" and 'esac'", 'case "$1" in\n  a)\n    x="$(echo "esac")"; \'esac\'\n    bash tools/ci/helper.sh\n    ;;\nesac\n'),
                ("in an arm after an escaped ; before esac", 'case "x" in\n  a)\n    echo a\\;esac\n    bash tools/ci/helper.sh\n    ;;\nesac\n'),
                ("in an arm after \\\" ; esac inside double quotes", 'case "x" in\n  a)\n    echo "a\\" ; esac ; \\""\n    bash tools/ci/helper.sh\n    ;;\nesac\n'),
                ("in an arm after ; esac inside ${ }", 'case "x" in\n  a)\n    echo ${x:-a ; esac }\n    bash tools/ci/helper.sh\n    ;;\nesac\n'),
                ("in an arm after ; esac inside a word's quotes", 'case "$1" in\n  never)\n    msg="a ; esac ; b"\n    bash tools/ci/helper.sh\n    ;;\nesac\n'),
                ("in an arm after ; esac inside a mid-word single quote", "case \"$1\" in\n  never)\n    x=a'b ; esac ; c'\n    bash tools/ci/helper.sh\n    ;;\nesac\n"),
                ("in an arm after ; esac inside $' '", "case \"$1\" in\n  never)\n    printf $'x ; esac ; y'\n    bash tools/ci/helper.sh\n    ;;\nesac\n"),
                ("in an arm after a comment straight after ;;", 'case "$1" in\n  a) x=1 ;;#;; esac\n  b)\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("across a line ending in an escaped backslash", 'bash tools/ci\\\\\n/helper.sh\n'),
                ("in a one-line case arm after a ;", 'case "$1" in a) true; bash tools/ci/helper.sh ;; esac\n'),
                ("in a later arm, after an echo of esac", 'case "$1" in\n  a) echo esac ;;\n  b)\n    tools/ci/helper.sh ;;\nesac\n'),
                ("as a case arm's command", 'case "$1" in a) tools/ci/helper.sh ;; esac\n'),
                ("as a case pattern on a line of its own", 'case x in\n  tools/ci/helper.sh|b\n  ) echo ;;\nesac\n'),
                ("as an arm's command on a line of its own", 'case x in\n  a)\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("as a subshell's command", '(bash tools/ci/helper.sh)\n'),
                ("as sh -s's stdin script name", 'sh -s tools/ci/helper.sh < /dev/null\n'),
                ("after an interpreter flag that takes an argument", 'bash --rcfile tools/ci/helper.sh x.sh\n'),
                ("under a variable used before its assignment", 'bash "$here/helper.sh"\n' + HERE),
                ("under a variable printf -v sets", HERE + 'printf -v here %s /var\nbash "$here/helper.sh"\n')):
            rc, out, err = hop(main)
            check(f"not run, {label}", rc == 1 and "tools/ci/helper.sh: unwired\n" in out
                  and "tools/ci/main.sh: unwired" not in out, out + err)
        for label, main in (
                ("a heredoc", HERE + 'cat <<EOF\nx\nEOF\nbash "$here/helper.sh"\n'),
                ("a heredoc inside a quoted $( )", 'git commit -m "$(cat <<\'EOF\'\nrun "bash tools/ci/helper.sh" first\nEOF\n)"\n'),
                ("a backtick", 'x=`date`\nbash tools/ci/helper.sh\n'),
                ("a quote that does not close on its line", 'msg="a\nb"\nbash tools/ci/helper.sh\n'),
                ("an arithmetic shift", 'x=$((1 << n))\nbash tools/ci/helper.sh\n'),
                ("a comment straight after ;", 'true;#;bash tools/ci/helper.sh\n'),
                ("a # inside a single quote nested in \"$( )\"", 'x="$(echo "\'" #\'; bash tools/ci/helper.sh; "\')"\n)" #"\n'),
                ("a $( spelt across a continuation", 'x="$\\\n(true;#)"; bash tools/ci/helper.sh\n)" #"\n'),
                ("a $' spelt across a continuation", "x=$\\\n'\\'';#'; bash tools/ci/helper.sh\n"),
                ("a # after an operator inside a double-quoted $( )", 'x="$(true;#)"; bash tools/ci/helper.sh\n)" #"\n'),
                ("a $' ' string holding an escaped quote", "x=$'\\'';#'; bash tools/ci/helper.sh\n"),
                ("a comment straight after &", 'true &#& bash tools/ci/helper.sh\n'),
                ("a command before a comment straight after ;", 'bash tools/ci/helper.sh;# x\n'),
                ("a # after the ) of a $( ) hiding a heredoc", 'x=$(pwd)#; cat <<EOF\nbash tools/ci/helper.sh\nEOF\n'),
                ("a # after the ) of a $( ) hiding a case", 'x=$(pwd)#; case "$1" in\n  a)\n    bash tools/ci/helper.sh ;;\nesac\n'),
                ("a case whose last arm has no ;;", 'case "$1" in a) : ; esac\nbash tools/ci/helper.sh\n'),
                ("a heredoc after an escaped quote", ": \\' <<EOF \\'\nbash tools/ci/helper.sh\nEOF\n"),
                ("a heredoc in a double-quoted $( ) that closes on its line", 'x="$(cat <<EOF)"\nbash tools/ci/helper.sh\nEOF\n'),
                ("a backtick in double quotes", 'x="`date`"\nbash tools/ci/helper.sh\n'),
                ("an array that spans lines", 'files=(\n  tools/ci/helper.sh\n)\n'),
                ("an array that spans lines past a quoted )", 'files=( ")"\n  tools/ci/helper.sh\n)\n'),
                ("an array that spans lines past an escaped )", 'files=( \\)\n  tools/ci/helper.sh\n)\n'),
                ("an array that spans lines past a ) in ${ }", 'files=( ${x%)}\n  tools/ci/helper.sh\n)\n'),
                ("an array that spans lines past quotes nested in $( )", 'files=( "$(echo ")")"\n  tools/ci/helper.sh\n)\n'),
                ("a case inside a ( that spans lines", '( case $x in a) : ;; esac\n  bash tools/ci/helper.sh\n)\n'),
                ("a case in a double-quoted $( ) that spans lines", 'y=$1\nx="$(case $y in a) #"\nbash tools/ci/helper.sh\n;; esac) #"\n'),
                ("a one-line case in $( )", 'y=$(case $1 in a) echo 1 ;; esac)\nbash tools/ci/helper.sh\n'),
                ("a declared array that spans lines", 'declare -a L=(\n  tools/ci/helper.sh\n)\n')):
            rc, out, err = hop(main)
            check(f"a script with {label} is not read: its helper is reported, and stderr says why",
                  rc == 1 and "tools/ci/helper.sh: unwired\n" in out
                  and "tools/ci/main.sh was not read for what it runs (" in err
                  and "names tools/ci/helper.sh" in err, out + err)
        rc, out, err = hop('a \\\nb \\\nc\nx=`d`\nbash tools/ci/helper.sh\n')
        check("the reason names the physical line, past continuations",
              "(line 4: a backtick)" in err, out + err)
        rc, out, err = hop('x=1\ny \\\n  `d`\nbash tools/ci/helper.sh\n')
        check("…and, for a continued line, the line it starts on",
              "(line 2: a backtick)" in err, out + err)
        rc, out, err = hop('cat <<EOF\nx\nEOF\n')
        check("an unread script that does not name the member says nothing of it",
              rc == 1 and "was not read" not in err, out + err)
        rc, out, err = hop(HERE + 'bash "$here/helper.sh"\n', workflow=SUITES.replace("      - run: bash tools/ci/main.sh\n", ""))
        check("a member no workflow runs wires nothing it runs",
              rc == 1 and "tools/ci/main.sh: unwired\n" in out and "tools/ci/helper.sh: unwired\n" in out, out)
        rc, out, err = hop(HERE + 'bash "$here/mid.sh"\n',
                           {"tools/ci/mid.sh": HERE + 'bash "$here/helper.sh"\n', "tools/ci/test_mid.sh": ""})
        check("one hop only: a helper reached through a helper stays unwired",
              rc == 1 and "tools/ci/helper.sh: unwired\n" in out and "tools/ci/mid.sh" not in out, out)
        rc, out, err = hop("", {"tools/checks/ban_p.py": "bash tools/ci/helper.sh\n",
                                "tools/checks/test_ban_p.sh": ""},
                           SUITES + "      - run: python3 tools/checks/ban_p.py\n"
                                    "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_p.sh\n")
        check("a Python member's text is not read as shell", rc == 1 and "tools/ci/helper.sh: unwired\n" in out, out)
        root = tree({"tools/ci/main.sh": HERE + 'bash "$here/helper.sh"\n', "tools/ci/test_main.sh": "",
                     "tools/ci/helper.sh": ""}, SUITES)
        rc, out, err = run(root, lines_cfg)
        check("rule 2 is unchanged: the helper still needs its self-test",
              rc == 1 and "tools/ci/helper.sh: untested (tools/ci/test_helper.sh)\n" in out
              and "helper.sh: unwired" not in out, out)
        # Unreadable as invalid UTF-8, not by mode: root reads a mode-0 file.
        with open(os.path.join(root, "tools/ci/main.sh"), "wb") as fh:
            fh.write(b"bash tools/ci/helper.sh \xff\n")
        rc, out, err = run(root, lines_cfg)
        check("a wired member that cannot be read: exit 2, named, never a guess",
              rc == 2 and f"could not read a wired member: {root}/tools/ci/main.sh" in err, out + err)
        rc, out, err = hop("", {"tools/checks/ban_q.py": b"\xff tools/ci/helper.sh\n", "tools/checks/test_ban_q.sh": ""},
                           SUITES + "      - run: python3 tools/checks/ban_q.py\n"
                                    "      - run: bash tools/checks/run_suite.sh tools/checks/test_ban_q.sh\n")
        check("a non-shell member is not decoded, so its bytes refuse nothing", rc == 1 and "helper.sh: unwired\n" in out,
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
