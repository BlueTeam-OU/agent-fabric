#!/usr/bin/env python3
"""Tests for tools/fabric/install_agent_files.py's internals; the behaviour is
runtime/claude-code/test_install-agent-files.sh's, run against the shim
(ADR-040 §5 rule 5). What that oracle cannot reach is here, against a fixture
fabric root whose routing.py, identity.py and MCP install.py are stubs that
record how they were called: the pin and effort placement, a model line that
appears twice, the provider reaching routing, the user configuration paths,
install.py's flags, lines and failures, the backup's marker rule, the file
mode, the retired reviewer's removal, the counts and the arguments.

Hermetic: the environment passed on is rebuilt from nothing but PATH, HOME and
CLAUDE_CONFIG_DIR in scratch, and no run touches the real ~/.claude."""
from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE = os.path.join(HERE, "tools", "fabric", "install_agent_files.py")
AGENTS = os.path.join(HERE, "runtime", "claude-code", "agents")
CLASSES = ("code-low", "code-medium", "code-high", "code-plan", "code-review")

ROUTING_STUB = """\
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(d, "calls.log"), "a") as f:
    f.write(json.dumps({"tool": "routing", "argv": sys.argv[1:], "root": os.environ.get("AGENT_FABRIC_ROOT")}) + "\\n")
if os.path.exists(os.path.join(d, "fail-" + sys.argv[1])):
    sys.exit(3)
sys.stdout.write(open(os.path.join(d, sys.argv[1] + ".txt")).read())
"""
IDENTITY_STUB = """\
import os, sys
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "role.txt")
if not os.path.exists(p):
    sys.exit(1)
print(open(p).read().strip())
"""
INSTALL_STUB = """\
import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(d, "..", "..", "..", "tools", "fabric", "calls.log"), "a") as f:
    f.write(json.dumps({"tool": "install", "argv": sys.argv[1:]}) + "\\n")
fail = os.path.join(d, "fail")
if os.path.exists(fail):
    sys.exit(int(open(fail).read()))
out = os.path.join(d, "out-" + sys.argv[2] + ".txt")
if os.path.exists(out):
    sys.stdout.write(open(out).read())
"""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print(f"       {detail}")
        fails += not good

    scratch = tempfile.mkdtemp(prefix="test_install_agent_files.")
    n = 0
    try:
        def fixture() -> tuple[str, str, str]:
            """A fresh fabric root, HOME and CLAUDE_CONFIG_DIR, each its own directory."""
            nonlocal n
            n += 1
            base = os.path.join(scratch, f"f{n}")
            root, home, cfg = (os.path.join(base, x) for x in ("fabric", "home", "cfg"))
            for d in (home, cfg, os.path.join(root, "tools", "fabric"), os.path.join(root, "runtime", "mcp", "websearch-locale")):
                os.makedirs(d)
            shutil.copy(MODULE, os.path.join(root, "tools", "fabric", "install_agent_files.py"))
            shutil.copy(os.path.join(os.path.dirname(MODULE), "fabric_writes.py"), os.path.join(root, "tools", "fabric"))
            shutil.copytree(AGENTS, os.path.join(root, "runtime", "claude-code", "agents"))
            for rel, body in (("tools/fabric/routing.py", ROUTING_STUB), ("runtime/identity.py", IDENTITY_STUB),
                              ("runtime/mcp/websearch-locale/install.py", INSTALL_STUB)):
                with open(os.path.join(root, rel), "w") as f:
                    f.write(body)
            put(root, "tools/fabric/pins.txt", "code-review fable claude-pinned-model\n")
            put(root, "tools/fabric/efforts.txt", "".join(f"{k} - none\n" for k in CLASSES))
            return root, home, cfg

        def put(root: str, rel: str, text: str) -> None:
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(text)

        def env_for(home: str, cfg: str | None, **extra: str) -> dict:
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home}
            if cfg is not None:
                env["CLAUDE_CONFIG_DIR"] = cfg
            env.update(extra)
            return env

        def run(root: str, home: str, cfg: str | None, *args: str, **extra: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-I", os.path.join(root, "tools", "fabric", "install_agent_files.py"), *args],
                                  capture_output=True, text=True, env=env_for(home, cfg, **extra), check=False)

        def calls(root: str) -> list[dict]:
            p = os.path.join(root, "tools", "fabric", "calls.log")
            return [json.loads(x) for x in open(p).read().splitlines()] if os.path.exists(p) else []

        def read(p: str) -> str:
            with open(p) as f:
                return f.read()

        # The pin replaces the FIRST model line only, and the effort sits right after it.
        root, home, cfg = fixture()
        put(root, "tools/fabric/efforts.txt", "".join(f"{k} high ok\n" for k in CLASSES))
        two = os.path.join(root, "runtime", "claude-code", "agents", "code-review.md")
        text = read(two)
        with open(two, "w") as f:
            f.write(text + "\nmodel: second-in-the-body\n")
        r = run(root, home, cfg)
        got = read(os.path.join(cfg, "agents", "code-review.md")).splitlines()
        i = next(k for k, ln in enumerate(got) if ln.startswith("model: "))
        check("the pin replaces the model line", got[i] == "model: claude-pinned-model", got[i])
        check("the effort line follows the model line directly", got[i + 1] == "effort: high", got[i:i + 2])
        check("only the first model line is replaced", "model: second-in-the-body" in got and got.count("effort: high") == 1, str(got))
        low = read(os.path.join(cfg, "agents", "code-low.md"))
        check("a class with no pin keeps the repo file's model line", read(os.path.join(root, "runtime", "claude-code", "agents", "code-low.md")).splitlines()[1:3] == [ln for ln in low.splitlines() if ln != "effort: high"][1:3], low[:200])
        check("exit 0 and the count line", r.returncode == 0 and r.stdout.splitlines()[-1] == "agent files (anthropic): 5 written, 0 already current.", r.stdout + r.stderr)

        # An agents directory that cannot be written: one line and exit 1, as
        # install(1) said it under the bash, never a traceback (review of #86).
        root2, home2, cfg2 = fixture()
        os.makedirs(cfg2, exist_ok=True)
        with open(os.path.join(cfg2, "agents"), "w") as f:   # a file where the directory goes
            f.write("not a directory\n")
        r = run(root2, home2, cfg2)
        check("a destination that cannot be written: exit 1, one line naming it, no traceback",
              r.returncode == 1 and "install-agent-files: cannot write" in r.stderr
              and "Traceback" not in r.stderr and r.stderr.strip().count("\n") == 0, r.stderr)

        # A level of "-" is no effort line at all.
        root, home, cfg = fixture()
        run(root, home, cfg)
        check("effort '-' writes no effort: line", all("effort:" not in read(os.path.join(cfg, "agents", f"{k}.md")) for k in CLASSES))

        # The mode is 644 whatever the umask.
        root, home, cfg = fixture()
        old = os.umask(0o077)
        try:
            run(root, home, cfg)
        finally:
            os.umask(old)
        st = os.stat(os.path.join(cfg, "agents", "code-low.md")).st_mode & 0o777
        check("a file is written with mode 644", st == 0o644, oct(st))

        # The provider: argument, then AGENT_FABRIC_LAUNCH_PROVIDER, then anthropic; and what routing is told.
        root, home, cfg = fixture()
        r = run(root, home, cfg, "--provider=openrouter")
        rc = [c for c in calls(root) if c["tool"] == "routing"]
        check("--provider=P reaches routing for pins and efforts, with --me and the root",
              [c["argv"] for c in rc] == [["pins", "--me", "--provider", "openrouter"], ["efforts", "--me", "--provider", "openrouter"]]
              and all(c["root"] == root for c in rc), str(rc))
        check("the count line names the provider", "agent files (openrouter):" in r.stdout, r.stdout)
        root, home, cfg = fixture()
        r = run(root, home, cfg, "--provider", "openrouter")
        check("--provider P (two words) is the same", "agent files (openrouter):" in r.stdout, r.stdout + r.stderr)
        root, home, cfg = fixture()
        r = run(root, home, cfg, AGENT_FABRIC_LAUNCH_PROVIDER="openrouter")
        check("AGENT_FABRIC_LAUNCH_PROVIDER is the default provider", "agent files (openrouter):" in r.stdout, r.stdout)
        root, home, cfg = fixture()
        r = run(root, home, cfg, "--provider", "anthropic", AGENT_FABRIC_LAUNCH_PROVIDER="openrouter")
        check("the argument outranks the environment", "agent files (anthropic):" in r.stdout, r.stdout)

        # Arguments.
        root, home, cfg = fixture()
        r = run(root, home, cfg, "--bogus")
        check("an unknown argument exits 2, names it, writes nothing",
              r.returncode == 2 and "unknown argument --bogus" in r.stderr and not os.path.exists(os.path.join(cfg, "agents")), r.stderr)
        r = run(root, home, cfg, "--provider")
        check("--provider with no value exits 2", r.returncode == 2, r.stdout + r.stderr)

        # Where the user configuration lives, and what install.py is told.
        root, home, cfg = fixture()
        put(root, "runtime/mcp/websearch-locale/out-remove.txt", "  +  a mcpServers.websearch-locale (removed)\n\n  =  b\n  +  c (would write)\n")
        put(root, "runtime/mcp/websearch-locale/out-allow-websearch.txt", "  +  d\n")
        r = run(root, home, cfg, "--dry-run")
        ic = [c["argv"] for c in calls(root) if c["tool"] == "install"]
        check("a non-language-culture login: remove, then allow-websearch, in CLAUDE_CONFIG_DIR, each told --dry-run",
              ic == [[os.path.join(cfg, ".claude.json"), "remove", "--dry-run"], [os.path.join(cfg, "settings.json"), "allow-websearch", "--dry-run"]], str(ic))
        check("install.py's lines are printed, blank ones dropped, and counted (+ written, = current, would-write not)",
              r.stdout.splitlines()[-5:-1] == ["  +  a mcpServers.websearch-locale (removed)", "  =  b", "  +  c (would write)", "  +  d"]
              and r.stdout.splitlines()[-1] == "agent files (anthropic): 2 written, 1 already current.", r.stdout)
        check("the blank line is gone", "\n\n" not in r.stdout, r.stdout)
        root, home, cfg = fixture()
        run(root, home, cfg)
        ic = [c["argv"] for c in calls(root) if c["tool"] == "install"]
        check("no --dry-run to install.py on a real run", all("--dry-run" not in a for a in ic), str(ic))
        root, home, _ = fixture()
        run(root, home, None)
        ic = [c["argv"] for c in calls(root) if c["tool"] == "install"]
        check("without CLAUDE_CONFIG_DIR: ~/.claude.json and ~/.claude/settings.json, agents in ~/.claude/agents",
              ic == [[os.path.join(home, ".claude.json"), "remove"], [os.path.join(home, ".claude", "settings.json"), "allow-websearch"]]
              and os.path.isfile(os.path.join(home, ".claude", "agents", "code-low.md")), str(ic))

        # language-culture with a locale file: set and deny-websearch.
        root, home, cfg = fixture()
        me = pwd.getpwuid(os.getuid()).pw_name
        suffix = me.rsplit("-", 1)[-1]
        put(root, "runtime/role.txt", "language-culture\n")
        put(root, f"identities/roles/language-culture/locale/{suffix}/locale.json", "{}")
        put(root, "runtime/mcp/websearch-locale/server.mjs", "")
        run(root, home, cfg)
        ic = [c["argv"] for c in calls(root) if c["tool"] == "install"]
        lf = os.path.join(root, "identities", "roles", "language-culture", "locale", suffix, "locale.json")
        check("a language-culture login with a locale file: set <server> <locale.json>, then deny-websearch",
              ic == [[os.path.join(cfg, ".claude.json"), "set", os.path.join(root, "runtime/mcp/websearch-locale/server.mjs"), lf],
                     [os.path.join(cfg, "settings.json"), "deny-websearch"]], str(ic))
        os.unlink(lf)
        run(root, home, cfg)
        ic = [c["argv"] for c in calls(root) if c["tool"] == "install"][2:]
        check("the same role with no locale file: remove and allow", [a[1] for a in ic] == ["remove", "allow-websearch"], str(ic))

        # The locale suffix is what follows the LAST dash of the login.
        root, home, cfg = fixture()
        put(root, "runtime/role.txt", "language-culture\n")
        put(root, "identities/roles/language-culture/locale/ka/worker.md", "---\nname: locale-worker\ndescription: (agent-fabric) ka\n---\n")
        drv = ("import sys; sys.path.insert(0, sys.argv[1]); import install_agent_files as m; "
               "m.login = lambda: 'gz-writer-ka'; sys.exit(m.main([]))")
        r = subprocess.run([sys.executable, "-c", drv, os.path.join(root, "tools", "fabric")], capture_output=True, text=True,
                           env=env_for(home, cfg), check=False)
        check("login 'gz-writer-ka' takes locale ka's worker", os.path.isfile(os.path.join(cfg, "agents", "locale-worker.md")), r.stdout + r.stderr)

        # install.py's failure is the installer's, after the class files, and prints no count line.
        root, home, cfg = fixture()
        put(root, "runtime/mcp/websearch-locale/fail", "7")
        r = run(root, home, cfg)
        check("install.py exiting 7 makes the installer exit 7 with no count line, class files already written",
              r.returncode == 7 and "agent files (" not in r.stdout and os.path.isfile(os.path.join(cfg, "agents", "code-low.md")), f"{r.returncode} {r.stdout}")

        # The backup: a file carrying the marker is never backed up, one without is, once.
        root, home, cfg = fixture()
        a = os.path.join(cfg, "agents")
        os.makedirs(a)
        put(cfg, "agents/code-low.md", "this was written by agent-fabric earlier\n")
        put(cfg, "agents/code-high.md", "the user's own\n")
        r = run(root, home, cfg)
        check("a file with the marker and no backup is overwritten without one", not os.path.exists(os.path.join(a, "code-low.md.before-agent-fabric")), r.stdout)
        check("an unmarked file is kept aside, and the run says so",
              read(os.path.join(a, "code-high.md.before-agent-fabric")) == "the user's own\n"
              and f"(kept the previous file as {os.path.join(a, 'code-high.md.before-agent-fabric')})" in r.stdout, r.stdout)
        root, home, cfg = fixture()
        put(cfg, "agents/code-high.md", "the user's own\n")
        run(root, home, cfg, "--dry-run")
        check("a dry run writes and backs up nothing",
              read(os.path.join(cfg, "agents", "code-high.md")) == "the user's own\n"
              and not os.path.exists(os.path.join(cfg, "agents", "code-high.md.before-agent-fabric")))

        # The retired blind-reviewer.md: removed by the marker, counted, said; dry run touches nothing.
        root, home, cfg = fixture()
        old = os.path.join(cfg, "agents", "blind-reviewer.md")
        put(cfg, "agents/blind-reviewer.md", "a reviewer from agent-fabric\n")
        r = run(root, home, cfg, "--dry-run")
        check("dry run: the retired reviewer is named and stays",
              os.path.exists(old) and f"  -  {old} (would remove: retired name of code-review)" in r.stdout, r.stdout)
        r = run(root, home, cfg)
        check("the retired reviewer carrying the marker is removed, said and counted",
              not os.path.exists(old) and f"  -  {old} (retired name of code-review)" in r.stdout
              and r.stdout.splitlines()[-1] == "agent files (anthropic): 6 written, 0 already current.", r.stdout)
        put(cfg, "agents/blind-reviewer.md", "the user's own reviewer\n")
        run(root, home, cfg)
        check("a blind-reviewer.md without the marker is left", os.path.exists(old))

        # The locale worker's removal is counted too.
        root, home, cfg = fixture()
        w = os.path.join(cfg, "agents", "locale-worker.md")
        put(cfg, "agents/locale-worker.md", "(agent-fabric)\n")
        r = run(root, home, cfg)
        check("a removed worker counts as written", not os.path.exists(w) and r.stdout.splitlines()[-1] == "agent files (anthropic): 6 written, 0 already current.", r.stdout)
        check("…and the reason says the role is unbound when identity.py gives none", "role is unbound" in r.stdout, r.stdout)

        # A routing failure writes nothing and says which subcommand.
        for sub in ("pins", "efforts"):
            root, home, cfg = fixture()
            put(root, f"tools/fabric/fail-{sub}", "")
            r = run(root, home, cfg)
            check(f"routing {sub} failing: exit 1, named, nothing written",
                  r.returncode == 1 and f"routing.py {sub} failed" in r.stderr and not os.path.exists(os.path.join(cfg, "agents")), r.stderr)

        # A missing class source is an error, not a traceback.
        root, home, cfg = fixture()
        os.unlink(os.path.join(root, "runtime", "claude-code", "agents", "code-plan.md"))
        r = run(root, home, cfg)
        check("a missing class source exits 1 naming it", r.returncode == 1 and "code-plan.md" in r.stderr and "Traceback" not in r.stderr, r.stderr)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print("test_install_agent_files:", "FAILED" if fails else "OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
