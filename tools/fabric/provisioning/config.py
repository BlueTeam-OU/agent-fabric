"""tools/fabric/provisioning/config.py — where new-agent finds its parts: the
fabric checkout it runs from, the secrets tools, the host executor, the worker
on the placed host, and the bounds a person would rather see fail than wait
past. Module attributes read at call time, so a test points them at a fixture
(tests/test_new_agent.py) and every step module sees it."""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SECRETS = os.path.join(ROOT, "runtime", "provisioning", "secrets", "fabric-secrets")
STORE_ENROLL = os.path.join(ROOT, "runtime", "provisioning", "secrets", "store-enroll.sh")
STORE = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
HX = os.path.join(ROOT, "runtime", "hostexec", "hostexec")
WORKER = "@fabric/runtime/provisioning/new-agent-worker.sh"
# A host phase installs claude, ori and a project's toolchain (pnpm
# install can take minutes); the coordinator's own steps cross a host and
# GitHub. Bounds a person would rather see fail than wait past.
WORKER_TIMEOUT_S = 3600
STEP_TIMEOUT_S = 900
