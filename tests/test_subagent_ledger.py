#!/usr/bin/env python3
"""Behavioural tests for runtime/claude-code/hooks/subagent-ledger.py: the
SubagentStop hook that appends one counts-only row v1 per subagent stop
to <state>/agents/<login>/ledger.jsonl. Ported from the bash
test_subagent-ledger.sh, check for check (ADR-040 §7).

What this holds still: the row read from the fixture transcript
(runtime/claude-code/hooks/testdata/subagent-ledger/), field by field, and
that every row holds exactly the v1 keys — a message split over several
records counts once at its final usage, a <synthetic> message and a torn
last line count for nothing, the model is that of most turns; without a
dispatch header the row is "inferred", purpose other-subagent, the
description kept and never parsed (its #251 is not a pr), repository and
head_sha from the transcript's cwd; with an `agent-fabric-dispatch v1`
header as the brief's first fenced block its fields are copied, a field of
the wrong type is not, and a header that is not the first block, or not a
JSON object, is not one; the header review_brief renders is read whole;
status and status_source for every ending the transcript can show, none
of the unfinished ones "completed"; provider from the model id, effort
from the hook input else the transcript; no text of the transcript
reaches the ledger; a second stop appends a second line; a credential in
a remote URL never reaches the row; a run that never got an API answer
still writes its row (turns 0, failed or cancelled); a dispatch row's
missing or malformed field stays null, never filled from the cwd; a
transcript with no conversation, and every input it cannot read, writes
nothing, prints nothing and exits 0. Plain script: prints ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory

scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import review_brief  # noqa: E402

UNDER_TEST = os.path.join(ROOT, "runtime", "claude-code", "hooks", "subagent-ledger.py")
FIXTURE = os.path.join(ROOT, "runtime", "claude-code", "hooks", "testdata", "subagent-ledger")
KEYS = ["agent_id", "agent_type", "attribution", "base_sha", "cache_read", "cache_write", "completed_at", "description",
        "dispatch_id", "effort", "engine", "evidence", "first_turn_context", "head_sha", "input", "job_id", "model",
        "output", "parent_session_id", "pr", "project", "provider", "purpose", "reasoning", "repository", "review_id",
        "review_round", "schema_version", "session_id", "started_at", "status", "status_source", "tool_use_id",
        "turns", "wall_time"]
DESCRIPTION = "review #251 range ade76f23 (round 2, see #12)"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    if not os.path.isfile(UNDER_TEST):
        print(f"test: not found: {UNDER_TEST}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as sandbox:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(sandbox, "state")
        ledger = os.path.join(sandbox, "state", "agents", pwd.getpwuid(os.geteuid()).pw_name, "ledger.jsonl")

        # The subagent's working copy: a repository whose origin names the project.
        repo = os.path.join(sandbox, "work")

        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True,
                                  timeout=30, env=git_env()).stdout.strip()

        subprocess.run(["git", "init", "-q", repo], check=True, timeout=30, env=git_env())
        git("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty",
            "-m", "fixture")
        git("remote", "add", "origin", "git@github.com:BlueTeam-OU/agent-fabric.git")
        head_sha = git("rev-parse", "HEAD")

        subagents = os.path.join(sandbox, "subagents")
        os.makedirs(subagents)
        with open(os.path.join(FIXTURE, "agent-afixture.jsonl"), encoding="utf-8") as fh:
            fixture_text = fh.read()
        tr = os.path.join(subagents, "agent-afixture.jsonl")
        with open(tr, "w", encoding="utf-8") as fh:
            fh.write(fixture_text.replace("@CWD@", repo))
        shutil.copy(os.path.join(FIXTURE, "agent-afixture.meta.json"), subagents)

        def run_hook(stdin: str) -> str:
            """The hook's stdout and stderr, then rc=N: "rc=0" alone is a silent success."""
            r = subprocess.run([sys.executable, UNDER_TEST], input=stdin, capture_output=True, text=True,
                               timeout=60, env=env)
            return f"{r.stdout}{r.stderr}rc={r.returncode}"

        def fire(transcript: str, effort: dict | None = None) -> str:
            payload = {"hook_event_name": "SubagentStop", "session_id": "sess-1", "transcript_path": "/parent.jsonl",
                       "cwd": "/", "stop_hook_active": False, "agent_id": "afixture", "agent_type": "code-review",
                       "agent_transcript_path": transcript}
            if effort is not None:
                payload["effort"] = effort
            return run_hook(json.dumps(payload))

        def lines() -> list[str]:
            try:
                with open(ledger, encoding="utf-8") as fh:
                    return fh.read().splitlines()
            except OSError:
                return []

        def only_row() -> dict:
            """The ledger's one row, {} when it has none or more than one or it is not a JSON object."""
            got = lines()
            try:
                row = json.loads(got[0]) if len(got) == 1 else {}
            except ValueError:
                row = {}
            return row if isinstance(row, dict) else {}

        def fresh(transcript: str, effort: dict | None = None) -> tuple[str, dict]:
            if os.path.exists(ledger):
                os.remove(ledger)
            out = fire(transcript, effort)
            return out, only_row()

        row: dict = {}

        def field(name: str, want, why: str) -> None:
            got = row.get(name, "<absent>")
            check(f"{name} = {json.dumps(want)} ({why})", got == want and type(got) is type(want), f"got: {json.dumps(got)}")

        def has_keys(why: str) -> None:
            check(f"the row holds exactly the v1 keys ({why})", sorted(row) == KEYS, json.dumps(sorted(row)))

        def variant(name: str, change: Callable[[list[dict], Callable[[], dict], Callable[..., None]], None]) -> str:
            """The fixture with its records changed, for the cases one line apart."""
            with open(tr, encoding="utf-8") as fh:
                recs = [json.loads(x) for x in fh.read().split("\n") if x.startswith("{") and x.endswith("}")]

            def last_api() -> dict:
                return next(r for r in reversed(recs) if r["type"] == "assistant" and r["message"]["model"] != "<synthetic>")

            def add(**rec) -> None:
                recs.append({"agentId": "afixture", "isSidechain": True, "cwd": recs[0]["cwd"],
                             "timestamp": "2026-10-14T10:00:13.000Z", **rec})

            change(recs, last_api, add)
            out = os.path.join(subagents, f"agent-a{name}.jsonl")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps(r) + "\n" for r in recs))
            shutil.copy(os.path.join(FIXTURE, "agent-afixture.meta.json"), out[: -len(".jsonl")] + ".meta.json")
            return out

        def brief(text) -> Callable:
            """A variant whose brief — the first user message — is `text` (a string, or content blocks)."""
            def change(recs, last_api, add):
                recs[0]["message"]["content"] = text
            return change

        def fenced(body: str, info: str = "agent-fabric-dispatch v1", close: bool = True) -> str:
            return f"```{info}\n{body}" + ("\n```" if close else "")

        with open(tr, encoding="utf-8") as fh:
            transcript_text = fh.read()

        print("subagent ledger: no dispatch header — inferred, the counts and the status")
        out = fire(tr, {"level": "xhigh"})
        check("exit 0, nothing printed", out == "rc=0", out)
        check("one line in the ledger", len(lines()) == 1, "\n".join(lines()))
        row = only_row()
        has_keys("inferred")
        field("schema_version", 1, "every row")
        field("engine", "claude", "the hook's own engine")
        field("attribution", "inferred", "no header in the brief")
        field("purpose", "other-subagent", "no header")
        field("description", DESCRIPTION, "kept, from the .meta.json")
        field("pr", None, "the description is never parsed")
        field("review_round", None, "the description is never parsed")
        field("dispatch_id", None, "no header")
        field("session_id", "sess-1", "the hook's session, from the payload")
        field("parent_session_id", "sess-1", "no header: the hook's session, the dispatcher's")
        field("agent_id", "afixture", "from the payload")
        field("agent_type", "code-review", "from the payload")
        field("tool_use_id", "toolu_fixture", "from the .meta.json")
        field("model", "claude-opus-5-5", "the model of most turns, synthetic not counted")
        field("provider", "anthropic", "a plain model id")
        field("effort", "xhigh", "the hook input's effort.level")
        field("turns", 3, "distinct API messages; the split message once, the synthetic none")
        field("input", 6, "3+2+1")
        field("cache_write", 150, "100+50+0")
        field("cache_read", 3250, "1000+1100+1150")
        field("output", 56, "40 (the split message's final count)+7+9")
        field("reasoning", 30, "msg_A's thinking_tokens once; the others report none")
        field("first_turn_context", 1103, "input+cache_write+cache_read of msg_A")
        field("wall_time", 12.5, "first to last timestamp")
        field("started_at", "2026-10-14T10:00:00.000Z", "no header: the transcript's first timestamp")
        field("repository", "blueteam-ou/agent-fabric", "origin of the transcript's cwd, lowercase")
        field("head_sha", head_sha, "HEAD of the transcript's cwd")
        field("base_sha", None, "no header")
        field("status", "completed", "the last API message ends its turn")
        field("status_source", "transcript:end_turn", "the evidence")
        check("completed_at is an ISO UTC time",
              isinstance(row.get("completed_at"), str) and bool(re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*Z$", row["completed_at"])),
              json.dumps(row))
        check("no text of the transcript reaches the ledger", "NEVER-IN-THE-LEDGER" not in "\n".join(lines()))
        modes = (oct(os.stat(ledger).st_mode & 0o777) if os.path.exists(ledger) else None,
                 oct(os.stat(os.path.dirname(ledger)).st_mode & 0o777) if os.path.exists(ledger) else None)
        check("ledger 600 in a 700 directory", modes == ("0o600", "0o700"), str(modes))

        print("subagent ledger: a second stop appends; no hook effort reads the transcript's")
        fire(tr)
        got = lines()
        try:
            whole = len(got) == 2 and all(isinstance(json.loads(x), dict) for x in got)
        except ValueError:
            whole = False
        check("two whole lines", whole, "\n".join(got))
        row = json.loads(got[-1]) if whole else {}
        field("effort", "high", "no effort input: the effort of most turns (high, high, medium)")

        print("subagent ledger: the dispatch header is copied")
        hdr = {"dispatch_id": "d-1", "parent_session_id": "parent-9", "job_id": "j7", "project": "agent-fabric",
               "repository": "o/n", "pr": 251, "review_id": "r-3", "review_round": 2, "purpose": "pr-review",
               "engine": "codex", "evidence_mode": "pinned", "base_sha": "ade76f23",
               "head_sha": "0123456789abcdef0123456789abcdef01234567", "started_at": "2026-10-14T09:59:00Z",
               "extra": "ignored"}
        t = variant("header", brief([{"type": "text", "text": "Intro line.\n\n" + fenced(json.dumps(hdr))
                                      + "\n\nBRIEF-TEXT-NEVER-IN-THE-LEDGER"}]))
        _, row = fresh(t)
        has_keys("dispatch")
        field("attribution", "dispatch", "the brief's first fenced block is the header")
        field("purpose", "pr-review", "copied")
        field("dispatch_id", "d-1", "copied")
        field("parent_session_id", "parent-9", "copied, over the hook's session")
        field("session_id", "sess-1", "still the hook's")
        field("job_id", "j7", "copied")
        field("project", "agent-fabric", "copied")
        field("pr", 251, "copied")
        field("review_id", "r-3", "copied")
        field("repository", "o/n", "copied, not the cwd's origin")
        field("review_round", 2, "copied")
        field("evidence", "pinned", "copied from evidence_mode")
        field("base_sha", "ade76f23", "copied")
        field("head_sha", "0123456789abcdef0123456789abcdef01234567", "copied, over the cwd's HEAD")
        field("started_at", "2026-10-14T09:59:00Z", "copied, over the first timestamp")
        field("engine", "claude", "the engine that ran, never the header's")
        field("description", DESCRIPTION, "kept beside the header")
        check("no text of the brief reaches a dispatch row", "NEVER-IN-THE-LEDGER" not in "\n".join(lines()))
        _, row = fresh(variant("headercase", brief(fenced('{"repository": "github.com/BlueTeam-OU/Agent-Fabric"}'))))
        field("repository", "blueteam-ou/agent-fabric", "a host-prefixed header repository: owner/name, lowercase")
        _, row = fresh(variant("headernohead", brief(fenced('{"purpose":"pr-review"}'))))
        field("head_sha", None, "a header without head_sha: null, never the cwd's HEAD")
        field("repository", None, "a header without repository: null, never the cwd's origin")

        print("subagent ledger: the header fabric-review renders is read whole")
        # The producer's own output, used verbatim: a key the producer and this
        # hook spell differently is a field never copied. Every value it writes
        # is set, so a null on both sides proves nothing; the parent session is
        # this test's, never the caller's.
        os.environ["CLAUDE_CODE_SESSION_ID"] = "parent-9"
        for mode in ("pinned", "working-tree"):
            rendered = review_brief.dispatch_header(
                {"mode": "re-review", "repository": repo, "range": "a..b", "evidence": mode, "pr": 251,
                 "review_round": 2, "job_id": "j7"},
                {"base_sha": "ade76f23" * 5, "head_sha": "0123456789abcdef0123456789abcdef01234567"},
                "claude", None, "d-1", "2026-10-14T09:59:00Z")
            produced = json.loads("\n".join(rendered[1:-1]))
            check(f"the producer sets every field it writes (evidence_mode {mode})",
                  all(v is not None for v in produced.values()), json.dumps(produced))
            _, row = fresh(variant(f"rendered{mode}", brief("\n".join(rendered) + "\n\n# Review brief")))
            renamed = {"evidence_mode": "evidence"}
            want = {renamed.get(k, k): v for k, v in produced.items() if k != "engine"}
            want["repository"] = produced["repository"].split("/", 1)[1] if produced["repository"] else None
            got = {k: row.get(k, "<absent>") for k in want}
            check(f"every field review_brief writes reaches the row (evidence_mode {mode})",
                  row.get("attribution") == "dispatch" and got == want, f"want {json.dumps(want)}\ngot  {json.dumps(got)}")
            dispatch_repo = row.get("repository")
        _, inferred = fresh(tr)
        check("a dispatch row and an inferred row of one origin name one repository",
              dispatch_repo == inferred.get("repository") == "blueteam-ou/agent-fabric",
              f"{dispatch_repo} / {inferred.get('repository')}")
        del os.environ["CLAUDE_CODE_SESSION_ID"]

        print("subagent ledger: a header field of the wrong type is not copied")
        bad = {"purpose": "a sentence of brief text", "review_id": "r-3\n", "evidence_mode": "trust me",
               "started_at": "2026-10-14T09:59:00", "base_sha": "ade76f23\n", "pr": "251", "review_round": True,
               "head_sha": "not-a-sha", "repository": "https://x:s3cret@github.com/a/b", "dispatch_id": "x" * 201}
        _, row = fresh(variant("badtype", brief(fenced(json.dumps(bad)))))
        field("attribution", "dispatch", "still a header")
        field("pr", None, "a string is not a pr")
        field("review_round", None, "a bool is not a round")
        field("dispatch_id", None, "past 200 characters is not an identifier")
        field("head_sha", None, "not a sha: null, never the cwd's HEAD")
        field("repository", None, "not owner/name: null, never the cwd's origin")
        field("evidence", None, "not pinned or working-tree")
        field("review_id", None, "an identifier with a trailing newline is not one")
        field("base_sha", None, "a sha with a trailing newline is not one")
        field("purpose", "other-subagent", "prose is not an identifier")
        field("started_at", "2026-10-14T10:00:00.000Z", "a time without its zone: the transcript's first timestamp")
        check("the header's credential-shaped value never reaches the row", "s3cret" not in "\n".join(lines()))

        print("subagent ledger: what is not the header is not read as one")
        _, row = fresh(variant("notfirst", brief("see:\n" + fenced("quoted", "text") + "\n"
                                                 + fenced('{"purpose":"pr-review","pr":9}'))))
        check("a header after another fenced block: inferred",
              row.get("attribution") == "inferred" and row.get("purpose") == "other-subagent" and row.get("pr", 0) is None,
              json.dumps(row))
        _, row = fresh(variant("v2", brief(fenced('{"purpose":"pr-review"}', "agent-fabric-dispatch v2"))))
        check("a v2 header: not v1, inferred",
              row.get("attribution") == "inferred" and row.get("purpose") == "other-subagent", json.dumps(row))
        for name, body, close in (("notjson", "{purpose: pr-review}", True), ("array", "[1]", True),
                                  ("unclosed", '{"purpose":"pr-review"}', False)):
            _, row = fresh(variant(f"inv{name}", brief(fenced(body, close=close))))
            check(f"{name} header: invalid-header, other-subagent",
                  row.get("attribution") == "invalid-header" and row.get("purpose") == "other-subagent"
                  and row.get("dispatch_id", 0) is None, json.dumps(row))

        print("subagent ledger: status from how the transcript ends")

        def status_case(name: str, change: Callable, status: str, source: str) -> None:
            _, r = fresh(variant(f"st{name}", change))
            got = f"{r.get('status')} {r.get('status_source')}"
            check(f"{name}: {status} ({source})", got == f"{status} {source}", f"got: {got}")

        def handback(error: bool) -> Callable:
            def change(recs, last_api, add):
                last_api()["message"]["content"] = [{"type": "tool_use", "id": "toolu_h", "name": "SubagentHandback", "input": {}}]
                if not error:
                    last_api()["message"]["stop_reason"] = "tool_use"
                result = {"type": "tool_result", "tool_use_id": "toolu_h", "content": "no" if error else "ok",
                          **({"is_error": True} if error else {})}
                add(type="user", message={"role": "user", "content": [result]})
            return change

        def stop_reason(value) -> Callable:
            def change(recs, last_api, add):
                last_api()["message"]["stop_reason"] = value
            return change

        def api_error(error: str, model: str, usage: bool) -> Callable:
            def change(recs, last_api, add):
                message = {"id": "msg_E", "model": model, "role": "assistant",
                           "content": [{"type": "text", "text": "limit" if usage else "x"}]}
                if usage:
                    message["usage"] = {}
                add(type="assistant", isApiErrorMessage=True, error=error, message=message)
            return change

        def synthetic(recs, last_api, add):
            add(type="assistant", message={"id": "msg_E", "model": "<synthetic>", "role": "assistant",
                                           "content": [{"type": "text", "text": "x"}], "usage": {}})

        def unanswered(recs, last_api, add):
            last_api()["message"]["content"] = [{"type": "tool_use", "id": "toolu_y", "name": "Bash", "input": {}}]
            last_api()["message"]["stop_reason"] = "tool_use"

        def after_result(recs, last_api, add):
            add(type="user", message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_z", "content": "x"}]})

        def interrupted(recs, last_api, add):
            add(type="user", message={"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]})

        status_case("stop-sequence", stop_reason("stop_sequence"), "completed", "transcript:end_turn")
        status_case("handback", handback(False), "completed", "transcript:handback")
        status_case("handback-error", handback(True), "failed", "transcript:handback-error")
        status_case("max-tokens", stop_reason("max_tokens"), "failed", "transcript:stop-reason:max_tokens")
        status_case("api-error", api_error("rate_limit", "<synthetic>", True), "failed", "transcript:api-error:rate_limit")
        status_case("api-error-free-text", api_error("rate limit: see https://x", "<synthetic>", True), "failed",
                    "transcript:api-error:unknown")
        status_case("api-error-flag-only", api_error("server_error", "claude-opus-5-5", False), "failed",
                    "transcript:api-error:server_error")
        status_case("synthetic", synthetic, "cancelled", "transcript:synthetic")
        status_case("tool-use-unanswered", unanswered, "cancelled", "transcript:tool-use-unanswered")
        status_case("after-tool-result", after_result, "cancelled", "transcript:after-tool-result")
        status_case("interrupted", interrupted, "cancelled", "transcript:interrupted")
        status_case("message-incomplete", stop_reason(None), "cancelled", "transcript:message-incomplete")

        def broker(recs, last_api, add):
            for r in recs:
                if r["type"] == "assistant" and r["message"]["model"] != "<synthetic>":
                    r["message"]["model"] = "anthropic/claude-opus-5"

        _, row = fresh(variant("broker", broker))
        field("provider", "openrouter", "a broker vendor/model id")

        def no_reason(recs, last_api, add):
            for r in recs:
                if r["type"] == "assistant":
                    r["message"]["usage"].pop("output_tokens_details", None)

        _, row = fresh(variant("noreason", no_reason))
        field("reasoning", None, "no message reports thinking tokens")

        print("subagent ledger: a run with no API answer still writes its row")

        def first_call_fails(recs, last_api, add):
            del recs[1:]
            api_error("rate_limit", "<synthetic>", True)(recs, last_api, add)

        out, row = fresh(variant("firstcallfails", first_call_fails), {"level": "high"})
        want = {"status": "failed", "status_source": "transcript:api-error:rate_limit", "turns": 0, "output": 0,
                "model": None, "provider": None, "effort": "high"}
        check("first call refused: failed, turns 0", out == "rc=0" and {k: row.get(k, 0) for k in want} == want,
              f"{out} {json.dumps(row)}")

        def brief_only(recs, last_api, add):
            del recs[1:]

        _, row = fresh(variant("briefonly", brief_only))
        check("the brief alone: cancelled, turns 0",
              (row.get("status"), row.get("status_source"), row.get("turns")) == ("cancelled", "transcript:message-incomplete", 0),
              json.dumps(row))

        print("subagent ledger: what it cannot read about, it leaves null")
        other = os.path.join(sandbox, "other")
        os.makedirs(other)
        t2 = os.path.join(other, "agent-anometa.jsonl")
        with open(t2, "w", encoding="utf-8") as fh:
            fh.write(fixture_text.replace("@CWD@", os.path.join(sandbox, "not-a-repo")))
        out, row = fresh(t2)
        want = {"description": None, "tool_use_id": None, "pr": None, "repository": None, "head_sha": None,
                "agent_type": "code-review", "turns": 3}
        check("no .meta.json, no repository: the counts still, the rest null",
              out == "rc=0" and {k: row.get(k, 0) for k in want} == want, f"{out} {json.dumps(row)}")

        print("subagent ledger: a credential in the remote URL never reaches the row")
        for url in ("https://user:s3cret@git.example.com/repo.git", "https://s3cret@host/repo",
                    "https://x:s3cret@github.com/BlueTeam-OU/agent-fabric.git"):
            git("remote", "set-url", "origin", url)
            _, row = fresh(tr)
            got = row.get("repository")
            check(f"{url} -> {got}", isinstance(got, str) and bool(got) and "s3cret" not in got and "@" not in got, str(got))
        git("remote", "set-url", "origin", "git@github.com:BlueTeam-OU/agent-fabric.git")

        print("subagent ledger: no row, no output, exit 0 on what it cannot read")
        empty = os.path.join(subagents, "agent-aempty.jsonl")
        with open(empty, "w", encoding="utf-8") as fh:
            fh.write("".join(x + "\n" for x in transcript_text.split("\n") if '"type":"attachment"' in x))
        for case, run in (("missing-transcript", lambda: fire(os.path.join(sandbox, "nope.jsonl"))),
                          ("no-conversation", lambda: fire(empty)),
                          ("no-path", lambda: run_hook('{"hook_event_name":"SubagentStop","agent_id":"a"}')),
                          ("malformed-stdin", lambda: run_hook("not json")),
                          ("not-an-object", lambda: run_hook("[1]"))):
            if os.path.exists(ledger):
                os.remove(ledger)
            out = run()
            check(f"{case}: nothing written, exit 0", out == "rc=0" and not os.path.exists(ledger), out)

    print(f"\nsubagent ledger: {'all passed' if not fails else f'{fails} failure(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
