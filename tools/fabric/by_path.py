"""tools/fabric/by_path.py — load a package of this directory BY PATH under a name of its own.

A package found through sys.path is whichever one the interpreter meets first: a test fixture's copy of the fabric, or a second
checkout, would answer for it. The job tool has always loaded its parts so (tools/fabric/jobs.py); the work package
(tools/fabric/work) is loaded the same way by the job tool and by the control agent, so both hold one table.
"""
from __future__ import annotations

import importlib.util
import os
import sys


def load_package(name: str, directory: str):
    """The package in `directory` as `name`, registered in sys.modules so that its own `from name import …` resolves. A copy of
    it already loaded under `name` from another directory is replaced, never reused."""
    init = os.path.join(directory, "__init__.py")
    have = sys.modules.get(name)
    if have is not None and os.path.realpath(getattr(have, "__file__", "") or "") == os.path.realpath(init):
        return have
    for loaded in [n for n in sys.modules if n == name or n.startswith(name + ".")]:
        del sys.modules[loaded]
    spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[directory])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module
