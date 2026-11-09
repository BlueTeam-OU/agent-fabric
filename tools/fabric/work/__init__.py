"""tools/fabric/work — the owner of the work lifecycle (agent-fabric ADR-037 rule 14, ADR-067): the table of which subsystem
moves a job from which state to which (table.py), the only code that writes a job's state into an agent's list
(lifecycle.py), the only code that writes a claim into a role's pool.json (claims.py), and the one title a REQUEST's job has
(request_title.py).

Loaded BY PATH as `fabric_work` (by_path.py), as tools/fabric/jobs.py loads its parts: the job tool and the control agent
both use it, and neither may let a fixture fabric on sys.path answer for its imports. It imports nothing outside the standard
library, so the control agent's pool can use it without the job tool.
"""
from fabric_work import claims, table
from fabric_work.lifecycle import Proof, Refusal, create, fill, listed, seal, transition
from fabric_work.request_title import MESSAGE_ID, TITLE_MAX, TITLE_NAMES_REQUEST, request_id_of, request_title

__all__ = ["MESSAGE_ID", "Proof", "Refusal", "TITLE_MAX", "TITLE_NAMES_REQUEST", "claims", "create", "fill", "listed", "request_id_of", "request_title", "seal", "table", "transition"]
