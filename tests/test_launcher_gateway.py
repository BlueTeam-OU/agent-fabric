#!/usr/bin/env python3
"""tools/fabric/launcher/gateway.py and what makes `--provider gateway` a provider
the rest of the tools understand: the version check, READY parsing, the harness's
environment, the state record, and the mapping of "gateway" to the anthropic column.
The launch end to end, with a fake gateway, is tests/test_launch_cli.py's. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import launch  # noqa: E402,F401  (loads the fabric_launcher package)
import install_agent_files  # noqa: E402
from fabric_launcher import gateway  # noqa: E402
from fabric_launcher.base import Refused  # noqa: E402
import resume  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    def refused(fn, *a, **kw) -> str:
        try:
            fn(*a, **kw)
        except Refused as e:
            return str(e)
        return ""

    with tempfile.TemporaryDirectory(prefix="test_launcher_gateway.") as tmp:
        def script(name: str, body: str) -> str:
            path = os.path.join(tmp, name)
            with open(path, "w") as fh:
                fh.write("#!/usr/bin/env python3\n" + body)
            os.chmod(path, 0o755)
            return path

        ok_json = '{"gateway_version": "1.2.3", "runtime_contract": 1, "plan_schemas": [0, 1]}'
        print("the version check")
        v = gateway.check_version(script("ok", f"print('''{ok_json}''')"))
        check("a supported contract and a plan schema it accepts: returned", v["gateway_version"] == "1.2.3", v)
        for label, body, wants in (
                ("an unsupported runtime contract", "print('{\"gateway_version\":\"1.2.3\",\"runtime_contract\":2,\"plan_schemas\":[0]}')", "speaks runtime contract 2"),
                ("a gateway that does not accept plan schema 0", "print('{\"gateway_version\":\"1.2.3\",\"runtime_contract\":1,\"plan_schemas\":[1]}')", "accepts plan schemas [1]"),
                ("a contract that is a string", "print('{\"gateway_version\":\"1\",\"runtime_contract\":\"1\",\"plan_schemas\":[0]}')", "did not answer"),
                ("a bool contract", "print('{\"gateway_version\":\"1\",\"runtime_contract\":true,\"plan_schemas\":[0]}')", "did not answer"),
                ("not JSON", "print('hello')", "did not answer"),
                ("a JSON array", "print('[]')", "did not answer"),
                ("a non-zero exit", "import sys\nprint('{}')\nsys.exit(3)", "exited 3")):
            msg = refused(gateway.check_version, script("bad", body))
            check(f"{label}: refused, nothing started", wants in msg and "Nothing started" in msg, msg)
        check("a missing binary: refused", "cannot run" in refused(gateway.check_version, os.path.join(tmp, "absent")))
        check("a hung --version: refused at the bound", "did not answer within" in refused(
            gateway.check_version, script("hang", "import time\ntime.sleep(30)"), 1))

        print("READY")
        digest = "sha256:" + "a" * 64
        good = {"event": "ready", "gateway_version": "1", "runtime_contract": 1, "plan_schema": 0,
                "listener": "http://127.0.0.1:54321", "plan_digest": digest}

        def parse_raises(**over) -> str:
            try:
                gateway._parse_ready((json.dumps({**good, **over}) + "\n").encode(), digest)
            except gateway._Refuse as e:
                return str(e)
            return ""
        check("a good READY parses", parse_raises() == "")
        for label, over, wants in (("an unsupported contract", {"runtime_contract": 2}, "runtime contract 2"),
                                   ("a plan schema other than 0", {"plan_schema": 1}, "plan schema 1"),
                                   ("a public listener", {"listener": "http://0.0.0.0:54321"}, "not loopback"),
                                   ("an https listener", {"listener": "https://127.0.0.1:54321"}, "not loopback"),
                                   ("a listener port above 65535", {"listener": "http://127.0.0.1:99999"}, "not loopback"),
                                   ("a listener with a path", {"listener": "http://127.0.0.1:54321/x"}, "not loopback"),
                                   ("a digest of another plan", {"plan_digest": "sha256:" + "b" * 64}, "not the sha256"),
                                   ("a malformed digest", {"plan_digest": "nope"}, "no plan digest"),
                                   ("another event", {"event": "starting"}, "not a READY record")):
            check(f"{label}: refused", wants in parse_raises(**over), parse_raises(**over))
        try:
            gateway._parse_ready(b"not json\n", digest)
            got = ""
        except gateway._Refuse as e:
            got = str(e)
        check("a first line that is not JSON: refused", "not a READY record" in got, got)

        print("the harness's environment, the state record")
        class Fake:
            pid, listener, plan_digest, version, runtime_contract, key = 4242, "http://127.0.0.1:1", digest, "1", 1, "k" * 64
            started_at = "2026-10-10T00:00:00Z"
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "t", "ANTHROPIC_AUTH_TOKEN": "t", "ANTHROPIC_API_KEY": "old", "OPENROUTER_API_KEY": "o",
               "ANTHROPIC_CUSTOM_HEADERS": "h", "ANTHROPIC_MODEL": "m", "PATH": "/bin", "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-x"}
        gateway.harness_env(Fake, env)
        check("the base URL and the local key are set; every upstream credential and broker variable is gone",
              env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:1" and env["ANTHROPIC_API_KEY"] == "k" * 64
              and not any(k in env for k in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
                                              "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_MODEL")), env)
        check("…and what is not a credential is left", env["PATH"] == "/bin" and env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-x", env)
        state = os.path.join(tmp, "state")
        gateway.record_state(state, Fake)
        rec = open(os.path.join(state, "gateway.json")).read()
        check("the record holds pid, version, listener, plan digest, started_at and not the key",
              json.loads(rec) == {"pid": 4242, "gateway_version": "1", "runtime_contract": 1, "listener": "http://127.0.0.1:1",
                                  "plan_digest": digest, "started_at": "2026-10-10T00:00:00Z"} and "k" * 8 not in rec, rec)
        gateway.forget_state(state)
        check("forgotten at the end", not os.path.exists(os.path.join(state, "gateway.json")))
        gateway.forget_state(state)
        check("forgetting what is not there is not an error", True)
        try:
            gateway.plan_digest(os.path.join(tmp, "no-plan"))
            got = ""
        except Refused as e:
            got = str(e)
        check("a plan that cannot be read: refused, nothing started", "cannot be read" in got and "Nothing started" in got, got)
        env2 = {}
        os.environ.pop("AGENT_FABRIC_GATEWAY_READY_TIMEOUT_S", None)
        check("the READY wait defaults", gateway.ready_timeout(env2) == gateway.READY_TIMEOUT_S)
        check("…is overridable", gateway.ready_timeout({"AGENT_FABRIC_GATEWAY_READY_TIMEOUT_S": "7"}) == 7.0)
        check("…and a bad override falls back", gateway.ready_timeout({"AGENT_FABRIC_GATEWAY_READY_TIMEOUT_S": "-1"}) == gateway.READY_TIMEOUT_S)
        found = script("agent-fabric-gateway", "pass")
        check("the installed binary: AGENT_FABRIC_GATEWAY_BIN wins; else the one on PATH",
              gateway.binary_path({"AGENT_FABRIC_GATEWAY_BIN": "/x/gw", "PATH": tmp}) == "/x/gw"
              and gateway.binary_path({"PATH": f"/nonexistent:{tmp}"}) == found, found)
        check("no binary anywhere: refused", "not installed" in refused(gateway.binary_path, {"PATH": "/nonexistent"}))

    print("gateway is a provider the other tools read")
    check("install_agent_files knows it and reads it as the anthropic column",
          "gateway" in install_agent_files.PROVIDERS and install_agent_files.routing_provider("gateway") == "anthropic"
          and install_agent_files.routing_provider("openrouter") == "openrouter")
    with tempfile.TemporaryDirectory(prefix="test_launcher_gateway.") as tmp:
        prof = os.path.join(tmp, "profiles.json")
        with open(prof, "w") as fh:
            json.dump({"agents": {"alice": {"launch_provider": "gateway"}}, "roles": {"r": {"launch_provider": "openrouter"}},
                       "defaults": {"launch_provider": "anthropic"}}, fh)
        os.environ["AGENT_FABRIC_RESUME_PROFILES"] = prof
        try:
            check("fabric-resume takes a profile's launch_provider of gateway for the agent that names it",
                  resume.profile_provider("alice", "r") == "gateway" and resume.profile_provider("bob", "r") == "openrouter", (
                      resume.profile_provider("alice", "r"), resume.profile_provider("bob", "r")))
        finally:
            del os.environ["AGENT_FABRIC_RESUME_PROFILES"]

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
