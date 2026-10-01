#!/usr/bin/env python3
"""Tests for tools/fabric/guards/ban_generated_by_attribution.py's
internals; the behaviour is policies/test_ban_generated_by_attribution.sh's,
run against the shim (ADR-040 §5 rule 5)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import git  # noqa: E402
from guards import ban_generated_by_attribution as guard  # noqa: E402

MODULE = os.path.join(HERE, "tools", "fabric", "guards", "ban_generated_by_attribution.py")
# No global config: a signing key or a hook of the account running this
# must not reach the fixture's commits.
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def sh(repo: str, *args: str, msg: bytes | None = None) -> str:
    r = subprocess.run(["git", "-C", repo, *args], input=msg, capture_output=True, env=GIT_ENV, check=True)
    return r.stdout.decode().strip()


def commit(repo: str, message: bytes) -> str:
    sh(repo, "commit", "-q", "--allow-empty", "-F", "-", msg=message)
    return sh(repo, "rev-parse", "HEAD")


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("the trailer shape")
    for text, want in (
        ("Co-authored-by: A <a@x>", True), ("  \tClaude-Session: x", True), ("CO-AUTHORED-BY:x", True),
        ("body\n\nco-authored-by: A", True), ("body\r\nClaude-Session:x\r\n", True),
        ("do not add a Co-authored-by: trailer", False), ("Co-authored-by", False),
        ("x Claude-Session: y", False), ("Co-authored-by-x: y", False),
        ("Co-authored-by\n: y", False), ("-Co-authored-by: y", False), ("", False),
    ):
        check(repr(text), guard.has_trailer(text) is want)

    print("the footer shape, wrapped or not")
    for text, want in (
        ("Generated with [Claude Code](https://x)", True), ("Generated with\n[Claude Code](x)", True),
        ("generated WITH \r\n  [claude code]", True), ("see https://claude.ai/code/session_01", True),
        ("Generated with Claude Code", False), ("Generated with [Other](x)", False),
        ("Generatedwith [Claude Code]", False), ("claude.ai/code/sessions", False),
    ):
        check(repr(text), guard.has_footer(text) is want)

    print("jq's paths and alternatives")
    check("null propagates", guard.jq_path({"a": None}, "a", "b", "c") is None)
    check("a missing key is null", guard.jq_path({}, "a", "b") is None)
    for bad in ("s", 5, [1], True):
        try:
            guard.jq_path({"a": bad}, "a", "b")
            check(f"indexing {bad!r} is an error", False)
        except ValueError:
            check(f"indexing {bad!r} is an error", True)
    check("false and null are skipped", guard.first_present({"x": False, "y": None, "z": "v"}, ("x",), ("y",), ("z",)) == "v")
    check("the first present wins", guard.first_present({"x": "1", "y": "2"}, ("x",), ("y",)) == "1")
    check("nothing present is empty", guard.first_present({}, ("x",), ("y",)) == "")
    check("an empty string is present, and empty", guard.first_present({"x": "", "y": "2"}, ("x",), ("y",)) == "")
    check("a non-string is its JSON", guard.first_present({"x": 5}, ("x",)) == "5")

    tmp = tempfile.mkdtemp(prefix="test-ban-attr-", dir=os.environ.get("TMPDIR") or None)
    cwd = os.getcwd()
    try:
        print("the payload is read as jq -e would")
        ev = os.path.join(tmp, "ev.json")
        for raw, want in ((b'{"a":1}', {"a": 1}), (b"[]", []), (b"null", None), (b"false", None), (b"{", None), (b"", None)):
            with open(ev, "wb") as f:
                f.write(raw)
            check(f"{raw!r}", guard.load_payload(ev) == want)
        check("a directory", guard.load_payload(tmp) is None)
        check("a missing file", guard.load_payload(os.path.join(tmp, "nope")) is None)
        with open(ev, "wb") as f:
            f.write(b'{"pull_request":{"body":"\xff\xfe Claude-Session: x"}}')
        check("invalid UTF-8 is replaced, not refused", guard.load_payload(ev) is not None)

        print("the range")
        repo = os.path.join(tmp, "r")
        os.mkdir(repo)
        sh(repo, "-c", "init.defaultBranch=main", "init", "-q")
        sh(repo, "config", "user.email", "t@example.invalid")
        sh(repo, "config", "user.name", "test")
        sh(repo, "config", "commit.gpgsign", "false")
        base = commit(repo, b"base\n\nCo-authored-by: old <o@x>")
        sh(repo, "checkout", "-q", "-b", "topic")
        clean = commit(repo, b"feat: clean")
        os.chdir(repo)

        def write(doc) -> str:
            with open(ev, "w") as f:
                f.write(json.dumps(doc))
            return ev

        pr = {"pull_request": {"base": {"sha": base}, "head": {"sha": clean}, "body": "fine"}}
        check("a pull_request payload names both ends", guard.payload_range(write(pr)) == (base, clean))
        mg = {"merge_group": {"base_sha": base, "head_sha": clean}}
        check("a merge_group payload names both ends", guard.payload_range(write(mg)) == (base, clean))
        both = {**mg, "pull_request": {"base": {"sha": clean}, "head": {"sha": clean}}}
        check("pull_request wins over merge_group", guard.payload_range(write(both)) == (clean, clean))
        gone = "0123456789abcdef0123456789abcdef01234567"
        check("an end absent locally refuses to guess",
              guard.payload_range(write({"pull_request": {"base": {"sha": gone}, "head": {"sha": clean}}})) is None)
        check("a head that is not a commit refuses",
              guard.payload_range(write({"pull_request": {"base": {"sha": base}, "head": {"sha": base + "^{tree}"}}})) is None)
        check("one end only refuses", guard.payload_range(write({"merge_group": {"head_sha": clean}})) is None)
        check("a payload that is not an object refuses", guard.payload_range(write([1])) is None)
        check("an unset path refuses", guard.payload_range("") is None)
        check("an unreadable file refuses", guard.payload_range(os.path.join(tmp, "nope")) is None)

        check("the override comes first",
              guard.ref_range({"AGENT_FABRIC_ATTRIBUTION_BASE": base, "GITHUB_BASE_REF": "main"}) == (base, "HEAD"))
        check("a bad override falls through to main", guard.ref_range({"AGENT_FABRIC_ATTRIBUTION_BASE": "refs/nope"}) == ("main", "HEAD"))
        check("GITHUB_BASE_REF is tried as a bare name", guard.ref_range({"GITHUB_BASE_REF": "topic"}) == ("topic", "HEAD"))
        check("an empty GITHUB_BASE_REF is not origin/", guard.ref_range({"GITHUB_BASE_REF": ""}) == ("main", "HEAD"))
        check("an unknown GITHUB_BASE_REF falls through", guard.ref_range({"GITHUB_BASE_REF": "zz"}) == ("main", "HEAD"))
        sh(repo, "branch", "-m", "main", "trunk")
        check("no candidate resolves: None", guard.ref_range({}) is None)
        sh(repo, "branch", "-m", "trunk", "main")

        print("Unicode spaces, as CI's grep under C.UTF-8 (review of #72)")
        check("an ideographic space before the trailer", guard.has_trailer("x\n\u3000Co-authored-by: a"))
        check("an en space inside the footer", guard.has_footer("Generated with\u2002[Claude Code](u)"))
        check("a line break still ends the trailer's indent", not guard.has_trailer("x\n\nfoo Co-authored-by: a"))

        print("the verdict")
        env = {"AGENT_FABRIC_ATTRIBUTION_BASE": "main"}
        st, out, err = guard.check(env)
        check("clean: OK on stdout, exit 0",
              st == 0 and len(out) == 1 and out[0].startswith("ban_generated_by_attribution: OK — ") and not err)
        check("with no event, the OK line claims no description", out[0].endswith(
            "; no pull-request event, so no description to read."))
        empty_event = os.path.join(repo, "..", "event.json")
        with open(empty_event, "w") as f:
            f.write('{"pull_request": {"body": "clean"}}')
        st, out, err = guard.check(dict(env, GITHUB_EVENT_PATH=empty_event))
        check("with one, it names the description it read", st == 0 and out[0].endswith(
            "nor in the pull-request description."))
        with open(empty_event, "w") as f:
            f.write('{"merge_group": {"head_sha": "x", "base_sha": "y"}}')
        st, out, err = guard.check(dict(env, GITHUB_EVENT_PATH=empty_event))
        check("a merge_group event has no description, and says so", st == 0 and out[0].endswith(
            "; no pull-request event, so no description to read."))
        os.unlink(empty_event)

        commit(repo, b"feat: two\n\nClaude-Session: x\n\nGenerated with\n[Claude Code](u)")
        st, out, err = guard.check(env)
        check("a trailer and a footer: exit 1, nothing on stdout", st == 1 and not out)
        check("FAIL is first on stderr", err[0] == "ban_generated_by_attribution: FAIL")
        check("the commit is named once per shape", sum(l.startswith("  commit ") and "feat: two" in l for l in err) == 2)
        check("each shape has its line",
              "      carries a banned attribution trailer" in err
              and "      carries generated-with attribution or a session URL" in err)
        check("the explanation follows a blank line",
              "" in err and any("git rebase -i <base>" in l for l in err) and err[-1].endswith("reword it."))

        # The offender above is in the range; a commit after it whose message
        # cannot be read must not take its offence away (review of #72).
        later = commit(repo, b"feat: three, clean")
        real_run = guard.git.run

        def failing(repo_, *args, **kw):
            if args[:1] == ("log",) and later in args:
                raise git.GitError("git log", "no answer within 120 s")
            return real_run(repo_, *args, **kw)
        guard.git.run = failing
        try:
            st, out, err = guard.check(env)
        finally:
            guard.git.run = real_run
        check("an unreadable later commit keeps the earlier offence: exit 1",
              st == 1 and any("feat: two" in l for l in err))

        # The offender's own subject unreadable: its offence stays, by sha.

        def no_subject(repo_, *args, **kw):
            if args[:1] == ("log",) and "--format=%s" in args:
                raise git.GitError("git log", "no answer within 120 s")
            return real_run(repo_, *args, **kw)
        guard.git.run = no_subject
        try:
            st, out, err = guard.check(env)
        finally:
            guard.git.run = real_run
        check("an unreadable subject keeps its commit's offence: exit 1",
              st == 1 and any("(subject unreadable)" in l for l in err))

        commit(repo, b"feat: three")
        st, out, err = guard.check(env)
        check("an offender below the tip is found", st == 1 and sum("feat: two" in l for l in err) == 2)
        sh(repo, "reset", "-q", "--hard", "HEAD~1")

        st, out, err = guard.check({"AGENT_FABRIC_ATTRIBUTION_BASE": "HEAD"})
        check("an empty range is enforced and clean", st == 0 and out[0].startswith("ban_generated_by_attribution: OK"))

        sh(repo, "reset", "-q", "--hard", clean)
        commit(repo, b"feat: latin\n\nCo-authored-by: Andr\xe9 <a@x>")
        st, out, err = guard.check(env)
        check("a message that is not UTF-8 is still read", st == 1 and any("carries a banned attribution trailer" in l for l in err))
        commit(repo, b"sub\xe9ject\n\nClaude-Session: x")
        st, out, err = guard.check(env)
        check("a subject that is not UTF-8 is reported, not a crash", st == 1)
        sh(repo, "reset", "-q", "--hard", clean)

        print("a failure to read is never a pass")
        real = git.run

        def failing(what: str):
            def fake(repo_, *args, **kw):
                if args and args[0] == what:
                    if kw.get("check", True):
                        raise git.GitError(f"git {what}", "boom")
                    return subprocess.CompletedProcess(args, 128, "", f"fatal: {what}: boom")
                return real(repo_, *args, **kw)
            return fake

        def with_git(fake):
            git.run = fake
            try:
                return guard.check(env)
            finally:
                git.run = real

        for what in ("rev-list", "log"):
            st, out, err = with_git(failing(what))
            check(f"git {what} failing: exit 0, NOT ENFORCED, never OK, the reason given",
                  st == 0 and any("NOT ENFORCED" in l for l in out) and not any("OK" in l for l in out)
                  and any("boom" in l for l in out))
        st, out, err = with_git(failing("rev-parse"))
        check("every candidate answering no: NOT ENFORCED, never OK", st == 0 and all("NOT ENFORCED" in l for l in out) and out)

        def missing(repo_, *args, **kw):
            raise git.GitError("git " + args[0], "git is not installed")
        st, out, err = with_git(missing)
        check("git missing: NOT ENFORCED naming it", st == 0 and any("git is not installed" in l for l in out))

        print("the description half")

        def with_payload(text: str):
            with open(ev, "w") as f:
                f.write(text)
            return guard.check({**env, "GITHUB_EVENT_PATH": ev})

        st, out, err = with_payload(json.dumps({"pull_request": {"body": "Generated with [Claude Code](u)"}}))
        check("a footer in the body fails and names the description",
              st == 1 and err[1] == "  the pull-request description carries generated-with attribution or a session URL")
        st, out, err = with_payload(json.dumps({"pull_request": {"body": "x\n  co-authored-by: a\nhttps://claude.ai/code/session_1"}}))
        check("both shapes in the body give two lines",
              st == 1 and err[1:3] == ["  the pull-request description carries a banned attribution trailer",
                                       "  the pull-request description carries generated-with attribution or a session URL"])
        for label, doc in (("no body", {"pull_request": {}}), ("a null body", {"pull_request": {"body": None}}),
                           ("an empty body", {"pull_request": {"body": ""}}), ("no pull_request", {"merge_group": {}}),
                           ("a string pull_request", {"pull_request": "x"}), ("an array payload", [1])):
            st, out, err = with_payload(json.dumps(doc))
            check(f"{label}: clean and enforced", st == 0 and out[0].startswith("ban_generated_by_attribution: OK") and not err)
        for label, text in (("null", "null"), ("false", "false"), ("garbage", "not json{"), ("empty", "")):
            st, out, err = with_payload(text)
            check(f"a payload that is {label} does not parse",
                  st == 0 and out == ["ban_generated_by_attribution: PR description: NOT ENFORCED — the event payload does not parse",
                                      "ban_generated_by_attribution: what could be checked was clean."])
        st, out, err = guard.check({**env, "GITHUB_EVENT_PATH": os.path.join(tmp, "nope")})
        check("an unreadable payload is named",
              out[0] == "ban_generated_by_attribution: PR description: NOT ENFORCED — the event payload is not readable")
        commit(repo, b"feat: after the payload's head\n\nClaude-Session: x")
        st, out, err = guard.check({"GITHUB_EVENT_PATH": write(pr), "AGENT_FABRIC_ATTRIBUTION_BASE": "main"})
        check("the payload's range wins over the override's", st == 0 and out[0].startswith("ban_generated_by_attribution: OK"))
        sh(repo, "reset", "-q", "--hard", clean)
        st, out, err = guard.check({"GITHUB_EVENT_PATH": write(pr)})
        check("the payload's own range is used with no override", st == 0 and out[0].startswith("ban_generated_by_attribution: OK"))
        st, out, err = guard.check({"GITHUB_EVENT_PATH": os.path.join(tmp, "nope"), "GITHUB_BASE_REF": "zz"})
        st2, out2, _ = guard.check({"GITHUB_EVENT_PATH": os.path.join(tmp, "nope")})
        check("a fallback that still finds main is enforced", st == 0 and out2 == out and "commit messages" not in out[0])
        sh(repo, "branch", "-m", "main", "trunk")
        st, out, err = guard.check({"GITHUB_EVENT_PATH": os.path.join(tmp, "nope")})
        check("neither half runnable: two notes and no 'clean' line",
              st == 0 and len(out) == 2 and all("NOT ENFORCED" in l for l in out))
        sh(repo, "branch", "-m", "trunk", "main")

        print("the entry point")
        r = subprocess.run([sys.executable, MODULE, "--ignored", "args"], capture_output=True, text=True, cwd=repo,
                           env={**GIT_ENV, "AGENT_FABRIC_ATTRIBUTION_BASE": "main"}, stdin=subprocess.DEVNULL, timeout=60)
        check("arguments are ignored", r.returncode == 0 and r.stdout.startswith("ban_generated_by_attribution: OK") and not r.stderr)
        outside = {k: v for k, v in GIT_ENV.items() if not k.startswith(("AGENT_FABRIC_ATTRIBUTION", "GITHUB_"))}
        r = subprocess.run([sys.executable, MODULE], capture_output=True, text=True, cwd=tmp, env=outside,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("outside a repository: NOT ENFORCED, exit 0", r.returncode == 0 and "NOT ENFORCED" in r.stdout and "OK —" not in r.stdout)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"{fails} failure(s)" if fails else "all passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
