#!/usr/bin/env python3
"""fabric-pr post-review, driven through the real script with a
mocked `gh` on PATH. Ported from runtime/github/test_post-review.sh
(ADR-040 Wave 6), case for case.

What this exists to hold still: the MARKER. The review class's review is
authored by the same GitHub account as every other session's work, so
nothing but an exact marker distinguishes it from a thread reply — and
pr-review-status reads that exact string. A marker that drifts on one
side turns real review coverage back into "0 reviews", silently, which is
the failure this whole mechanism was built to end. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import glob
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

# Every git this suite starts, fixture or under test, reads none of the
# caller's ~/.gitconfig: set here, it reaches the calls that pass no env.
os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = ["bash", os.path.abspath(os.environ["POST_REVIEW"])] if os.environ.get("POST_REVIEW") else [os.path.join(ROOT, "bin", "fabric-pr"), "post-review"]
if not os.path.isfile(UNDER_TEST[1] if UNDER_TEST[0] == "bash" else UNDER_TEST[0]):
    sys.exit(f"test: script under test not found at {UNDER_TEST}")
# Both ends of the marker contract are Python modules, run as the commands
# every caller uses (fabric-pr post-review, fabric-pr review-status).
EMITTER = os.path.join(ROOT, "tools", "fabric", "github", "post_review.py")
READER = os.path.join(ROOT, "tools", "fabric", "github", "pr_review_status.py")
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from github.review_status.verdicts import head_covered  # noqa: E402 — the gate's own coverage test
from github import review_coverage as rcov  # noqa: E402
# The card and config every header below names; a case that needs the config the tool itself computes asks for it.
CARD, CONFIG = "5" * 40, "6" * 64

# The fake gh: the PR, its files as REST pages, and the POST, whose body is
# recorded so a case asserts on what was SENT, not on what the script said
# it would send.
GH_MOCK = r"""#!/usr/bin/env bash
S="$GH_STATE"
case "$1" in
  repo) echo "gzapi-org/gzapp"; exit 0 ;;
  pr)   cat "$S/pr.json"; exit 0 ;;
  api)
    # The merge-base of the PR with its base branch, as `--jq .merge_base_commit.sha` leaves it.
    case "$2" in */compare/*)
      [ -f "$S/mergebase" ] && { cat "$S/mergebase"; exit 0; }
      echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
    esac
    # gh.api_list: `api -i <path>`, the status line and headers, a blank line, the list.
    if [ "$2" = "-i" ]; then
      case "$3" in
        */reviews*) f="$S/reviews.json" ;;
        */commits*) f="$S/commits_flat.json" ;;
        *) f="" ;;
      esac
      [ -n "$f" ] && [ -f "$f" ] && { printf 'HTTP/2.0 200 OK\r\n\r\n'; cat "$f"; exit 0; }
      echo "gh: Not Found (HTTP 404)" >&2; exit 1
    fi
    if [ "$2" = "--paginate" ]; then
      case "$4" in */commits*)
        [ -f "$S/commits.json" ] && { cat "$S/commits.json"; exit 0; }
        echo '[{"message":"Not Found","documentation_url":"https://docs.github.com","status":"404"}]'
        echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
      esac
      [ -f "$S/files.json" ] && { cat "$S/files.json"; exit 0; }
      # As real gh does under --slurp: the error BODY on stdout, wrapped,
      # and a failing status (review of #70: stderr alone hid the case).
      echo '[{"message":"Not Found","documentation_url":"https://docs.github.com","status":"404"}]'
      echo "gh: Not Found (HTTP 404)" >&2; exit 1
    fi
    for a in "$@"; do
      [ "$prev" = "--input" ] && cp "$a" "$S/payload.json"
      prev="$a"
    done
    echo "POST $2" >> "$S/calls"
    [ -f "$S/api_fail" ] && { echo "gh: Validation Failed (HTTP 422)" >&2; exit 1; }
    [ -f "$S/api_empty" ] && { echo ""; exit 0; }
    echo "https://github.com/gzapi-org/gzapp/pull/1#pullrequestreview-1"
    exit 0 ;;
esac
echo "mock gh: unhandled $1" >&2; exit 1
"""


def rs_cfg():
    """The status reader's configuration for the account the cases post as: no posters, no verdict authors."""
    from github.review_status.config import read_config
    return read_config({})


def reader_marker() -> str:
    """The reader's REVIEW_MARKER, from the one file of pr_review_status.py
    and its parts (tools/fabric/github/review_status/) that defines it;
    none, or two, is no answer."""
    parts = sorted(glob.glob(os.path.join(os.path.dirname(READER), "review_status", "*.py")))
    found = [m for m in (marker_of(f) for f in [READER, *parts]) if m]
    return found[0] if len(found) == 1 else ""


def marker_of(path: str) -> str:
    """The REVIEW_MARKER constant as the source spells it, quotes dropped."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("REVIEW_MARKER = "):
                return line.split("=", 1)[1].strip().replace("'", "").replace('"', "")
    return ""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
    clone_name = "gzapp-testclone"
    # The session is the agent (login), not the clone directory; the
    # clone's name is still accepted as this session for older branches.
    me = f"{host}/{pwd.getpwuid(os.geteuid()).pw_name}"
    me_legacy = f"{host}/{clone_name}"
    other = f"{host}/gzapp-otherclone"

    with tempfile.TemporaryDirectory() as sandbox:
        clone, state = f"{sandbox}/{clone_name}", f"{sandbox}/state"
        for d in (clone, f"{sandbox}/bin", state):
            os.makedirs(d)
        subprocess.run(["git", "-C", clone, "init", "-q"], check=True, timeout=30, stderr=subprocess.DEVNULL, env=git_env())
        genv = git_env()

        def git(*args: str) -> str:
            r = subprocess.run(["git", "-C", clone, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                               capture_output=True, text=True, env=genv, timeout=60)
            if r.returncode:
                raise RuntimeError(f"git {args}: {r.stderr}")
            return r.stdout.strip()

        def commit(msg: str, files: dict) -> str:
            for name, text in files.items():
                path = os.path.join(clone, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            git("add", "-A")
            git("commit", "-q", "-m", msg)
            return git("rev-parse", "HEAD")

        # The PR's head, an older commit of it a report may have reviewed, and the merge-base both start from: real
        # commits, because a v2 report's range is checked in this clone.
        ROOT_C = commit("root", {"r.txt": "r\n"})
        OLD = commit("old", {"o.py": "o\n"})
        HEAD = commit("head", {"h.py": "h\n"})
        with open(f"{sandbox}/bin/gh", "w", encoding="utf-8") as fh:
            fh.write(GH_MOCK)
        os.chmod(f"{sandbox}/bin/gh", 0o755)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        # The repository the mock serves (gh.this_repo never reads gh's default).
        base["GH_REPO"] = "gzapi-org/gzapp"
        base.update(PATH=f"{sandbox}/bin:{base.get('PATH', '')}", GH_STATE=state)

        def drop(name: str) -> None:
            for n in {name, "commits_flat.json" if name == "commits.json" else name}:
                if os.path.exists(f"{state}/{n}"):
                    os.remove(f"{state}/{n}")

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)
            if name == "commits.json":   # gh.api_list reads the flat list, post_review's own call the pages
                with open(f"{state}/commits_flat.json", "w", encoding="utf-8") as fh:
                    json.dump([c for page in json.loads(text) for c in page], fh)

        def set_pr(branch: str, *files: str) -> None:
            """The PR on <branch>, changing <files> ("old=>new" a rename);
            none: the file list cannot be read."""
            put("pr.json", json.dumps({"number": 552, "state": "OPEN", "headRefName": branch,
                                       "headRefOid": HEAD, "baseRefName": "main", "author": {"login": "me"}}) + "\n")
            put("mergebase", ROOT_C)
            drop("reviews.json")
            drop("files.json")
            drop("commits.json")
            if files:
                page = [{"previous_filename": f.split("=>")[0], "filename": f.split("=>")[1]} if "=>" in f
                        else {"filename": f} for f in files]
                put("files.json", json.dumps([page]) + "\n")
            put("calls", "")
            drop("payload.json")

        case: dict[str, str] = {}

        # A report with no dispatch header names its head with --head or is refused (ADR-020 §5 rule 6), so the checks
        # of everything else name the PR's head for it; head=None leaves --head out, and a report with a header names
        # its own.
        def range_header(head: str, base: str = ROOT_C) -> str:
            h = {"evidence_mode": "pinned", "engine": "claude", "base_sha": base, "head_sha": head, "card_base": CARD,
                 "config": CONFIG}
            return "```agent-fabric-dispatch v1\n" + json.dumps(h, indent=2) + "\n```\n"

        def covering(body: str) -> str:
            """The coverage block for the range the first header names: every path of `git diff --name-only`, read;
            none for a header that names no range."""
            m = re.search(r"```agent-fabric-dispatch v1\n(.*?)\n```", body, re.S)
            try:
                h = json.loads(m[1]) if m else {}
                paths = git("diff", "--name-only", f"{h['base_sha']}..{h['head_sha']}").splitlines() if h.get("card_base") else None
            except (ValueError, KeyError, RuntimeError, TypeError):
                paths = None
            if paths is None:
                return ""
            doc = {"paths": {p: {"status": "read"} for p in paths}, "lenses": {"security": "applied"}}
            return f"\n```{rcov.BLOCK_INFO}\n{json.dumps(doc, indent=1)}\n```\n"

        # A new review is v2 only: a body without a header gets the one naming `head`'s range, and a header without a
        # block the block of its range; v2=False posts what it is given.
        def invoke(body: str, *args: str, head: str | None = HEAD, v2: bool = True) -> tuple[int, str]:
            if v2 and head and "agent-fabric-dispatch" not in body:
                body, head = range_header(head) + body, None
            if v2 and "agent-fabric-dispatch" in body and rcov.BLOCK_INFO not in body:
                body += covering(body)
            if head and "agent-fabric-dispatch" not in body:
                args = (*args, "--head", head)
            env = {**base, "AGENT_FABRIC_ROOT": case.get("fabric", f"{sandbox}/no-fabric")}
            if case.get("launch_role"):
                env["AGENT_FABRIC_LAUNCH_ROLE"] = case["launch_role"]
            if case.get("fake_role"):
                env["FAKE_ROLE"] = case["fake_role"]
            r = subprocess.run(["timeout", "20", *UNDER_TEST, *args], cwd=clone, env=env, input=body,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            # Both streams for the checks of what is said; stdout alone kept for those of where it is said, which the
            # contract fixes (review of 3de34c0d, F4).
            case["stdout"] = r.stdout
            return r.returncode, r.stdout + r.stderr

        def calls() -> str:
            try:
                with open(f"{state}/calls", encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def posted() -> bool:
            return "POST" in calls()

        def payload() -> dict:
            try:
                with open(f"{state}/payload.json", encoding="utf-8") as fh:
                    d = json.load(fh)
                return d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                return {}

        def body_of() -> str:
            b = payload().get("body")
            return b if isinstance(b, str) else ""

        print("post-review: the marker is the first line of what is SENT")
        # Asserted against the request payload, not the script's own output:
        # the reader reads the stored body, so that is the only thing that
        # matters.
        set_pr(f"{me}/feat/thing")
        rc, out = invoke("A P1 in the ownership guard.", "552")
        check("exits 0", rc == 0, out)
        check("a review was posted", posted(), calls())
        v2_line = f"<!-- agent-fabric-review v2 base={ROOT_C} head={HEAD} card={CARD} config={CONFIG} -->"
        check("the marker is line 1 of the body", body_of().split("\n")[0] == v2_line, body_of()[:200])
        check("the caller's body survives verbatim", "A P1 in the ownership guard." in body_of(), body_of())
        # THE HEADLINE PROMISE, with a body that would catch a regression to
        # `-f body="…"`: a review body quotes code by definition, and a shell
        # would expand backticks and $vars before gh ever saw them — which
        # has already posted a mangled comment in this repo.
        nasty = "backtick `id` dollar $HOME quote \" apostrophe ' unicode ünïcode $(echo pwned)"
        set_pr(f"{me}/feat/thing")
        invoke(nasty, "552")
        check("a body full of shell metacharacters survives byte-for-byte", nasty in body_of(), body_of())

        print("post-review: it is posted as a REVIEW, at the head commit")
        p = payload()
        check("event=COMMENT (a review object, not an issue comment)", p.get("event") == "COMMENT", json.dumps(p))
        check("pinned to the head commit", p.get("commit_id") == HEAD, json.dumps(p))
        check("posted to the reviews endpoint", "POST repos/gzapi-org/gzapp/pulls/552/reviews" in calls(), calls())

        print("post-review: it says what it is — the review class's blind review, nothing less")
        check("stdout names the commit it is recorded on, the PR's head",
              f"recorded on {HEAD}, the head of PR #552" in case["stdout"], out)
        check("the body names the method", "**Blind review**" in body_of(), body_of())
        for word in ("substitute", "fallback", "not a real review", "not an equivalent"):
            check(f"the body never says '{word}'", word not in body_of(), body_of())

        print("post-review: --model is recorded when given, absent when not")
        set_pr(f"{me}/feat/thing")
        invoke("findings", "552", "--model", "opus")
        check("records the model", "<!-- model: opus -->" in body_of(), body_of())
        check("…and calls it the review class's", "the review class, dispatched" in body_of(), body_of())
        set_pr(f"{me}/feat/thing")
        invoke("findings", "552", "--model", "codex")
        check("the second engine's is marked the same", body_of().split("\n")[:2]
              == [v2_line, "<!-- model: codex -->"], body_of())
        check("…and names Codex, never the review class (ADR-053)",
              "Codex, the second review engine" in body_of() and "the review class, dispatched" not in body_of(),
              body_of())
        set_pr(f"{me}/feat/thing")
        invoke("findings", "552", "--model", "Codex")
        check("--model Codex is captioned as Codex too, as the status reader counts it (review of #220, F3)",
              "Codex, the second review engine" in body_of() and "the review class, dispatched" not in body_of(), body_of())
        set_pr(f"{me}/feat/thing")
        invoke("findings", "552")
        check("no model line when unset", "<!-- model:" not in body_of(), body_of())

        print("post-review: an older branch named for this clone is still this session's")
        set_pr(f"{me_legacy}/feat/thing")
        rc, out = invoke("findings", "552")
        check("exits 0", rc == 0, out)
        check("posted on the legacy-prefixed branch", posted())

        print("post-review: another session's PR is refused")
        set_pr(f"{other}/fix/theirs")
        rc, out = invoke("I should not be able to post this.", "552")
        check("exits 2", rc == 2, out)
        check("names the owning session", other in out, out)
        check("nothing was sent", not posted(), calls())

        print("post-review: the locale carve-out's merger may post on another session's locale-only PR")
        # A fabric whose identity.py answers the role the case plants: the
        # merger of a locale PR is fabric-coordinator (agent-fabric
        # AGENTS.md, carve-out).
        fake = f"{sandbox}/fake-fabric"
        os.makedirs(f"{fake}/runtime")
        with open(f"{fake}/runtime/identity.py", "w", encoding="utf-8") as fh:
            fh.write('import os, sys\nprint(os.environ.get("FAKE_ROLE", "") if "--role" in sys.argv else "someone")\n')
        loc = "identities/roles/language-culture/locale/ge/team.md"
        # Launched as the merger, as well as bound.
        case.update(fabric=fake, fake_role="fabric-coordinator", launch_role="fabric-coordinator")
        set_pr(f"{other}/i18n/ge-team", loc)
        rc, out = invoke("findings", "552")
        check("the merger posts on a locale-only PR", rc == 0, out)
        check("…it was sent", posted())
        check("…the marker is still its first line", body_of().split("\n")[0] == v2_line, body_of()[:200])
        check("…and it says it was posted by the carve-out's merger",
              "posted by the locale carve-out's merger" in body_of(), body_of()[:300])

        def refused(*files: str) -> tuple[bool, str]:
            set_pr(f"{other}/i18n/ge-team", *files)
            rc, out = invoke("no", "552")
            return rc == 2 and not posted(), f"rc={rc}\n{out}"
        check("one file outside a locale refuses", *refused(loc, "tools/fabric/lint.py"))
        check("a path nested below a locale directory refuses",
              *refused("identities/roles/language-culture/locale/ge/sub/x.md"))
        check("an unreadable file list refuses", *refused())
        set_pr(f"{other}/i18n/ge-team", *(f"identities/roles/language-culture/locale/ge/f{i}.md" for i in range(1, 101)))
        rc, out = invoke("no", "552")
        check("a locale PR of 100 files posts", rc == 0 and posted(), f"rc={rc}\n{out}")
        check("3000 files, GitHub's list cap: it may be cut, so it refuses",
              *refused(*(f"identities/roles/language-culture/locale/ge/f{i}.md" for i in range(1, 3001))))
        set_pr(f"{other}/i18n/ge-team", loc)
        put("files.json", '[["not an object"]]\n')
        rc, out = invoke("no", "552")
        check("pages whose items are not files refuse, never read as 0 outside", rc == 2 and not posted(),
              f"rc={rc}\n{out}")
        check("a code file renamed INTO a locale directory refuses: its old path counts",
              *refused(f"tools/fabric/lint.py=>{loc}"))
        case["launch_role"] = "devex-tooling"
        check("bound fabric-coordinator but launched as another role: refused", *refused(loc))
        del case["launch_role"]
        check("bound fabric-coordinator, not started by the launcher (no stamp): refused", *refused(loc))
        case.update(launch_role="fabric-coordinator", fake_role="devex-tooling")
        check("another role refuses, even on a locale-only PR", *refused(loc))
        case.clear()

        print("post-review: a branch naming no session is allowed, with a warning")
        for b in ("agent/global-event-identity", "dependabot/pub/apps/x/y", "add-claude-github-actions-178"):
            set_pr(b)
            rc, out = invoke("findings", "552")
            check(f"posts on '{b}'", rc == 0 and posted(), f"rc={rc}")
        check("says the branch names no session", "names no session" in out, out)

        print("post-review: an unusual <type> is still another session's")
        # A shape test on <type> would make a real session's branch writable;
        # this predicate must agree with the sibling script's.
        for t in ("Fix", "chore(gh)", "WIP", "2fix"):
            set_pr(f"{other}/{t}/x")
            rc, _ = invoke("no", "552")
            check(f"refuses '{t}/'", rc == 2 and not posted(), f"rc={rc}")

        print("post-review: unreadable PR metadata REFUSES, it does not post")
        # .headRefName of an empty or field-less payload is "" or "null":
        # either has fewer than four segments, so a guard reading it as
        # "names no session" would take the POSTING path, where not knowing
        # whose PR this is has to mean stop.
        for pr_payload in ("{}", ""):
            put("pr.json", pr_payload)
            put("calls", "")
            drop("payload.json")
            rc, _ = invoke("findings", "552")
            check(f"refuses a PR payload of '{pr_payload or '<empty>'}'", rc == 2 and not posted(), f"rc={rc}")

        print("post-review: --dry-run sends nothing")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke("findings", "552", "--dry-run")
        check("exits 0", rc == 0, out)
        check("shows the marker", v2_line in out, out)
        check("no request was sent", not posted(), calls())

        print("post-review: a working-tree report is never posted as the review of a head (ADR-020 §5 rule 10)")
        # The header as a brief carries it (review_brief.dispatch_header), at the top of the report.
        def dispatch(mode: str, fence: str = "```agent-fabric-dispatch v1", head: str | None = HEAD) -> str:
            return (fence + "\n" + json.dumps({"dispatch_id": "d-1", "parent_session_id": "s-0123-session",
                                               "job_id": "j9", "repository": "/home/someone/projects/clone",
                                               "engine": "claude", "evidence_mode": mode, "head_sha": head,
                                               "base_sha": ROOT_C, "card_base": CARD, "config": CONFIG},
                                              indent=2) + "\n```\n")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("working-tree") + "F1 (P2) …", "552")
        check("refused, exit 2, nothing sent", rc == 2 and not posted(), f"rc={rc}\n{out}{calls()}")
        check("…saying working-tree and the rule", "'working-tree'" in out and "ADR-020" in out, out)
        rc, out = invoke(dispatch("working-tree") + "F1 (P2) …", "552", "--dry-run")
        check("--dry-run refuses it too", rc == 2 and "would post" not in out, f"rc={rc}\n{out}")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("pinned") + "F1 (P2) …", "552")
        check("a pinned report posts, its findings whole", rc == 0 and posted()
              and "\n\nF1 (P2) …\n\n```agent-fabric-coverage v1\n" in body_of(), f"rc={rc}\n{out}{calls()}")
        check("…and no dispatch header, no session id, job or clone path in what GitHub gets (#259, risk 1)",
              not any(w in body_of() for w in ("agent-fabric-dispatch", "s-0123-session", "j9", "/home/someone",
                                               "evidence_mode")), body_of())
        rc, out = invoke(dispatch("pinned") + "F1 (P2) …", "552", "--dry-run")
        check("--dry-run shows the body without it too", rc == 0 and "F1 (P2) …" in out
              and "s-0123-session" not in out, out)
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("working-tree", "``` agent-fabric-dispatch v1") + "F1 (P2) …", "552")
        check("a spaced-fence working-tree header is refused, nothing sent (#259, F5)",
              rc == 2 and "'working-tree'" in out and not posted(), f"rc={rc}\n{out}{calls()}")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("pinned"), "552")
        check("a report that is only a header is refused as empty, nothing sent",
              rc == 2 and "empty" in out and not posted(), f"rc={rc}\n{out}{calls()}")

        print("post-review: a pinned review is posted against the head it read, never the PR's head now")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("pinned") + "F1 (P2) …", "552")
        check("a report on the current head posts against it, saying nothing more",
              rc == 0 and payload().get("commit_id") == HEAD and "not the head" not in out, f"rc={rc}\n{out}")
        check("…and the gate counts it for the head", head_covered(HEAD, [], [payload()]), json.dumps(payload()))
        set_pr(f"{me}/feat/thing")
        put("commits.json", json.dumps([[{"sha": OLD}, {"sha": HEAD}]]) + "\n")
        rc, out = invoke(dispatch("pinned", head=OLD) + "F1 (P2) …", "552")
        check("a report of an older head, posted after a push, posts against that head (OBSERVATION 01a14011)",
              rc == 0 and posted() and payload().get("commit_id") == OLD, f"rc={rc}\n{out}{calls()}")
        check("…the gate counts nothing for the new head, and counts the head it read",
              not head_covered(HEAD, [], [payload()]) and head_covered(OLD, [], [payload()]), json.dumps(payload()))
        check("…and it says on stdout which commit it is recorded on, and that the head is not covered",
              f"recorded on {OLD}; the head {HEAD} of PR #552 is not covered by it." in case["stdout"], out)
        rc, out = invoke(dispatch("pinned", head=OLD) + "F1 (P2) …", "552", "--dry-run")
        check("--dry-run shows the head it would post against", rc == 0 and f"recorded on {OLD};" in out, out)

        print("post-review: a report with no header names the head it read with --head, or is refused")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke("F1 (P2) …", "552", head=None)
        check("no header, no --head: refused, nothing sent (ADR-020 §5 rule 6)",
              rc == 2 and not posted() and "no dispatch header and no --head" in out, f"rc={rc}\n{out}{calls()}")
        rc, out = invoke("F1 (P2) …", "552", "--dry-run", head=None)
        check("…--dry-run refuses it too", rc == 2 and "would post" not in out, f"rc={rc}\n{out}")
        set_pr(f"{me}/feat/thing")
        put("commits.json", json.dumps([[{"sha": OLD}, {"sha": HEAD}]]) + "\n")
        rc, out = invoke(range_header(OLD) + "F1 (P2) …", "552", "--head", OLD, head=None)
        check("--head an older commit of the PR posts against it, the head not covered",
              rc == 0 and payload().get("commit_id") == OLD and not head_covered(HEAD, [], [payload()])
              and f"the head {HEAD} of PR #552 is not covered" in case["stdout"], f"rc={rc}\n{out}{calls()}")
        set_pr(f"{me}/feat/thing")
        put("commits.json", json.dumps([[{"sha": HEAD}]]) + "\n")
        rc, out = invoke(range_header(OLD) + "F1 (P2) …", "552", "--head", OLD, head=None)
        check("--head outside the PR refuses, nothing sent",
              rc == 2 and not posted() and "is not a commit of PR #552" in out, f"rc={rc}\n{out}{calls()}")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke("F1 (P2) …", "552", "--head", HEAD[:12], head=None)
        check("an abbreviated --head refuses, nothing sent", rc == 2 and not posted() and "full commit sha" in out,
              f"rc={rc}\n{out}")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("pinned") + "F1 (P2) …", "552", "--head", OLD, head=None)
        check("--head naming another commit than the header's refuses, nothing sent",
              rc == 2 and not posted() and "is not the head_sha" in out, f"rc={rc}\n{out}{calls()}")
        set_pr(f"{me}/feat/thing")
        rc, out = invoke(dispatch("pinned") + "F1 (P2) …", "552", "--head", HEAD, head=None)
        check("--head naming the header's own commit posts", rc == 0 and payload().get("commit_id") == HEAD,
              f"rc={rc}\n{out}")

        def refused_head(label: str, report: str, why: str, commits: list | None = None) -> None:
            set_pr(f"{me}/feat/thing")
            if commits is not None:
                put("commits.json", json.dumps(commits) + "\n")
            rc, out = invoke(report + "F1 (P2) …", "552", head=OLD)
            check(label, rc == 2 and not posted() and why in out, f"rc={rc}\n{out}{calls()}")
        refused_head("headers naming different heads refuse, nothing sent",
                     dispatch("pinned") + dispatch("pinned", head=OLD), "different heads")
        refused_head("a pinned header naming no head_sha refuses, nothing sent",
                     dispatch("pinned", head=None), "names no head_sha")
        refused_head("a head_sha that is not a sha refuses, nothing sent",
                     dispatch("pinned", head="main"), "names no head_sha")
        refused_head("a sha outside the PR refuses, nothing sent",
                     dispatch("pinned", head=OLD), "is not a commit of PR #552", [[{"sha": HEAD}]])
        refused_head("unreadable PR commits refuse, nothing sent",
                     dispatch("pinned", head=OLD), "could not be read")
        refused_head("a sha not in a list GitHub cut at 250 refuses, nothing sent", dispatch("pinned", head=OLD),
                     "a list it cuts there", [[{"sha": f"{n:040x}"} for n in range(250)]])

        print("post-review: invocation errors are refused, not guessed at")
        set_pr(f"{me}/feat/thing")
        for label, body, args in (("an empty body is refused", "", ("552",)),
                                  ("a missing PR number is refused", "x", ()),
                                  ("a non-numeric PR is refused", "x", ("notanumber",)),
                                  ("--model without a value is refused", "x", ("552", "--model")),
                                  ("--head without a value is refused", "x", ("552", "--head")),
                                  ("an unknown option is refused", "x", ("552", "--bogus"))):
            rc, out = invoke(body, *args, head=None)
            check(label, rc == 2, f"rc={rc}\n{out}")

        print("post-review: a rejected post is reported, never assumed")
        set_pr(f"{me}/feat/thing")
        put("api_fail", "")
        rc, out = invoke("findings", "552")
        check("exits 2", rc == 2, out)
        check("says GitHub rejected it", "rejected" in out, out)
        check("  with GitHub's own reason", "Validation Failed (HTTP 422)" in out, out)
        check("  and says to look before re-running, never to post by hand", "never post it by hand" in out, out)
        drop("api_fail")
        set_pr(f"{me}/feat/thing")
        put("api_empty", "")
        rc, out = invoke("findings", "552")
        check("an empty URL is treated as NOT posted", rc == 2, out)
        check("  and says so", "NOT posted" in out, out)
        drop("api_empty")

        print("post-review: a report whose headers name a range is posted as v2 (agent-fabric ADR-065 §2 C, §5 rule 4)")
        c0 = commit("c0", {"a.py": "one\n", "b.py": "two\n"})
        c1 = commit("c1", {"a.py": "one\nmore\n", "sub/c.py": "three\n"})
        c2 = commit("c2", {"sub/c.py": "three\nfour\n"})
        git("checkout", "-q", "-b", "side", c0)
        side = commit("side", {"d.py": "d\n"})
        git("checkout", "-q", "-")
        from github.review_status import verdicts  # noqa: E402

        def fence_header(**over) -> str:
            h = {"evidence_mode": "pinned", "engine": "claude", "base_sha": c0, "head_sha": c1, "card_base": CARD,
                 "config": CONFIG, **over}
            return "```agent-fabric-dispatch v1\n" + json.dumps({k: v for k, v in h.items() if v != "-"}, indent=2) + "\n```\n"

        def cover(*paths: str, bad: tuple = (), lenses: dict | None = None) -> str:
            doc = {"paths": {p: ({"status": "not read", "reason": "too large"} if p in bad else {"status": "read"}) for p in paths},
                   "lenses": {"security": "applied"} if lenses is None else lenses}
            return f"```{rcov.BLOCK_INFO}\n{json.dumps(doc, indent=1)}\n```\n"

        def v2_pr(head: str = c1, *, listed: tuple = (c0, c1), merge_base: str = c0) -> None:
            put("pr.json", json.dumps({"number": 552, "state": "OPEN", "headRefName": f"{me}/feat/thing", "headRefOid": head,
                                       "baseRefName": "main", "author": {"login": "me"}}) + "\n")
            put("mergebase", merge_base)
            drop("reviews.json")
            put("commits.json", json.dumps([[{"sha": c} for c in listed]]) + "\n")
            put("calls", "")
            drop("payload.json")

        def v2_post(report: str, *args: str, header: str | None = None, raw: bool = False) -> tuple[int, str]:
            """raw: the report as given, with no coverage block added to a header that has none."""
            return invoke((fence_header() if header is None else header) + report, "552", *args, head=None, v2=not raw)

        report = "Found a P2 in sub/c.py.\n\n"
        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py"))
        check("a complete v2 report posts", rc == 0 and posted(), out)
        want = f"<!-- agent-fabric-review v2 base={c0} head={c1} card={CARD} config={CONFIG} -->"
        check("the first line is the marker the headers name", body_of().split("\n")[0] == want, body_of()[:300])
        check("pinned to the head the headers name", payload().get("commit_id") == c1, json.dumps(payload())[:200])
        check("no partial line, the blind review text follows the marker", body_of().split("\n")[1].startswith("**Blind review**"), body_of()[:300])
        check("the findings survive and the dispatch header is taken out", "Found a P2 in sub/c.py." in body_of() and "agent-fabric-dispatch" not in body_of())
        check("exactly one coverage block, at the end", body_of().count(rcov.BLOCK_INFO) == 1 and body_of().rstrip().endswith("```"), body_of()[-200:])
        reading = rcov.read_review(body_of())
        check("the readers' parser counts what was posted", reading is not None and reading.counts and reading.marker.head == c1, reading)
        counted = verdicts.classify([{"user": {"login": "me"}, "commit_id": c1, "body": body_of(), "author_association": "NONE"}],
                                    "me", rs_cfg())
        check("…and the status classifier files it as coverage", len(counted.blind) == 1 and not counted.partial, counted)

        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py", bad=("a.py",)), "--model", "codex")
        check("a partial report posts", rc == 0 and posted(), out)
        lines = body_of().split("\n")
        check("the line after the marker says how many paths are not read", lines[1] == "partial coverage: 1 path(s) not read", lines[:4])
        check("the model line follows it, so an engine is still read from the header", lines[2] == "<!-- model: codex -->"
              and verdicts.engine_of({"body": body_of()}) == "codex", lines[:4])
        check("a reader does not count it, and says why", verdicts.uncounted_v2({"body": body_of(), "commit_id": c1}) == "partial coverage: 1 path(s) not read")
        partial = verdicts.classify([{"user": {"login": "me"}, "commit_id": c1, "body": body_of(), "author_association": "NONE"}], "me", rs_cfg())
        check("…it is in the partial bucket, not the blind one", not partial.blind and len(partial.partial) == 1)

        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), "--dry-run")
        check("--dry-run shows the v2 body and sends nothing", rc == 0 and not posted() and want in out and rcov.BLOCK_INFO in out, out)

        print("post-review: v2 refusals — each leaves nothing posted")
        for label, body, header, why in (
            ("a block that omits a path of the range", report + cover("a.py"), None, "omits 1"),
            ("a block that names a path outside the range", report + cover("a.py", "sub/c.py", "z.py"), None, "outside the range"),
            ("a block naming a path of the PR but not of the range", report + cover("a.py", "sub/c.py", "b.py"), None, "outside the range"),
            ("no coverage block", report, None, "no coverage block"),
            ("a block that is not JSON", report + f"```{rcov.BLOCK_INFO}\nnot json\n```\n", None, "not JSON"),
            ("duplicate keys in the block", report + f'```{rcov.BLOCK_INFO}\n{{"paths": {{}}, "paths": {{}}, "lenses": {{}}}}\n```\n', None, "each key once"),
            ("a second coverage block", report + cover("a.py", "sub/c.py") + cover("a.py", "sub/c.py"), None, "more than one"),
            ("a second block quoted in a longer fence", report + cover("a.py", "sub/c.py") + "\n````text\n" + cover("a.py") + "````\n", None, "lines open a coverage block"),
            ("a marker-like line later in the body", f"{want}\n" + report + cover("a.py", "sub/c.py"), None, "looks like a review marker"),
            ("a v1 marker line in the body", "<!-- agent-fabric-review v1 -->\n" + report + cover("a.py", "sub/c.py"), None, "looks like a review marker"),
            ("a block with a path not read and no reason", report + f'```{rcov.BLOCK_INFO}\n{{"paths": {{"a.py": {{"status": "not read"}}, "sub/c.py": {{"status": "read"}}}}, "lenses": {{}}}}\n```\n', None, "needs a reason"),
            ("a huge block", report + f"```{rcov.BLOCK_INFO}\n" + json.dumps({"paths": {f"p{i}" * 5: {"status": "read"} for i in range(9000)}, "lenses": {}}) + "\n```\n", None, "over the"),
            ("a report too long for one review", "x" * 66000 + "\n" + cover("a.py", "sub/c.py"), None, "GitHub takes"),
            ("headers that disagree on the config", report + cover("a.py", "sub/c.py"), fence_header() + fence_header(config="7" * 64), "different ranges"),
            ("headers that disagree on the base", report + cover("a.py", "sub/c.py"), fence_header() + fence_header(base_sha=c1), "different"),
            ("one header with the range's fields and one without", report + cover("a.py", "sub/c.py"), fence_header() + fence_header(card_base="-", config="-"), "some of its dispatch headers"),
            ("a header with a config and no card_base", report + cover("a.py", "sub/c.py"), fence_header(card_base="-"), "card_base"),
            ("a header with a config and no base_sha", report + cover("a.py", "sub/c.py"), fence_header(base_sha="-"), "base_sha"),
            ("a short base", report + cover("a.py", "sub/c.py"), fence_header(base_sha=c0[:12]), "base_sha"),
            ("a config that is not sha256 hex", report + cover("a.py", "sub/c.py"), fence_header(config="Z" * 64), "config"),
            ("a base that is not an ancestor of the head", report + cover("a.py", "sub/c.py"), fence_header(base_sha=side), "not an ancestor"),
            ("a base the clone does not have", report + cover("a.py", "sub/c.py"), fence_header(base_sha="9" * 40), "failed"),
        ):
            v2_pr()
            rc, out = v2_post(body, header=header, raw=label == "no coverage block")
            check(f"{label}: refused, nothing posted", rc == 2 and not posted() and why in out, f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c2))
        rc, out = v2_post(report + cover("a.py", "sub/c.py"))
        check("a head that is not a commit of the PR: refused", rc == 2 and not posted() and "not a commit of PR #552" in out, out)
        v2_pr(c2, listed=(c0, c1, c2))
        rc, out = v2_post(report + cover("a.py", "sub/c.py"))
        check("an older head of the PR posts against it, saying it is not the head", rc == 0 and payload().get("commit_id") == c1
              and f"the head {c2} of PR #552 is not covered by it" in out, out)
        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), "--head", c0)
        check("a --head that names another commit: refused", rc == 2 and not posted(), out)

        print("post-review: hostile paths of the PR")
        evil = {"we\nird.py": "x\n", "tick```.py": "y\n"}
        git("checkout", "-q", "-b", "evil", c1)
        e1 = commit("evil", evil)
        v2_pr(e1, listed=(c0, c1, e1), merge_base=c1)
        h = fence_header(base_sha=c1, head_sha=e1)
        rc, out = v2_post(report + cover("we\nird.py", "tick```.py"), header=h)
        check("a path with a newline in the range refuses, even when the block names it", rc == 2 and not posted() and "control character" in out, out)
        git("rm", "-q", "-f", "we\nird.py")
        git("commit", "-q", "-m", "drop the newline path")
        e2 = git("rev-parse", "HEAD")
        v2_pr(e2, listed=(c0, c1, e1, e2), merge_base=c1)
        h = fence_header(base_sha=c1, head_sha=e2)
        rc, out = v2_post(report + cover("tick```.py"), header=h)
        check("a path holding a backquote run posts", rc == 0 and posted(), out)
        again = rcov.read_review(body_of())
        check("…in a fence longer than the run, which still reads as one block", again is not None and again.counts and "tick```.py" in again.coverage.paths
              and "\n````" + rcov.BLOCK_INFO in body_of(), body_of()[-300:])

        print("post-review: a new review is v2 only; v1 stays readable, never writable (ADR-065 §5 rule 4)")
        v2_pr()
        rc, out = invoke("findings", "552", v2=False, head=c1)
        check("no header, only --head: refused, nothing sent, saying the header is what is missing",
              rc == 2 and not posted() and "has no dispatch header" in out and "v2" in out, f"rc={rc}\n{out}")
        v2_pr()
        rc, out = invoke(fence_header(card_base="-", config="-") + "findings", "552", head=None, v2=False)
        check("a header with no card_base and no config: refused, nothing sent, naming both",
              rc == 2 and not posted() and "none of card_base and config" in out, f"rc={rc}\n{out}")
        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), "--dry-run")
        check("…and the same report with its range posts (the control: the refusal is the missing range)", rc == 0 and want in out, out)
        v2_pr()
        old_body = "<!-- agent-fabric-review v1 -->\nan old review\n"
        check("…a v1 review already posted still counts for the head it is on (readers keep reading v1)",
              head_covered(c1, [], [{"user": {"login": "me"}, "commit_id": c1, "body": old_body, "author_association": "NONE"}]))

        print("post-review: the posted body reads back as the coverage that was validated")
        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py") + "\n```text\nan unclosed fence\n")
        check("a valid block followed by an unclosed fence: refused, nothing sent", rc == 2 and not posted() and "does not read back" in out,
              f"rc={rc}\n{out}")
        v2_pr()
        rc, out = v2_post(report + cover("a.py", "sub/c.py") + "\n```text\nan closed fence\n```\n")
        check("…the same with the fence closed posts, and reads as the validated coverage (the control)",
              rc == 0 and posted() and rcov.read_review(body_of()).counts, f"rc={rc}\n{out}")
        v2_pr()
        rc, out = v2_post("An open fence first:\n```text\n" + cover("a.py", "sub/c.py"))
        check("a fence opened before the block: refused too, nothing sent", rc == 2 and not posted(), f"rc={rc}\n{out}")

        print("post-review: a v2 review's base is the PR's merge-base or its last checkpoint's head")
        def real_config(card: str) -> str:
            """The fingerprint post-review itself computes in the case's environment, for a checkpoint it must accept."""
            env = {**base, "AGENT_FABRIC_ROOT": f"{sandbox}/no-fabric"}
            r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import review_brief; "
                                "print(review_brief.config_fingerprint(sys.argv[2], sys.argv[3]))",
                                os.path.join(ROOT, "tools", "fabric"), clone, card],
                               env=env, capture_output=True, text=True, timeout=60)
            if r.returncode or len(r.stdout.strip()) != 64:
                raise RuntimeError(r.stderr)
            return r.stdout.strip()

        def checkpoint_review(*, bad: tuple = ()) -> dict:
            """A trusted v2 review of c0..c1 posted by the PR's author."""
            cfg = real_config(CARD)
            doc = {"paths": {p: ({"status": "not read", "reason": "too large"} if p in bad else {"status": "read"})
                             for p in ("a.py", "sub/c.py")}, "lenses": {}}
            text = (f"<!-- agent-fabric-review v2 base={c0} head={c1} card={CARD} config={cfg} -->\nround 1\n\n"
                    f"```{rcov.BLOCK_INFO}\n{json.dumps(doc)}\n```\n")
            return {"user": {"login": "me"}, "commit_id": c1, "submitted_at": "2026-10-20T10:00:00Z", "body": text}

        narrow = fence_header(base_sha=c1, head_sha=c2)
        v2_pr(c2, listed=(c0, c1, c2))
        rc, out = v2_post(report + cover("sub/c.py"), header=narrow)
        check("a narrow range with no checkpoint: refused, nothing sent, naming the merge-base",
              rc == 2 and not posted() and f"merge-base {c0[:12]}" in out and "has none" in out, f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c1, c2))
        put("reviews.json", json.dumps([checkpoint_review(bad=("a.py",))]))
        rc, out = v2_post(report + cover("sub/c.py"), header=narrow)
        check("a narrow range after a PARTIAL round: refused, nothing sent (a partial review is no checkpoint)",
              rc == 2 and not posted() and "neither the merge-base" in out, f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c1, c2))
        put("reviews.json", json.dumps([checkpoint_review(bad=("a.py",))]))
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), header=fence_header(base_sha=c0, head_sha=c2))
        check("…the full range after the same partial round posts (the control)", rc == 0 and posted(), f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c1, c2))
        put("reviews.json", json.dumps([checkpoint_review()]))
        rc, out = v2_post(report + cover("sub/c.py"), header=narrow)
        check("a re-review from the head of a whole checkpoint posts (the chain)", rc == 0 and posted(), f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c1, c2))
        put("reviews.json", json.dumps([checkpoint_review()]))
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), header=fence_header(base_sha=c0, head_sha=c2))
        check("…and a base that is the merge-base posts with the checkpoint there too", rc == 0 and posted(), f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c1, c2))
        drop("mergebase")
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), header=fence_header(base_sha=c0, head_sha=c2))
        check("the merge-base unreadable: refused even for the full range, nothing sent (fails closed)",
              rc == 2 and not posted() and "could not be read" in out, f"rc={rc}\n{out}")
        v2_pr(c2, listed=(c0, c1, c2))
        put("mergebase", "not a sha\n")
        rc, out = v2_post(report + cover("a.py", "sub/c.py"), header=fence_header(base_sha=c0, head_sha=c2))
        check("a merge-base answer that is no sha: refused too", rc == 2 and not posted() and "could not be read" in out, f"rc={rc}\n{out}")

        print("post-review: the marker matches the READER's, byte for byte")
        # THE CROSS-FILE CONTRACT. Two constants in two modules; a one-sided
        # edit turns real coverage back into "0 reviews" with nothing failing.
        emit, read_ = marker_of(EMITTER), reader_marker()
        check("emitter and fabric-pr review-status agree on the marker", bool(emit) and emit == read_,
              f"emitter: {emit}\nreader : {read_}")

    print(f"\ntest_post_review_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
