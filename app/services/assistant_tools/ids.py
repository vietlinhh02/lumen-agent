"""Identifier normalization helpers for assistant tool arguments."""

from __future__ import annotations

import uuid
from typing import Any


def coerce_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
