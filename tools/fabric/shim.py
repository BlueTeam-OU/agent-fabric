#!/usr/bin/env python3
"""tools/fabric/shim.py — a model family's compatibility shim, end to end.

>>> help
    shim.py list                          every preset on the OpenRouter account
    shim.py show <slug> [--version N]     one preset's prompt and config
    shim.py pull <slug>                   live -> routing/shims/<slug>/ (system_prompt.md, config.json)
    shim.py diff <slug>                   routing/shims/<slug>/ against the live designated version
    shim.py push <slug> [--name NAME]     routing/shims/<slug>/ -> a new live version (creates the preset)
    shim.py check <model> [--shim SLUG] [--quick] [--out DIR]
                                          the compatibility task through the composite, read back
<<< help

WHAT A SHIM IS. A model family speaks Claude Code's Anthropic-compatible
wire protocol through OpenRouter only with a compatibility delta: a
system-prompt text OpenRouter PREPENDS to every request, and a provider
routing config. On OpenRouter that object is a PRESET (per account,
`@preset/<slug>`), versioned; the runtime derives the composite
`<model>@preset/<slug>` from routing/shims.json (tools/fabric/routing.py).
Two shims exist — glm2claude-shim, deepseek2claude-shim — both made by
hand in the dashboard on 2026-09-13/14; their text lived nowhere in git.

WHAT THIS TOOL IS FOR (owner, 2026-09-16): the next shim is built, checked
and recorded through the API, from sources under version control:

  routing/shims/<slug>/system_prompt.md   the prepended text
  routing/shims/<slug>/config.json        the provider routing, and any sampling
                                          parameter to pin (temperature, max_tokens,
                                          top_p — verified persisted 2026-09-16); {} for none

    shim.py push <slug>       creates the preset or adds a version (POST
                              /presets/<slug>/messages: `system` becomes
                              the version's system_prompt, `provider`
                              its config; the slug is created if absent)
    shim.py check <model> --shim <slug>
                              runs the six-step compatibility task the
                              DeepSeek admission used (docs/live-checks/
                              2026-09-14-deepseek.md §4) as a headless
                              Claude Code session on the composite, then
                              reads every generation back from
                              /api/v1/generation and judges: tool calls
                              issued, files read, the answer written,
                              no fabricated harness markup, which
                              provider served, tokens and cost
    shim.py diff / pull       keep git and the account in step

Then routing/shims.json gets its family entry (by hand: the note there is
the admission record, and admission to a class is architect-cto's under
routing/policies/review-grade.json), and the check's report goes to
docs/live-checks/. What this never does: print a credential (the key is
read from the environment and only ever sent as a header), or decide
admission.

API, read back 2026-09-16 (docs/live-checks/2026-09-16-openrouter-presets.md):
  GET  /api/v1/presets                    list (data[]: id, name, slug, status, designated_version_id, …)
  GET  /api/v1/presets/{slug}             one, with designated_version {version, system_prompt, config}
  GET  /api/v1/presets/{slug}/versions    all versions, oldest first
  GET  /api/v1/presets/{slug}/versions/N  one version (N is the integer)
  POST /api/v1/presets/{slug}/messages    create the preset / add a version from a messages-shaped body
  GET  /api/v1/generation?id=gen-…        what a request was actually served as
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import httpsafe  # noqa: E402
import roots  # noqa: E402

# ENGINE data (ADR-045 §5 rule 2): a shim is a model family's
# compatibility delta on OpenRouter, the same for every operator — a
# routing default, beside routing/shims.json, which tools/fabric/routing.py
# reads from the engine root too; an operator's choice of models is
# routing/profiles.json. So the engine root (AGENT_FABRIC_ROOT, else this
# checkout), never the operator's tree.
SHIMS_DIR = os.path.join(roots.engine_root(), "routing", "shims")
API = "https://openrouter.ai/api/v1"

# The six-step task: enough tool calls, enough context (the launcher alone
# is 16k characters) and a hard stop, so a model that invents turns,
# imitates harness markup or never answers shows it within one run.
CHECK_TASK = """\
Do exactly these six steps, in order, using the Read tool for files and the Bash tool for the command; \
after step 6 read nothing else and write the answer.
1. Read CLAUDE.md in full.
2. Read README.md in full.
3. Read runtime/openrouter/launch in full.
4. Read tests/run.sh in full.
5. Read routing/capabilities.json in full.
6. Run: bin/fabric-status
Then answer, from what you read and ran, in four short numbered lines: \
(a) the API path and session model bin/fabric-status reported; \
(b) the five capability classes and the openrouter model each maps to in routing/capabilities.json; \
(c) the one sentence in CLAUDE.md that bans machine attribution in commit messages, quoted; \
(d) how many `run "` lines tests/run.sh contains.
Finish your answer with the exact line: CHECK-COMPLETE
"""
QUICK_TASK = """\
Do exactly these two steps, in order, using the Read tool, then answer and read nothing else.
1. Read README.md in full.
2. Read tests/run.sh in full.
Answer in two short numbered lines: (a) the first heading of README.md, quoted; (b) how many `run "` lines tests/run.sh contains.
Finish your answer with the exact line: CHECK-COMPLETE
"""
# Harness markup a model must treat as input and never emit; each is a
# fabrication when found in assistant text (the DeepSeek flash failure).
FABRICATION_MARKS = ("<system-reminder>", "<total_tokens>", "</total_tokens>", "<function_calls>", "<tool_result>")


def die(msg: str) -> "NoReturn":  # noqa: F821
    print(f"shim: {msg}", file=sys.stderr)
    sys.exit(1)


def api_key() -> str:
    """The account's own key, from the file sync writes: no shell sources it
    (ADR-038 rule 9). An exported one still wins, for a caller that set it
    on purpose."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.config/agent-fabric/secrets.env"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("export OPENROUTER_API_KEY="):
                    key = (shlex.split(line.split("=", 1)[1]) or [""])[0]
    except (OSError, ValueError):
        key = None
    if not key:
        die("no OPENROUTER_API_KEY in ~/.config/agent-fabric/secrets.env (fabric-secrets sync).")
    return key


# The API key goes to OpenRouter's host only: a redirect elsewhere is an
# error, never followed with the key; proxies as urllib reads them (https,
# so a CONNECT shows the proxy no header).
OPENER = httpsafe.opener(proxies=True, redirects="same-origin")


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://github.com/BlueTeam-OU/agent-fabric",
                                          "X-Title": "agent-fabric shim.py"})
    try:
        with OPENER.open(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:400].decode(errors="replace")
        die(f"OpenRouter refused {method} {path} ({exc.code}): {detail}")


# ---- sources under version control -----------------------------------------
def source_dir(slug: str) -> str:
    return os.path.join(SHIMS_DIR, slug)


def shown(path: str) -> str:
    """A source path as a person reads it: relative to the engine tree the
    sources are in (SHIMS_DIR's routing/..), not to this code's checkout."""
    return os.path.relpath(path, os.path.dirname(os.path.dirname(SHIMS_DIR)))


def read_source(slug: str) -> tuple[str, dict]:
    d = source_dir(slug)
    prompt_path, config_path = os.path.join(d, "system_prompt.md"), os.path.join(d, "config.json")
    if not os.path.isfile(prompt_path):
        die(f"no source for {slug!r}: {shown(prompt_path)} is missing (shim.py pull {slug}, or write it).")
    with open(prompt_path, encoding="utf-8") as fh:
        prompt = fh.read()
    config: dict = {}
    if os.path.isfile(config_path):
        with open(config_path, encoding="utf-8") as fh:
            config = json.load(fh)
    return prompt, config


def write_source(slug: str, prompt: str, config: dict) -> list[str]:
    d = source_dir(slug); os.makedirs(d, exist_ok=True)
    paths = []
    for name, text in (("system_prompt.md", prompt if prompt.endswith("\n") else prompt + "\n"),
                       ("config.json", json.dumps(config, indent=2, sort_keys=True) + "\n")):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        paths.append(shown(p))
    return paths


# ---- the commands ---------------------------------------------------------------
def cmd_list() -> int:
    for p in call("GET", "/presets").get("data", []):
        print(f"{p['slug']:28} {p['status']:9} {p['name']}")
    return 0


def designated(slug: str) -> tuple[dict, dict]:
    p = call("GET", f"/presets/{slug}").get("data") or {}
    v = p.get("designated_version") or {}
    return p, v


def cmd_show(slug: str, version: int | None) -> int:
    if version:
        v = call("GET", f"/presets/{slug}/versions/{version}").get("data") or {}
        p = {"slug": slug}
    else:
        p, v = designated(slug)
    print(f"# {p.get('name', slug)}  ({slug}, status {p.get('status', '?')}, version {v.get('version')}, "
          f"updated {v.get('updated_at', '?')})\n")
    print("## config\n"); print(json.dumps(v.get("config") or {}, indent=2)); print("\n## system_prompt\n")
    print(v.get("system_prompt") or "(none)")
    return 0


def cmd_pull(slug: str) -> int:
    p, v = designated(slug)
    if not v:
        die(f"{slug!r} has no designated version.")
    for rel in write_source(slug, v.get("system_prompt") or "", v.get("config") or {}):
        print(f"  wrote {rel}")
    print(f"pulled {slug} version {v.get('version')} ({p.get('name')})")
    return 0


def diff_lines(slug: str) -> list[str]:
    prompt, config = read_source(slug)
    _, v = designated(slug)
    live_prompt = (v.get("system_prompt") or "")
    lines = list(difflib.unified_diff(live_prompt.splitlines(), prompt.rstrip("\n").splitlines(),
                                      fromfile=f"live:{slug}@v{v.get('version')}/system_prompt",
                                      tofile=f"routing/shims/{slug}/system_prompt.md", lineterm=""))
    live_cfg = json.dumps(v.get("config") or {}, indent=2, sort_keys=True).splitlines()
    src_cfg = json.dumps(config, indent=2, sort_keys=True).splitlines()
    lines += list(difflib.unified_diff(live_cfg, src_cfg, fromfile=f"live:{slug}@v{v.get('version')}/config",
                                       tofile=f"routing/shims/{slug}/config.json", lineterm=""))
    return lines


def cmd_diff(slug: str) -> int:
    lines = diff_lines(slug)
    if not lines:
        print(f"{slug}: routing/shims/{slug}/ matches the live designated version")
        return 0
    print("\n".join(lines))
    return 1


def cmd_push(slug: str, name: str | None) -> int:
    prompt, config = read_source(slug)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        die(f"slug {slug!r}: lower-case letters, digits and dashes only.")
    body: dict = {"system": prompt.rstrip("\n"), "messages": [{"role": "user", "content": "x"}]}
    body.update({k: v for k, v in config.items() if k != "system"})  # provider, and any persisted parameter
    if name:
        body["name"] = name
    before, _ = designated(slug) if slug in {p["slug"] for p in call("GET", "/presets").get("data", [])} else ({}, {})
    data = call("POST", f"/presets/{slug}/messages", body).get("data") or {}
    v = data.get("designated_version") or {}
    what = "created" if not before else f"new version (was {((before.get('designated_version') or {}).get('version'))})"
    print(f"pushed {slug}: {what} -> version {v.get('version')} ({data.get('name')}, status {data.get('status')})")
    if (v.get("system_prompt") or "").rstrip("\n") != prompt.rstrip("\n"):
        die("the live system_prompt does not match what was sent — read it back with shim.py show.")
    return 0


# ---- the compatibility check ------------------------------------------------------
def generation(gen_id: str) -> dict:
    """The served record for one request. The newest generation is indexed
    a few seconds after the response; retry briefly, then give up quietly
    (an unindexed row is reported as such, never as a failure)."""
    for attempt in range(6):
        req = urllib.request.Request(f"{API}/generation?id={gen_id}",
                                     headers={"Authorization": f"Bearer {api_key()}"})
        try:
            with OPENER.open(req, timeout=30) as resp:
                return json.load(resp).get("data") or {}
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                return {}
            time.sleep(2 + attempt)
    return {}


def cmd_check(model: str, shim: str | None, quick: bool, out: str | None) -> int:
    composite = f"{model}@preset/{shim}" if shim else model
    if not shutil_which("ori"):
        die("the ori CLI is not on PATH (the check runs Claude Code through the broker).")
    out = out or tempfile.mkdtemp(prefix="shim-check-")
    os.makedirs(out, exist_ok=True)
    task = QUICK_TASK if quick else CHECK_TASK
    started = time.time()
    env = {**os.environ, "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"}
    cmd = ["ori", "claude", "--model", composite, "-p", task, "--output-format", "stream-json", "--verbose",
           "--max-turns", "12"]
    print(f"check: {composite}\n  cwd {ROOT}\n  transcript {out}/stream.jsonl", file=sys.stderr)
    with open(os.path.join(out, "stream.jsonl"), "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=fh, stderr=subprocess.PIPE, text=True, timeout=900)
    elapsed = time.time() - started
    events = []
    with open(os.path.join(out, "stream.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("{"):
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
    # What the session did: tool calls, reads, assistant text, the final answer.
    tool_uses, reads, texts, request_ids = [], [], [], []
    for e in events:
        msg = e.get("message") if isinstance(e.get("message"), dict) else None
        if e.get("type") == "assistant" and msg:
            for block in msg.get("content") or []:
                if block.get("type") == "tool_use":
                    tool_uses.append(block.get("name"))
                    if block.get("name") == "Read":
                        reads.append((block.get("input") or {}).get("file_path", ""))
                elif block.get("type") == "text":
                    texts.append(block.get("text") or "")
            # One assistant event per content block: a turn's id repeats.
            rid = e.get("requestId") or (msg.get("id") if isinstance(msg.get("id"), str) and msg["id"].startswith("gen-") else None)
            if rid and rid.startswith("gen-") and rid not in request_ids:
                request_ids.append(rid)
    result = next((e for e in events if e.get("type") == "result"), {})
    answer = (result.get("result") or (texts[-1] if texts else "")) or ""
    fabricated = sorted({m for t in texts for m in FABRICATION_MARKS if m in t})
    expected_reads = 2 if quick else 5
    verdict = {
        "composite": composite, "elapsed_s": round(elapsed, 1), "exit": proc.returncode,
        "turns": len([e for e in events if e.get("type") == "assistant"]),
        "tool_calls": len(tool_uses), "reads": len(reads), "bash": tool_uses.count("Bash"),
        "answered": "CHECK-COMPLETE" in answer, "fabricated_markup": fabricated,
        "harness_cost_usd": result.get("total_cost_usd"), "is_error": result.get("is_error"),
    }
    # What was actually served, per generation: provider, tokens, finish, cost.
    gens = []
    for rid in request_ids:
        g = generation(rid)
        gens.append({"id": rid, "provider": g.get("provider_name") or "(not indexed yet)", "model": g.get("model"),
                     "prompt": g.get("tokens_prompt"), "completion": g.get("tokens_completion"),
                     "reasoning": g.get("native_tokens_reasoning"), "cached": g.get("native_tokens_cached"),
                     "finish": g.get("finish_reason"), "cost": g.get("total_cost")})
    verdict["generations"] = gens
    verdict["providers"] = sorted({g["provider"] for g in gens if g.get("model")})
    verdict["bill_usd"] = round(sum(g.get("cost") or 0 for g in gens), 4) if gens else None
    passed = (proc.returncode == 0 and verdict["answered"] and not fabricated
              and verdict["reads"] >= expected_reads and (quick or verdict["bash"] >= 1))
    verdict["pass"] = passed
    with open(os.path.join(out, "verdict.json"), "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=2)
    with open(os.path.join(out, "answer.md"), "w", encoding="utf-8") as fh:
        fh.write(answer)
    print(json.dumps({k: v for k, v in verdict.items() if k != "generations"}, indent=2))
    if gens:
        print("\n| gen | provider | prompt | completion | reasoning | cached | finish | cost |\n|---|---|--:|--:|--:|--:|---|--:|")
        for g in gens:
            print(f"| `{g['id']}` | {g['provider']} | {g['prompt']} | {g['completion']} | {g['reasoning']} | {g['cached']} | {g['finish']} | {g['cost']} |")
    print(f"\n{'PASS' if passed else 'FAIL'}: {composite}  (report in {out}/)", file=sys.stderr)
    if proc.stderr.strip():
        print(proc.stderr.strip()[-600:], file=sys.stderr)
    return 0 if passed else 1


def shutil_which(name: str) -> str | None:
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shim.py", description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("slug"); s.add_argument("--version", type=int)
    s = sub.add_parser("pull"); s.add_argument("slug")
    s = sub.add_parser("diff"); s.add_argument("slug")
    s = sub.add_parser("push"); s.add_argument("slug"); s.add_argument("--name")
    s = sub.add_parser("check"); s.add_argument("model"); s.add_argument("--shim"); s.add_argument("--quick", action="store_true")
    s.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "list": return cmd_list()
    if a.cmd == "show": return cmd_show(a.slug, a.version)
    if a.cmd == "pull": return cmd_pull(a.slug)
    if a.cmd == "diff": return cmd_diff(a.slug)
    if a.cmd == "push": return cmd_push(a.slug, a.name)
    if a.cmd == "check": return cmd_check(a.model, a.shim, a.quick, a.out)
    return 2


if __name__ == "__main__":
    sys.exit(main())
