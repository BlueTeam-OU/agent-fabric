"""A ChatGPT sign-in a test builds for itself (agent-fabric ADR-053 rule 8): a JWT-shaped access token with a chosen
exp, the sign-in file Codex writes with a refresh token and an id token that must never travel, and the account id.
Every value is fake; the sentinel strings let a test prove a value did not leak."""
from __future__ import annotations

import base64
import json
import os

ACCOUNT = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
REFRESH = "REFRESH-TOKEN-SENTINEL-must-never-travel"
ID_TOKEN = "ID-TOKEN-SENTINEL-must-never-travel"


def b64(doc: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(doc).encode()).decode().rstrip("=")


def fake_jwt(exp: int, who: str = "fake-subject") -> str:
    return f"{b64({'alg': 'RS256', 'typ': 'JWT'})}.{b64({'exp': exp, 'sub': who})}.ZmFrZS1zaWduYXR1cmU"


def write_signin(home: str, exp: int, *, account: str = ACCOUNT, mode: int = 0o600, who: str = "fake-subject") -> str:
    """$home/auth.json as Codex leaves it after a ChatGPT sign-in; its path."""
    os.makedirs(home, exist_ok=True)
    path = os.path.join(home, "auth.json")
    doc = {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
           "tokens": {"id_token": ID_TOKEN, "access_token": fake_jwt(exp, who), "refresh_token": REFRESH, "account_id": account},
           "last_refresh": "2026-10-13T00:00:00Z"}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.chmod(path, mode)
    return path
