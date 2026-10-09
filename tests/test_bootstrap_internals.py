#!/usr/bin/env python3
"""Tests for tools/fabric/bootstrap.py's internals; the behaviour is
tests/test_bootstrap_cli.py's, run against the shim (ADR-040 §5 rule 5).
What that oracle cannot reach is here, each the case a mutant of the module
survived it with: the workspace settings that are JSON but not an object,
step 3 in a dry run, a failing agent-files install, the checkout itself
among the working copies, git's own answer for a work tree, a bus that is
not a socket, the runtime directory's default, the relay holder's
lookup, and the control agent's implementation (runtime/control/agentd.json;
the oracle's fixture keeps every login on node).

Hermetic: the environment is rebuilt from nothing — HOME, the XDG
directories, CLAUDE_CONFIG_DIR and PATH in one scratch directory, PATH
holding fakes of systemctl, ss, pgrep and curl in front of /usr/bin:/bin —
and restored after each case. Nothing runs bootstrap as a whole.

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The module beside the script under test, as the oracle finds it ($BOOTSTRAP,
# default runtime/claude-code/bootstrap.sh): a mutant's tree is tested the same way.
SCRIPT = os.path.abspath(os.environ.get("BOOTSTRAP") or os.path.join(HERE, "runtime", "claude-code", "bootstrap.sh"))
MODULE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT))), "tools", "fabric")
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, MODULE_DIR)
import bootstrap  # noqa: E402

fails = 0


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
    else:
        fails += 1
        print(f"  FAIL {label}")
        for line in str(detail).splitlines():
            print(f"      {line}")


def put(path: str, content: str, mode: int | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if mode is not None:
        os.chmod(path, mode)


def git(*args: str) -> None:
    subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.org", "-c",
                    "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                   check=True, capture_output=True, env=os.environ.copy())


class Scratch:
    """One scratch account; os.environ is its environment until close()."""

    def __init__(self, T: str, name: str) -> None:
        self.root = os.path.join(T, name)
        self.home = os.path.join(self.root, "home")
        self.fake = os.path.join(self.root, "fakebin")
        self.log = os.path.join(self.root, "fake.log")
        os.makedirs(self.home)
        os.makedirs(self.fake)
        open(self.log, "w").close()
        for tool in ("systemctl", "ss", "pgrep", "curl"):
            # Each fake logs its argv, prints $FAKE_<TOOL>_OUT and exits $FAKE_<TOOL>_RC.
            put(os.path.join(self.fake, tool),
                "#!/bin/sh\n"
                f'echo "{tool} $*" >>"$FAKE_LOG"\n'
                f'[ -n "${{FAKE_{tool.upper()}_OUT:-}}" ] && printf "%s\\n" "$FAKE_{tool.upper()}_OUT"\n'
                f'exit "${{FAKE_{tool.upper()}_RC:-0}}"\n', 0o755)
        self.saved = dict(os.environ)
        os.environ.clear()
        os.environ.update({
            "HOME": self.home, "PATH": f"{self.fake}:/usr/bin:/bin", "LC_ALL": "C.UTF-8",
            "CLAUDE_CONFIG_DIR": os.path.join(self.root, "claude-config"),
            "XDG_CONFIG_HOME": os.path.join(self.root, "xdg-config"),
            "XDG_RUNTIME_DIR": os.path.join(self.root, "run"),
            "XDG_STATE_HOME": os.path.join(self.root, "state"),
            "GIT_CONFIG_NOSYSTEM": "1", "FAKE_LOG": self.log,
        })
        os.makedirs(os.environ["XDG_RUNTIME_DIR"])

    def calls(self) -> list[str]:
        with open(self.log, encoding="utf-8") as f:
            return f.read().splitlines()

    def close(self) -> None:
        os.environ.clear()
        os.environ.update(self.saved)


def quiet(fn, *args):
    """fn(*args) with its stdout and stderr captured: (result or the Stop, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            result = fn(*args)
        except bootstrap.Stop as s:
            result = s
    return result, out.getvalue(), err.getvalue()


def fabric(s: Scratch, remote: str | None = None) -> tuple[str, str]:
    """A workspace with a fabric checkout in it: the files the steps read."""
    projects = os.path.join(s.home, "projects")
    root = os.path.join(projects, "agent-fabric")
    os.makedirs(os.path.join(root, "runtime", "claude-code", "workspace"))
    shutil.copyfile(os.path.join(HERE, "runtime", "claude-code", "workspace", "settings.json"),
                    os.path.join(root, "runtime", "claude-code", "workspace", "settings.json"))
    put(os.path.join(root, "projects", "registry.json"), json.dumps({"version": 1, "projects": {
        "agent-fabric": {"remotes": ["git@github.com:example-org/agent-fabric.git"]},
        "alpha": {"remotes": ["git@github.com:example-org/alpha.git"]}}}))
    git("init", "-q", root)
    if remote:
        git("-C", root, "remote", "add", "origin", remote)
    return projects, root


def workspace_settings_not_an_object(T: str) -> None:
    print("step 2: workspace settings that are JSON but not an object")
    check("merge: a list is refused", _raises(lambda: bootstrap.merge_workspace_settings(
        {"statusLine": {}, "hooks": {}}, "/r", [1])))
    check("merge: hooks that are not an object are refused", _raises(lambda: bootstrap.merge_workspace_settings(
        {"statusLine": {}, "hooks": {"SessionStart": []}}, "/r", {"hooks": []})))
    check("merge: null is an empty file", bootstrap.merge_workspace_settings(
        {"statusLine": 1, "hooks": {}}, "/r", None) == {"statusLine": 1, "hooks": {}})
    s = Scratch(T, "settings-list")
    try:
        projects, root = fabric(s)
        put(os.path.join(projects, ".claude", "settings.json"), "[1, 2]\n")
        r, out, err = quiet(bootstrap.Bootstrap(projects, False, root).workspace_settings)
        check("the run stops with exit 1 and one line naming the file, no traceback, nothing written",
              isinstance(r, bootstrap.Stop) and r.rc == 1 and "settings.json: not a JSON object" in r.message
              and open(os.path.join(projects, ".claude", "settings.json")).read() == "[1, 2]\n", (r, out, err))
    finally:
        s.close()


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def role_command_dry_run(T: str) -> None:
    print("step 3: the retired /role command in a dry run")
    s = Scratch(T, "role-dry")
    try:
        projects, root = fabric(s)
        role = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "commands", "role.md")
        put(role, "the agent-fabric /role command\n")
        b = bootstrap.Bootstrap(projects, True, root)
        r, out, _ = quiet(b.retire_role_command)
        check("kept, said as would remove, not counted",
              os.path.isfile(role) and out == f"  -  {role} (would remove: /role is retired, use fabric-role)\n"
              and b.changed == 0, out)
    finally:
        s.close()


def agent_files_failure(T: str) -> None:
    print("agent files: the installer's failure ends the run with its status")
    s = Scratch(T, "agent-files")
    try:
        projects, root = fabric(s)
        argv_file = os.path.join(s.root, "argv")
        put(os.path.join(root, "tools", "fabric", "install_agent_files.py"),
            f"import sys\nopen({argv_file!r}, 'w').write(' '.join(sys.argv[1:]))\nsys.exit(3)\n")
        r, out, _ = quiet(bootstrap.Bootstrap(projects, True, root).agent_files)
        check("exit 3, the checkout's installer run, the dry run passed on",
              isinstance(r, bootstrap.Stop) and r.rc == 3 and open(argv_file).read() == "--dry-run", (r, out))
    finally:
        s.close()


def commands_unreadable(T: str) -> None:
    print("links: an unreadable commands.json")
    s = Scratch(T, "commands")
    try:
        projects, root = fabric(s)
        put(os.path.join(root, "runtime", "claude-code", "commands.json"), "{broken\n")
        b = bootstrap.Bootstrap(projects, False, root)
        _, out, err = quiet(b.link_commands)
        check("one line on stderr, nothing linked, counted NOT written once",
              err == "  !  runtime/claude-code/commands.json unreadable — no command linked\n" and out == ""
              and b.failed == 1 and b.changed == 0, (out, err, b.failed))
        put(os.path.join(root, "runtime", "claude-code", "commands.json"), '{"commands": ["a"]}\n')
        b = bootstrap.Bootstrap(projects, False, root)
        _, out, err = quiet(b.link_commands)
        check("…and when `commands` is not an object", b.failed == 1 and "unreadable" in err, (out, err))
    finally:
        s.close()


def checkout_among_working_copies(T: str) -> None:
    print("step 5: the checkout itself is not one of the working copies")
    s = Scratch(T, "checkout")
    try:
        projects, root = fabric(s, remote="git@github.com:example-org/agent-fabric.git")
        alpha = os.path.join(projects, "alpha")
        git("init", "-q", alpha)
        git("-C", alpha, "remote", "add", "origin", "git@github.com:example-org/alpha.git")
        b = bootstrap.Bootstrap(projects, True, root)
        trusted, out, err = quiet(b.working_copy_hooks)
        check("only alpha said; the checkout, registered by its remote, left to step 4",
              out == f"  +  {alpha} (alpha): core.hooksPath = {root}/policies/githooks\n" and err == "", out + err)
        check("…and trusted once, as the checkout", trusted == [projects, root, alpha], trusted)
    finally:
        s.close()


def moved_origin_repointed(T: str) -> None:
    print("step 5a: an origin naming a moved_from remote takes the current one")
    s = Scratch(T, "moved")
    try:
        projects, root = fabric(s, remote="git@github.com:old-org/agent-fabric.git")
        put(os.path.join(root, "projects", "registry.json"), json.dumps({"version": 1, "projects": {
            "agent-fabric": {"remotes": ["git@github.com:new-org/agent-fabric.git", "https://github.com/new-org/agent-fabric",
                                         "git@github.com:old-org/agent-fabric.git", "https://github.com/old-org/agent-fabric"],
                             "moved_from": ["git@github.com:old-org/agent-fabric.git", "https://github.com/old-org/agent-fabric"]},
            "alpha": {"remotes": ["git@github.com:new-org/alpha.git", "https://github.com/new-org/alpha",
                                  "https://github.com/Old-Org/alpha"],
                      "moved_from": ["https://github.com/Old-Org/alpha"]},
            "beta": {"remotes": ["git@github.com:example-org/beta.git", "git@github.com:someone/beta.git"]}}}))
        alpha, beta = os.path.join(projects, "alpha"), os.path.join(projects, "beta")
        for wc, url in ((alpha, "https://github.com/old-org/ALPHA.git"), (beta, "git@github.com:someone/beta.git")):
            git("init", "-q", wc)
            git("-C", wc, "remote", "add", "origin", url)
        origin = lambda wc: subprocess.run(["git", "-C", wc, "config", "--get", "remote.origin.url"],
                                           capture_output=True, text=True).stdout.strip()
        b = bootstrap.Bootstrap(projects, True, root)
        _, out, _ = quiet(b.working_copy_hooks)
        check("a dry run says both re-points and writes neither",
              "origin git@github.com:old-org/agent-fabric.git -> git@github.com:new-org/agent-fabric.git (moved)" in out
              and "origin https://github.com/old-org/ALPHA.git -> https://github.com/new-org/alpha (moved)" in out
              and origin(root) == "git@github.com:old-org/agent-fabric.git", out)
        b = bootstrap.Bootstrap(projects, False, root)
        _, out, _ = quiet(b.working_copy_hooks)
        check("the checkout and a working copy follow, each keeping its scheme; case does not hide a move",
              origin(root) == "git@github.com:new-org/agent-fabric.git" and origin(alpha) == "https://github.com/new-org/alpha",
              (origin(root), origin(alpha)))
        check("a second listed remote that is not moved_from is left alone",
              origin(beta) == "git@github.com:someone/beta.git", origin(beta))
        b = bootstrap.Bootstrap(projects, False, root)
        _, out, _ = quiet(b.working_copy_hooks)
        check("a second run re-points nothing", "(moved)" not in out, out)
        # One copy that cannot be re-pointed is that copy's failure, and the others go on.
        gamma = os.path.join(projects, "gamma")
        git("init", "-q", gamma)
        git("-C", gamma, "remote", "add", "origin", "https://github.com/Old-Org/alpha")
        git("-C", gamma, "config", "--add", "remote.origin.url", "https://github.com/Old-Org/alpha")
        git("-C", alpha, "remote", "set-url", "origin", "https://github.com/Old-Org/alpha")
        b = bootstrap.Bootstrap(projects, False, root)
        _, out, err = quiet(b.working_copy_hooks)
        check("…said on stderr, counted, and the copy beside it still re-pointed",
              "origin not re-pointed" in err and b.failed == 1 and origin(alpha) == "https://github.com/new-org/alpha", (out, err, b.failed))
        # No current remote of the origin's scheme: left as it is, never switched to the other scheme.
        git("-C", alpha, "remote", "set-url", "origin", "git@github.com:Old-Org/alpha.git")
        put(os.path.join(root, "projects", "registry.json"), json.dumps({"version": 1, "projects": {
            "agent-fabric": {"remotes": ["git@github.com:new-org/agent-fabric.git"]},
            "alpha": {"remotes": ["https://github.com/new-org/alpha", "git@github.com:Old-Org/alpha.git"],
                      "moved_from": ["git@github.com:Old-Org/alpha.git"]}}}))
        b = bootstrap.Bootstrap(projects, False, root)
        _, out, err = quiet(b.working_copy_hooks)
        check("…no other scheme put in its place: left, said and counted",
              origin(alpha) == "git@github.com:Old-Org/alpha.git" and "no current ssh remote" in err and b.failed >= 1,
              (origin(alpha), err))
    finally:
        s.close()


def work_tree_answer(T: str) -> None:
    print("step 5: git's own answer for a work tree")
    s = Scratch(T, "worktree")
    try:
        projects, root = fabric(s)
        plain, bare = os.path.join(projects, "plain"), os.path.join(projects, "bare.git")
        os.makedirs(plain)
        git("init", "-q", "--bare", bare)
        b = bootstrap.Bootstrap(projects, True, root)
        check("a plain directory outside any repository is not one", b.is_work_tree(plain) is False)
        check("a bare repository is not one", b.is_work_tree(bare) is False)
        check("a checkout is one", b.is_work_tree(root) is True)
    finally:
        s.close()


def user_manager(T: str) -> None:
    print("step 6: the user manager")
    s = Scratch(T, "manager")
    try:
        projects, root = fabric(s)
        put(os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus"), "not a socket\n")
        b = bootstrap.Bootstrap(projects, False, root)
        check("a bus that is a regular file is no manager, and systemctl is never asked",
              b.user_manager() is False and s.calls() == [], s.calls())
        del os.environ["XDG_RUNTIME_DIR"]
        os.environ["FAKE_SYSTEMCTL_RC"] = "1"
        b.user_manager()
        check("XDG_RUNTIME_DIR unset: set to /run/user/<euid> for what runs after",
              os.environ.get("XDG_RUNTIME_DIR") == f"/run/user/{os.geteuid()}", os.environ.get("XDG_RUNTIME_DIR"))
        os.environ["XDG_RUNTIME_DIR"] = ""
        b.user_manager()
        check("…and when it is empty", os.environ.get("XDG_RUNTIME_DIR") == f"/run/user/{os.geteuid()}")
    finally:
        s.close()


def relay_holder(T: str) -> None:
    print("step 6b: who holds the relay's port")
    s = Scratch(T, "holder")
    try:
        os.environ["FAKE_SS_OUT"] = 'LISTEN 0 5 127.0.0.1:8765 0.0.0.0:* users:(("claude-bridge",pid=4242,fd=3))'
        check("ss's pid, pgrep not asked", bootstrap.relay_holder(1234) == "4242" and not any(
            c.startswith("pgrep") for c in s.calls()), s.calls())
        open(s.log, "w").close()
        os.environ["FAKE_SS_OUT"] = 'users:(("claude-bridge",pid=,fd=3))'
        os.environ["FAKE_PGREP_OUT"] = "777\n778"
        check("a pid= with no digits: the first pgrep line, by uid and exact name",
              bootstrap.relay_holder(1234) == "777" and "pgrep -u 1234 -x claude-bridge" in s.calls(), s.calls())
        os.environ["FAKE_PGREP_OUT"] = ""
        os.environ["FAKE_PGREP_RC"] = "1"
        check("nothing names it: empty", bootstrap.relay_holder(1234) == "")
    finally:
        s.close()


def glob_order(T: str) -> None:
    print("step 5: the working copies' order")
    s = Scratch(T, "order")
    try:
        check("the glob's slash sorts alpha-wt before alpha in C",
              bootstrap.glob_order(["beta", "alpha", "alpha-wt"]) == ["alpha-wt", "alpha", "beta"])
    finally:
        s.close()


def journal_bound(T: str) -> None:
    print("step 9: the journal's import is bounded")
    s = Scratch(T, "journal")
    try:
        projects, root = fabric(s)
        put(os.path.join(root, "tools", "fabric", "episodic.py"), "import time\ntime.sleep(30)\n")
        saved = bootstrap.JOURNAL_IMPORT_TIMEOUT
        bootstrap.JOURNAL_IMPORT_TIMEOUT = 1
        try:
            t0 = time.monotonic()
            _, out, err = quiet(bootstrap.Bootstrap(projects, False, root).journal_import)
            took = time.monotonic() - t0
        finally:
            bootstrap.JOURNAL_IMPORT_TIMEOUT = saved
        check("an import that hangs is stopped at the bound, said in one line, and the run goes on",
              took < 10 and out == "  !  episodic journal: the import did not finish in 1 s; the next bootstrap tries again\n"
              and not err, (round(took, 1), out, err))
        check("the bound is 20 s: within the 30 s moveto's enter gives all of bootstrap",
              bootstrap.JOURNAL_IMPORT_TIMEOUT == 20)
    finally:
        s.close()


def agentd_selector(T: str) -> None:
    print("step 6: the control agent's implementation, from runtime/control/agentd.json")
    import agentd_unit
    me = bootstrap.login()
    template = open(os.path.join(HERE, "runtime", "control", f"{bootstrap.UNIT}.service"), "rb").read()
    node_line = "ExecStart=/usr/bin/env node %h/projects/agent-fabric/runtime/control/agentd.mjs"
    check("the fabric's unit is today's Node line", node_line in template.decode().splitlines())
    saved_python = agentd_unit.FABRIC_PYTHON

    import socket
    here = socket.gethostname().split(".")[0]

    def account(name: str, selector: str | None, placed: str | None = here) -> tuple[Scratch, str, str]:
        s = Scratch(T, name)
        projects, root = fabric(s)
        if placed is not None:
            put(os.path.join(root, "runtime", "hosts", "registry.json"),
                json.dumps({"version": 1, "placement": {me: placed}}))
        put(os.path.join(root, "runtime", "control", f"{bootstrap.UNIT}.service"), template.decode())
        if selector is not None:
            put(os.path.join(root, "runtime", "control", "agentd.json"), selector)
        return s, projects, root

    def unit_path() -> str:
        return os.path.join(os.environ["XDG_CONFIG_HOME"], "systemd", "user", f"{bootstrap.UNIT}.service")

    # A stand-in for the pinned interpreter, so the case holds on a host
    # without one; the unit must still name the fixed path, never this one.
    fake_python = os.path.join(T, "fabric-python")
    put(fake_python, "#!/bin/sh\nexit 0\n", 0o755)
    agentd_unit.FABRIC_PYTHON = fake_python
    try:
        s, projects, root = account("agentd-node", json.dumps({"default": "node", "python": ["someone-else"]}))
        try:
            b = bootstrap.Bootstrap(projects, False, root)
            _, out, err = quiet(b.control_agent)
            check("the default: the Node unit byte for byte, nothing more said, nothing failed",
                  open(unit_path(), "rb").read() == template and "runs" not in out and not err and b.failed == 0,
                  (out, err))
            b = bootstrap.Bootstrap(projects, True, root)
            _, out, _ = quiet(b.control_agent)
            check("a dry run says node", f"  *  {bootstrap.UNIT}.service runs node (runtime/control/agentd.json)\n" in out, out)
        finally:
            s.close()

        s, projects, root = account("agentd-python", json.dumps({"default": "node", "python": [me]}))
        try:
            b = bootstrap.Bootstrap(projects, True, root)
            _, out, _ = quiet(b.control_agent)
            check("a dry run says python, and writes nothing",
                  f"  *  {bootstrap.UNIT}.service runs python (runtime/control/agentd.json)\n" in out
                  and not os.path.exists(unit_path()), out)
            b = bootstrap.Bootstrap(projects, False, root)
            _, out, err = quiet(b.control_agent)
            got = open(unit_path(), encoding="utf-8").read().splitlines()
            want = [("ExecStart=/usr/local/bin/fabric-python %h/projects/agent-fabric/tools/fabric/control/agentd.py"
                     if line == node_line else line) for line in template.decode().splitlines()]
            check("a listed login: the pinned interpreter's fixed path runs agentd.py, every other line the Node unit's",
                  got == want and b.failed == 0 and not err, "\n".join(got))
            check("…said in the run", f"  *  {bootstrap.UNIT}.service runs python (runtime/control/agentd.json)" in out, out)
            check("…and read back as python", agentd_unit.implementation_of("\n".join(got)) == "python")
            # The cutover itself: an account on the Node unit, a manager running.
            put(unit_path(), template.decode())
            import socket
            bus = socket.socket(socket.AF_UNIX)
            bus.bind(os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus"))
            try:
                b = bootstrap.Bootstrap(projects, False, root)
                quiet(b.control_agent)
            finally:
                bus.close()
            check("node to python is a changed unit: reloaded, then restarted",
                  s.calls() == ["systemctl --user daemon-reload", f"systemctl --user enable --now {bootstrap.UNIT}",
                                f"systemctl --user restart {bootstrap.UNIT}", f"systemctl --user is-active {bootstrap.UNIT}"],
                  s.calls())
            os.remove(os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus"))
            open(s.log, "w").close()
            agentd_unit.FABRIC_PYTHON = os.path.join(T, "no-such-python")
            os.remove(unit_path())
            put(unit_path(), template.decode())
            bus = socket.socket(socket.AF_UNIX)
            bus.bind(os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus"))
            try:
                b = bootstrap.Bootstrap(projects, False, root)
                _, out, err = quiet(b.control_agent)
            finally:
                bus.close()
            check("python with no pinned interpreter on the host: the Node unit written and enabled, one warning, not a failure",
                  open(unit_path(), "rb").read() == template and b.failed == 0 and "is not executable" in err
                  and err.count("\n") == 1 and "python not used" in err
                  and f"systemctl --user enable --now {bootstrap.UNIT}" in s.calls(), (out, err, s.calls()))
            agentd_unit.FABRIC_PYTHON = fake_python
        finally:
            s.close()

        for name, selector, why in (
                ("agentd-absent", None, "unreadable"),
                ("agentd-broken", "{broken\n", "is not JSON"),
                ("agentd-key", json.dumps({"default": "node", "python": [], "deno": []}), "unknown key 'deno'"),
                ("agentd-default", json.dumps({"default": "deno", "python": []}), "default is 'deno'"),
                ("agentd-list", json.dumps({"default": "node", "python": me}), "python is not a list")):
            s, projects, root = account(name, selector)
            try:
                b = bootstrap.Bootstrap(projects, False, root)
                _, out, err = quiet(b.control_agent)
                check(f"a selector {why}: the Node unit written, one warning on stderr, not a failure",
                      open(unit_path(), "rb").read() == template and b.failed == 0
                      and why in err and err.count("\n") == 1 and "python not used" in err and "runs python" not in out, (out, err))
            finally:
                s.close()

        # Placement: a listed login whose registry entry names another host
        # (or none) is not that host's account.
        for name, placed in (("agentd-elsewhere", "some-other-host"), ("agentd-unplaced", None)):
            s, projects, root = account(name, json.dumps({"default": "node", "python": [me]}), placed)
            try:
                if placed is None:
                    put(os.path.join(root, "runtime", "hosts", "registry.json"), json.dumps({"version": 1, "placement": {}}))
                put(unit_path(), "[Unit]\nDescription=what the account had\n")
                b = bootstrap.Bootstrap(projects, False, root)
                _, out, err = quiet(b.control_agent)
                check(f"a listed login not placed on this host ({name}): the Node unit written, one warning naming the placement, not a failure",
                      open(unit_path(), "rb").read() == template and b.failed == 0
                      and "python not used" in err and "placed on" in err and err.count("\n") == 1
                      and "runs python" not in out, (out, err))
            finally:
                s.close()

        # A template the python swap cannot read falls back to Node with one
        # warning; the template is written as it is, as every account had it.
        bad_templates = (
            ("agentd-no-execstart", b"[Unit]\nDescription=x\n", "0 ExecStart lines"),
            ("agentd-two-execstart", b"[Service]\nExecStart=/a\nExecStart=/b\n", "2 ExecStart lines"),
            ("agentd-not-utf8", b"[Service]\nExecStart=/a\n# \xff\xfe\n", "utf-8"))
        for name, body, why in bad_templates:
            s, projects, root = account(name, json.dumps({"default": "node", "python": [me]}))
            try:
                with open(os.path.join(root, "runtime", "control", f"{bootstrap.UNIT}.service"), "wb") as fh:
                    fh.write(body)
                b = bootstrap.Bootstrap(projects, False, root)
                _, out, err = quiet(b.control_agent)
                check(f"a template with {why}: the Node unit written, one warning, no traceback, not a failure",
                      open(unit_path(), "rb").read() == body and b.failed == 0
                      and "python not used" in err and why in err and err.count("\n") == 1
                      and "Traceback" not in err and "runs python" not in out, (out, err))
            finally:
                s.close()

        # The placement check also covers an unlisted login when the default is python.
        for name, placed in (("agentd-default-python-elsewhere", "some-other-host"),
                             ("agentd-default-python-here", here)):
            s, projects, root = account(name, json.dumps({"default": "python", "python": []}), placed)
            try:
                b = bootstrap.Bootstrap(projects, False, root)
                _, out, err = quiet(b.control_agent)
                if placed == here:
                    check("default python, unlisted login placed here: python runs",
                          "runs python" in out and not err and b.failed == 0, (out, err))
                else:
                    check("default python, unlisted login placed elsewhere: the Node unit, one warning naming the placement",
                          open(unit_path(), "rb").read() == template and b.failed == 0
                          and "python not used" in err and "placed on" in err and err.count("\n") == 1
                          and "runs python" not in out, (out, err))
            finally:
                s.close()

        # The fallback unit is enabled all the same.
        s, projects, root = account("agentd-elsewhere-enabled", json.dumps({"default": "node", "python": [me]}), "some-other-host")
        try:
            bus = socket.socket(socket.AF_UNIX)
            bus.bind(os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus"))
            try:
                b = bootstrap.Bootstrap(projects, False, root)
                _, out, err = quiet(b.control_agent)
            finally:
                bus.close()
            check("…and enabled --now as today",
                  f"systemctl --user enable --now {bootstrap.UNIT}" in s.calls() and b.failed == 0, s.calls())
        finally:
            s.close()
    finally:
        agentd_unit.FABRIC_PYTHON = saved_python

    check("the selector's shape: a sound one has no problems",
          agentd_unit.problems({"description": "d", "default": "python", "python": ["a", "b"]}) == [])
    check("…a login named twice is one",
          agentd_unit.problems({"default": "node", "python": ["a", "a"]}) == ["python names a login twice"])
    check("…the default is required", agentd_unit.problems({"python": []}) == ["default is None; it is node or python"])
    check("an installed unit read back: node, python, or neither",
          agentd_unit.implementation_of(template.decode()) == "node"
          and agentd_unit.implementation_of("[Service]\nExecStart=/bin/true\n") is None)


def main() -> int:
    T = os.path.realpath(tempfile.mkdtemp(prefix="test_bootstrap_internals."))
    try:
        for case in (glob_order, workspace_settings_not_an_object, role_command_dry_run, agent_files_failure,
                     commands_unreadable,
                     checkout_among_working_copies, moved_origin_repointed, work_tree_answer, user_manager, relay_holder, journal_bound,
                     agentd_selector):
            case(T)
    finally:
        shutil.rmtree(T, ignore_errors=True)
    if fails:
        print(f"test_bootstrap_internals: {fails} FAILED")
        return 1
    print("test_bootstrap_internals: all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
