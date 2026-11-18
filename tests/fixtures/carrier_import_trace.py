"""Prints the checkout files a carrier loads (tests/test_control_upgrade.py CarrierRestart): its engine and the modules its commands import lazily."""
import os, runpy, sys, json
root = sys.argv[1]
runpy.run_path(os.path.join(root, "tools/fabric/gzcoord/carrier/main.py"), run_name="trace")
import episodic, roots  # noqa: E402,F401
from gzcoord import gzmsg, paths  # noqa: E402,F401
from gzcoord.inbox_parts import tokens  # noqa: E402,F401
files = sorted({os.path.realpath(m.__file__) for n, m in list(sys.modules.items()) if n != "__main__" and getattr(m, "__file__", None)})  # not this script
print(json.dumps([os.path.relpath(f, root) for f in files if f.startswith(root + os.sep)]))
