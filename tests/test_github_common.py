#!/usr/bin/env python3
"""tools/fabric/github/common.py: how a body is read from stdin and where a
project's own tool config is found. The tools' CLI suites cover both through
the tools; these cases pin the helpers' own edges."""
from __future__ import annotations

import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import common, local  # noqa: E402
import roots  # noqa: E402
import workingcopy  # noqa: E402


class FakeStdin:
    def __init__(self, data: bytes, tty: bool = False):
        self.buffer = io.BytesIO(data)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("read_body")
    real_stdin = sys.stdin
    try:
        sys.stdin = FakeStdin("a\nb\n\n".encode())
        check("bytes decoded, a trailing blank line kept", common.read_body() == "a\nb\n\n")
        sys.stdin = FakeStdin(b"bad \xff byte")
        check("invalid UTF-8 becomes U+FFFD, never a lone surrogate", common.read_body() == "bad � byte")
        sys.stdin = FakeStdin(b"text", tty=True)
        check("a terminal is no body: None, and nothing read", common.read_body() is None)
        sys.stdin = FakeStdin(b"")
        check("an empty pipe is an empty body, not None", common.read_body() == "")
    finally:
        sys.stdin = real_stdin

    print("project_config_path")
    saved = {k: os.environ.pop(k, None) for k in ("T_CFG",)}
    real = (local.toplevel, workingcopy.resolve, roots.project_integration)
    try:
        os.environ["T_CFG"] = "/explicit/x.json"
        local.toplevel = lambda: None
        check("the variable wins, even outside a working copy", common.project_config_path("T_CFG", "x.json") == "/explicit/x.json")
        del os.environ["T_CFG"]
        check("outside a working copy, no variable: empty", common.project_config_path("T_CFG", "x.json") == "")
        local.toplevel = lambda: "/wc"
        workingcopy.resolve = lambda top: {"project": "pid"}
        roots.project_integration = lambda pid, *parts: "/".join(("/proj", pid, *parts))
        check("a registered project: its integration/gh file, whether or not it exists",
              common.project_config_path("T_CFG", "x.json") == "/proj/pid/gh/x.json")
        workingcopy.resolve = lambda top: {}
        check("a working copy with no project: empty", common.project_config_path("T_CFG", "x.json") == "")

        def exits(top):
            raise SystemExit(2)
        workingcopy.resolve = exits
        check("a marker naming nothing the registry knows exits: empty, not an exit", common.project_config_path("T_CFG", "x.json") == "")
        os.environ["T_CFG"] = ""
        check("an empty variable is unset", common.project_config_path("T_CFG", "x.json") == "")
    finally:
        local.toplevel, workingcopy.resolve, roots.project_integration = real
        os.environ.pop("T_CFG", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    print("apply_project_env (pr-tools.json)")
    import json
    import tempfile
    with tempfile.TemporaryDirectory(prefix="test_github_common.") as tmp:
        cfg = os.path.join(tmp, "pr-tools.json")

        def write(doc) -> None:
            with open(cfg, "w", encoding="utf-8") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc))

        saved_cfg = os.environ.get(common.PR_TOOLS_SETTING)
        stubs = (local.toplevel, workingcopy.resolve, roots.project_integration)
        os.environ[common.PR_TOOLS_SETTING] = cfg
        full = {"description": "d", "env_aliases": {"T_THEIRS": "T_OURS", "T_OTHER": "T_OTHERS"},
                "legacy_review_markers": ["<!-- old v1 -->", "<!-- older v1 -->"]}
        try:
            write(full)
            env = {"T_THEIRS": "mine", "T_OTHER": "x", "T_OTHERS": "kept"}
            common.apply_project_env("t", env)
            check("an alias fills the fabric's name when it is unset", env["T_OURS"] == "mine")
            check("…and never overrides one that is set", env["T_OTHERS"] == "kept")
            check("legacy markers become the default, one per line",
                  env["AGENT_FABRIC_LEGACY_REVIEW_MARKERS"] == "<!-- old v1 -->\n<!-- older v1 -->")
            env = {"T_THEIRS": "mine", "T_OURS": "", "AGENT_FABRIC_LEGACY_REVIEW_MARKERS": ""}
            common.apply_project_env("t", env)
            check("an empty fabric name is unset, as bash's ${A:-$B} read it",
                  env["T_OURS"] == "mine" and env["AGENT_FABRIC_LEGACY_REVIEW_MARKERS"].startswith("<!-- old"))
            env = {"T_THEIRS": "", "AGENT_FABRIC_LEGACY_REVIEW_MARKERS": "<!-- mine -->"}
            common.apply_project_env("t", env)
            check("an empty project name sets nothing; a set marker list is kept",
                  "T_OURS" not in env and env["AGENT_FABRIC_LEGACY_REVIEW_MARKERS"] == "<!-- mine -->")
            os.remove(cfg)
            env = {"T_THEIRS": "mine"}
            err = io.StringIO()
            real_err, sys.stderr = sys.stderr, err
            try:
                common.apply_project_env("tool", env)
                code = None
            except SystemExit as e:
                code = e.code
            finally:
                sys.stderr = real_err
            check("a setting that names a missing file: exit 2, the tool and file named, nothing applied",
                  code == 2 and err.getvalue().startswith(f"tool: {cfg} is not a usable pr-tools.json")
                  and env == {"T_THEIRS": "mine"})
            del os.environ[common.PR_TOOLS_SETTING]
            local.toplevel = lambda: None
            common.apply_project_env("t", env)
            check("no setting and no project: neither aliases nor markers, and no complaint", env == {"T_THEIRS": "mine"})
            local.toplevel = lambda: "/wc"
            workingcopy.resolve = lambda top: {"project": "pid"}
            roots.project_integration = lambda pid, *parts: os.path.join(tmp, "absent", pid, *parts)
            err = io.StringIO()
            real_err, sys.stderr = sys.stderr, err
            try:
                common.apply_project_env("t", env)
                code = None
            except SystemExit as e:
                code = e.code
            finally:
                sys.stderr = real_err
            check("no setting, a registered project with no pr-tools.json: neither, silently (the usual case)",
                  code is None and err.getvalue() == "" and env == {"T_THEIRS": "mine"})
            os.environ[common.PR_TOOLS_SETTING] = cfg
            for label, bad in (("not JSON", "{"), ("not an object", "[]"), ("an unknown key", {"env_alias": {}}),
                               ("aliases not names", {"env_aliases": {"A B": "C"}}),
                               ("aliases not strings", {"env_aliases": {"A": 1}}),
                               ("markers not a list", {"legacy_review_markers": "x"}),
                               ("an empty marker", {"legacy_review_markers": [""]}),
                               ("a multi-line marker", {"legacy_review_markers": ["a\nb"]})):
                write(bad)
                env = {"T_THEIRS": "mine"}
                err = io.StringIO()
                real_err, sys.stderr = sys.stderr, err
                try:
                    common.apply_project_env("tool", env)
                    code = None
                except SystemExit as e:
                    code = e.code
                finally:
                    sys.stderr = real_err
                check(f"a file that is {label}: exit 2, the tool and file named, nothing applied",
                      code == 2 and err.getvalue().startswith(f"tool: {cfg} is not a usable pr-tools.json")
                      and env == {"T_THEIRS": "mine"})
        finally:
            local.toplevel, workingcopy.resolve, roots.project_integration = stubs
            if saved_cfg is None:
                os.environ.pop(common.PR_TOOLS_SETTING, None)
            else:
                os.environ[common.PR_TOOLS_SETTING] = saved_cfg

    print("the four commands that read the project's names ask for them first")
    from github import arm, post_review, pr_gate, pr_review_status
    asked: list[str] = []
    seen: list[tuple[str, int, list[str]]] = []
    real_apply, real_argv, real_out = common.apply_project_env, sys.argv, sys.stdout
    common.apply_project_env = lambda prog, environ=None: asked.append(prog)
    try:
        for prog, call in (("pr-gate", pr_gate.main), ("pr-review-status", pr_review_status.main),
                           ("post-review", post_review.main), ("arm", lambda: arm.main(["--help"]))):
            sys.argv, sys.stdout = [prog, "--help"], io.StringIO()
            asked.clear()
            rc = call()
            seen.append((prog, rc, list(asked)))
    finally:
        common.apply_project_env, sys.argv, sys.stdout = real_apply, real_argv, real_out
    for prog, rc, names in seen:
        check(f"{prog} --help: exit 0, and it asked under {prog!r} (got {rc}, {names})", rc == 0 and names == [prog])

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
