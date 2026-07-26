"""Reads A2A `skill` selection leniently -- some clients (A2A Inspector's own
"Message Metadata" UI field, confirmed live) attach per-request metadata to
the Message object (message.metadata) rather than the request envelope
(RequestContext.metadata / SendMessageRequest.params.metadata), even though
this repo's own executors were written against the latter. Real clients
disagree on which one they populate; accept either rather than making callers
guess which field a given client actually fills in."""

from __future__ import annotations

from google.protobuf import json_format


def skill_from_metadata(context) -> str | None:
    if context.metadata:
        skill = context.metadata.get("skill")
        if skill:
            return skill
    message = context.message
    if message is not None:
        message_metadata = json_format.MessageToDict(message.metadata)
        return message_metadata.get("skill")
    return None
