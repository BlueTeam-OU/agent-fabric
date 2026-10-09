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
# Both ends of the marker contract are Python modules; the scripts are
# their shims, run as the paths every caller uses.
EMITTER = os.path.join(ROOT, "tools", "fabric", "github", "post_review.py")
READER = os.path.join(ROOT, "tools", "fabric", "github", "pr_review_status.py")

# The fake gh: the PR, its files as REST pages, and the POST, whose body is
# recorded so a case asserts on what was SENT, not on what the script said
# it would send.
GH_MOCK = r"""#!/usr/bin/env bash
S="$GH_STATE"
case "$1" in
  repo) echo "gzapi-org/gzapp"; exit 0 ;;
  pr)   cat "$S/pr.json"; exit 0 ;;
  api)
    if [ "$2" = "--paginate" ]; then
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
        with open(f"{sandbox}/bin/gh", "w", encoding="utf-8") as fh:
            fh.write(GH_MOCK)
        os.chmod(f"{sandbox}/bin/gh", 0o755)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        # The repository the mock serves (gh.this_repo never reads gh's default).
        base["GH_REPO"] = "gzapi-org/gzapp"
        base.update(PATH=f"{sandbox}/bin:{base.get('PATH', '')}", GH_STATE=state)

        def drop(name: str) -> None:
            if os.path.exists(f"{state}/{name}"):
                os.remove(f"{state}/{name}")

        def put(name: str, text: str) -> None:
            with open(f"{state}/{name}", "w", encoding="utf-8") as fh:
                fh.write(text)

        def set_pr(branch: str, *files: str) -> None:
            """The PR on <branch>, changing <files> ("old=>new" a rename);
            none: the file list cannot be read."""
            put("pr.json", json.dumps({"number": 552, "state": "OPEN", "headRefName": branch,
                                       "headRefOid": "abcdef1234567890"}) + "\n")
            drop("files.json")
            if files:
                page = [{"previous_filename": f.split("=>")[0], "filename": f.split("=>")[1]} if "=>" in f
                        else {"filename": f} for f in files]
                put("files.json", json.dumps([page]) + "\n")
            put("calls", "")
            drop("payload.json")

        case: dict[str, str] = {}

        def invoke(body: str, *args: str) -> tuple[int, str]:
            env = {**base, "AGENT_FABRIC_ROOT": case.get("fabric", f"{sandbox}/no-fabric")}
            if case.get("launch_role"):
                env["AGENT_FABRIC_LAUNCH_ROLE"] = case["launch_role"]
            if case.get("fake_role"):
                env["FAKE_ROLE"] = case["fake_role"]
            r = subprocess.run(["timeout", "20", *UNDER_TEST, *args], cwd=clone, env=env, input=body,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
            return r.returncode, r.stdout

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
        check("the marker is line 1 of the body", body_of().split("\n")[0] == "<!-- agent-fabric-review v1 -->",
              body_of()[:200])
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
        check("pinned to the head commit", p.get("commit_id") == "abcdef1234567890", json.dumps(p))
        check("posted to the reviews endpoint", "POST repos/gzapi-org/gzapp/pulls/552/reviews" in calls(), calls())

        print("post-review: it says what it is — the review class's blind review, nothing less")
        check("output says the reader counts it as THE review", "counts it as the review of this head" in out, out)
        check("the body names the method", "**Blind review**" in body_of(), body_of())
        for word in ("substitute", "fallback", "not a real review", "not an equivalent"):
            check(f"the body never says '{word}'", word not in body_of(), body_of())

        print("post-review: --model is recorded when given, absent when not")
        set_pr(f"{me}/feat/thing")
        invoke("findings", "552", "--model", "opus")
        check("records the model", "<!-- model: opus -->" in body_of(), body_of())
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
        # CLAUDE.md, carve-out).
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
        marker = marker_of(EMITTER)
        check("…the marker is still its first line", bool(marker) and body_of().split("\n")[0] == marker,
              f"want '{marker}'; {body_of()[:200]}")
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
        check("shows the marker", "agent-fabric-review v1" in out, out)
        check("no request was sent", not posted(), calls())

        print("post-review: invocation errors are refused, not guessed at")
        set_pr(f"{me}/feat/thing")
        for label, body, args in (("an empty body is refused", "", ("552",)),
                                  ("a missing PR number is refused", "x", ()),
                                  ("a non-numeric PR is refused", "x", ("notanumber",)),
                                  ("--model without a value is refused", "x", ("552", "--model")),
                                  ("an unknown option is refused", "x", ("552", "--bogus"))):
            rc, out = invoke(body, *args)
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

        print("post-review: the marker matches the READER's, byte for byte")
        # THE CROSS-FILE CONTRACT. Two constants in two modules; a one-sided
        # edit turns real coverage back into "0 reviews" with nothing failing.
        emit, read_ = marker_of(EMITTER), reader_marker()
        check("emitter and pr-review-status.sh agree on the marker", bool(emit) and emit == read_,
              f"emitter: {emit}\nreader : {read_}")

    print(f"\ntest_post_review_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
