#!/usr/bin/env python3
"""Tests for tools/fabric/httpsafe.py: a credential reaches only the host
it was given for. Local servers only; each guard has its control, urllib's
own default, which does leak, so a pass means the guard did the work."""
from __future__ import annotations

import http.server
import os
import socket
import sys
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import httpsafe  # noqa: E402
import relay  # noqa: E402
import shim  # noqa: E402
import store_provision  # noqa: E402

SECRET = "Bearer not-a-real-credential"


def serve(handler) -> http.server.HTTPServer:
    s = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    seen: list = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — the stdlib's name
            seen.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    target = serve(Target)

    def redirector(location: str):
        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/landed":
                    seen.append((self.path, self.headers.get("Authorization")))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"{}")
                    return
                self.send_response(302)
                # {port} is this server's own, for a redirect that changes only the scheme.
                self.send_header("Location", location.replace("{port}", str(self.server.server_port)))
                self.end_headers()

            def log_message(self, *a):
                pass
        return serve(Redirect)

    # "localhost" is another host name than "127.0.0.1": another origin.
    away = redirector(f"http://localhost:{target.server_port}/stolen")

    def get(op, url: str):
        return op.open(urllib.request.Request(url, headers={"Authorization": SECRET}), timeout=10)

    print("redirects")
    seen.clear()
    get(urllib.request.build_opener(urllib.request.ProxyHandler({})), f"http://127.0.0.1:{away.server_port}/").read()
    check("control: urllib's default follows to another host WITH the header", ("/stolen", SECRET) in seen, seen)
    for redirects in ("same-origin", "none"):
        seen.clear()
        try:
            get(httpsafe.opener(proxies=False, redirects=redirects), f"http://127.0.0.1:{away.server_port}/")
            check(f"{redirects}: a redirect to another host is refused", False)
        except urllib.error.HTTPError as e:
            check(f"{redirects}: a redirect to another host is an HTTPError ({e.code}), never followed", e.code == 302 and not seen, seen)
    same = redirector("/landed")
    seen.clear()
    get(httpsafe.opener(proxies=False, redirects="same-origin"), f"http://127.0.0.1:{same.server_port}/").read()
    check("same-origin: a redirect on the same host is followed, the header with it", seen == [("/landed", SECRET)], seen)
    seen.clear()
    try:
        get(httpsafe.opener(proxies=False, redirects="none"), f"http://127.0.0.1:{same.server_port}/")
        check("none: even a same-host redirect is refused", False)
    except urllib.error.HTTPError as e:
        check("none: even a same-host redirect is refused", e.code == 302 and not seen, seen)
    for label, location in (("another port", f"http://127.0.0.1:{target.server_port}/stolen"),
                            ("another scheme, the same host and port", "https://127.0.0.1:{port}/stolen"),
                            ("a port that is no number", "http://127.0.0.1:abc/stolen")):
        r = redirector(location)
        seen.clear()
        try:
            get(httpsafe.opener(proxies=False, redirects="same-origin"), f"http://127.0.0.1:{r.server_port}/")
            check(f"same-origin: {label} is refused", False)
        except urllib.error.HTTPError as e:
            check(f"same-origin: {label} is another origin, an HTTPError, never followed", e.code == 302 and not seen, seen)
        r.shutdown()
        r.server_close()
    for bad in ("all", "", None):
        try:
            httpsafe.opener(proxies=False, redirects=bad)
            check(f"redirects={bad!r} is refused", False)
        except ValueError:
            check(f"redirects={bad!r} is refused", True)

    print("proxies")
    caught: list = []
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(4)

    def proxy():
        while True:
            try:
                c, _ = lsock.accept()
            except OSError:
                return
            caught.append(c.recv(65536))
            c.sendall(b"HTTP/1.1 502 x\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            c.close()
    threading.Thread(target=proxy, daemon=True).start()
    saved = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "no_proxy", "NO_PROXY")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        os.environ["http_proxy"] = f"http://127.0.0.1:{lsock.getsockname()[1]}"
        relay_url = f"http://127.0.0.1:{target.server_port}"

        def leaked() -> bool:
            return any(b"not-a-real-credential" in d for d in caught)
        try:
            get(urllib.request.build_opener(), f"http://relay.invalid:{target.server_port}/x")
        except urllib.error.HTTPError:
            pass
        check("control: urllib's default opener sends an http:// request through http_proxy, the header in clear",
              leaked(), caught)
        caught.clear()
        seen.clear()
        get(httpsafe.opener(proxies=True, redirects="none"), relay_url + "/plain").read()
        check("proxies=True: never the http proxy, which would carry the header in clear",
              not caught and seen == [("/plain", SECRET)], (caught, seen))
        os.environ["https_proxy"] = os.environ["http_proxy"]
        try:
            get(httpsafe.opener(proxies=True, redirects="none"), "https://api.invalid/x")
        except (urllib.error.URLError, OSError):
            pass
        connect = [d for d in caught if d.startswith(b"CONNECT ")]
        check("proxies=True: the https proxy by CONNECT, which carries no Authorization",
              connect and not leaked(), caught)
        caught.clear()
        try:
            get(httpsafe.opener(proxies=False, redirects="none"), "https://127.0.0.1:1/x")
        except (urllib.error.URLError, OSError):
            pass
        check("proxies=False: not the https proxy either", not caught, caught)
        del os.environ["https_proxy"]
        caught.clear()
        seen.clear()
        get(httpsafe.opener(proxies=False, redirects="none"), relay_url + "/direct").read()
        check("proxies=False: the environment's proxy is never asked", not caught and seen == [("/direct", SECRET)], (caught, seen))
        seen.clear()
        relay.call(relay_url, "not-a-real-credential", "/api/x")
        check("relay.call: straight to the relay, never through http_proxy", not caught and seen == [("/api/x", SECRET)],
              (caught, seen))
        seen.clear()
        try:
            relay.call(f"http://127.0.0.1:{away.server_port}", "not-a-real-credential", "/api/x")
            check("relay.call: a redirect is an error", False)
        except urllib.error.HTTPError as e:
            check("relay.call: a redirect is an error, the token never followed", e.code == 302 and not seen, seen)
    finally:
        lsock.close()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("the API callers")
    for name, mod in (("shim", shim), ("store_provision", store_provision)):
        seen.clear()
        get(mod.OPENER, f"http://127.0.0.1:{same.server_port}/").read()
        check(f"{name}: a same-origin redirect is followed (a renamed resource)", seen == [("/landed", SECRET)], seen)
        ph = [h for h in mod.OPENER.handlers if isinstance(h, urllib.request.ProxyHandler)]
        want = {k: v for k, v in urllib.request.getproxies().items() if k in ("https", "no")}
        # A ProxyHandler with no proxies registers nothing, so urllib keeps
        # none in handlers: no handler is no proxy.
        check(f"{name}: the environment's https proxy, never its http one",
              (ph[0].proxies if ph else {}) == want and len(ph) <= 1, [h.proxies for h in ph])
    for name, op in (("shim", shim.OPENER), ("store_provision", store_provision.OPENER)):
        seen.clear()
        try:
            get(op, f"http://127.0.0.1:{away.server_port}/")
            check(f"{name}: a redirect to another host is refused", False)
        except urllib.error.HTTPError as e:
            check(f"{name}: a redirect to another host is refused, its credential never followed", e.code == 302 and not seen, seen)
    for s in (target, away, same):
        s.shutdown()
        s.server_close()

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
