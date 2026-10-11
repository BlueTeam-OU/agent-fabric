"""Importing this gives the test process, and every subprocess it starts, a throwaway agent state directory
(AGENT_FABRIC_STATE_DIR): the assembler keeps the drain's own file there (memory-drain-reads.json, ADR-050 rule 8),
and a test that drains must not write into the login that runs it. Removed when the process ends."""
import atexit
import os
import shutil
import tempfile

STATE = tempfile.mkdtemp(prefix="isolated-state-")
atexit.register(shutil.rmtree, STATE, True)
os.environ["AGENT_FABRIC_STATE_DIR"] = STATE
