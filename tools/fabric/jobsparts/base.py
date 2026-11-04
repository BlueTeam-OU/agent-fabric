"""tools/fabric/jobsparts/base.py — the module's constants, the Job types, the one refusal, the list's lock (identity) and mutate().
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

from typing import Any
from typing import TypedDict
import importlib.util
import os
import re


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tools/fabric/, where jobs.py is


FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))


# A job as jobs.json keeps it (tools/fabric/control/jobs.py reads it too). The
# keys a state change adds live in a total=False subclass: under `from
# __future__ import annotations` TypedDict counts NotRequired[...] as
# required. tests/test_types.py holds every job the CLI writes to it.
class _JobKeys(TypedDict):
    id: str
    title: str
    topic: str | None
    project: str | None
    working_copy: str | None
    state: str
    source: dict[str, Any]
    artifacts: list[str]
    created: str
    updated: str
    log: list[dict[str, str]]


class Job(_JobKeys, total=False):
    blocked_on: str
    reason: str
    no_artifact: str
    priority: str
    waits_on: str
    blockers: list[str]
    branch: str
    worktree: str
    deliver_to: str
    project_from: str


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


identity = _load("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))


# The registry-id grammar, loaded by path like identity: the parts never import
# a top-level name a fixture fabric on sys.path could answer.
PROJECT_SLUG = _load("fabric_registry_id", os.path.join(HERE, "registry_id.py")).REGISTRY_ID


# The fleet hold's reader (ADR-037 rule 13), loaded by path for the same reason.
hold_view = _load("fabric_hold_view", os.path.join(HERE, "hold_view.py"))


STATES = ("queued", "active", "paused", "blocked", "delivered", "done", "dropped")


OPEN = ("queued", "active", "paused", "blocked", "delivered")


TERMINAL = ("done", "dropped")


# A GZCoord MESSAGE-ID as gzmsg mints it; tools/fabric/control/sessions.py
# MESSAGE_ID says only ids of this shape, so a relay seq is refused here.
MESSAGE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII)


POOL_ID = re.compile(r"p[1-9][0-9]{0,8}", re.ASCII)   # tools/fabric/control/pool.py POOL_ID


PRIORITIES = ("blocking", "high", "normal", "low")


DEFAULT_PRIORITY = "normal"


class Refused(Exception):
    """A change the list does not allow; the message is the whole answer."""


class NothingQueued(Refused):
    """`next` found no queued job; the pool is asked after the lock is let go."""


# A waiting address whose state record is older than the stream's bound:
# its age in seconds, None when the record's time could not be read.
Stale = dict[str, int | None]


def mutate(fn):
    """Run fn(doc) under the lock and return what it returns; a Refused
    leaves the file as it was."""
    out = {}

    def edit(doc):
        out["value"] = fn(doc)
        return doc
    identity.update_jobs(edit)
    return out.get("value")
