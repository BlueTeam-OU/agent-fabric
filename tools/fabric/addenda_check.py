"""tools/fabric/addenda_check.py — the validator of a holder's addenda (agent-fabric ADR-060 §5 rules 1, 6, 9).

STUB: the signature other stages base on; the checks land in the next commit."""
from __future__ import annotations

import re


def validate(role: str, aid: str, name: str, raw: bytes) -> list[str]:
    """Findings (empty = valid) for the file `name` of `settings/roles/<role>/`
    in the store of agent id `aid`, whose bytes are `raw`."""
    return []


def validate_set(role: str, aid: str, files: dict[str, bytes]) -> dict[str, list[str]]:
    """Every file's findings, plus what only a set shows (a stale gloss, a
    gloss with no addendum, a non-English addendum without its gloss)."""
    return {name: validate(role, aid, name, raw) for name, raw in files.items()}


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def frontmatter(text: str) -> dict[str, str]:
    """STUB of the real parser (quotes and trailing space stripped)."""
    m = FRONTMATTER_RE.match(text)
    out = {}
    for line in (m.group(1).split("\n") if m else []):
        k, _, v = line.partition(": ")
        v = v.strip()
        out[k] = v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v
    return out
