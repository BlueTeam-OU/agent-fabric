#!/usr/bin/env python3
"""bin/fabric-genimage (tools/fabric/genimage.py): an image from OpenAI's
image API, saved as a PNG. Ported from a project's scripts/genimage.mjs
and scripts/test/genimage-api-error.sh (the commit that added this file
names them); R1-R9 and K1-K9 are the contract's oracle cases, by its
numbers.

No test reaches api.openai.com: the HTTP call is replaced through the
module's opener seam (the endpoint itself has no override), and the
default opener's redirect and proxy refusals are shown against local
servers, each beside the stock urllib opener as the positive control. The
command itself runs through a link, as bootstrap links it, in a minimal
environment with a scratch HOME and working copy. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import base64
import contextlib
import http.server
import io
import json
import os
import shlex
import socketserver
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import genimage  # noqa: E402

BIN = os.path.join(ROOT, "bin", "fabric-genimage")
FRAG = "Incorrect API key provided: sk-proj-****CANARYabcd"
KEY51 = "sk-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUV"
SECRETS_LINE = "• key:    from ~/.config/agent-fabric/secrets.env"


class FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status, self._body = status, body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class FakeOpener:
    """What the API answers: a status and a body, an exception, or nothing
    until released. Records each request it was given."""

    def __init__(self, status: int = 200, body: bytes = b"", error: BaseException | None = None,
                 hold: threading.Event | None = None):
        self.status, self.body, self.error, self.hold = status, body, error, hold
        self.requests: list[urllib.request.Request] = []

    def open(self, req: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        self.requests.append(req)
        if self.hold is not None:
            self.hold.wait()
        if self.error is not None:
            raise self.error
        if 200 <= self.status < 300:
            return FakeResponse(self.status, self.body)
        raise urllib.error.HTTPError(req.full_url, self.status, "refused", {}, io.BytesIO(self.body))  # type: ignore[arg-type]


def image(data: bytes, **extra: object) -> bytes:
    return json.dumps({"data": [{"b64_json": base64.b64encode(data).decode(), **extra}]}).encode()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as sandbox:
        home, wc, outside, bindir = (os.path.join(sandbox, n) for n in ("home", "wc", "outside", "bin"))
        for d in (home, os.path.join(wc, "sub"), outside, bindir):
            os.makedirs(d)
        base_env = {"PATH": "/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1"}
        subprocess.run(["git", "init", "-q", wc], env=base_env, check=True, capture_output=True, timeout=30)
        link = os.path.join(bindir, "fabric-genimage")
        os.symlink(BIN, link)
        secrets = os.path.join(home, ".config", "agent-fabric", "secrets.env")
        os.makedirs(os.path.dirname(secrets))
        env_local = os.path.join(wc, ".env.local")

        def put(path: str, text: str | None) -> None:
            if text is None:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(path)
                return
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

        def fixture_env(env_key: str | None = None, local: str | None = None, sec: str | None = None) -> dict[str, str]:
            put(env_local, local)
            put(secrets, sec)
            env = dict(base_env)
            if env_key is not None:
                env["OPENAI_API_KEY"] = env_key
            return env

        def run(argv: list[str], env: dict[str, str] | None = None, cwd: str = os.path.join(wc, "sub"),
                opener: FakeOpener | None = None, timeout: float = 5) -> tuple[int, str, str]:
            """In process, through run(): the seams a caller of the command lacks."""
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = genimage.run(argv, environ=env if env is not None else fixture_env(env_key="test-key"), cwd=cwd,
                                  opener=opener or FakeOpener(500, b"{}"), timeout=timeout)
            return rc, out.getvalue(), err.getvalue()

        def cli(argv: list[str], env: dict[str, str], cwd: str = os.path.join(wc, "sub")) -> tuple[int, str, str]:
            r = subprocess.run([link, *argv], cwd=cwd, env={**env, "AGENT_FABRIC_PYTHON": sys.executable},
                               capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            return r.returncode, r.stdout, r.stderr

        print("arguments")
        rc, out, err = cli(["--help"], fixture_env())
        check("--help: stdout, exit 0, every option", rc == 0 and err == "" and all(
            o in out for o in ("-o, --out", "--size", "--quality", "--model", "--background", "--dry-run", "-h, --help",
                               "working copy root", ".env.local", "secrets.env")), out + err)
        for label, argv, line in (
                ("an unknown option", ["p", "-o", "a.png", "--bogus"], "fabric-genimage: unknown option --bogus"),
                ("an option with no value left", ["p", "-o"], "fabric-genimage: -o needs a value"),
                ("--size with no value left", ["p", "-o", "a.png", "--size"], "fabric-genimage: --size needs a value"),
                ("an empty prompt (and no -o: the prompt is checked first)", ["  "],
                 "fabric-genimage: a prompt is required (quote it as one argument)"),
                ("no -o", ["a", "fox"], "fabric-genimage: -o <path> is required (e.g. -o gita/assets/hero.png)"),
                ("-o not a .png", ["p", "-o", "a.jpg"], "fabric-genimage: output must be a .png (the API returns PNG)"),
                ("an unknown option before -h is reported", ["--bogus", "-h"], "fabric-genimage: unknown option --bogus")):
            rc, out, err = cli(argv, fixture_env())
            check(f"{label}: exit 1, one line", rc == 1 and err == line + "\n" and out == "", f"rc={rc}\n{out}{err}")
        rc, out, _ = cli(["-h", "--bogus"], fixture_env())
        check("-h before an unknown option is the help", rc == 0 and out.startswith("usage:"), out)
        rc, out, _ = cli(["a", "fox", "-o", "x/FOX.PNG", "--size", "--dry-run", "--quality", "low"], fixture_env())
        check("a value is the next token whatever it looks like (--size --dry-run); .PNG accepted",
              rc == 1 and "• model gpt-image-1 · --dry-run · quality low\n" in out and "(dry run" not in out, out)

        print("dry run: what is printed, nothing asked")
        rc, out, err = cli(["a", " red", "fox ", "-o", "art/fox.png", "--background", "transparent", "--dry-run"],
                           fixture_env(sec="export OPENAI_API_KEY=sk-from-secrets\n"))
        check("the four lines and the dry-run line, exit 0", rc == 0 and err == "" and out == (
            "• model gpt-image-1 · 1536x1024 · quality high · background transparent\n"
            "• prompt: a  red fox\n• out:    art/fox.png\n" + SECRETS_LINE + "\n(dry run — no request made)\n"),
              f"rc={rc}\n{out}{err}")
        check("…and nothing was written", not os.path.exists(os.path.join(wc, "art")))

        print("the key (K1-K9)")
        values = ("oa-FILE", "sk-proj-a_b.c-d", "it's $x \"q\" sp", "trailing\\")
        check("K1 shlex.quote round trip, compared without printing",
              all(genimage.shell_unquote(shlex.quote(v)) == v for v in values))
        dry = ["p", "-o", "a.png", "--dry-run"]
        for label, env, want in (
                ("K2 only secrets.env", lambda: fixture_env(sec="export OPENAI_API_KEY=s\n"), SECRETS_LINE),
                ("K3 the environment first", lambda: fixture_env(env_key="e", local="OPENAI_API_KEY=l\n", sec="export OPENAI_API_KEY=s\n"),
                 "• key:    from the environment"),
                ("K4 .env.local before secrets.env", lambda: fixture_env(local="OPENAI_API_KEY=l\n", sec="export OPENAI_API_KEY=s\n"),
                 "• key:    from .env.local"),
                ("K5 an exported empty OPENAI_API_KEY counts as unset", lambda: fixture_env(env_key="", local="OPENAI_API_KEY=l\n"),
                 "• key:    from .env.local"),
                ("K7 a value with a newline is unreadable",
                 lambda: fixture_env(sec=f"export OPENAI_API_KEY={shlex.quote('a' + chr(10) + 'b')}\n"),
                 "• key:    present in ~/.config/agent-fabric/secrets.env but unreadable"),
                ("K8 nothing anywhere", fixture_env, "• key:    none found")):
            # Each case's files are written as it runs, not when the table is built.
            rc, out, err = cli(dry, env())
            check(f"{label}: {want.split(':', 1)[1].strip()}", rc == 0 and want + "\n" in out, f"rc={rc}\n{out}{err}")
        rc, out, err = cli(["p", "-o", "a.png"], fixture_env(sec=f"export OPENAI_API_KEY={shlex.quote('a' + chr(10) + 'b')}\n"))
        check("K7 …and a real run exits 1 with the unreadable line", rc == 1 and err == (
            "fabric-genimage: OPENAI_API_KEY present in ~/.config/agent-fabric/secrets.env but unreadable"
            " — run `fabric-secrets sync` again\n"), f"rc={rc}\n{err}")
        rc, out, err = cli(["p", "-o", "a.png"], fixture_env())
        check("K8 …and a real run exits 1 with the not-found line", rc == 1 and err == (
            "fabric-genimage: OPENAI_API_KEY not found in the environment, .env.local or"
            " ~/.config/agent-fabric/secrets.env — run `fabric-secrets sync`, or put `OPENAI_API_KEY=sk-...`"
            " in .env.local at the working copy's root (gitignored)\n"), f"rc={rc}\n{err}")

        def bearer(env: dict[str, str]) -> str | None:
            fake = FakeOpener(200, image(b"png"))
            run(["p", "-o", "k.png"], env=env, opener=fake)
            return fake.requests[0].get_header("Authorization") if fake.requests else None

        # The key line and the key are read apart (CodeQL alert 53 on #110):
        # a key gone between the two reads is a refusal, never a request
        # sent with no key.
        saved_resolve = genimage.resolve_key
        genimage.resolve_key = lambda *a: ""
        try:
            fake = FakeOpener(200, image(b"png"))
            rc, out, err = run(["p", "-o", "gone.png"], env=fixture_env(env_key="e"), opener=fake)
        finally:
            genimage.resolve_key = saved_resolve
        check("a key that was there for the key line and is gone for the request: refused, nothing sent",
              rc == 1 and "OPENAI_API_KEY (from the environment) is gone now" in err and not fake.requests, f"rc={rc}\n{err}")
        check("K6 the last of two export lines is used",
              bearer(fixture_env(sec="export OPENAI_API_KEY=first\nexport OPENAI_API_KEY=second\n")) == "Bearer second")
        check(".env.local: export prefix, quotes stripped, # lines skipped, the first non-empty value wins",
              bearer(fixture_env(local="# OPENAI_API_KEY=commented\nOPENAI_API_KEY=\nexport OPENAI_API_KEY='quoted'\n"
                                "OPENAI_API_KEY=later\n")) == "Bearer quoted")
        for empty in ("", "''", '""'):
            check(f"secrets.env: an empty value ({empty or 'nothing'}) is unreadable",
                  "but unreadable" in cli(dry, fixture_env(sec=f"export OPENAI_API_KEY={empty}\n"))[1])
        env = fixture_env()
        os.makedirs(env_local)
        rc, out, err = cli(dry, env)
        check(".env.local that cannot be read: a line naming it, exit 1",
              rc == 1 and err == "fabric-genimage: cannot read .env.local (EISDIR)\n", f"rc={rc}\n{err}")
        os.rmdir(env_local)
        check("secrets.env: a word after the value is unreadable, never guessed",
              cli(dry, fixture_env(sec="export OPENAI_API_KEY=abc def\n"))[1].count("but unreadable") == 1)
        canary = "sk-CANARY-from-secrets-0123456789"
        seen = []
        for opener in (None, FakeOpener(401, FRAG.encode()), FakeOpener(200, image(b"x"))):
            env = fixture_env(sec=f"export OPENAI_API_KEY={canary}\n")
            if opener is None:
                seen.append("".join(cli(dry, env)[1:]))
            else:
                seen.append("".join(run(["p", "-o", "c.png"], env=env, opener=opener)[1:]))
        check("K9 a key from secrets.env appears 0 times, dry run, refusal or success",
              all(canary not in s for s in seen) and len(seen) == 3, "\n".join(seen))

        print("refusals (R1-R9): status and allow-listed type/code only")
        cases = (
            ("R1 401, JSON body", 401, json.dumps({"error": {"message": FRAG, "type": "invalid_request_error",
                                                             "code": "invalid_api_key"}}),
             ["API 401", "invalid_request_error/invalid_api_key"], None),
            ("R2 401, not JSON", 401, f"<html>{FRAG}</html>", ["API 401", "unparseable body"], None),
            ("R3 a fragment in code", 401, json.dumps({"error": {"message": "x", "type": "invalid_request_error",
                                                                 "code": FRAG}}),
             ["API 401", "invalid_request_error/other"], None),
            ("R4 JSON without error", 500, json.dumps({"detail": FRAG}), ["API 500", "no error type"], None),
            ("R5 a whole key in code", 401, json.dumps({"error": {"message": "x", "type": "invalid_request_error",
                                                                  "code": KEY51}}),
             [], "fabric-genimage: API 401 (invalid_request_error/other)"),
            ("R6 a whole key in type", 401, json.dumps({"error": {"message": "x", "type": KEY51,
                                                                  "code": "invalid_api_key"}}),
             [], "fabric-genimage: API 401 (other/invalid_api_key)"),
            ("R7 an unlisted code", 400, json.dumps({"error": {"type": "invalid_request_error", "code": "some_new_code"}}),
             [], "fabric-genimage: API 400 (invalid_request_error/other)"),
            ("R8 a null code left out", 429, json.dumps({"error": {"type": "insufficient_quota", "code": None}}),
             [], "fabric-genimage: API 429 (insufficient_quota)"),
            ("an error that is not an object", 400, json.dumps({"error": FRAG}), [], "fabric-genimage: API 400 (no error type)"),
            ("NaN is not JSON", 400, "NaN", [], "fabric-genimage: API 400 (unparseable body)"),
            ("an error with neither type nor code", 401, json.dumps({"error": {"message": FRAG}}), [],
             "fabric-genimage: API 401 (no error type)"),
            ("a type that is not a string", 401, json.dumps({"error": {"type": 5}}), [],
             "fabric-genimage: API 401 (other)"),
            ("JSON nested past Python's recursion keeps the status", 401, "[" * 200000 + "]" * 200000, [],
             "fabric-genimage: API 401 (no error type)"),
            ("a leading BOM is dropped, as Node's text() does", 401,
             "\ufeff" + json.dumps({"error": {"type": "invalid_request_error"}}), [],
             "fabric-genimage: API 401 (invalid_request_error)"),
            ("a 3xx is a refusal", 302, "", [], "fabric-genimage: API 302 (unparseable body)"),
        )
        for label, status, body, wants, line in cases:
            rc, out, err = run(["test", "-o", "r.png"], opener=FakeOpener(status, body.encode()))
            both = out + err
            good = rc == 1 and "CANARY" not in both and KEY51 not in both and all(w in err for w in wants)
            if line is not None:
                good = good and line in err.splitlines()
            check(label, good, f"rc={rc}\n{both}")
        check("R9 an sk- value is refused even when a list holds it",
              genimage.error_kind(json.dumps({"error": {"type": "sk-on-list", "code": "sk-on-list"}}).encode(),
                                  frozenset({"sk-on-list"}), frozenset({"sk-on-list"})) == "other/other")
        check("…and a listed value that is not sk- prints as itself (R9's control)",
              genimage.error_kind(json.dumps({"error": {"type": "listed"}}).encode(), frozenset({"listed"}),
                                  frozenset()) == "listed")

        print("the request")
        fake = FakeOpener(200, image(b"png"))
        run(["a", "fox", "-o", "q.png", "--background", "opaque", "--model", "dall-e-3"], opener=fake)
        req = fake.requests[0] if fake.requests else None
        check("POST to the one endpoint, JSON, the key as a bearer token",
              req is not None and req.full_url == genimage.ENDPOINT and req.get_method() == "POST"
              and req.get_header("Content-type") == "application/json"
              and req.get_header("Authorization") == "Bearer test-key")
        check("the body: model, prompt, n, size, quality, background, response_format for dall-e",
              req is not None and req.data == json.dumps(
                  {"model": "dall-e-3", "prompt": "a fox", "n": 1, "size": "1536x1024", "quality": "high",
                   "background": "opaque", "response_format": "b64_json"}, separators=(",", ":")).encode(),
              repr(req.data if req else None))
        fake = FakeOpener(200, image(b"png"))
        run(["p", "-o", "q2.png"], opener=fake)
        check("no background or response_format unless asked",
              json.loads(fake.requests[0].data) == {"model": "gpt-image-1", "prompt": "p", "n": 1,
                                                    "size": "1536x1024", "quality": "high"})

        print("success")
        rc, out, err = run(["p", "-o", "deep/er/half.png"],
                           opener=FakeOpener(200, image(b"\x00" * 512, revised_prompt="a better fox") .replace(
                               b"}]}", b'}], "usage": {"total_tokens": 9, "input_tokens": 4, "output_tokens": 5}}')))
        written = os.path.join(wc, "deep", "er", "half.png")
        check("written under the working copy root from a subdirectory, parents created",
              rc == 0 and os.path.isfile(written) and open(written, "rb").read() == b"\x00" * 512, f"rc={rc}\n{err}")
        check("512 bytes is 1 KB: round half up, as the .mjs", "✓ wrote deep/er/half.png (1 KB)\n" in out, out)
        check("the revised prompt and the tokens lines", out.endswith(
            "  revised prompt: a better fox\n  tokens: 9 (input 4, output 5)\n"), out)
        rc, out, _ = run(["p", "-o", "half.png"], opener=FakeOpener(200, image(b"\x00" * 2560)))
        check("2560 bytes is 3 KB (half to even would say 2); replaced in place", "(3 KB)\n" in out
              and open(os.path.join(wc, "half.png"), "rb").read() == b"\x00" * 2560, out)
        rc, out, _ = run(["p", "-o", "half.png"], opener=FakeOpener(200, image(b"\x01" * 3)))
        check("an existing file is replaced", rc == 0 and open(os.path.join(wc, "half.png"), "rb").read() == b"\x01" * 3)
        rc, out, _ = run(["p", "-o", "u.png"], opener=FakeOpener(200, image(b"x").replace(
            b"}]}", b'}], "usage": {"total_tokens": 9}}')))
        check("a missing usage field prints ?", out.endswith("  tokens: 9 (input ?, output ?)\n"), out)
        rc, out, _ = run(["p", "-o", "u.png"], opener=FakeOpener(200, image(b"x").replace(b"}]}", b'}], "usage": 7}')))
        check("a usage that is not an object prints no tokens line", rc == 0 and "tokens" not in out, out)
        left = sorted(n for n in os.listdir(wc) if ".tmp-" in n)
        check("no temporary file is left beside a written one", left == [], " ".join(left))

        print("no image data: nothing written")
        for label, body in (("a 2xx that is not JSON", b"<html>ok</html>"), ("no data", b"{}"),
                            ("b64_json that is not base64", b'{"data":[{"b64_json":"%%%"}]}'),
                            ("an empty b64_json", b'{"data":[{"b64_json":""}]}'),
                            ("JSON nested past Python's recursion", b"[" * 200000 + b"]" * 200000)):
            rc, out, err = run(["p", "-o", "none.png"], opener=FakeOpener(200, body))
            check(label, rc == 1 and err == "fabric-genimage: no image data in response\n"
                  and not os.path.exists(os.path.join(wc, "none.png")), f"rc={rc}\n{err}")

        print("failures name a class, never text")
        rc, out, err = run(["p", "-o", "t.png"], opener=FakeOpener(error=urllib.error.URLError(
            ConnectionRefusedError(111, f"refused at https://api.openai.com Bearer {KEY51}"))))
        check("a transport failure: its reason's class only", rc == 1 and err ==
              "fabric-genimage: request failed (ConnectionRefusedError)\n" and KEY51 not in out + err, err)
        rc, out, err = run(["p", "-o", "t.png"], opener=FakeOpener(error=ValueError(f"header Bearer {KEY51}")))
        check("any other exception in the request: its class only",
              rc == 1 and err == "fabric-genimage: request failed (ValueError)\n", err)
        hold = threading.Event()
        try:
            rc, out, err = run(["p", "-o", "t.png"], opener=FakeOpener(200, image(b"x"), hold=hold), timeout=0.2)
        finally:
            hold.set()
        check("no answer within the time: TimeoutError, nothing written",
              rc == 1 and err == "fabric-genimage: request failed (TimeoutError)\n"
              and not os.path.exists(os.path.join(wc, "t.png")), f"rc={rc}\n{err}")
        put(os.path.join(wc, "blocker"), "a file\n")
        rc, out, err = run(["p", "-o", "blocker/x.png"], opener=FakeOpener(200, image(b"x")))
        check("a write that fails: the path as given and the errno name",
              rc == 1 and err in ("fabric-genimage: cannot write blocker/x.png (ENOTDIR)\n",
                                  "fabric-genimage: cannot write blocker/x.png (EEXIST)\n"), err)
        os.makedirs(os.path.join(wc, "adir.png"))
        rc, out, err = run(["p", "-o", "adir.png"], opener=FakeOpener(200, image(b"x")))
        check("a directory at the path: refused, the directory kept, no temporary left",
              rc == 1 and err == "fabric-genimage: cannot write adir.png (EISDIR)\n"
              and os.path.isdir(os.path.join(wc, "adir.png"))
              and not [n for n in os.listdir(wc) if ".tmp-" in n], err)

        print("the working copy root")
        put(os.path.join(outside, ".env.local"), "OPENAI_API_KEY=outside\n")
        fake = FakeOpener(200, image(b"x"))
        rc, _, err = run(["p", "-o", "o.png"], env=fixture_env(), cwd=outside, opener=fake)
        check("outside a repository: the cwd (.env.local read there, the file written there)",
              rc == 0 and fake.requests[0].get_header("Authorization") == "Bearer outside"
              and os.path.isfile(os.path.join(outside, "o.png")), err)
        rc, _, err = run(["p", "-o", "o.png"], env={**fixture_env(env_key="k"), "GIT_DIR": os.path.join(outside, "nothing")},
                         opener=FakeOpener(200, image(b"x")))
        check("a session's GIT_DIR does not move it", rc == 0 and os.path.isfile(os.path.join(wc, "o.png")), err)
        rc, _, err = run(["p", "-o", "o.png"], env={**fixture_env(env_key="k"), "PATH": os.path.join(sandbox, "empty")},
                         opener=FakeOpener(200, image(b"x")))
        check("git missing: refused, never taken as the cwd",
              rc == 1 and err == "fabric-genimage: cannot find the working copy root (git is not installed)\n", err)

        print("the default opener: no redirect, no proxy (beside urllib's stock opener)")
        hits: dict[str, int] = {"far": 0, "proxy": 0, "near": 0}

        def server(name: str, status: int, location: str | None = None) -> socketserver.TCPServer:
            class H(http.server.BaseHTTPRequestHandler):
                def do_GET(self) -> None:
                    hits[name] += 1
                    self.send_response(status)
                    if location:
                        self.send_header("Location", location)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

                def log_message(self, *a: object) -> None:
                    pass
            s = socketserver.TCPServer(("127.0.0.1", 0), H)
            threading.Thread(target=s.serve_forever, daemon=True).start()
            return s

        far = server("far", 200)
        near = server("near", 302, f"http://127.0.0.1:{far.server_address[1]}/")
        proxy = server("proxy", 200)
        url = f"http://127.0.0.1:{near.server_address[1]}/"
        saved = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY")}
        try:
            for k in ("no_proxy", "NO_PROXY"):
                os.environ.pop(k, None)
            os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{proxy.server_address[1]}"
            with contextlib.suppress(Exception):
                urllib.request.build_opener().open(url, timeout=10).close()
            control = dict(hits)
            hits.update(far=0, proxy=0, near=0)
            os.environ.pop("http_proxy"), os.environ.pop("HTTP_PROXY")
            with contextlib.suppress(Exception):
                urllib.request.build_opener().open(url, timeout=10).close()
            control_redirect = dict(hits)
            hits.update(far=0, proxy=0, near=0)
            os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{proxy.server_address[1]}"
            code = None
            try:
                genimage.make_opener().open(url, timeout=10).close()
            except urllib.error.HTTPError as e:
                code = e.code
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            for s in (far, near, proxy):
                s.shutdown()
                s.server_close()
        check("control: urllib's stock opener goes through *_PROXY", control["proxy"] == 1, json.dumps(control))
        check("control: urllib's stock opener follows a redirect to another host",
              control_redirect == {"far": 1, "proxy": 0, "near": 1}, json.dumps(control_redirect))
        check("make_opener ignores the proxy and does not follow: the 302 is the answer",
              code == 302 and hits == {"far": 0, "proxy": 0, "near": 1}, f"code={code} {json.dumps(hits)}")

    print(f"\ntest_genimage: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
