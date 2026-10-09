#!/usr/bin/env python3
"""runtime/openrouter/model-audit.sh — which model is THIS session actually
running on, and what would each alias resolve to? Answers from the
environment — the durable version is OTel claude_code.llm_request (model,
agent.name) against local Tempo; the JSONL transcript is documented as
internal and is not parsed.

  runtime/openrouter/model-audit.sh

Prints: the effective provider variables, the four alias pins, the session
model, and how to read back what was actually SERVED (OpenRouter
/generation, the Activity page) — because configured and served can differ,
and the served model is the only ground truth.

Contract (ADR-040 Wave 9; ported from the bash script, which the golden files
in tests/fixtures/model-audit were taken from):
  argv    none read.
  env     ANTHROPIC_*, CLAUDE_CODE_SUBAGENT_MODEL, CLAUDE_CODE_EFFORT_LEVEL,
          AGENT_FABRIC_LAUNCH_{SESSION_MODEL,PROFILE,AGENT}: read, never changed.
  stdout  the report, four sections; stderr nothing; exit 0.
  secrets an ALLOWLIST, not a denylist: only the alias pins, the session pins,
          the effort level and the routing URL (scheme://host[:port], parsed)
          are printed; every other variable of the families is "<set, N chars>"
          (N the byte count of the value), so a name nobody knew about cannot
          leak a credential into output written to be pasted into a PR thread.
Deliberate difference from the bash: the variables are listed in byte order of
their `NAME=value` records, where `sort -z` ordered them by the caller's locale.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit

PRINTED = {"ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
           "ANTHROPIC_DEFAULT_FABLE_MODEL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
           "CLAUDE_CODE_EFFORT_LEVEL"}


def of_interest(name: str) -> bool:
    # CLAUDE_CODE_EFFORT_LEVEL decides the OTHER routed dimension and
    # outranks every agent file, so an audit that cannot see it reports a
    # session it does not fully describe (review of 2026-09-23, F1).
    return name.startswith("ANTHROPIC_") or name in ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL")


def base_url_shown(value: str) -> str:
    """scheme://host[:port] only, PARSED, failing closed: a base URL can carry
    userinfo, a query or a fragment, and the sed that preceded this printed
    every shape it did not match verbatim — an uppercase scheme, `?api_key=`
    with no path (review on PR #679, judged CONFIRMED). Not a URL at all:
    reported set, never echoed."""
    try:
        u = urlsplit(value)
        host, port = u.hostname, u.port
    except ValueError:
        return f"<set, {len(value)} chars>"
    if u.scheme and host:
        return f"{u.scheme}://{host}{':%d' % port if port else ''}"
    return f"<set, {len(value)} chars>"


def names_openrouter(base_url: str) -> bool:
    """Classified on the PARSED hostname, case-insensitively, exact or a
    subdomain of openrouter.ai (the host the ori broker exports): the
    substring test called HTTPS://OPENROUTER.AI vanilla and a look-alike with
    "openrouter" in its path OpenRouter (review on PR #679)."""
    try:
        host = urlsplit(base_url).hostname or ""
    except ValueError:
        host = ""
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


def report(environ: "os._Environ[bytes] | dict[bytes, bytes]") -> list[str]:
    def get(name: str) -> str:
        return os.fsdecode(environ.get(os.fsencode(name), b""))

    out = ["== provider variables in this session's environment =="]
    found = False
    # ALLOWLIST, not denylist (review on PR #679, judged CONFIRMED): a credential
    # in any other ANTHROPIC_* (ANTHROPIC_CUSTOM_HEADERS carrying an Authorization
    # header, ANTHROPIC_FOUNDRY_API_KEY, whatever a proxy adds next) must never
    # reach output written to be pasted into a PR thread. Records are whole
    # `NAME=value` items, so a value holding a newline cannot pose as a name.
    for key, value in sorted(environ.items(), key=lambda kv: kv[0] + b"=" + kv[1]):
        name, v = os.fsdecode(key), os.fsdecode(value)
        if not of_interest(name) or not v:
            continue
        found = True
        if name in PRINTED:
            out.append(f"  {name} = {v}")
        elif name == "ANTHROPIC_BASE_URL":
            out.append(f"  {name} = {base_url_shown(v)}")
        else:
            out.append(f"  {name} = <set, {len(value)} chars>")
    if not found:
        out.append("  (none set — a vanilla Anthropic-routed launch, or variables not exported here)")
    out += ["", "== the launcher's stamp (runtime/openrouter/launch) =="]
    # The session model reaches claude only as --model, which nothing inside the
    # session can read back; the launcher stamps what it applied.
    # AGENT_FABRIC_LAUNCH_* is the stamp the launcher writes.
    session = get("AGENT_FABRIC_LAUNCH_SESSION_MODEL")
    if session:
        out.append(f"  profile : {get('AGENT_FABRIC_LAUNCH_PROFILE') or '?'}")
        if get("AGENT_FABRIC_LAUNCH_AGENT"):
            out.append(f"  agent   : {get('AGENT_FABRIC_LAUNCH_AGENT')}")
        out.append(f"  session : {session}")
    else:
        out += ["  not launched via runtime/openrouter/launch — the session model is the harness",
                "  default or a settings-scope \"model\" key, and is not visible from the",
                "  environment. /status inside the session shows it."]
    out += ["", "== the four alias pins (ANTHROPIC_DEFAULT_*) =="]
    for tier in ("HAIKU", "SONNET", "OPUS", "FABLE"):
        out.append(f"  {tier.lower():<10} {get(f'ANTHROPIC_DEFAULT_{tier}_MODEL') or '<unset — harness default>'}")
    out += ["", "== how to read back what was actually SERVED =="]
    if names_openrouter(get("ANTHROPIC_BASE_URL")):
        out += ["  This session is routed through OpenRouter. After a request:",
                "    GET https://openrouter.ai/api/v1/generation?id=<generation id>",
                "  ...or the Activity page; response 'model'/'provider' name the model",
                "  that ACTUALLY served the request. Configured and served can differ",
                "  (router fallback); the response is the ground truth."]
    else:
        out += ["  ANTHROPIC_BASE_URL does not name OpenRouter in this environment —",
                "  this reads as a vanilla Anthropic-routed session."]
    out += ["", "  The durable path: OTel claude_code.llm_request (model, agent.name)",
            "  against local Tempo — per-request, per-agent, no transcript parsing.",
            "  (The transcript JSONL is documented as internal; do not parse it.)"]
    return out


def main() -> int:
    data = "".join(line + "\n" for line in report(os.environb))
    try:
        sys.stdout.buffer.write(data.encode("utf-8", "surrogateescape"))
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    return 0


if __name__ == "__main__":
    sys.exit(main())
