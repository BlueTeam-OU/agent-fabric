#!/usr/bin/env python3
"""runtime/github/arm.sh with gh, pr-gate and pr-review-status mocked on
PATH: each gate has a case that trips it and one that passes; the arming
path posts the basis (on stdin) and runs gh pr merge --auto exactly once,
and a dry run posts and runs nothing. Ported from gzapp's
tools/gh/test_arm.sh, case for case, run through gzapp's forwarder
(projects/gzapp/integration/gh/arm.sh: its arm.json and the GZAPP_*
names); then InterWeave's arm.json, which has no classes, and a project
with none. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GZAPP = os.path.join(ROOT, "projects", "gzapp", "integration", "gh", "arm.sh")
SHIM = os.path.join(ROOT, "runtime", "github", "arm.sh")
IW_CONFIG = os.path.join(ROOT, "projects", "interweave", "integration", "gh", "arm.json")

GH_MOCK = r'''#!/usr/bin/env python3
import json, os, sys
s, a = os.environ["MOCK_STATE"], sys.argv[1:]
line = " ".join(a)
def has(n): return os.path.exists(os.path.join(s, n))
with open(os.path.join(s, "calls"), "a") as fh:
    fh.write(line + "\n")
    if line.startswith("pr comment ") and line.endswith("--body-file -"):
        fh.write(f"pr comment {a[2]} --body {sys.stdin.read()}\n"); sys.exit(0)
pr = json.load(open(os.path.join(s, "pr.json")))
if line.startswith("repo view"):
    print("gzapi-org/gzapp"); sys.exit(0)
if line.startswith("api repos/gzapi-org/gzapp/pulls/7/files") and "--paginate --slurp" in line:
    print(json.dumps([[{"filename": f} for f in pr["files"]]])); sys.exit(0)
if line == "api graphql --input -":
    sys.stdin.read()
    p = {"autoMergeRequest": None, "mergeQueueEntry": None}
    if has("queued"): p["mergeQueueEntry"] = {"position": 2}
    elif has("armed"): p["autoMergeRequest"] = {"enabledAt": "x"}
    print(json.dumps({"data": {"repository": {"pullRequest": p}}})); sys.exit(0)
if line.startswith("pr view "):
    if has("viewfail"): sys.exit(1)
    print(json.dumps({k: v for k, v in pr.items() if k != "files"})); sys.exit(0)
if line == "pr merge 7 --merge --auto":
    open(os.path.join(s, "armed"), "w").close(); sys.exit(0)
print("mock gh: unhandled: " + line, file=sys.stderr); sys.exit(1)
'''

GATE_MOCK = r'''#!/usr/bin/env python3
import os
print(open(os.path.join(os.environ["MOCK_STATE"], "gate.json")).read())
'''

# The --json object agent-fabric's reader prints (the fields arm reads),
# from state files: `blind` and `independent` list commits (sha8),
# `unresolved` the thread count ("null" for a failed lookup). review_rc 0
# with no `blind` file stands for a review-class review of the head.
# `no_blind_field` drops blind.rows.
REVIEW_MOCK = r'''#!/usr/bin/env python3
import json, os, sys
s = os.environ["MOCK_STATE"]
def rd(n, d=None):
    p = os.path.join(s, n)
    return open(p).read().strip() if os.path.exists(p) else d
with open(os.path.join(s, "calls"), "a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
if "--json" not in sys.argv[1:]:
    print("mock pr-review-status: arm must ask for --json", file=sys.stderr); sys.exit(2)
rc = int(rd("review_rc", "1"))
if rc == 2: sys.exit(2)
blind = rd("blind") if rd("blind") is not None else ("abcdef01" if rc == 0 else "")
rows = lambda t: [{"login": "someone", "commit_sha8": x, "at": "2026-09-25T00:00:00Z"} for x in (t or "").split() if x]
out = {"state": "OPEN", "head": "abcdef0123456789", "head_reviewed": rc == 0,
       "independent": {"count": len(rows(rd("independent"))), "rows": rows(rd("independent"))},
       "unresolved_threads": json.loads(rd("unresolved", "0")),
       "blind": {"count": 0} if rd("no_blind_field") is not None else {"count": len(rows(blind)), "rows": rows(blind)}}
print(json.dumps(out)); sys.exit(rc)
'''

HEAD = "abcdef0123456789abcdef0123456789abcdef01"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GZAPP_")) and k != "GIT_DIR"}

    with tempfile.TemporaryDirectory() as sandbox:
        state, bindir = f"{sandbox}/state", f"{sandbox}/bin"
        os.makedirs(state)
        os.makedirs(bindir)
        for name, text in (("gh", GH_MOCK), ("pr-gate", GATE_MOCK), ("pr-review-status", REVIEW_MOCK)):
            with open(f"{bindir}/{name}", "w") as fh:
                fh.write(text)
            os.chmod(f"{bindir}/{name}", 0o755)

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w") as fh:
                fh.write(text)

        def reset() -> None:
            for n in ("calls", "armed", "queued", "viewfail", "blind", "independent", "unresolved", "no_blind_field"):
                if os.path.exists(f"{state}/{n}"):
                    os.remove(f"{state}/{n}")
            put("review_rc", "1")

        def set_pr(branch: str, body: str, files: list[str], st: str = "OPEN", draft: bool = False) -> None:
            put("pr.json", json.dumps({"number": 7, "state": st, "isDraft": draft, "headRefName": branch,
                                       "headRefOid": HEAD, "body": body, "files": files, "title": "the pr"}))

        def set_gate(n: int | None, known: bool | None = True) -> None:
            row: dict = {"number": 7}
            if n is not None or known is not None:
                row["work_commits"] = n
            if known is not None:
                row["commits_known"] = known
            put("gate.json", json.dumps([row]))

        def calls() -> str:
            p = f"{state}/calls"
            return open(p).read() if os.path.exists(p) else ""

        def run(*args: str, script: str = GZAPP, env: dict | None = None) -> tuple[int, str]:
            e = dict(base_env, MOCK_STATE=state, PATH=f"{bindir}:{base_env.get('PATH', '')}",
                     GZAPP_PR_GATE=f"{bindir}/pr-gate", GZAPP_PR_REVIEW_STATUS=f"{bindir}/pr-review-status",
                     GZAPP_PR_SESSION="develop-qzapp/me")
            if script == SHIM:
                # The shim reads the fabric's names; only gzapp's forwarder maps GZAPP_*.
                e.update(AGENT_FABRIC_PR_GATE=e.pop("GZAPP_PR_GATE"), AGENT_FABRIC_PR_SESSION=e.pop("GZAPP_PR_SESSION"),
                         AGENT_FABRIC_PR_REVIEW_STATUS=e.pop("GZAPP_PR_REVIEW_STATUS"))
            e.update(env or {})
            r = subprocess.run(["bash", script, *args], env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, text=True, timeout=120, cwd=sandbox)
            return r.returncode, r.stdout

        me = "develop-qzapp/me/feat/x"
        owner = "reviewed; the owner's word given"
        mig = ["infra/db/migrations/0053_x.sql"]

        print("arm: usage")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7"); check("no --basis: exit 2, says so", rc == 2 and "--basis" in out, out)
        rc, out = run("--basis", "x"); check("no number: exit 2", rc == 2, out)
        rc, out = run("7", "--basis", "x", "--boundary", "--no-boundary", "why")
        check("--boundary with --no-boundary: exit 2", rc == 2, out)
        rc, out = run("--help"); check("--help prints the gates, exit 0", rc == 0 and "SECURITY-BOUNDARY" in out, out)

        print("arm: gate 1 — open and not a draft")
        reset(); set_pr(me, "plain", ["docs/a.md"], "MERGED"); set_gate(9)
        rc, out = run("7", "--basis", "b"); check("a merged PR is refused", rc == 1 and "MERGED, not open" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"], "OPEN", True)
        rc, out = run("7", "--basis", "b"); check("a draft is refused", rc == 1 and "draft" in out, out)

        print("arm: gate 2 — another session's PR")
        reset(); set_pr("develop-qzapp/other/feat/x", "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b"); check("refused by branch prefix", rc == 1 and "not this session's" in out, out)
        check("nothing armed on a refusal", "pr merge" not in calls(), calls())
        rc, out = run("7", "--basis", "b", "--any-owner"); check("--any-owner overrides", rc == 0 and "ARMED #7" in out, out)

        print("arm: gate 3 — AWAITING-SUPPLY without its range line")
        reset(); set_pr(me, "AWAITING-SUPPLY: develop-qzapp/db-admin\nAWAITING-SUPPLY: web-dev-01\n\n"
                            "aaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("the unmet login is named", rc == 1 and "AWAITING-SUPPLY db-admin with no range line" in out, out)
        check("the login with a range line passes", "web-dev-01 with no range" not in out, out)
        reset(); set_pr(me, "AWAITING-SUPPLY: db-admin\n\n3ebdb83a..9f00aa11: db-admin (db-admin)", ["docs/a.md"])
        rc, out = run("7", "--basis", "b"); check("with its range line the PR arms", rc == 0, out)

        print("arm: gate 4 — the security boundary needs a review of the head")
        reset(); set_pr(me, "plain", mig + ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("a migration with no review: refused", rc == 1 and "no review-class review of the current head" in out, out)
        check("asked pr-review-status for the PR as --json", "7 -q --json" in calls().splitlines(), calls())
        reset(); set_pr(me, "plain", ["apps/backend_dotnet/src/Gzapp.Infrastructure/Auth/DriverIdentity.cs"]); put("review_rc", "0")
        rc, out = run("7", "--basis", "b")
        check("an Auth/ change reviewed but no owner's word: refused", rc == 1 and "owner's word as well as the review" in out, out)
        rc, out = run("7", "--basis", owner)
        check("…with the review AND the owner's word: armed",
              rc == 0 and "has the review class's review, and no unresolved thread" in out, out)
        for path, label in (("apps/backend_dotnet/src/Gzapp.Admin/Drivers/AdminDriverDirectoryRepository.cs", "Drivers/"),
                            ("packages/web-shared/src/auth/refresh.ts", "a lowercase client auth/ (case-insensitive)"),
                            ("apps/backend_dotnet/src/Gzapp.Persistence/Consent/ConsentRepository.cs", "Consent/")):
            reset(); set_pr(me, "plain", [path])
            rc, out = run("7", "--basis", "b"); check(f"{label} with no review: refused", rc == 1, out)
        reset(); set_pr(me, "plain", ["apps/backend_dotnet/src/Gzapp.Persistence/DriverPositions/Store.cs"]); put("review_rc", "5")
        rc, out = run("7", "--basis", "b"); check("Regime 3 positions with no review coming (exit 5): refused", rc == 1, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("blind", ""); put("independent", "abcdef01")
        rc, out = run("7", "--basis", owner)
        check("an independent review of the head, reader exit 0: not the boundary's review",
              rc == 1 and "no review-class review of the current head" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("blind", "1234abcd")
        rc, out = run("7", "--basis", owner)
        check("a blind review of an EARLIER commit: refused", rc == 1 and "no review-class review of the current head" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("unresolved", "2")
        rc, out = run("7", "--basis", owner)
        check("2 threads open: refused, the count named", rc == 1 and "with 2 unresolved review thread(s)" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("unresolved", "null")
        rc, out = run("7", "--basis", owner)
        check("unresolved_threads null: exit 2, never read as zero", rc == 2 and "no unresolved_threads count" in out, out)
        reset(); set_pr(me, "plain", mig); put("review_rc", "0"); put("no_blind_field", "")
        rc, out = run("7", "--basis", owner)
        check("no blind.rows: exit 2", rc == 2 and "carried no blind.rows" in out, out)
        reset(); put("review_rc", "2")
        rc, out = run("7", "--basis", "b"); check("pr-review-status exit 2: exit 2", rc == 2, out)
        reset(); set_pr(me, "plain", ["docs/adr/ADR-054-privacy-regime-separation-four-regimes.md",
                                      "infra/local/grafana/provisioning/dashboards/x.json", "docs/devices/eye-beacon.md"])
        put("review_rc", "5")
        rc, out = run("7", "--basis", "b")
        check("docs and local-infra paths matching a boundary word still pass", rc == 0 and "not a security-boundary change" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md", "product/i18n/ka-GE.json"]); put("review_rc", "5")
        rc, out = run("7", "--basis", "b")
        check("docs + i18n pass without a review", rc == 0 and "not a security-boundary change" in out, out)
        check("…and the review status was not asked", not any(l[:1].isdigit() for l in calls().splitlines()), calls())
        reset(); set_pr(me, "plain", ["docs/a.md"])
        rc, out = run("7", "--basis", "b", "--boundary"); check("--boundary forces the gate on a docs PR", rc == 1, out)
        reset(); set_pr(me, "plain", mig)
        rc, out = run("7", "--basis", "the owner's word", "--no-boundary", "comment-only DDL, owner waived")
        check("--no-boundary waives it and says so", rc == 0 and "WAIVED" in out, out)

        print("arm: gate 5 — the classes that arm under 8 without asking")
        reset(); set_pr("develop-qzapp/me/docs/x", "Wording.\n\nClass: docs-only",
                        ["docs/adr/ADR-054-x.md", ".claude/skills/pr-gate/SKILL.md", "apps/backend_dotnet/CLAUDE.md"]); set_gate(2)
        rc, out = run("7", "--basis", "two wording commits")
        check("docs-only stated and true: 2 work commits arm", rc == 0 and "arms at the gate as docs-only" in out, out)
        check("…and the comment records the class",
              "pr comment 7 --body Arming basis: two wording commits — 2 work commits, class: docs-only, head" in calls(), calls())
        reset(); set_pr("develop-qzapp/me/docs/x", "- **Class: single-check tooling** fix\n",
                        ["tools/gh/arm.sh", "tools/gh/test_arm.sh", ".github/workflows/_ban-checks.yml"]); set_gate(1)
        rc, out = run("7", "--basis", "one check")
        check("single-check tooling stated (bold, in a list) and true: arms",
              rc == 0 and "arms at the gate as single-check tooling" in out, out)
        for files, named, label in ((["docs/a.md", "product/i18n/ka-GE.json"], "product/i18n/ka-GE.json", "an i18n dictionary"),
                                    (["docs/a.md", ".claude/settings.json"], ".claude/settings.json", ".claude/settings.json")):
            reset(); set_pr("develop-qzapp/me/docs/x", "Class: docs-only", files); set_gate(2)
            rc, out = run("7", "--basis", "b"); check(f"{label} is NOT docs-only: refused, named", rc == 1 and named in out, out)
        reset(); set_pr("develop-qzapp/me/docs/x", "Class: single-check tooling", [".claude/settings.json", "tools/gh/arm.sh"]); set_gate(1)
        rc, out = run("7", "--basis", "b"); check("…but settings.json IS tooling: arms", rc == 0, out)
        reset(); set_pr("develop-qzapp/me/docs/x", "Class: docs-only", ["docs/a.md", "apps/backend_dotnet/src/Gzapp.Core/Thing.cs"]); set_gate(2)
        rc, out = run("7", "--basis", "b")
        check("a stated class the files contradict is refused",
              rc == 1 and "states Class: docs-only but the changed files are not that class" in out, out)
        check("…naming the file outside the class", "Gzapp.Core/Thing.cs" in out, out)
        reset(); set_pr("develop-qzapp/me/docs/x", "Class: docs-only", ["docs/a.md"]); set_gate(20)
        rc, out = run("7", "--basis", "b")
        check("over 16 under a class: armed with the advice said", rc == 0 and "over 16: smaller batches next time" in out, out)
        reset(); set_pr(me, "Class: docs-only", ["apps/backend_dotnet/src/Gzapp.Infrastructure/Auth/DriverIdentity.cs"]); set_gate(2)
        put("review_rc", "0")
        rc, out = run("7", "--basis", "b"); check("a boundary file under a stated docs-only class: refused", rc == 1, out)

        print("arm: gate 5 — the count rule")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(17)
        rc, out = run("7", "--basis", "b")
        check("17 work commits: armed with the advice said",
              rc == 0 and "17 work commits — over 16: smaller batches next time; arming on the basis given" in out, out)
        check("…and the comment carries the count", "pr comment 7 --body Arming basis: b — 17 work commits, head" in calls(), calls())
        reset(); set_gate(5)
        rc, out = run("7", "--basis", "five commits, all docs")
        check("5 work commits with no owner's word: refused", rc == 1 and "owner's word" in out, out)
        rc, out = run("7", "--basis", "the owner has not been asked yet")
        check("a basis that merely mentions the owner is not the owner's word", rc == 1, out)
        rc, out = run("7", "--basis", "on the owner’s word (curly apostrophe)")
        check("the phrase with a curly apostrophe counts", rc == 0, out)
        rc, out = run("7", "--basis", "five commits; the owner's word given today")
        check("5 work commits on the owner's word: armed", rc == 0 and "under 8, on the owner's word" in out, out)
        reset(); put("gate.json", '[{"number":7}]')
        rc, out = run("7", "--basis", "b"); check("no commit count from pr-gate: exit 2", rc == 2, out)
        reset(); set_gate(None, False)
        rc, out = run("7", "--basis", "on the owner's word")
        check("commits_known false: exit 2, never 'under 8'", rc == 2 and "could not count" in out, out)
        check("…and nothing was armed", "pr merge" not in calls(), calls())
        reset(); set_gate(0, None)
        rc, out = run("7", "--basis", "on the owner's word")
        check("a row with no commits_known field is not trusted either", rc == 2, out)

        print("arm: the arming path and the dry run")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "nine work commits at the review gate")
        check("exits 0", rc == 0, out)
        check("gh pr merge --auto ran once", calls().count("pr merge 7 --merge --auto") == 1, calls())
        check("the basis comment carries the count and the head, on stdin",
              "pr comment 7 --body Arming basis: nine work commits at the review gate — 9 work commits, head abcdef01." in calls(), calls())
        check("prints the watcher line for the session", "tools/gh/wait-merged.sh 7 &" in out, out)
        reset(); put("queued", "")
        rc, out = run("7", "--basis", "b")
        check("a PR that went straight into the queue reads as armed", rc == 0 and "queued at 2" in out, out)
        reset()
        rc, out = run("7", "--basis", "b", "--dry-run")
        check("dry run exits 0", rc == 0 and "DRY RUN" in out, out)
        check("dry run posts and arms nothing", "pr merge" not in calls() and "pr comment" not in calls(), calls())
        reset(); put("viewfail", "")
        rc, out = run("7", "--basis", "b"); check("unreadable PR: exit 2", rc == 2, out)

        print("arm: another project's rules — InterWeave's arm.json, through the shim")
        iw = {"AGENT_FABRIC_ARM_CONFIG": IW_CONFIG}
        for path in ("crates/identity/profile-identity/src/lib.rs", "crates/human/store/src/lib.rs",
                     "architecture/contracts/schemas/human-chat/envelope.schema.json",
                     "crates/transport/libp2p/src/dialing.rs", "apps/transportctl/src/phrase.rs"):
            reset(); set_pr(me, "plain", [path]); set_gate(9)
            rc, out = run("7", "--basis", "b", script=SHIM, env=iw)
            check(f"InterWeave: {path} is a boundary", rc == 1 and "no review-class review" in out, out)
        reset(); set_pr(me, "plain", ["infra/db/migrations/0053_x.sql", "architecture/adr/0050-x.md",
                                      "crates/identity/profile-identity/README.md", "tools/checks/check_x.sh",
                                      "crates/human/ui-slint/src/lib.rs"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, env=iw)
        check("InterWeave: gzapp's migrations, prose, a crate README, tooling and the UI are not",
              rc == 0 and "not a security-boundary change" in out, out)
        reset(); set_pr(me, "Class: docs-only", ["architecture/adr/0050-x.md"]); set_gate(2)
        rc, out = run("7", "--basis", "b", script=SHIM, env=iw)
        check("InterWeave has no classes: a stated docs-only under 8 still asks the owner",
              rc == 1 and "none in this project" in out, out)

        print("arm: a project with no arm.json")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, env={"AGENT_FABRIC_ARM_CONFIG": f"{sandbox}/none.json"})
        check("no arm.json: exit 2, the boundary never judged absent",
              rc == 2 and "declares no arm.json" in out and "pr merge" not in calls(), out)
        reset(); put("bad.json", '{"boundary": {"paths": "("}}')
        rc, out = run("7", "--basis", "b", script=SHIM, env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/bad.json"})
        check("an arm.json whose pattern does not compile: exit 2", rc == 2 and "not a usable arm.json" in out, out)
        reset(); set_pr("develop-qzapp/other/feat/x", "plain", ["docs/a.md"])
        rc, out = run("7", "--basis", "b", script=SHIM, env={"AGENT_FABRIC_ARM_CONFIG": f"{sandbox}/none.json"})
        check("…but gates 1–3 refuse without one", rc == 1 and "not this session's" in out, out)

    print("test_arm_cli: " + ("OK" if not fails else f"FAILED — {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
