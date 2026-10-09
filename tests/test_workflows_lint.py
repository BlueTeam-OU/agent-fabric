#!/usr/bin/env python3
"""tools/fabric/github/workflows_lint.py. Its behaviour's oracle is a
managed project's tools/checks/test_check_workflows_lint.sh, run unchanged
against the shim (ADR-040 §5 rule 5) but for three cases devex-tooling
retired: two reach the fetch's temp files through a failing mktemp on PATH
and one its move through a failing mv, which Python never calls, and one
seds the bash function out to show it refuses to run outside $(…), a rule
that existed because bash scoped its traps by the subshell. Their analogues
are here, in process: each failure point on its own — the download file,
the extract directory, the move — with its line and nothing of the fetch
left; INT and TERM handlers as fetch found them, with the control that one
was installed during the download. Then what the port adds: --root and
the toplevel default, the bounds on the download and the tools, the
cache's names, the pins. Plain script: prints ok/FAIL, exit 1 on any
failure."""
from __future__ import annotations

import io
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from github import workflows_lint as wl  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

TOOL = os.path.join(ROOT, "runtime", "github", "check-workflows-lint.sh")

# curl as the fetch calls it: `curl … -o <out> <url>`, the url a local
# tarball; $CURL_HANGS makes it write part of the file and stall.
CURL = r'''#!/usr/bin/env bash
out=""; url=""
while (( $# )); do case "$1" in -o) out="$2"; shift 2 ;; -*) shift ;; *) url="$1"; shift ;; esac; done
if [[ -n "${CURL_HANGS:-}" ]]; then head -c 100 "$url" > "$out"; exec sleep 30; fi
cp "$url" "$out"
'''


def tarball(dist: str, name: str, body: str) -> tuple[str, str]:
    """A release tarball holding one executable `name`; (path, sha256)."""
    data = body.encode()
    path = os.path.join(dist, f"{name}.tgz")
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(data), 0o755
        tf.addfile(info, io.BytesIO(data))
    return path, wl._sha256(path)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        bin_, dist = os.path.join(sandbox, "bin"), os.path.join(sandbox, "dist")
        os.makedirs(bin_)
        os.makedirs(dist)
        with open(os.path.join(bin_, "curl"), "w", encoding="utf-8") as fh:
            fh.write(CURL)
        os.chmod(os.path.join(bin_, "curl"), 0o755)
        # The tools record the directory they ran in, and exit with
        # $FAKE_ACTIONLINT_RC or $FAKE_ZIZMOR_RC.
        tool = '#!/usr/bin/env bash\npwd > "$RAN_IN"\nrc="FAKE_$(basename "$0" | tr a-z A-Z)_RC"\nexit "${!rc:-0}"\n'
        al, al_sha = tarball(dist, "actionlint", tool)
        zz, zz_sha = tarball(dist, "zizmor", tool)
        cache = os.path.join(sandbox, "cache")
        saved_path = os.environ["PATH"]
        os.environ["PATH"] = bin_ + os.pathsep + saved_path

        def leftovers() -> list[str]:
            out = []
            for d, _dirs, files in os.walk(cache):
                out += [os.path.join(d, n) for n in _dirs + files if n.startswith((".download.", ".extract."))]
            return out

        def fetch_refusal() -> str:
            try:
                wl.fetch("actionlint", "1", al_sha, al, cache)
            except wl.Refused as e:
                return str(e)
            return ""

        def fresh() -> None:
            shutil.rmtree(cache, ignore_errors=True)

        try:
            # ── the fetch's failure points, one at a time ────────────────
            print("workflows_lint: each failure point of the fetch")
            entry = os.path.join(cache, f"actionlint-1-{al_sha[:12]}")
            real = (wl.tempfile.mkstemp, wl.tempfile.mkdtemp, wl.os.replace)

            def boom(*_a, **_k):
                raise OSError(28, "No space left on device")
            for label, which, want in (
                    ("the download file", 0, f"cannot create a download file in {entry}"),
                    ("the extract directory", 1, f"cannot create an extract directory in {entry}"),
                    ("the move into the cache", 2, f"cannot move actionlint into {entry}")):
                fresh()
                fns = list(real)
                fns[which] = boom
                wl.tempfile.mkstemp, wl.tempfile.mkdtemp, wl.os.replace = fns
                try:
                    got = fetch_refusal()
                finally:
                    wl.tempfile.mkstemp, wl.tempfile.mkdtemp, wl.os.replace = real
                check(f"{label} failing is its own line", got == want, got)
                check("  and nothing of the fetch is left", not leftovers()
                      and not os.path.exists(os.path.join(entry, "actionlint")), str(leftovers()))
            fresh()
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w") as fh:
                fh.write("x")
            got = fetch_refusal()
            os.remove(cache)
            check("a cache entry that cannot be made is named", got == f"cannot create {entry}", got)

            # ── the handlers ─────────────────────────────────────────────
            print("workflows_lint: INT and TERM, this fetch's only")
            seen = {}
            real_run = wl.subprocess.run

            def spy(argv, *a, **k):
                if argv[0] == "curl":
                    seen["term"], seen["int"] = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
                return real_run(argv, *a, **k)
            before = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
            fresh()
            wl.subprocess.run = spy
            try:
                path = wl.fetch("actionlint", "1", al_sha, al, cache)
            finally:
                wl.subprocess.run = real_run
            check("control: during the download both are the fetch's",
                  seen.get("term") not in (before[0], None) and seen.get("int") not in (before[1], None))
            check("after it, both are as it found them",
                  (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == before)
            check("and the binary is in its entry", path == os.path.join(entry, "actionlint") and os.access(path, os.X_OK))
            fresh()
            try:
                fetch_refusal_text = wl.fetch("actionlint", "1", "0" * 64, al, cache)
            except wl.Refused as e:
                fetch_refusal_text = str(e)
            check("restored on a refusal too", (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
                  == before and "does not match its pinned sha256" in fetch_refusal_text)
            check("a digest that is not 64 hex digits is a mismatch, never a pass",
                  "does not match" in _refuse(lambda: wl.fetch("actionlint", "1", al_sha[:-1], al, cache)))
            check("an upper-case digest is the same digest", bool(wl.fetch("zizmor", "1", zz_sha.upper(), zz, cache)))

            # ── the bounds ───────────────────────────────────────────────
            print("workflows_lint: the bounds")
            fresh()
            saved_bound = wl.DOWNLOAD_TIMEOUT_S
            wl.DOWNLOAD_TIMEOUT_S = 1
            os.environ["CURL_HANGS"] = "1"
            t0 = time.monotonic()
            try:
                got = fetch_refusal()
            finally:
                wl.DOWNLOAD_TIMEOUT_S = saved_bound
                del os.environ["CURL_HANGS"]
            check("a download past its bound is the could-not-download line",
                  got == f"could not download actionlint 1 ({al})", got)
            check("  the whole download is bounded, its child killed", time.monotonic() - t0 < 10)
            check("  and nothing is left", not leftovers(), str(leftovers()))

            slow = os.path.join(sandbox, "slow")
            with open(slow, "w") as fh:
                fh.write("#!/usr/bin/env bash\nexec sleep 30\n")
            os.chmod(slow, 0o755)
            saved_bound = wl.TOOL_TIMEOUT_S
            wl.TOOL_TIMEOUT_S = 1
            try:
                got = _refuse(lambda: wl.run_tool("zizmor", [slow], sandbox))
            finally:
                wl.TOOL_TIMEOUT_S = saved_bound
            check("a tool past its bound could not run", got == "zizmor could not run (timed out after 1 s)", got)

            # ── names and pins ───────────────────────────────────────────
            print("workflows_lint: the cache and the pins")
            check("AGENT_FABRIC_TOOL_CACHE wins", wl.cache_dir({"AGENT_FABRIC_TOOL_CACHE": "/c", "XDG_CACHE_HOME": "/x"})
                  == "/c")
            check("else XDG_CACHE_HOME", wl.cache_dir({"XDG_CACHE_HOME": "/x", "HOME": "/h"}) == "/x/agent-fabric-tools")
            check("else HOME's .cache", wl.cache_dir({"HOME": "/h"}) == "/h/.cache/agent-fabric-tools")
            check("a project's name is not read", wl.cache_dir({"GZAPP_TOOL_CACHE": "/g", "HOME": "/h"})
                  == "/h/.cache/agent-fabric-tools")
            v, s, u = wl.pin("actionlint", {})
            check("the pinned release's url names its version",
                  (v, u) == ("1.7.12", "https://github.com/rhysd/actionlint/releases/download/v1.7.12/"
                                       "actionlint_1.7.12_linux_amd64.tar.gz") and len(s) == 64)
            v, s, u = wl.pin("zizmor", {"ZIZMOR_VERSION": "9.9.9"})
            check("a version override moves the default url, not the digest",
                  v == "9.9.9" and "/v9.9.9/" in u and s == wl.PINS["zizmor"][1])
        finally:
            os.environ["PATH"] = saved_path

        # ── through the shim ─────────────────────────────────────────────
        print("workflows_lint: through runtime/github/check-workflows-lint.sh")
        with open(os.path.join(bin_, "shellcheck"), "w", encoding="utf-8") as fh:
            fh.write('#!/usr/bin/env bash\necho ShellCheck\necho "version: stub"\n')
        os.chmod(os.path.join(bin_, "shellcheck"), 0o755)
        repo = os.path.join(sandbox, "repo")
        os.makedirs(os.path.join(repo, ".github", "workflows"))
        os.makedirs(os.path.join(repo, "sub"))
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_"))}
        base.update(PATH=bin_ + os.pathsep + "/usr/bin:/bin", HOME=sandbox, AGENT_FABRIC_TOOL_CACHE=cache,
                    ACTIONLINT_URL=al, ACTIONLINT_SHA256=al_sha, ZIZMOR_URL=zz, ZIZMOR_SHA256=zz_sha,
                    RAN_IN=os.path.join(sandbox, "ran-in"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                    GIT_CEILING_DIRECTORIES=sandbox)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]

        def run(*args: str, cwd: str = sandbox, **env: str):
            r = subprocess.run([TOOL, *args], env=dict(base, **env), cwd=cwd, capture_output=True, text=True,
                               timeout=120)
            return r.returncode, r.stdout, r.stderr

        rc, out, err = run("--root", repo)
        check("a clean run: both tools, the OK line, exit 0",
              rc == 0 and out == "check_workflows_lint: actionlint 1.7.12, version: stub\n"
                                 "check_workflows_lint: zizmor 1.30.1 (offline)\n"
                                 "check_workflows_lint: OK — every workflow passes actionlint and zizmor.\n",
              f"{rc} {out!r} {err!r}")
        subprocess.run(["git", "init", "-q", repo], env=base, check=True, timeout=30, capture_output=True)
        rc, out, err = run(cwd=os.path.join(repo, "sub"))
        with open(os.path.join(sandbox, "ran-in")) as fh:
            ran_in = fh.read().strip()
        check("without --root, the working directory's toplevel", rc == 0 and ran_in == os.path.realpath(repo),
              f"{rc} {ran_in} {err}")
        rc, out, err = run("--root", repo, FAKE_ACTIONLINT_RC="1")
        check("a finding: the hint, exit 1", rc == 1 and out.endswith(
            "check_workflows_lint: fix the finding, or excuse ONE site inline with its reason\n"
            "(# zizmor: ignore[<rule>]); a rule this repository decides against\n"
            "goes in .github/zizmor.yml with its reason.\n"), out)
        rc, out, err = run("-h")
        check("--help is the module's text, exit 0",
              rc == 0 and out.startswith("runtime/github/check-workflows-lint.sh [--root <dir>]") and not err)
        for args, cwd, want in (
                (("--root",), sandbox, "check_workflows_lint: --root needs a value\n"),
                (("extra",), sandbox, "check_workflows_lint: unexpected argument: extra\n"),
                ((), sandbox, "check_workflows_lint: not in a git working copy; pass --root <dir>\n")):
            rc, out, err = run(*args, cwd=cwd)
            check(f"{args or 'no --root outside a working copy'}: exit 2, stderr only",
                  rc == 2 and out == "" and err == want, f"{rc} {out!r} {err!r}")

    print("ok" if not fails else f"{fails} failure(s)")
    return 1 if fails else 0


def _refuse(fn) -> str:
    try:
        fn()
    except wl.Refused as e:
        return str(e)
    return ""


if __name__ == "__main__":
    sys.exit(main())
