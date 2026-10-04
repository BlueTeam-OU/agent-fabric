#!/usr/bin/env python3
"""The names in this process's environment, one per line, values never:
tests/test_review_bash_guard_cli.py runs it through the review fence's
rewrite to see which names a reviewer's command keeps."""
import os

print("\n".join(sorted(os.environ)))
