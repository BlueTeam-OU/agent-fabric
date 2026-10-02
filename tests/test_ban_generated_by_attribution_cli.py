#!/usr/bin/env python3
"""The CLI parity oracle for policies/ban_generated_by_attribution.sh: the
assertions of policies/test_ban_generated_by_attribution.sh, one check each,
same labels, same fixtures (ADR-040 Wave 6).

The thing this holds still is the RANGE. The guard must fail on a trailer the
branch adds and stay silent about one already on the base -- a batch of those
is already on main, and a guard that fails forever gets disabled, which is the
same as no guard at all. The second thing is that PROSE IS NOT A TRAILER: the
guard has to be describable in the commit message that introduces it.

The script under test is $ATTRIBUTION_CLI, default
policies/ban_generated_by_attribution.sh, run as `bash <script>`.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.environ.get("ATTRIBUTION_CLI") or os.path.join(HERE, "policies", "ban_generated_by_attribution.sh")
if not os.path.isfile(CLI):
    sys.exit(f"test: script under test not found at {CLI}")

fails = 0
counter = 0
repo = ""
T = ""


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def base_env() -> dict[str, str]:
    # GITHUB_EVENT_PATH is always set in Actions, so without stripping it every
    # "must pass" case would read the description of whatever PR is running CI:
    # a PR whose own body carried the footer turned three fixture assertions
    # red, naming the description rather than the fixture. A self-test must not
    # read the ambient event.
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_", "GZCOORD_")) and k != "CLAUDECODE"}
    e.update(HOME=f"{T}/home", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C.UTF-8")
    return e


def git(path: str, *args: str) -> None:
    p = subprocess.run(["git", "-C", path, "-c", "commit.gpgsign=false", *args],
                       env=base_env(), capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"test: fixture setup failed: git {args}: {p.stderr}")


def init(path: str, branch: str) -> None:
    os.makedirs(path)
    git(path, "-c", f"init.defaultBranch={branch}", "init", "-q")
    git(path, "config", "user.email", "t@example.invalid")
    git(path, "config", "user.name", "test")
    git(path, "config", "commit.gpgsign", "false")


def commit(path: str, msg: str) -> None:
    git(path, "commit", "-q", "--allow-empty", "-m", msg)


def new_repo() -> None:
    """A repo whose `main` already carries a banned trailer, so every case
    also proves the guard is not auditing landed history."""
    global repo, counter
    counter += 1
    repo = f"{T}/r{counter}"
    init(repo, "main")
    commit(repo, "base work\n\nCo-authored-by: Someone <someone@example.invalid>")
    git(repo, "checkout", "-q", "-b", "topic")


def guard(cwd: str, **env: str) -> tuple[int, str]:
    e = base_env()
    e.update(env)
    p = subprocess.run(["bash", CLI], cwd=cwd, env=e, capture_output=True, timeout=60)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def run_guard(**env: str) -> tuple[int, str]:
    """The guard with the fixture's own main as the base."""
    return guard(repo, AGENT_FABRIC_ATTRIBUTION_BASE="main", **env)


def expect_rc(label: str, want: int) -> None:
    got, out = run_guard()
    head = "\n".join(out.splitlines()[:4])
    check(label, got == want, f"want rc={want}; got rc={got}\n{head}")


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def body() -> None:
    print("clean branches")

    new_repo()
    commit(repo, "feat: an ordinary commit")
    expect_rc("an ordinary commit passes", 0)

    # The asymmetry this guard lives or dies by.
    new_repo()
    commit(repo, "feat: adds nothing banned")
    expect_rc("a trailer already on the BASE is not this branch's problem", 0)

    # The guard must be describable in the commit that introduces it.
    new_repo()
    commit(repo, """feat(checks): ban the Co-authored-by trailer

The harness keeps asking for a Co-Authored-By line and a Generated with
Claude Code footer. Prose naming them is not a trailer and must pass, or
this guard cannot be explained in the commit that adds it.""")
    expect_rc("prose naming the banned strings is not a trailer", 0)

    # The killer for an UNANCHORED pattern: the key AND its colon, mid-sentence.
    # The case above has no colon after the key, so it passed for a reason
    # unrelated to anchoring and an unanchored regex survived it.
    new_repo()
    commit(repo, """docs: describe the ban

Do not add a Co-authored-by: trailer to a commit, and never a
session line: Claude-Session: is banned the same way.""")
    expect_rc("the key mid-sentence, colon and all, is not a trailer", 0)

    print("branches that must fail")

    new_repo()
    commit(repo, "feat: work\n\nCo-authored-by: Claude <noreply@anthropic.invalid>")
    expect_rc("a Co-authored-by trailer fails", 1)

    new_repo()
    commit(repo, "feat: work\n\nco-AUTHORED-by: Claude <noreply@anthropic.invalid>")
    expect_rc("the trailer match is case-insensitive", 1)

    new_repo()
    commit(repo, "feat: work\n\nCo-authored-by:Claude <noreply@anthropic.invalid>")
    expect_rc("a trailer with no space after the colon fails", 1)

    new_repo()
    commit(repo, """feat: work

An indented paste is still the line, not prose:

    Co-authored-by: Claude <noreply@anthropic.invalid>""")
    expect_rc("an INDENTED trailer is still a trailer", 1)

    new_repo()
    commit(repo, "feat: work\n\nGenerated with\n[Claude Code](https://example.invalid)")
    expect_rc("a hard-wrapped generated-with footer fails", 1)

    new_repo()
    commit(repo, "feat: work\n\nClaude-Session: https://example.invalid/x")
    expect_rc("a Claude-Session trailer fails", 1)

    new_repo()
    commit(repo, "feat: work\n\nGenerated with [Claude Code](https://example.invalid)")
    expect_rc("a generated-with footer fails", 1)

    new_repo()
    commit(repo, "feat: work\n\nhttps://claude.ai/code/session_0123456789")
    expect_rc("a session URL fails", 1)

    # Only the SECOND of three commits offends: a guard that stops at the tip
    # would pass this.
    new_repo()
    commit(repo, "feat: first")
    commit(repo, "feat: second\n\nCo-authored-by: Claude <noreply@anthropic.invalid>")
    commit(repo, "feat: third")
    expect_rc("an offending commit in the MIDDLE of the range is found", 1)
    _, out = run_guard()
    check("the failure names the offending commit", "feat: second" in out, out)

    print("the pull-request description")

    # The payload half needs no token: the body is in the event JSON.
    new_repo()
    commit(repo, "feat: clean commit")
    ev = f"{T}/event.json"
    write(ev, '{"pull_request":{"body":"Some description.\\n\\nGenerated with [Claude Code](https://example.invalid)\\n"}}')
    rc, _ = run_guard(GITHUB_EVENT_PATH=ev)
    check("a PR description carrying the footer fails", rc == 1, f"got rc={rc}")

    write(ev, '{"pull_request":{"body":"An ordinary description with no attribution.\\n"}}')
    rc, _ = run_guard(GITHUB_EVENT_PATH=ev)
    check("an ordinary PR description passes", rc == 0, f"got rc={rc}")

    # A merge_group payload has no pull_request key; that must not be an error.
    write(ev, '{"merge_group":{"head_sha":"deadbeef"}}')
    rc, _ = run_guard(GITHUB_EVENT_PATH=ev)
    check("a payload with no PR body is not an error", rc == 0, f"got rc={rc}")

    print("what cannot be checked must say so, never OK")

    # An environment that cannot show a range must not fail every PR.
    new_repo()
    commit(repo, "feat: work\n\nCo-authored-by: Claude <noreply@anthropic.invalid>")
    rc, out = guard(repo, AGENT_FABRIC_ATTRIBUTION_BASE="refs/nope")
    check("a bad override is not used unverified — the chain falls through",
          rc == 1 and "FAIL" in out, f"rc={rc}\n{out}")

    # THE PATH THAT SILENTLY PASSED EVERYTHING. When no range resolves the
    # guard must exit 0 -- an environment that cannot show a range is not a
    # violation -- but it must NOT say OK, or a no-op reads as coverage. This
    # is the line that made the first version green while enforcing nothing on
    # every event, and it had no test at all.
    orphan = f"{T}/orphan"
    init(orphan, "solo")
    commit(orphan, "work\n\nCo-authored-by: Claude <noreply@anthropic.invalid>")
    rc, out = guard(orphan)
    check("no resolvable range: exits 0, says NOT ENFORCED, never says OK",
          rc == 0 and "NOT ENFORCED" in out and "OK —" not in out, f"rc={rc}\n{out}")

    # Same rule for the description half: a payload it cannot read is not a pass.
    new_repo()
    commit(repo, "feat: clean commit")
    rc, out = run_guard(GITHUB_EVENT_PATH=f"{T}/not-a-file.json")
    check("an unreadable payload says NOT ENFORCED rather than OK",
          rc == 0 and "NOT ENFORCED" in out, f"rc={rc}\n{out}")

    write(ev, "this is not json{")
    rc, out = run_guard(GITHUB_EVENT_PATH=ev)
    check("a malformed payload says NOT ENFORCED rather than OK",
          rc == 0 and "NOT ENFORCED" in out, f"rc={rc}\n{out}")


def main() -> int:
    global T
    T = tempfile.mkdtemp(prefix="test_ban_attribution_cli.")
    try:
        os.makedirs(f"{T}/home")
        body()
    finally:
        shutil.rmtree(T, ignore_errors=True)
    print()
    if fails == 0:
        print("all passed")
        return 0
    print(f"{fails} FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
