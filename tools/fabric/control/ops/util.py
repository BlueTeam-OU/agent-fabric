"""tools/fabric/control/ops/util.py — what the ops share.

The contract of the whole package is ops/__init__.py's header. tools/fabric
goes onto sys.path here, as every tool of the directory does for its
siblings (relay.py, gzcoord/paths.py), so `gzcoord` and `roots` import by
name from any part.

Every extractor that runs a program takes `run`, called as
subprocess.run is (an argument list, keyword options), so a test hands in
a fake with the same shape; failures are the real ones — CalledProcessError
for a non-zero exit (check=True), TimeoutExpired, OSError for a command
that is not there — and each extractor says which it means.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import selectors
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

FABRIC_TOOLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
if FABRIC_TOOLS not in sys.path:
    sys.path.insert(0, FABRIC_TOOLS)


def state_dir() -> str:
    """This login's fabric state directory, as runtime/identity.py resolves
    it (upgrade.mjs's stateDir mirrors it). control/upgrade.py's state_dir
    is the form that takes the home, environment and login explicitly."""
    spec = importlib.util.spec_from_file_location(
        "fabric_runtime_identity", os.path.join(os.path.dirname(os.path.dirname(FABRIC_TOOLS)), "runtime", "identity.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent_state_dir()


def read_json(file: str) -> Any:
    """The file's JSON, or None for a file that is absent or not JSON."""
    try:
        with open(file, encoding="utf-8") as fh:
            return loads(fh.read())
    except (OSError, ValueError):
        return None


def sha12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def decode(b: bytes | str | None) -> str:
    """A child's output as text; a byte that is not UTF-8 is replaced, as Node's decoding replaced it."""
    if b is None:
        return ""
    return b if isinstance(b, str) else b.decode("utf-8", "replace")


def iso_ms(ms: float) -> str:
    """Date.prototype.toISOString for epoch milliseconds: a fraction of a
    millisecond is dropped, as the Date constructor drops it."""
    whole = int(ms)
    return datetime.fromtimestamp(whole // 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{whole % 1000:03d}Z"


def truthy(v: Any) -> bool:
    """JavaScript's truthiness: {} and [] are true, where Python's are false."""
    if isinstance(v, (dict, list)):
        return True
    if isinstance(v, float) and v != v:
        return False
    return bool(v)


def whole(n: float) -> float | int:
    """An integral float as an int, so a sum prints as the Node's did (12, not 12.0)."""
    return int(n) if isinstance(n, float) and n.is_integer() else n


_ISO = re.compile(r"([+-]\d{6}|\d{4})(?:-(\d{2})(?:-(\d{2}))?)?"
                  r"(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(Z|[+-]\d{2}:\d{2})?)?", re.A)


def date_parse_ms(v: Any) -> float | None:
    """Date.parse for the ECMAScript date-time format, the one the harness
    writes: epoch milliseconds, or None where the Node read NaN. A date
    alone is UTC; a time without an offset is local, as V8 reads it. The
    legacy forms V8 also guesses at are None here: no record carries one."""
    if not isinstance(v, str):
        return None
    m = _ISO.fullmatch(v)
    if not m:
        return None
    y, mo, d, hh, mm, ss, frac, off = m.groups()
    try:
        ms = int((frac or "0")[:3].ljust(3, "0"))
        tz: timezone | None
        if off == "Z" or (hh is None):
            tz = timezone.utc
        elif off:
            sign = 1 if off[0] == "+" else -1
            tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[4:6])))
        else:
            tz = None
        t = datetime(int(y), int(mo or 1), int(d or 1), int(hh or 0), int(mm or 0), int(ss or 0), tzinfo=tz)
        return int(t.timestamp() if tz else t.astimezone().timestamp()) * 1000 + ms
    except (ValueError, OverflowError):
        return None


def node_error(e: BaseException, cmd: list[str]) -> str:
    """The first line of the message Node's child_process put in a reply
    for the same failure, so a reply reads the same from either language."""
    if isinstance(e, FileNotFoundError):
        return f"spawn {cmd[0]} ENOENT"
    if isinstance(e, (subprocess.CalledProcessError, subprocess.TimeoutExpired, OutputOverflow)):
        return f"Command failed: {' '.join(cmd)}"
    return str(e).split("\n")[0]


_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _wholes(v: Any) -> Any:
    if isinstance(v, float):
        return None if not math.isfinite(v) else whole(v)   # JSON.stringify writes NaN and Infinity as null
    if isinstance(v, dict):
        return {k: _wholes(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_wholes(x) for x in v]
    return v


def js_json(v: Any, indent: int | None = None) -> str:
    """JSON.stringify(v) or JSON.stringify(v, null, indent) for what the
    persisted state holds: non-ASCII as itself, an integral number without
    a fraction (5, not 5.0), a lone surrogate escaped. A float that Python
    writes with an exponent and Node without (1e-05 against 0.00001) is
    not converted: python-dev-01's serialiser for the signed bytes
    (ADR-040 Wave 8, #131) replaces this once it lands."""
    text = json.dumps(_wholes(v), ensure_ascii=False, allow_nan=False,
                      **({"indent": indent} if indent is not None else {"separators": (",", ":")}))
    return _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group(0)):04x}", text)


def js_round(x: float) -> float | int:
    """Math.round: halves go up, where Python's round() goes to even; NaN and
    the infinities come back as they are, as Math.round returned them."""
    if not math.isfinite(x):
        return x
    return math.floor(x + 0.5)


def loads(text: str | bytes) -> Any:
    """JSON.parse: NaN and Infinity are refused, and a document nested past
    the interpreter's stack is a ValueError like any other bad one, never a
    RecursionError that no caller of a parse expects."""
    try:
        return json.loads(text, parse_constant=reject_constant)
    except RecursionError:
        raise ValueError("JSON nested too deeply") from None


def reject_constant(name: str) -> Any:
    """json.loads' parse_constant for what JSON.parse refuses: NaN, Infinity."""
    raise ValueError(f"{name} is not JSON")


def _feed(pipe: Any, data: bytes) -> None:
    try:
        pipe.write(data)
    except (BrokenPipeError, OSError):
        pass   # the child closed its input: what it answers is read as it is
    finally:
        try:
            pipe.close()
        except OSError:
            pass


class OutputOverflow(subprocess.SubprocessError):
    """A child wrote more than its bound; it was killed. output and stderr
    hold what had been read."""

    def __init__(self, cmd: list[str], limit: int, output: bytes, stderr: bytes) -> None:
        super().__init__(f"{cmd[0]} wrote more than {limit} bytes")
        self.cmd, self.limit, self.output, self.stderr = cmd, limit, output, stderr


def run_bounded(cmd: list[str], *, timeout: float, max_bytes: int, env: dict[str, str] | None = None,
                cwd: str | None = None, input: bytes | None = None) -> subprocess.CompletedProcess:  # noqa: A002 — subprocess.run's word
    """Run a command with its output bounded as well as its time. Bytes in,
    bytes out; stdin is `input`, or closed. Raises subprocess.TimeoutExpired,
    OutputOverflow or CalledProcessError (each carrying what was read), and
    OSError for a command that is not there. The child is killed and
    reaped on every raise."""
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL if input is None else subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, cwd=cwd)
    if input is not None:
        # Written beside the reads: a child that answers before it has read
        # everything would otherwise fill its pipe and ours, and both wait.
        threading.Thread(target=_feed, args=(proc.stdin, input), daemon=True).start()
    bufs: dict[str, bytearray] = {"out": bytearray(), "err": bytearray()}
    deadline = time.monotonic() + timeout
    sel = selectors.DefaultSelector()
    assert proc.stdout is not None and proc.stderr is not None
    sel.register(proc.stdout, selectors.EVENT_READ, "out")
    sel.register(proc.stderr, selectors.EVENT_READ, "err")
    try:
        while sel.get_map():
            left = deadline - time.monotonic()
            if left <= 0:
                raise subprocess.TimeoutExpired(cmd, timeout, bytes(bufs["out"]), bytes(bufs["err"]))
            for key, _ in sel.select(left):
                chunk = os.read(key.fileobj.fileno(), 65536)   # type: ignore[union-attr]
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                bufs[key.data] += chunk
                if len(bufs["out"]) + len(bufs["err"]) > max_bytes:
                    raise OutputOverflow(cmd, max_bytes, bytes(bufs["out"]), bytes(bufs["err"]))
        rc = proc.wait(max(deadline - time.monotonic(), 0.001))
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        sel.close()
        proc.stdout.close()
        proc.stderr.close()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd, bytes(bufs["out"]), bytes(bufs["err"]))
    return subprocess.CompletedProcess(cmd, rc, bytes(bufs["out"]), bytes(bufs["err"]))
