from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def jsonable(value: Any) -> Any:
    """把不可变的 state 快照转换成普通、与 JSON 兼容的结构。

    ``TaskState`` 的快照使用 ``MappingProxyType`` 和 ``tuple``，
    ``json.dumps`` 无法序列化它们。``JevClient.systemone`` 在发送前会用
    ``json.dumps(allow_nan=False)`` 校验请求载荷，因此必须在这里把快照展平，
    否则客户端会抛出 ``RequestValidationError``。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    raise ValueError("state 值必须与 JSON 兼容")
