from __future__ import annotations

from litellm.proxy.cavadalabs.dispatcher_runtime import CavadaLabsRuntimeOperations
from litellm.proxy.cavadalabs.dispatcher_shared import (
    CavadaLabsRuntimeContext,
    _actor_key_hash,
    _actor_user_id,
    _as_aware_utc,
    _create_browser_token,
    _domain_matches,
    _is_unique_violation,
    _month_start_utc,
    _now_utc,
    _origin_host,
    _parse_response,
    _rate_limit_window,
    _row_to_dict,
    _unique_strings,
    hash_web_token,
)


class CavadaLabsDispatcherService(CavadaLabsRuntimeOperations):
    pass


__all__ = [
    "CavadaLabsDispatcherService",
    "CavadaLabsRuntimeContext",
    "_actor_key_hash",
    "_actor_user_id",
    "_as_aware_utc",
    "_create_browser_token",
    "_domain_matches",
    "_is_unique_violation",
    "_month_start_utc",
    "_now_utc",
    "_origin_host",
    "_parse_response",
    "_rate_limit_window",
    "_row_to_dict",
    "_unique_strings",
    "hash_web_token",
]
