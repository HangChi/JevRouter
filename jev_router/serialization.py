from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def jsonable(value: Any) -> Any:
    """Convert an immutable state snapshot into a plain JSON-compatible structure.

    ``TaskState`` snapshots use ``MappingProxyType`` and ``tuple``, which
    ``json.dumps`` cannot serialize. ``JevClient.systemone`` validates the request
    payload with ``json.dumps(allow_nan=False)`` before sending it, so snapshots
    must be flattened here or the client raises ``RequestValidationError``.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    raise ValueError("state values must be JSON-compatible")
