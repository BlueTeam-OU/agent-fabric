#!/usr/bin/env python3
"""tools/fabric/github/workflows_lint.py [--root <dir>]

Every workflow passes actionlint (its run: scripts through shellcheck)
and zizmor (the workflow security audit), with the release of each
pinned here, once, for CI and for a session running the guards before
it pushes.

What each catches. actionlint: a run: script that does not parse (a
broken script fails only on the path that reaches the broken line), and
shellcheck warnings; info- and style-level notes are ignored, since
which fire varies with the shellcheck release. zizmor, offline: ${{ }}
spliced into a script, over-broad permissions, persisted checkout
tokens, spoofable bot checks, inherited secrets. The project's
.github/zizmor.yml disables what it has decided against, each with its
reason; a single site is excused inline with `# zizmor: ignore[<rule>]`
and its reason.

The tools are release binaries, fetched once into the cache
(AGENT_FABRIC_TOOL_CACHE, else $XDG_CACHE_HOME/agent-fabric-tools, else
~/.cache/agent-fabric-tools), each checked against its sha256 before it
is extracted or run. A cached binary is reused only from a directory
named for its version and digest, so a pin bump fetches afresh.
shellcheck comes from PATH: actionlint skips its script pass SILENTLY
without one, so its absence is exit 2.

  --root <dir>   the repository to check (default: the working
                 directory's toplevel)
  -h, --help     this text

Exit codes:
  0  both tools ran and found nothing
  1  a finding (printed)
  2  a tool could not be obtained or run (no network, a checksum
     mismatch, no shellcheck) — nothing was checked
"""
# The docstring is --help, whole. Ported from a managed project's
# tools/checks/check_workflows_lint.sh (ADR-040; its test, run unchanged
# against the shim, the oracle), with the other project's copy's argv.
#
# THE CONTRACT, frozen from devex-tooling's port contract 5/8:
#   argv    [--root <dir>] [-h|--help]; "--root needs a value" and
#           "unexpected argument: <x>", exit 2. Without --root, the working
#           directory's git toplevel; outside one, exit 2.
#   env     the pins (ACTIONLINT_VERSION, ACTIONLINT_SHA256, ACTIONLINT_URL,
#           ZIZMOR_VERSION, ZIZMOR_SHA256, ZIZMOR_URL), each overridable: the
#           test's seam, and it moves nothing silently — a version without
#           its digest fails the checksum. AGENT_FABRIC_TOOL_CACHE,
#           XDG_CACHE_HOME, HOME for the cache; PATH for curl, tar and
#           shellcheck.
#   stdout  "<me>: actionlint <ver>, <shellcheck's version line>", the
#           tool's own output, "<me>: zizmor <ver> (offline)", its output,
#           then the three-line hint (a finding) or the OK line.
#   stderr  every refusal, "<me>: …", one line.
#   exit    0 clean, 1 a finding, 2 could not check; 130 or 143 when
#           interrupted by INT or TERM, nothing of the fetch left behind.
# Departures from the bash: --root, never REPO_ROOT; the downloads and the
# tools are bounded; the cache's names are the fabric's.
from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from github.cli_root import Refused, parse_root, toplevel  # noqa: E402

PROG = "check_workflows_lint"
# The pins. Bump version and digest together; the digest is the release
# asset's (GitHub shows it on the release page; `sha256sum` the download).
PINS = {
    "actionlint": ("1.7.12", "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
                   "https://github.com/rhysd/actionlint/releases/download/v{v}/actionlint_{v}_linux_amd64.tar.gz"),
    "zizmor": ("1.30.1", "e65324f4430c2717591937edcec90ccbefaf14c174f8ec9415e03ca875b46e1a",
               "https://github.com/zizmorcore/zizmor/releases/download/v{v}/zizmor-x86_64-unknown-linux-gnu.tar.gz"),
}
DOWNLOAD_TIMEOUT_S = 600
TOOL_TIMEOUT_S = 600
SHELLCHECK_HINT = "dnf install ShellCheck / apt-get install shellcheck"


class Interrupted(BaseException):
    """INT or TERM during a fetch; `code` is the exit, 130 or 143. A
    BaseException, so no `except Exception` between the signal and the
    cleanup swallows it."""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


def pin(name: str, env) -> tuple[str, str, str]:
    version, sha, url = PINS[name]
    up = name.upper()
    version = env.get(f"{up}_VERSION") or version
    sha = env.get(f"{up}_SHA256") or sha
    url = env.get(f"{up}_URL") or url.format(v=version)
    return version, sha, url


def cache_dir(env) -> str:
    explicit = env.get("AGENT_FABRIC_TOOL_CACHE")
    if explicit:
        return explicit
    base = env.get("XDG_CACHE_HOME") or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".cache")
    return os.path.join(base, "agent-fabric-tools")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(name: str, version: str, sha: str, url: str, cache: str) -> str:
    """The binary's path, fetched into <cache>/<name>-<version>-<sha[:12]>
    unless already there. A refusal is Refused; INT or TERM is Interrupted,
    after this fetch's download and extract files are removed."""
    entry = os.path.join(cache, f"{name}-{version}-{sha[:12]}")
    binary = os.path.join(entry, name)
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
        return binary
    try:
        os.makedirs(entry, exist_ok=True)
    except OSError:
        raise Refused(f"cannot create {entry}") from None
    tmp = stage = ""

    def interrupted(signum, _frame):
        raise Interrupted(128 + signum)
    # An interrupt mid-download or mid-extract would otherwise leave this
    # run's .download.* and .extract.* in the cache entry for good: the
    # cache check never runs them, but nothing removes them either. The
    # handlers are this fetch's only, and restored on every way out.
    saved = {s: signal.signal(s, interrupted) for s in (signal.SIGINT, signal.SIGTERM)
             if signal.getsignal(s) is not signal.SIG_IGN}
    try:
        try:
            fd, tmp = tempfile.mkstemp(prefix=".download.", dir=entry)
            os.close(fd)
        except OSError:
            tmp = ""
            raise Refused(f"cannot create a download file in {entry}") from None
        try:
            r = subprocess.run(["curl", "-fsSL", "--retry", "3", "--retry-all-errors", "-o", tmp, url],
                               stdin=subprocess.DEVNULL, timeout=DOWNLOAD_TIMEOUT_S)
            ok = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if not ok:
            raise Refused(f"could not download {name} {version} ({url})")
        # Anything but the digest's own hex digits — a short or malformed pin
        # included — is a mismatch, never a pass.
        if _sha256(tmp) != sha.lower():
            raise Refused(f"{name} {version} does not match its pinned sha256 — not run")
        # Extracted beside the cache entry and moved into place, so an
        # interrupted run never leaves a truncated binary that the cache
        # check above would then reuse on every later run. tar's own words
        # are kept: "Not found in archive" (the release moved the binary), a
        # truncated stream and a full disk are different fixes.
        try:
            stage = tempfile.mkdtemp(prefix=".extract.", dir=entry)
        except OSError:
            stage = ""
            raise Refused(f"cannot create an extract directory in {entry}") from None
        try:
            r = subprocess.run(["tar", "-xzf", tmp, "-C", stage, name], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=DOWNLOAD_TIMEOUT_S)
            err = r.stdout.decode("utf-8", "replace").rstrip("\n") if r.returncode else None
        except (OSError, subprocess.TimeoutExpired) as e:
            err = str(e)
        if err is not None:
            raise Refused(f"cannot extract {name} {version} from its archive: {err or 'tar failed with no message'}")
        try:
            os.replace(os.path.join(stage, name), binary)
        except OSError:
            raise Refused(f"cannot move {name} into {entry}") from None
        return binary
    finally:
        for path in (tmp, stage):
            if path:
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else _unlink(path)
        for s, handler in saved.items():
            signal.signal(s, handler)


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def run_tool(label: str, argv: list[str], root: str) -> int:
    try:
        return subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, timeout=TOOL_TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        raise Refused(f"{label} could not run (timed out after {TOOL_TIMEOUT_S} s)") from None
    except OSError as e:
        raise Refused(f"{label} could not run ({e.strerror})") from None


def check(root: str, env) -> int:
    if not shutil.which("shellcheck", path=env.get("PATH")):
        raise Refused(f"shellcheck is not on PATH; actionlint would lint no run: script ({SHELLCHECK_HINT})")
    cache = cache_dir(env)
    al_version, al_sha, al_url = pin("actionlint", env)
    zz_version, zz_sha, zz_url = pin("zizmor", env)
    actionlint = fetch("actionlint", al_version, al_sha, al_url, cache)
    zizmor = fetch("zizmor", zz_version, zz_sha, zz_url, cache)
    if not root:
        root = toplevel()
    if not (os.path.isdir(root) and os.access(root, os.X_OK)):
        raise Refused(f"cannot enter {root}")
    if not os.path.isdir(os.path.join(root, ".github", "workflows")):
        raise Refused(f"no .github/workflows under {root}")

    # Each tool's own exit codes tell a finding from a failure to run:
    # actionlint 1 is findings (2 and 3 are usage and fatal errors), zizmor
    # 10-14 are findings by severity. Anything else is exit 2 here, never a
    # finding and never a pass.
    bad = False
    try:
        sc = subprocess.run(["shellcheck", "--version"], capture_output=True, text=True, timeout=30,
                            stdin=subprocess.DEVNULL).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        sc = []
    print(f"{PROG}: actionlint {al_version}, {sc[1] if len(sc) > 1 else ''}", flush=True)
    rc = run_tool("actionlint", [actionlint, "-no-color", "-oneline", "-ignore", ":(info|style):"], root)
    if rc == 1:
        bad = True
    elif rc != 0:
        raise Refused(f"actionlint could not run (exit {rc})")
    print(f"{PROG}: zizmor {zz_version} (offline)", flush=True)
    rc = run_tool("zizmor", [zizmor, "--offline", "--format", "plain", ".github/"], root)
    if 10 <= rc <= 14:
        bad = True
    elif rc != 0:
        raise Refused(f"zizmor could not run (exit {rc})")

    if bad:
        print()
        print(f"{PROG}: fix the finding, or excuse ONE site inline with its reason")
        print("(# zizmor: ignore[<rule>]); a rule this repository decides against")
        print("goes in .github/zizmor.yml with its reason.")
        return 1
    print(f"{PROG}: OK — every workflow passes actionlint and zizmor.")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        root = parse_root(sys.argv[1:])
        if root is None:
            print(__doc__.strip("\n"))
            return 0
        return check(root, os.environ)
    except Refused as e:
        print(f"{PROG}: {e}", file=sys.stderr, flush=True)
        return 2
    except Interrupted as e:
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
