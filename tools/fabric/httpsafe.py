"""tools/fabric/httpsafe.py — the opener every credentialed urllib call of
the fabric goes through: a bearer token or an API key reaches only the
host it was given for.

    import httpsafe
    httpsafe.opener(proxies=False, redirects="none").open(req, timeout=30)

WHY. urllib's defaults send a credential further than its caller meant
(measured on Python 3.14.7, 2026-10-09):
  - a redirect is followed with the request's headers, Authorization
    included, to whatever host the Location names;
  - an http:// URL goes through http_proxy from the environment, the
    header in clear text to the proxy.
So each caller says what it allows:
  redirects  "none"         a 3xx is an HTTPError, the caller's to read
             "same-origin"  followed only to the same scheme, host and
                            port (GitHub answers a renamed repository so);
                            any other is an HTTPError, never followed
  proxies    False          the environment's proxies are ignored (a
                            relay on a loopback or tunnel address)
             True           the environment's https proxy, by CONNECT,
                            which shows the proxy no header; never its
                            http proxy, which would carry the header in
                            clear text (review of 69c69bbd, risk 1)
A Location that cannot be read (a port that is no number) is refused as
any other redirect is, an HTTPError, never a ValueError past a caller.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request


def _origin(url: str) -> tuple:
    u = urllib.parse.urlsplit(url)
    port = u.port or {"http": 80, "https": 443}.get(u.scheme)
    return u.scheme, (u.hostname or "").lower(), port


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow: str):
        super().__init__()
        self.allow = allow

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913 — the stdlib's signature
        try:
            same = _origin(newurl) == _origin(req.full_url)
        except ValueError:
            same = False
        if self.allow == "same-origin" and same:
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        # Returning None makes urllib raise the 3xx as an HTTPError: an
        # answer that is not 2xx, which every caller already reads.
        return None


def opener(*, proxies: bool, redirects: str) -> urllib.request.OpenerDirector:
    if redirects not in ("none", "same-origin"):
        raise ValueError(f"redirects is 'none' or 'same-origin', not {redirects!r}")
    proxy_map = {k: v for k, v in urllib.request.getproxies().items() if k in ("https", "no")} if proxies else {}
    handlers = [urllib.request.ProxyHandler(proxy_map), _Redirects(redirects)]
    return urllib.request.build_opener(*handlers)
