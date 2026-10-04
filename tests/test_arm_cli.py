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
    print("noslash" if has("badrepo") else "gzapi-org/gzapp"); sys.exit(0)
if line.startswith("api repos/gzapi-org/gzapp/pulls/7/files") and "--paginate --slurp" in line:
    def entry(f):
        old, _, new = f.rpartition("->")
        return {"filename": new, "previous_filename": old} if old else {"filename": f}
    print(json.dumps([[entry(f) for f in pr["files"]]])); sys.exit(0)
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

# The waiver's two readers, from state files: the relay's replay
# (`waiver.out` printed, `waiver_rc` its exit) and fabric-ctl's presence
# (`presence.out`, `ctl_rc`). Each call is recorded, prefixed, so a test
# can say whether it was asked at all.
INBOX_MOCK = r'''#!/usr/bin/env python3
import os, sys
s = os.environ["MOCK_STATE"]
rd = lambda n, d="": open(os.path.join(s, n)).read() if os.path.exists(os.path.join(s, n)) else d
with open(os.path.join(s, "calls"), "a") as fh:
    fh.write("replay " + " ".join(sys.argv[1:]) + "\n")
sys.stdout.write(rd("waiver.out")); sys.exit(int(rd("waiver_rc", "0") or 0))
'''
CTL_MOCK = r'''#!/usr/bin/env python3
import os, sys
s = os.environ["MOCK_STATE"]
rd = lambda n, d="": open(os.path.join(s, n)).read() if os.path.exists(os.path.join(s, n)) else d
with open(os.path.join(s, "calls"), "a") as fh:
    fh.write("ctl " + " ".join(sys.argv[1:]) + "\n")
sys.stdout.write(rd("presence.out")); sys.exit(int(rd("ctl_rc", "0") or 0))
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
        for name, text in (("gh", GH_MOCK), ("pr-gate", GATE_MOCK), ("pr-review-status", REVIEW_MOCK),
                           ("gzcoord-inbox", INBOX_MOCK), ("fabric-ctl", CTL_MOCK)):
            with open(f"{bindir}/{name}", "w") as fh:
                fh.write(text)
            os.chmod(f"{bindir}/{name}", 0o755)

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w") as fh:
                fh.write(text)

        def reset() -> None:
            for n in ("calls", "armed", "queued", "viewfail", "blind", "independent", "unresolved", "no_blind_field", "badrepo",
                      "waiver.out", "waiver_rc", "presence.out", "ctl_rc"):
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

        def run(*args: str, script: str = GZAPP, env: dict | None = None, cwd: str = sandbox) -> tuple[int, str]:
            e = dict(base_env, MOCK_STATE=state, PATH=f"{bindir}:{base_env.get('PATH', '')}",
                     GZAPP_PR_GATE=f"{bindir}/pr-gate", GZAPP_PR_REVIEW_STATUS=f"{bindir}/pr-review-status",
                     GZAPP_PR_SESSION="develop-qzapp/me", AGENT_FABRIC_GZCOORD_INBOX=f"{bindir}/gzcoord-inbox",
                     AGENT_FABRIC_CTL=f"{bindir}/fabric-ctl")
            if script == SHIM:
                # The shim reads the fabric's names; only gzapp's forwarder maps GZAPP_*.
                e.update(AGENT_FABRIC_PR_GATE=e.pop("GZAPP_PR_GATE"), AGENT_FABRIC_PR_SESSION=e.pop("GZAPP_PR_SESSION"),
                         AGENT_FABRIC_PR_REVIEW_STATUS=e.pop("GZAPP_PR_REVIEW_STATUS"))
            e.update(env or {})
            r = subprocess.run(["bash", script, *args], env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, text=True, timeout=120, cwd=cwd)
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
        reset(); set_pr(me, "plain", ["apps/backend_dotnet/src/Gzapp.Infrastructure/Auth/Tokens.cs->docs/tokens.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b")
        check("a file renamed OUT of a boundary directory is judged by its old name too",
              rc == 1 and "no review-class review" in out, out)

        print("arm: gate 4 — a waiver, read from the relay and checked against the fabric")
        cto, mid = "develop-qzapp/architect-cto-01", "01a10593-0000-7000-8000-00000000c7f0"
        with open(os.path.join(ROOT, "projects", "gzapp", "integration", "gh", "arm.json")) as fh:
            rules = json.load(fh)
        rules["waiver_role"] = "architect-cto"
        put("waiver-rules.json", json.dumps(rules))
        rules.pop("waiver_role")
        put("no-waiver-rules.json", json.dumps(rules))
        wenv = {"AGENT_FABRIC_ARM_CONFIG": f"{state}/waiver-rules.json"}

        waives = f"gzapi-org/gzapp#7@{HEAD[:8]}"

        def set_waiver(addressed: bool = True, typ: str = "DECISION", sender: str = cto, frm: str | None = None,
                       role_line: str = "architect-cto", text: str = "Waived for #7: comment-only DDL.",
                       line: str | None = waives, to: str | None = "develop-qzapp/me", extra: dict | None = None,
                       message_id: str | None = mid) -> None:
            if not addressed:
                put("waiver.out", json.dumps({"addressed": False, "seq": 4242}) + "\n"); put("waiver_rc", "2"); return
            meta = {"FROM": frm if frm is not None else sender, "ROLE": role_line, "PROJECT": "gzapp"}
            if to is not None:
                meta["TO"] = to
            if message_id is not None:
                meta["MESSAGE-ID"] = message_id
            if line is not None:
                meta["WAIVES"] = line
            meta.update(extra or {})
            put("waiver.out", json.dumps({"addressed": True, "seq": 4242, "sender": sender, "when": "t", "type": typ,
                                          "metadata": meta, "text": f"[GZCOORD/1] {typ}\n" + text}) + "\n")
            put("waiver_rc", "0")

        def set_presence(role: str | None = "architect-cto", account: str = "architect-cto-01",
                         host: str = "develop-qzapp", status: str = "ok", pstatus: str = "ok") -> None:
            put("presence.out", json.dumps({"account": account, "host": host, "status": status, "op": "presence",
                                            "presence": {"status": pstatus, "online": True, "role": role}}) + "\n")

        why = "comment-only DDL"

        def waive(*extra: str, basis: str = "nine at the gate", env: dict | None = None) -> tuple[int, str]:
            return run("7", "--basis", basis, "--no-boundary", why, "--waiver", mid, *extra, env=env or wenv)

        reset(); set_pr(me, "plain", mig); set_gate(9)
        rc, out = run("7", "--basis", "the owner's word", "--no-boundary", why, env=wenv)
        check("--no-boundary without --waiver: exit 2, nothing armed", rc == 2 and "come together" in out
              and "pr merge" not in calls(), out)
        rc, out = run("7", "--basis", "b", "--waiver", mid, env=wenv)
        check("--waiver without --no-boundary: exit 2", rc == 2 and "come together" in out, out)
        rc, out = run("7", "--basis", "b", "--no-boundary", why, "--waiver", env=wenv)
        check("--waiver with no value: exit 2", rc == 2 and "--waiver needs" in out, out)

        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive()
        check("a waiver from the role's holder, addressed here, naming the PR: armed",
              rc == 0 and "boundary gate WAIVED by architect-cto-01" in out and "ARMED #7" in out, out)
        check("…the comment records the login, the message and the reason",
              f"Boundary gate waived by architect-cto-01 ({mid}): {why}." in calls(), calls())
        check("…the replay asked by the id given, the role asked of fabric-ctl for the sender's login",
              f"replay --replay {mid} --json" in calls() and "ctl architect-cto-01 presence --json" in calls(), calls())
        check("…no review asked and no owner's word needed", not any(l[:1].isdigit() for l in calls().splitlines())
              and "owner's word" not in out, calls())
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = run("7", "--basis", "b", "--no-boundary", why, "--waiver", "4242", env=wenv)
        check("a waiver named by relay seq: the comment records its MESSAGE-ID", rc == 0
              and f"waived by architect-cto-01 ({mid})" in calls(), calls())
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(line=f"GZAPI-ORG/GZAPP#7@{HEAD[:16].upper()}"); set_presence()
        rc, out = waive(); check("WAIVES: the repository case-insensitive, a longer head prefix in capitals", rc == 0, out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive("--dry-run")
        check("a dry run checks the waiver and posts nothing", rc == 0 and "WAIVED" in out and "pr comment" not in calls()
              and "replay --replay" in calls(), out)

        for label, setup, said in (
                ("not addressed to this session", lambda: set_waiver(addressed=False), "not addressed to this session"),
                ("an INFO, not a DECISION or REPLY", lambda: set_waiver(typ="INFO"), "not a DECISION or REPLY"),
                ("a REQUEST", lambda: set_waiver(typ="REQUEST"), "not a DECISION or REPLY"),
                ("a FROM other than the relay's sender", lambda: set_waiver(frm="develop-qzapp/me"), "says FROM"),
                ("declining #7, with no WAIVES line", lambda: set_waiver(text="I do NOT waive #7.", line=None), "has no WAIVES"),
                ("whose WAIVES line names another PR", lambda: set_waiver(line=f"gzapi-org/gzapp#70@{HEAD[:8]}"),
                 "WAIVES gzapi-org/gzapp#70, not gzapi-org/gzapp#7"),
                ("whose WAIVES line names another repository", lambda: set_waiver(line=f"gzapi-org/other#7@{HEAD[:8]}"),
                 "WAIVES gzapi-org/other#7, not"),
                ("for an earlier head", lambda: set_waiver(line="gzapi-org/gzapp#7@12345678"),
                 "WAIVES head 12345678, and #7's head is now abcdef012345"),
                ("whose head is under 8 hex", lambda: set_waiver(line=f"gzapi-org/gzapp#7@{HEAD[:7]}"), "has no WAIVES"),
                ("with the WAIVES text in its body only", lambda: set_waiver(text=f"WAIVES: {waives}", line=None), "has no WAIVES"),
                ("sent to the role, not to this login", lambda: set_waiver(to=None, extra={"TO-ROLE": "python-dev"}),
                 "not sent TO develop-qzapp/me (a broadcast or a role address)"),
                ("broadcast", lambda: set_waiver(to=None, extra={"BROADCAST": "true"}), "a broadcast or a role address"),
                ("sent TO another login", lambda: set_waiver(to="develop-qzapp/other"), "(TO develop-qzapp/other)"),
                ("from the arming session itself", lambda: set_waiver(sender="develop-qzapp/me"), "the session arming")):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_presence(); setup()
            rc, out = waive()
            check(f"a waiver {label}: refused, nothing armed", rc == 1 and said in out and "pr merge" not in calls()
                  and "pr comment" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(sender="develop-qzapp/backend-dev-01")
        set_presence(role="backend-dev", account="backend-dev-01")
        rc, out = waive()
        check("a sender holding another role, its ROLE line claiming architect-cto: refused — the fabric's record wins",
              rc == 1 and "who holds backend-dev, not architect-cto" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence(role=None)
        rc, out = waive(); check("a sender holding no role: refused", rc == 1 and "holds no role" in out, out)

        for label, setup in (
                ("the replay finds no message (exit 1, no JSON)", lambda: (put("waiver.out", ""), put("waiver_rc", "1"))),
                ("the relay is down (exit 0, no JSON)", lambda: (put("waiver.out", "gzcoord: relay unreachable\n"), put("waiver_rc", "0"))),
                ("a refused token (exit 4)", lambda: (put("waiver.out", ""), put("waiver_rc", "4"))),
                ("JSON with no addressed field", lambda: (put("waiver.out", '{"seq": 1}'), put("waiver_rc", "0"))),
                ("addressed, with a failing exit", lambda: (set_waiver(), put("waiver_rc", "1"))),
                ("not addressed, with exit 0", lambda: (set_waiver(addressed=False), put("waiver_rc", "0")))):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_presence(); setup()
            rc, out = waive()
            check(f"{label}: exit 2, nothing posted", rc == 2 and "could not be read from the relay" in out
                  and "pr comment" not in calls() and "pr merge" not in calls(), out)
        for label, setup in (
                ("fabric-ctl fails", lambda: (set_presence(), put("ctl_rc", "3"))),
                ("fabric-ctl says no answer", lambda: set_presence(status="no answer")),
                ("presence could not be read", lambda: set_presence(pstatus="error")),
                ("presence for another host", lambda: set_presence(host="far-host")),
                ("presence for another account", lambda: set_presence(account="architect-cto-02")),
                ("fabric-ctl prints nothing", lambda: put("presence.out", ""))):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); setup()
            rc, out = waive()
            check(f"{label}: exit 2, the role unread is not a refusal nor a pass", rc == 2
                  and "could not say which role" in out and "pr merge" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
        rc, out = waive(env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/no-waiver-rules.json"})
        check("an arm.json with no waiver_role: exit 2, and the relay not asked", rc == 2 and "names no waiver_role" in out
              and "replay" not in calls() and "pr merge" not in calls(), out)
        put("bad-role.json", json.dumps(dict(rules, waiver_role="")))
        rc, out = waive(env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/bad-role.json"})
        check("a waiver_role that is not a slug: exit 2", rc == 2 and "not a usable arm.json" in out, out)
        for bad in (" architect-cto", "Architect CTO", "ghost-role"):
            reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(); set_presence()
            put("bad-role.json", json.dumps(dict(rules, waiver_role=bad)))
            rc, out = waive(env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/bad-role.json"})
            check(f"waiver_role {bad!r}, not a catalogue slug: exit 2, the relay not asked",
                  rc == 2 and "is not a role of identities/roles/catalog.json" in out and "replay" not in calls(), out)
        reset(); set_pr(me, "plain", mig); set_gate(9); set_waiver(message_id=None); set_presence()
        rc, out = run("7", "--basis", "b", "--no-boundary", why, "--waiver", "4242", env=wenv)
        check("a waiver with no MESSAGE-ID: exit 2, never recorded under the seq typed",
              rc == 2 and "carries no MESSAGE-ID" in out and "pr comment" not in calls(), out)

        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); set_waiver(addressed=False)
        rc, out = waive()
        check("a waiver on a PR that matched no boundary: armed, said, not read", rc == 0
              and "the waiver " + mid + " is not needed, not read, and not recorded" in out
              and "replay" not in calls() and "ctl " not in calls(), out)
        check("…and the comment carries no waiver", "pr comment 7 --body Arming basis: nine at the gate — 9 work commits,"
              " head abcdef01.\n" in calls() and "waived" not in calls(), calls())
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); set_waiver(); set_presence()
        rc, out = run("7", "--basis", "b", "--boundary", "--no-boundary", why, "--waiver", mid, env=wenv)
        check("--boundary with a waiver still contradicts: exit 2", rc == 2 and "contradict" in out, out)

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
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9); put("badrepo", "")
        rc, out = run("7", "--basis", "b")
        check("an answer of a shape gh never gave (a repository with no owner): exit 2, never 1, nothing armed",
              rc == 2 and "unexpected answer" in out and "pr merge" not in calls(), out)

        print("arm: another project's rules — InterWeave's arm.json, through the shim")
        iw = {"AGENT_FABRIC_ARM_CONFIG": IW_CONFIG}
        for path in ("crates/identity/profile-identity/src/lib.rs", "crates/human/store/src/lib.rs",
                     "architecture/contracts/schemas/human-chat/envelope.schema.json",
                     "crates/transport/libp2p/src/dialing.rs", "apps/transportctl/src/phrase.rs",
                     "crates/discovery/kademlia/src/budgets.rs", "crates/discovery/cache/src/record.rs",
                     "crates/human/core/src/retention.rs", "architecture/config/config.schema.yaml",
                     "architecture/config/examples/kademlia-enabled.yaml",
                     "fixtures/identity/ed25519-bip39-entropy-v1.json", "Cargo.toml", ".cargo/config.toml",
                     ".cargo/config", "crates/human/ui-slint/.cargo/config.toml",
                     "tools/foo/.cargo/config.toml", "xtask/.cargo/config",
                     "deny.toml", "crates/claude/channel-core/src/lib.rs", "apps/claude-channel/src/main.rs",
                     "apps/human-desktop/src/recovery_seed.rs"):
            reset(); set_pr(me, "plain", [path]); set_gate(9)
            rc, out = run("7", "--basis", "b", script=SHIM, env=iw)
            check(f"InterWeave: {path} is a boundary", rc == 1 and "no review-class review" in out, out)
        reset(); set_pr(me, "plain", ["infra/db/migrations/0053_x.sql", "architecture/adr/0050-x.md",
                                      "crates/identity/profile-identity/README.md", "tools/checks/check_x.sh",
                                      "crates/human/ui-slint/Cargo.toml", "Cargo.lock", "fixtures/README.md", "crates/human/client-api/src/lib.rs",
                                      "crates/human/ui-slint/src/lib.rs"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, env=iw)
        check("InterWeave: gzapp's migrations, prose, a crate README, tooling, the UI, a crate manifest, the lockfile and the fixtures' README are not",
              rc == 0 and "not a security-boundary change" in out, out)
        reset(); set_pr(me, "Class: docs-only", ["architecture/adr/0050-x.md"]); set_gate(2)
        rc, out = run("7", "--basis", "b", script=SHIM, env=iw)
        check("InterWeave has no classes: a stated docs-only under 8 still asks the owner",
              rc == 1 and "none in this project" in out, out)

        print("arm: the rules found from the clone's remote, AGENT_FABRIC_ARM_CONFIG unset")
        reg = json.load(open(os.path.join(ROOT, "projects", "registry.json")))
        iw_remote = (reg.get("projects") or reg)["interweave"]["remotes"][0]
        clones = {}
        for name, url in (("iw", iw_remote), ("stranger", "git@github.com:nobody/unregistered.git")):
            d = f"{sandbox}/{name}"
            subprocess.run(["git", "init", "-q", d], env=base_env, check=True, timeout=30)
            subprocess.run(["git", "-C", d, "remote", "add", "origin", url], env=base_env, check=True, timeout=30)
            clones[name] = d
        reset(); set_pr(me, "plain", ["crates/transport/libp2p/src/dialing.rs"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, cwd=clones["iw"])
        check("a clone of InterWeave is judged by InterWeave's rules (transport is a boundary there, not in gzapp's)",
              rc == 1 and "no review-class review" in out, out)
        reset(); set_pr(me, "plain", ["infra/db/migrations/0053_x.sql"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, cwd=clones["iw"])
        check("…and not by gzapp's (a migrations path is not InterWeave's boundary)",
              rc == 0 and "not a security-boundary change" in out, out)
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, cwd=clones["stranger"])
        check("a clone of an unregistered remote: exit 2, nothing armed",
              rc == 2 and "no project found" in out and "pr merge" not in calls(), out)

        print("arm: a project with no arm.json")
        reset(); set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, env={"AGENT_FABRIC_ARM_CONFIG": f"{sandbox}/none.json"})
        check("no arm.json: exit 2, the boundary never judged absent",
              rc == 2 and "declares no arm.json" in out and "pr merge" not in calls(), out)
        reset(); put("narrowed.json", json.dumps({"boundary": {"paths": "^src/", "cases": ["src/a.rs", "keys/k.rs"]}}))
        set_pr(me, "plain", ["docs/a.md"]); set_gate(9)
        rc, out = run("7", "--basis", "b", script=SHIM, env={"AGENT_FABRIC_ARM_CONFIG": f"{state}/narrowed.json"})
        check("a boundary case its own patterns miss: exit 2, nothing armed, the case named",
              rc == 2 and "keys/k.rs" in out and "pr merge" not in calls(), out)
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
