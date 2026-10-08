"""tools/fabric/secretstore/ — the parts of secret_store.py (agent-fabric ADR-038,
ADR-042), one module per subject. secret_store.py is the entry: the CLI, and the
module every caller imports; its docstring is the contract every part keeps."""

import os as _os
import sys as _sys

# roots.py is a sibling of this package; every part imports it.
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
