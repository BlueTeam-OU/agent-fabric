#!/usr/bin/env python3
"""tools/fabric/gateway_plan.py: the session plan (plan v0) for a login. The gateway's schema is kept in the module as
data and held equal to tests/fixtures/gateway-plan-v0/schema.json (its annotations dropped); the gateway's frozen
example passes it and a corpus of broken variants does not, the verdicts crossed with the `jsonschema` library where it
is installed; a plan per provider column is built from the routing the checkout has and checked rule by rule. Plain
script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gateway_plan as gp  # noqa: E402
import gateway_token  # noqa: E402
import routing  # noqa: E402

TOOL = os.path.join(HERE, "tools", "fabric", "gateway_plan.py")
FIX = os.path.join(HERE, "tests", "fixtures", "gateway-plan-v0")
ME = os.environ.get("USER") or __import__("pwd").getpwuid(os.getuid()).pw_name


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with open(os.path.join(FIX, "schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    with open(os.path.join(FIX, "example.plan.json"), encoding="utf-8") as fh:
        example = json.load(fh)

    print("the schema, as data")
    check("the module's schema is the gateway's, annotations aside", gp.SCHEMA == schema)
    check("the gateway's frozen example passes (the positive control)", gp.validate(example) == [], str(gp.validate(example)))

    print("broken plans")
    def mutate(fn):
        doc = copy.deepcopy(example)
        fn(doc)
        return doc
    broken = {
        "a field the schema does not name": lambda d: d.update(extra=1),
        "schema_version 1": lambda d: d.update(schema_version=1),
        "a missing section": lambda d: d.pop("routes"),
        "two listeners": lambda d: d["listeners"].append(copy.deepcopy(d["listeners"][0])),
        "a bind that is not loopback": lambda d: d["listeners"][0].update(bind="0.0.0.0:0"),
        "a bind port with a leading zero": lambda d: d["listeners"][0].update(bind="127.0.0.1:08080"),
        "a bind port above 65535": lambda d: d["listeners"][0].update(bind="127.0.0.1:65536"),
        "harness_auth from the environment": lambda d: d["listeners"][0]["harness_auth"].update(source="env"),
        "a backend over http": lambda d: d["backends"][0].update(base_url="http://api.anthropic.com"),
        "a base_url with userinfo": lambda d: d["backends"][0].update(base_url="https://u:p@api.anthropic.com"),
        "a base_url with a query": lambda d: d["backends"][0].update(base_url="https://api.anthropic.com/?x=1"),
        "a profile with both name and path": lambda d: d["auth_profiles"][0].update(name="X"),
        "a file profile with a relative path": lambda d: d["auth_profiles"][0].update(path="token"),
        "an env profile with no name": lambda d: d["auth_profiles"][1].pop("name"),
        "the Host header as a credential carrier": lambda d: d["auth_profiles"][1].update(header="Host"),
        "a companion header other than anthropic-beta": lambda d: d["auth_profiles"][0]["companion_headers"][0].update(name="anthropic-version"),
        "a companion value with a comma": lambda d: d["auth_profiles"][0]["companion_headers"][0].update(value="a,b"),
        "a prefix with a control character": lambda d: d["auth_profiles"][0].update(prefix="Bearer\n"),
        "a route with no target model": lambda d: d["routes"][0]["target"].pop("model"),
        "an unknown_route status of 200": lambda d: d["defaults"]["unknown_route"].update(status=200),
        "an opaque_id that is empty": lambda d: d["session"].update(opaque_id=""),
    }
    rules = {
        "an identifier declared twice": lambda d: d["routes"][1].update(route_id=d["routes"][0]["route_id"]),
        "a profile id declared twice": lambda d: d["auth_profiles"][1].update(profile_id=d["auth_profiles"][0]["profile_id"]),
        "a route naming a profile the plan does not declare": lambda d: d["routes"][0].update(auth_profile_id="nope"),
        "a route naming a backend the plan does not declare": lambda d: d["routes"][0]["target"].update(backend_id="nope"),
        "a route naming an ingress the plan does not declare": lambda d: d["routes"][0].update(ingress_id="nope"),
        "a selector on two routes": lambda d: d["routes"][1]["source"].update(model_selector=d["routes"][0]["source"]["model_selector"]),
    }
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    for label, fn in {**broken, **rules}.items():
        problems = gp.validate(mutate(fn))
        check(f"{label} is refused", problems != [], "passed")
        # The library matches ECMAScript patterns with Python's re, where a closing $ also matches before a final
        # newline: it passes "Bearer\n" as a prefix, which the gateway (ECMAScript) refuses. Ours is the stricter.
        if jsonschema is not None and label in broken and label != "a prefix with a control character":
            theirs = list(jsonschema.Draft202012Validator(schema).iter_errors(mutate(fn)))
            check(f"…and the library agrees ({label})", bool(theirs) == bool(problems), str(theirs[:1]))
    if jsonschema is None:
        print("  (jsonschema is not installed: the cross-check is not run)")
    check("a rule the schema cannot say is not a schema error", all(not list(jsonschema.Draft202012Validator(schema).iter_errors(mutate(fn))) for fn in rules.values())
          if jsonschema is not None else True)

    print("a plan per provider column")
    uid = os.getuid()
    for provider in ("anthropic", "openrouter"):
        plan = gp.build(ME, "python-dev", provider)
        doc = plan.doc
        check(f"{provider}: the plan validates", gp.validate(doc) == [], str(gp.validate(doc)))
        want = []
        for m in [routing.resolve_session("python-dev", ME, provider=provider)["composite"],
                  *[routing.resolve(k, provider, "python-dev", ME)["composite"] for k in routing.load_capabilities()["classes"]]]:
            if m not in want:
                want.append(m)
        check(f"{provider}: one identity route per distinct model routing resolves, the session's first",
              [r["source"]["model_selector"] for r in doc["routes"]] == want and all(r["source"]["model_selector"] == r["target"]["model"] for r in doc["routes"]),
              str([r["source"]["model_selector"] for r in doc["routes"]]))
        check(f"{provider}: the selectors returned are the routes' own", [s["selector"] for s in plan.selectors] == want
              and [s["route_id"] for s in plan.selectors] == [r["route_id"] for r in doc["routes"]])
        check(f"{provider}: every route uses the one profile and backend", {r["auth_profile_id"] for r in doc["routes"]} == {doc["auth_profiles"][0]["profile_id"]}
              and {r["target"]["backend_id"] for r in doc["routes"]} == {doc["backends"][0]["backend_id"]})
        check(f"{provider}: the listener is loopback with the OS's port and the key on a descriptor",
              doc["listeners"][0]["bind"] == "127.0.0.1:0" and doc["listeners"][0]["harness_auth"] == {"source": "fd"})
        check(f"{provider}: the bytes are the document, UTF-8 JSON with a final newline, and the digest is their sha256",
              json.loads(plan.bytes) == doc and plan.bytes.endswith(b"}\n") and plan.digest == "sha256:" + hashlib.sha256(plan.bytes).hexdigest())
        again = gp.build(ME, "python-dev", provider)
        check(f"{provider}: the same inputs give the same bytes and digest", again.bytes == plan.bytes and again.digest == plan.digest)
        check(f"{provider}: a session id changes the session alone",
              (lambda other: {k: v for k, v in other.doc.items() if k != "session"} == {k: v for k, v in doc.items() if k != "session"}
               and other.doc["session"]["opaque_id"] == f"{ME}:s1" and other.digest != plan.digest)(gp.build(ME, "python-dev", provider, session="s1")))
        check(f"{provider}: a port is the listener's", gp.build(ME, "python-dev", provider, port=4711).doc["listeners"][0]["bind"] == "127.0.0.1:4711")
    anth = gp.build(ME, "python-dev", "anthropic", uid=4242)
    profile = anth.doc["auth_profiles"][0]
    check("anthropic: the subscription profile reads the login's token file, Authorization Bearer, with the anthropic-beta companion",
          profile == {"profile_id": "claude-subscription", "source": "file", "path": gateway_token.token_path(4242), "header": "Authorization",
                      "prefix": "Bearer ", "companion_headers": [{"name": "anthropic-beta", "value": "oauth-2025-04-20"}]}
          and anth.token_file == gateway_token.token_path(4242) and anth.doc["backends"][0]["base_url"] == "https://api.anthropic.com", str(profile))
    orr = gp.build(ME, "python-dev", "openrouter")
    check("openrouter: the env profile, no token file, the composite ids as selectors",
          orr.doc["auth_profiles"][0] == {"profile_id": "openrouter-key", "source": "env", "name": "OPENROUTER_API_KEY", "header": "Authorization", "prefix": "Bearer "}
          and orr.token_file is None and any("@preset/" in s["selector"] for s in orr.selectors) and orr.doc["backends"][0]["base_url"] == "https://openrouter.ai/api")
    check("a role changes what routing resolves (the session's model), so the plan",
          gp.build(ME, "python-dev", "anthropic").selectors[0]["selector"] != gp.build(ME, None, "anthropic").selectors[0]["selector"])
    check("no credential shape in any plan", all("sk-" not in p.bytes.decode() and "oat01" not in p.bytes.decode() for p in (anth, orr)))
    real = routing.resolve
    def unpinned(klass, provider, *a, **k):
        res = real(klass, provider, *a, **k)
        if klass == "code-low":
            res = {**res, "resolution": "harness", "pinned": False, "alias": "haiku", "model": "haiku", "composite": "haiku"}
        return res
    routing.resolve = unpinned
    try:
        partial = gp.build(ME, "python-dev", "anthropic")
    finally:
        routing.resolve = real
    check("a class that rides a harness alias with no model is named, and has no route",
          len(partial.skipped) == 1 and partial.skipped[0].startswith("code-low:") and "haiku" not in [s["selector"] for s in partial.selectors])
    for bad, why in (({"provider": "gemini"}, "provider"), ({"port": 70000}, "port"), ({"port": True}, "port")):
        try:
            gp.build(ME, "python-dev", **{"provider": "anthropic", **bad})
            msg = ""
        except gp.PlanError as e:
            msg = str(e)
        check(f"a bad {why} is a PlanError, one line", msg != "" and "\n" not in msg, msg)
    try:
        gp.build("no-such-login-zz", "python-dev")
        msg = ""
    except gp.PlanError as e:
        msg = str(e)
    check("a login with no account here is refused by name", "no-such-login-zz" in msg, msg)
    long_model = "x" * 100 + "/" + "y" * 30
    check("a route id is a schema-valid slug however the model is spelled", all(gp.validate(
        {**anth.doc, "routes": [{**anth.doc["routes"][0], "route_id": gp.slug(m)}]}) == [] for m in (long_model, "A/B@c:d", "..", "!!!")))

    print("write and the command")
    with tempfile.TemporaryDirectory() as t:
        path = gp.write(anth, os.path.join(t, "plan.json"))
        check("write: the bytes, 0600, no temporary left", open(path, "rb").read() == anth.bytes and stat.S_IMODE(os.stat(path).st_mode) == 0o600
              and os.listdir(t) == ["plan.json"])
        env = {"PATH": os.environ.get("PATH", ""), "HOME": t}
        r = subprocess.run([sys.executable, "-I", TOOL, "--login", ME, "--role", "python-dev"], env=env, capture_output=True, text=True, timeout=60)
        check("the command prints the plan on stdout", r.returncode == 0 and r.stdout.encode() == gp.build(ME, "python-dev").bytes, r.stderr)
        out = os.path.join(t, "o.json")
        r = subprocess.run([sys.executable, "-I", TOOL, "--login", ME, "--role", "python-dev", "--out", out], env=env, capture_output=True, text=True, timeout=60)
        summary = json.loads(r.stdout)
        check("--out writes it and prints the plan path, digest, selectors, skipped and token file",
              r.returncode == 0 and summary["plan"] == out and summary["plan_digest"] == gp.build(ME, "python-dev").digest
              and summary["selectors"] == gp.build(ME, "python-dev").selectors and summary["token_file"] == gateway_token.token_path(uid)
              and open(out, "rb").read() == gp.build(ME, "python-dev").bytes, r.stdout + r.stderr)
        for argv, label in (([], "no login"), (["--login", ME, "--provider", "gemini"], "an unknown provider"), (["--login", ME, "--validate"], "--validate without --out")):
            r = subprocess.run([sys.executable, "-I", TOOL, *argv], env=env, capture_output=True, text=True, timeout=60)
            check(f"{label}: exit 2, usage on stderr, nothing on stdout", r.returncode == 2 and r.stdout == "" and r.stderr != "", r.stderr)
        r = subprocess.run([sys.executable, "-I", TOOL, "--login", "no-such-login-zz"], env=env, capture_output=True, text=True, timeout=60)
        check("an unknown login: exit 2, one line, no traceback", r.returncode == 2 and r.stderr.count("\n") == 1 and "Traceback" not in r.stderr, r.stderr)
        for code, want_rc, label in ((0, 0, "accepts"), (3, 1, "refuses the plan (exit 3)"), (4, 0, "finds no token file yet (exit 4)"), (1, 1, "fails otherwise")):
            fake = os.path.join(t, f"gw{code}")
            with open(fake, "w") as fh:
                fh.write(f"#!/bin/sh\n[ \"$1\" = validate-plan ] && [ \"$2\" = --plan ] && echo 'note {code}' >&2\nexit {code}\n")
            os.chmod(fake, 0o755)
            r = subprocess.run([sys.executable, "-I", TOOL, "--login", ME, "--role", "python-dev", "--out", out, "--validate", "--gateway-bin", fake],
                               env=env, capture_output=True, text=True, timeout=60)
            v = json.loads(r.stdout)["validation"]
            check(f"--validate: the gateway {label}: exit {want_rc}, its verdict reported", r.returncode == want_rc and v["exit"] == code and v["note"] == f"note {code}", r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-I", TOOL, "--login", ME, "--role", "python-dev", "--out", out, "--validate"], env=env, capture_output=True, text=True, timeout=60)
        check("--validate with no binary on PATH says so and is not a failure", r.returncode == 0 and json.loads(r.stdout)["validation"]["ran"] is False, r.stdout + r.stderr)

    print("test_gateway_plan:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
