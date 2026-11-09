"""tools/fabric/work/request_title.py — the one title a REQUEST's job has, whichever path adds it (rule 14, finding F11).

The id rides in the title, last: the requester's `request:<id>` blocker finds the job its REQUEST became by that suffix
(tools/fabric/jobsparts/blockers.py), and the inbox, the sender's jobs-add and `add --request` must dedupe on it. Only the
last `(REQUEST <id>)` is the job's: a SUBJECT is the sender's free text and may mention another request's id, which must not
make this one vanish.
"""
from __future__ import annotations

import re

# A GZCoord MESSAGE-ID as gzmsg mints it; tools/fabric/control/sessions.py MESSAGE_ID says only ids of this shape.
MESSAGE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII)
TITLE_NAMES_REQUEST = re.compile(r"\(REQUEST (" + MESSAGE_ID.pattern + r")\)\Z", re.ASCII)
# control/jobs.py TITLE_MAX: jobs-add refuses a longer title.
TITLE_MAX = 300


def request_id_of(title: str) -> str | None:
    # Collapsed as a job stores its title: one typed with a tab or newline names the id it will be stored with.
    found = TITLE_NAMES_REQUEST.search(" ".join(title.split()))
    return found.group(1) if found else None


def request_title(subject: str, message_id: str) -> str:
    """The title, cut to jobs-add's limit with the id kept: the subject gives way, never the id the receiver dedupes on."""
    tail = f" (REQUEST {message_id})"
    subject = " ".join(str(subject or "").split())
    return subject[:max(TITLE_MAX - len(tail), 0)].rstrip() + tail
