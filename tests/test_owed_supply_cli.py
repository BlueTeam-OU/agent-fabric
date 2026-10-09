#!/usr/bin/env python3
"""fabric-pr owed-supply, through the shim with gh mocked on PATH.
Ported case for case from a managed project's tools/gh/test_owed-supply.sh
(its script the oracle, ADR-040 §5): a supply branch is owed, claimed or
landed, and "I could not find out" (exit 2) must never be read as "nothing
owed" (exit 0). Then what the port changed or adds: the repository from
GH_REPO or origin, the default branch unread as exit 2, gh's own error
line, no jq, and what jq used to absorb (a null title, a lone surrogate, a
clock ahead of the commit). Plain script: prints ok/FAIL, exit 1 on any
failure."""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [os.path.join(ROOT, "bin", "fabric-pr"), "owed-supply"]
REPO = "gzapi-org/gzapp"

# gh as gh.py calls it: `api <path> --method GET [--paginate --slurp]` and
# `pr list ... --json ...`. State in $MOCK_STATE: branches.json, prs.json,
# commits.json ({sha: date}); ancestors, unrelated, body404, proxyfail,
# err500 (lines "<base> <head>" for compare); fail (an endpoint to fail:
# branches, prs, repo, repo_nofield, compare); calls (every call, appended).
GH = r'''#!@PYTHON@
import json, os, sys
S = os.environ["MOCK_STATE"]
args = sys.argv[1:]
with open(os.path.join(S, "calls"), "a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\n")
def read(name, default=""):
    try:
        with open(os.path.join(S, name), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return default
def lines(name):
    return {l.strip() for l in read(name).splitlines() if l.strip()}
fail = read("fail").strip()
R = "repos/gzapi-org/gzapp"
if args[:2] == ["pr", "list"]:
    if fail == "prs":
        sys.exit(1)
    print(read("prs.json", "[]")); sys.exit(0)
if args[:1] == ["api"]:
    path = args[1]
    if path.startswith(R + "/branches?"):
        if fail == "branches":
            print("gh: Server Error (HTTP 502)", file=sys.stderr); sys.exit(1)
        raw = read("branches.json", "[]")
        print(raw if fail == "branches_raw" else json.dumps([json.loads(raw)])); sys.exit(0)
    if path == R:
        if fail == "repo":
            print('{"message":"Bad credentials","status":"401"}')
            print("gh: Bad credentials (HTTP 401)", file=sys.stderr); sys.exit(1)
        print(json.dumps({} if fail == "repo_nofield" else {"default_branch": read("default", "main").strip()}))
        sys.exit(0)
    if path.startswith(R + "/compare/"):
        pair = " ".join(path[len(R + "/compare/"):].split("...", 1))
        if fail == "compare":
            print('{"message":"API rate limit exceeded","status":"403"}', file=sys.stderr); sys.exit(1)
        if pair in lines("ancestors"):
            print('{"behind_by":0}'); sys.exit(0)
        if pair in lines("unrelated"):
            print("gh: No common ancestor between x and y. (HTTP 404)", file=sys.stderr); sys.exit(1)
        if pair in lines("body404"):
            print('{"message":"Not Found","status":"404"}'); print("gh: Not Found", file=sys.stderr); sys.exit(1)
        if pair in lines("proxyfail"):
            print('Get "https://api.github.com/' + R + '/compare/' + pair.replace(" ", "...")
                  + '": proxyconnect tcp: dial tcp 127.0.0.1:1: connect: connection refused', file=sys.stderr)
            sys.exit(1)
        if pair in lines("err500"):
            print('{\n  "message": "Server Error"\n}'); print("gh: Server Error (HTTP 500)", file=sys.stderr)
            sys.exit(1)
        print('{"behind_by":3}'); sys.exit(0)
    if path.startswith(R + "/commits/"):
        sha = path.rsplit("/", 1)[1]
        date = json.loads(read("commits.json", "{}")).get(sha)
        print(json.dumps({"commit": {"committer": {} if date is None else {"date": date}}})); sys.exit(0)
print("mock gh: unhandled: " + " ".join(args), file=sys.stderr)
sys.exit(1)
'''


def ago(days: float = 0, hours: float = 0) -> str:
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days, hours=hours)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(prefix: str, n: int) -> str:
    return (prefix + "0" * 40)[:39] + str(n)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        bin_, state, work = (os.path.join(sandbox, d) for d in ("bin", "state", "work"))
        for d in (bin_, state, work):
            os.makedirs(d)
        with open(os.path.join(bin_, "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH.replace("@PYTHON@", sys.executable))
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        # PATH is the sandbox alone: bash for the shim's shebang and the
        # mock gh. No jq, no git — the port needs neither with GH_REPO set.
        os.symlink(shutil.which("bash") or "/bin/bash", os.path.join(bin_, "bash"))
        # fabric-pr finds its checkout with these two; the old shim used builtins only.
        for tool in ("dirname", "readlink"):
            os.symlink(shutil.which(tool), os.path.join(bin_, tool))
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_"))}
        base.update(PATH=bin_, MOCK_STATE=state, GH_REPO=REPO, HOME=sandbox)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
        out = {"text": "", "rc": -1, "stdout": ""}

        def put(name: str, text: str) -> None:
            with open(os.path.join(state, name), "w", encoding="utf-8") as fh:
                fh.write(text)

        def set_state(branches: list, prs: list, ancestors: str = "", commits: dict | None = None) -> None:
            for name in os.listdir(state):
                os.remove(os.path.join(state, name))
            put("branches.json", json.dumps(branches))
            put("prs.json", json.dumps(prs))
            put("ancestors", ancestors + "\n")
            put("commits.json", json.dumps(commits or {}))

        def run(*args: str, unset: tuple[str, ...] = (), **env: str) -> None:
            e = {k: v for k, v in dict(base, **env).items() if k not in unset}
            r = subprocess.run([*TOOL, *args], env=e, cwd=work, capture_output=True, text=True, timeout=120)
            out["text"], out["rc"], out["stdout"] = r.stdout + r.stderr, r.returncode, r.stdout

        def calls() -> str:
            try:
                with open(os.path.join(state, "calls"), encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def has(label: str, text: str, rc: int | None = 0) -> None:
            check(label, (rc is None or out["rc"] == rc) and text in out["text"],
                  f"want exit {rc} and {text!r}; got exit {out['rc']}\n{out['text']}")

        def lacks(label: str, text: str) -> None:
            check(label, text not in out["text"], f"output unexpectedly contained {text!r}\n{out['text']}")

        def doc() -> dict:
            try:
                return json.loads(out["stdout"])
            except ValueError:
                return {}

        def lines_matching(prefix: str) -> list[str]:
            return [l for l in out["text"].splitlines() if l.startswith(prefix)]

        print("owed-supply: the three states of a supply branch")
        a, b, c, d, e, f = (sha(p, i) for i, p in enumerate(("aaaa", "bbbb", "cccc", "dddd", "eeee", "ffff"), 1))
        three = ([{"name": "develop-qzapp/language-culture-ge/for/web-dev-01/picker-copy", "commit": {"sha": a}},
                  {"name": "develop-qzapp/db-admin/for/backend-dev-02/0051-reader", "commit": {"sha": b}},
                  {"name": "develop-qzapp/devex-tooling/for/domain-transit/stub-check", "commit": {"sha": c}},
                  {"name": "develop-qzapp/web-dev-01/feat/picker", "commit": {"sha": d}},
                  {"name": "main", "commit": {"sha": e}}],
                 [{"number": 901, "headRefName": "develop-qzapp/language-culture-ge/for/web-dev-01/picker-copy",
                   "headRefOid": a},
                  {"number": 902, "headRefName": "develop-qzapp/backend-dev-02/feat/0051", "headRefOid": f}],
                 f"{b} {f}", {c: ago(3), a: ago(1), b: ago(2)})
        set_state(*three)
        run()
        has("one of three is owed: the one reachable from no open PR", "1 supply branch(es)")
        has("…and it is stub-check", "stub-check")
        lacks("a supply branch that IS an open PR's head is not owed", "picker-copy")
        lacks("a supply branch whose head is an ancestor of an open PR's head (folded) is not owed", "0051-reader")
        lacks("branches of another shape are never listed", "feat/picker")
        lacks("…nor main", " main\n")
        check("the row carries age, PAST, supplier, caller, head and branch",
              "  3d    PAST      devex-tooling      domain-transit     cccc0000  "
              "develop-qzapp/devex-tooling/for/domain-transit/stub-check" in out["text"].splitlines(), out["text"])
        has("the header says where the FOLD-BY date lives", "FOLD-BY date is in the hand-off message")
        check("the table header is the bash's printf",
              "  AGE   FOLD-BY   SUPPLIER           CALLER             HEAD      BRANCH" in out["text"].splitlines(),
              out["text"])

        print("owed-supply: --days and --json")
        run("--days", "5")
        has("--days 5 hides the 3-day-old branch and says so", "no supply branch older than 5 day(s) is unclaimed")
        run("--days", "2")
        has("--days 2 keeps it", "stub-check")
        run("--days", "08")
        has("--days 08 is decimal 8, said as written", "no supply branch older than 08 day(s) is unclaimed")
        run("--json")
        owed = doc().get("owed") or [{}]
        check("--json carries the same row as data", out["rc"] == 0 and len(owed) == 1 and owed[0] == {
            "branch": "develop-qzapp/devex-tooling/for/domain-transit/stub-check", "head": c,
            "supplier": "devex-tooling", "caller": "domain-transit", "committed": three[3][c],
            "age_days": 3, "past_default_fold_by": True}, out["text"])
        check("--json is indented as jq printed it", out["stdout"].startswith('{\n  "owed": [\n    {\n'),
              out["stdout"])
        for bad in (["--days", "x"], ["--days"], ["--days", "-1"], ["--days", "٣"], ["--days", "5\n"]):
            run(*bad)
            has(f"--days {bad[1:]!r}: a usage error", "owed-supply: --days needs a whole number", rc=2)
        run("--bogus")
        has("an unknown option is a usage error", "owed-supply: unknown option '--bogus' (try --help)", rc=2)
        run("--bogus", "--help")
        check("…read in order: the bad word before --help still refuses", out["rc"] == 2, out["text"])

        print("owed-supply: the empty states are said, not silent")
        set_state([{"name": "main", "commit": {"sha": e}}], [])
        run()
        has("no supply branch at all: said", f"no supply branches on {REPO}")
        run("--json")
        check("…and --json prints empty owed, landed and awaiting, on one line as jq -c did",
              out["rc"] == 0 and out["stdout"] == '{"owed":[],"landed":[],"awaiting":[]}\n', out["text"])
        check("…with no default branch asked", f"api repos/{REPO} --method GET" not in calls(), calls())
        set_state([{"name": "h/s/for/c/x", "commit": {"sha": a}}],
                  [{"number": 1, "headRefName": "h/s/for/c/x", "headRefOid": a}])
        run()
        has("every supply branch claimed: nothing owed, said", "nothing owed")
        put("fail", "compare")
        run()
        has("a PR's own head is claimed without a compare", "nothing owed")

        print("owed-supply: landed, unrelated, and a compare that fails")
        one, two = sha("1111", 1), sha("2222", 2)
        set_state([{"name": "h/s/for/c/landed", "commit": {"sha": one}},
                   {"name": "h/s/for/c/fresh", "commit": {"sha": two}}], [],
                  f"{one} main\n{two} mainX", {two: "2026-09-01T00:00:00Z"})
        put("unrelated", f"{two} main\n")
        run()
        has("a branch reachable from the default branch is LANDED, said apart", "landed already (reachable from main")
        has("…by its head and name", "  11110000  h/s/for/c/landed")
        has("one with no common ancestor (404) is owed", "1 supply branch(es)")
        has("…and listed", "h/s/for/c/fresh")
        check("the landed branch is never an owed row",
              [l for l in lines_matching("  ") if "h/s/for/c/landed" in l] == ["  11110000  h/s/for/c/landed"],
              out["text"])
        run("--json")
        check("--json carries owed and landed apart",
              len(doc().get("landed", [])) == 1 and len(doc().get("owed", [])) == 1
              and doc()["landed"][0] == {"branch": "h/s/for/c/landed", "head": one}, out["text"])
        put("default", "trunk\n")
        put("ancestors", f"{one} trunk\n")
        put("unrelated", f"{two} trunk\n")
        run()
        has("the default branch is the repository's, not main", "landed already (reachable from trunk")
        x404 = "abc4040000000000000000000000000000000001"
        set_state([{"name": "h/s/for/c/x404y", "commit": {"sha": x404}}], [])
        put("proxyfail", f"{x404} main\n")
        run()
        has("a transport failure mentioning a sha that contains 404 is could-not-run",
            f"owed-supply: cannot run — the compare for {x404}...main failed: ", rc=2)
        put("fail", "compare")
        run()
        has("a compare failing for any reason but 404 (a rate limit): exit 2, never 'owed'",
            "cannot run — the compare", rc=2)
        lacks("…and no row", "supply branch(es)")
        set_state([{"name": "h/s/for/c/e", "commit": {"sha": x404}}], [])
        put("err500", f"{x404} main\n")
        run()
        has("the failure names gh's own error line, never the '{' of the body gh printed",
            f"the compare for {x404}...main failed: gh: Server Error (HTTP 500)", rc=2)
        set_state([{"name": "h/s/for/c/b", "commit": {"sha": x404}}], [], "", {x404: ago(2)})
        put("body404", f"{x404} main\n")
        run()
        has("a 404 named only in the error body is still unrelated, so owed", "1 supply branch(es)")

        print("owed-supply: a missing date is '?' not a crash; a failing gh is exit 2")
        nodate = sha("abab", 9)
        set_state([{"name": "h/s/for/c/nodate", "commit": {"sha": nodate}}], [])
        run()
        check("no committer date: age '?', FOLD-BY '?', still listed",
              out["rc"] == 0 and any(l.split()[:5] == ["?", "?", "s", "c", "abab0000"] for l in lines_matching("  ")),
              out["text"])
        run("--days", "1")
        has("…and --days keeps a branch whose age is unknown (unknown is not young)", "nodate")
        run("--json")
        check("…and --json says committed '' with age and FOLD-BY null",
              doc().get("owed", [{}])[0].get("committed") == "" and doc()["owed"][0]["age_days"] is None
              and doc()["owed"][0]["past_default_fold_by"] is None, out["text"])
        put("commits.json", json.dumps({nodate: "not a date"}))
        run()
        check("a date that does not parse is '?' too",
              out["rc"] == 0 and any(l.split()[:2] == ["?", "?"] for l in lines_matching("  ")), out["text"])
        put("fail", "branches")
        run()
        has("branches endpoint failing: exit 2", f"owed-supply: could not list branches of {REPO}", rc=2)
        put("fail", "branches_raw")
        put("branches.json", json.dumps([[{"name": 7}]]))
        run()
        has("a branch list that is not names: exit 2, never a traceback", "could not list branches", rc=2)
        lacks("…no traceback", "Traceback")
        put("branches.json", json.dumps([{"name": "h/s/for/c/nodate", "commit": {"sha": nodate}}]))
        put("fail", "prs")
        run()
        has("pr list failing: exit 2", "owed-supply: could not list open pull requests", rc=2)

        print("owed-supply: the default FOLD-BY is the next day")
        e5, f6, g7 = sha("eeee", 5), sha("ffff", 6), sha("9999", 7)
        set_state([{"name": "h/s1/for/c1/fresh", "commit": {"sha": e5}},
                   {"name": "h/s2/for/c2/stale", "commit": {"sha": f6}},
                   {"name": "h/s3/for/c3/ahead", "commit": {"sha": g7}}], [], "",
                  {e5: ago(hours=2), f6: ago(1), g7: ago(hours=-2)})
        run()
        check("two hours old: today", any(l.split()[:3] == ["0d", "today", "s1"] for l in lines_matching("  ")),
              out["text"])
        check("a day old: PAST the default", any(l.split()[:3] == ["1d", "PAST", "s2"] for l in lines_matching("  ")),
              out["text"])
        check("a commit two hours in the future is 0d today, truncated as bash did (never -1d)",
              any(l.split()[:3] == ["0d", "today", "s3"] for l in lines_matching("  ")), out["text"])
        run("--json")
        past = {r["supplier"]: r["past_default_fold_by"] for r in doc().get("owed", [])}
        check("--json carries past_default_fold_by per row", past == {"s1": False, "s2": True, "s3": False},
              out["text"])

        print("owed-supply: an open PR naming AWAITING-SUPPLY with no range line is AWAITING supply")
        set_state([], [
            {"number": 901, "headRefName": "h/a/feat/x", "headRefOid": sha("1111", 1), "title": "picker copy",
             "body": "Waiting on copy.\n\nAWAITING-SUPPLY: develop-qzapp/language-culture-ge\nAWAITING-SUPPLY: db-admin"
                     "\n\n3ebdb83a..9f00aa11: db-admin (db-admin)\n"},
            {"number": 902, "headRefName": "h/b/feat/y", "headRefOid": sha("2222", 2), "title": "folded already",
             "body": "- AWAITING-SUPPLY: web-dev-01\n\nranges: aaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)"},
            {"number": 903, "headRefName": "h/c/feat/z", "headRefOid": sha("3333", 3), "title": "no supply at all",
             "body": "plain body"},
            {"number": 904, "headRefName": "h/d/feat/w", "headRefOid": sha("4444", 4),
             "title": "a prefix login must not match",
             "body": "AWAITING-SUPPLY: web-dev\n\naaaaaaa1..bbbbbbb2: web-dev-01 (web-dev)"},
            {"number": 905, "headRefName": "h/e/feat/v", "headRefOid": sha("5555", 5), "title": None,
             "body": None}])
        run()
        has("#901: the login with no range line is listed, by its last address segment",
            "  #901  AWAITING-SUPPLY language-culture-ge  picker copy\n")
        lacks("#901: the login whose range line is present is not listed", "db-admin")
        lacks("#902: AWAITING-SUPPLY with its range line is not awaiting", "#902")
        lacks("#903: no AWAITING-SUPPLY, not listed", "#903")
        has("#904: a range line for web-dev-01 does not satisfy AWAITING-SUPPLY web-dev",
            "  #904  AWAITING-SUPPLY web-dev  a prefix login must not match\n")
        lacks("#905: a null body awaits nothing", "#905")
        has("the awaiting header says not to arm",
            "owed-supply: 2 open pull request(s) name a AWAITING-SUPPLY with no range line for it (supply asked for, "
            "not yet folded — do not arm):")
        has("…and the no-supply-branch line still prints alongside", "no supply branches on")
        run("--json")
        check("--json awaiting carries number and the unmet logins",
              [{k: r[k] for k in ("number", "awaiting_supply")} for r in doc().get("awaiting", [])]
              == [{"number": 901, "awaiting_supply": ["language-culture-ge"]},
                  {"number": 904, "awaiting_supply": ["web-dev"]}], out["text"])
        set_state([], [{"number": 7, "headRefName": "h/a/feat/x", "headRefOid": sha("1111", 1), "title": None,
                        "body": "AWAITING-SUPPLY: a.b\n\n1234567..89abcde: aXb (x)"},
                       {"number": 8, "headRefName": "h/b/feat/y", "headRefOid": sha("2222", 2),
                        "title": "half \ud800 a pair", "body": "AWAITING-SUPPLY: s"}])
        run()
        has("a login is matched literally (a.b is not met by aXb), and a null title prints as jq did",
            "  #7  AWAITING-SUPPLY a.b  null\n")
        has("a lone surrogate in a title is the replacement character, never a crash",
            "  #8  AWAITING-SUPPLY s  half \ufffd a pair\n")
        run("--json")
        check("…in --json too", out["rc"] == 0 and doc().get("awaiting", [{}, {}])[1].get("title")
              == "half \ufffd a pair" and doc()["awaiting"][0]["title"] is None, out["text"])

        print("owed-supply: what the port decides that the bash did not")
        set_state(*three)
        put("fail", "repo")
        run()
        has("the default branch unread is exit 2, never a fallback to main",
            f"owed-supply: cannot read the default branch of {REPO}: gh: Bad credentials (HTTP 401)", rc=2)
        lacks("…and no row is printed", "supply branch(es)")
        lacks("…nor a landed line", "landed already")
        put("fail", "repo_nofield")
        run("--json")
        has("an answer naming no default branch is exit 2 too",
            f"cannot read the default branch of {REPO}: the answer names none", rc=2)
        check("…with nothing on stdout", out["stdout"] == "", out["stdout"])
        os.remove(os.path.join(state, "fail"))
        run(unset=("GH_REPO",))
        has("no GH_REPO and no clone: the repository cannot be read, exit 2", "owed-supply: cannot read the repository: ",
            rc=2)
        check("…and gh is never asked for its default repository", "repo view" not in calls(), calls())
        run(GH_REPO="not a repo")
        has("a GH_REPO that is not <owner>/<repo>: exit 2", "owed-supply: cannot read the repository: GH_REPO is not",
            rc=2)
        os.remove(os.path.join(bin_, "gh"))
        run()
        has("no gh: exit 2", "owed-supply: gh is required", rc=2)
        with open(os.path.join(bin_, "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH.replace("@PYTHON@", sys.executable))
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        run()
        has("no jq on PATH and none needed", "1 supply branch(es)")
        put("fail", "compare")
        run(PYTHONIOENCODING="ascii", LANG="C", LC_ALL="C")
        has("an ASCII locale still writes its own em dash, as UTF-8", "owed-supply: cannot run — the compare", rc=2)
        set_state([{"name": "h/s/for/c/x", "commit": {"sha": a}}], [{"number": 1, "headRefName": "h/p/feat/1",
                                                                     "headRefOid": b},
                                                                    {"number": 2, "headRefName": "h/p/feat/2",
                                                                     "headRefOid": c}], f"{a} {b}")
        put("proxyfail", f"{a} {c}\n")
        run()
        has("the first PR that claims a branch ends the scan: a later compare is never asked", "nothing owed")
        check("…as the calls show", f"compare/{a}...{c}" not in calls(), calls())
        run("--help")
        check("--help is the module's docstring, citing the fabric's supply rule and the project's arm",
              out["rc"] == 0 and out["stdout"].startswith("fabric-pr owed-supply [--days N] [--json]\n")
              and "identities/prompt/team.md" in out["stdout"] and "the project's arm" in out["stdout"]
              and "CLAUDE.md" not in out["stdout"] and "tools/gh/arm.sh" not in out["stdout"], out["text"])
        run("--days", "x", "--help")
        has("…and a bad --days before it still refuses", "--days needs a whole number", rc=2)

    print("owed-supply: a call that times out fails that call (in-process)")
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "github"))
    import owed_supply as osu
    saved = osu.gh.api
    try:
        def slow(path: str, **_):
            raise osu.gh.GhError(f"gh api GET {path}", "no answer within 60 s", transient=True)
        osu.gh.api = slow
        try:
            osu.behind_by(REPO, "a" * 40, "main")
            check("a compare timing out refuses", False)
        except osu.Refusal as e:
            check("a compare timing out refuses, naming the bound",
                  str(e) == f"cannot run — the compare for {'a' * 40}...main failed: no answer within 60 s", str(e))
        check("a commit date timing out is unknown, not a failed run", osu.committed(REPO, "a" * 40) == "")
        try:
            osu.default_branch(REPO)
            check("a default-branch read timing out refuses", False)
        except osu.Refusal as e:
            check("a default-branch read timing out refuses", "cannot read the default branch" in str(e), str(e))
    finally:
        osu.gh.api = saved
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        osu.say_awaiting([])
    check("no awaiting rows print nothing", buf.getvalue() == "")
    check("age truncates toward zero both ways",
          osu.age_in_days("1970-01-02T00:00:00Z", 2 * 86400 - 1) == 0
          and osu.age_in_days("1970-01-03T00:00:00Z", 86400 + 1) == 0
          and osu.age_in_days("1970-01-01T00:00:00", 86400) == 1 and osu.age_in_days("", 0) is None)

    print(f"\ntest_owed_supply_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
