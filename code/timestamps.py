"""Forgiving ISO-8601 timestamp parsing with UTC normalization."""
from __future__ import annotations

import re
from datetime import datetime, timezone

_ZONE = re.compile(r"[+-]\d{2}:?\d{2}$")


def parse_timestamp(value: str) -> datetime:
    """Parse ISO timestamps and normalize common duplicated UTC suffixes to UTC."""
    text = (value or "").strip()
    if not text:
        raise ValueError("timestamp is empty")
    # Repair malformed doubled suffixes such as ...Z+00:00 and ...+00:00Z.
    while True:
        if text.endswith("Z") and text[:-1].endswith("Z"):
            text = text[:-1]
        elif text.endswith("Z") and _ZONE.search(text[:-1]):
            text = text[:-1]
        elif re.search(r"Z(?=[+-]\d{2}:?\d{2}$)", text):
            text = re.sub(r"Z(?=[+-]\d{2}:?\d{2}$)", "", text)
        else:
            break
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Basic ISO offsets are accepted by fromisoformat after colon insertion.
    if re.search(r"[+-]\d{4}$", text):
        text = text[:-5] + text[-5:-2] + ":" + text[-2:]
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
