from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.prisma_json import parse_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotResponse,
    CavadaLabsCompanyResponse,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsProjectResponse,
    CavadaLabsWebTokenResponse,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_CAVADA_TOKEN_PREFIX = "clwt"
_MAX_BROWSER_TOKEN_TTL = timedelta(hours=24)
_CHATBOT_MESSAGES_ROUTE = "/cavadalabs/chatbots/messages"
_JSON_FIELDS = {
    "billing_address",
    "metadata",
    "retention_policy",
    "default_billing_settings",
    "default_chatbot_settings",
    "retention_policy_override",
    "widget_theme_config",
    "transcript_retention_policy",
    "json_schema",
    "before_value",
    "after_value",
    "access_policy",
    "chunking_strategy",
    "retrieval_config",
}


@dataclass(frozen=True)
class CavadaLabsRuntimeContext:
    company: CavadaLabsCompanyResponse
    project: CavadaLabsProjectResponse
    chatbot: CavadaLabsChatbotResponse
    web_token: CavadaLabsWebTokenResponse
    primary_policy: CavadaLabsProjectModelPolicyResponse
    fallback_policies: List[CavadaLabsProjectModelPolicyResponse]


def hash_web_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _row_to_dict(row: Any, response_model: Type[ModelT]) -> Dict[str, Any]:
    if isinstance(row, dict):
        data = dict(row)
    else:
        model_dump = getattr(row, "model_dump", None)
        data = {}
        if callable(model_dump):
            try:
                dumped = model_dump()
                if isinstance(dumped, dict):
                    data = dumped
            except Exception:
                data = {}
        if not data:
            for field_name in response_model.model_fields.keys():
                if field_name in getattr(row, "__dict__", {}):
                    data[field_name] = getattr(row, field_name)

    return parse_prisma_json_fields(data, json_fields=_JSON_FIELDS)


def _parse_response(row: Any, response_model: Type[ModelT]) -> ModelT:
    return response_model.model_validate(_row_to_dict(row, response_model))


def _create_browser_token() -> Tuple[str, str, str]:
    token_id = uuid4().hex
    secret = secrets.token_urlsafe(32)
    token = f"{_CAVADA_TOKEN_PREFIX}-{token_id}.{secret}"
    return token, token[:24], hash_web_token(token)


def _is_unique_violation(exc: Exception) -> bool:
    return exc.__class__.__name__ == "UniqueViolationError"


def _actor_user_id(user_api_key_dict: UserAPIKeyAuth) -> str:
    return user_api_key_dict.user_id or "cavadalabs-admin"


def _actor_key_hash(user_api_key_dict: UserAPIKeyAuth) -> Optional[str]:
    token = getattr(user_api_key_dict, "token", None)
    if isinstance(token, str) and token:
        return token
    api_key = getattr(user_api_key_dict, "api_key", None)
    if isinstance(api_key, str) and api_key:
        return hash_web_token(api_key)
    return None


def _origin_host(origin: Optional[str]) -> Optional[str]:
    if not origin:
        return None
    parsed = urlparse(origin)
    return parsed.hostname.lower() if parsed.hostname else None


def _domain_matches(host: Optional[str], allowed_domains: List[str]) -> bool:
    if not allowed_domains:
        return True
    if host is None:
        return False
    host = host.lower()
    for domain in allowed_domains:
        normalized_domain = domain.lower()
        if normalized_domain.startswith("*."):
            suffix = normalized_domain[1:]
            if host.endswith(suffix):
                return True
        elif host == normalized_domain:
            return True
    return False


def _month_start_utc(reference_time: Optional[datetime] = None) -> datetime:
    now = reference_time or _now_utc()
    now = _as_aware_utc(now)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _rate_limit_window() -> Tuple[str, int]:
    now = _now_utc()
    next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    retry_after = max(int((next_minute - now).total_seconds()), 1)
    return now.strftime("%Y%m%d%H%M"), retry_after


def _unique_strings(values: List[Optional[str]]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value is None or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
