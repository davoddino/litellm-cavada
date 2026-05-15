from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Set


CAVADALABS_PRISMA_JSON_FIELDS: Set[str] = {
    "access_policy",
    "after_value",
    "artifacts",
    "before_value",
    "billing_address",
    "breakdowns",
    "chunking_strategy",
    "default_billing_settings",
    "default_chatbot_settings",
    "errors",
    "evaluation_evidence",
    "generated_from",
    "human_oversight",
    "inputs_snapshot",
    "json_schema",
    "metadata",
    "model_provider_metadata",
    "prohibited_practice_review",
    "redaction_patterns",
    "redaction_summary",
    "result",
    "retention_policy",
    "retention_policy_override",
    "retrieval_config",
    "rules",
    "samples",
    "totals",
    "transcript_retention_policy",
    "triggered_rules",
    "widget_theme_config",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def serialize_prisma_json_fields(
    data: Dict[str, Any],
    *,
    json_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Convert CavadaLabs Prisma Json columns to JSON text before writes.

    prisma-client-python rejects bare Python dict/list/None values for Json
    fields in this project. LiteLLM's established proxy pattern is to send JSON
    text to Prisma and parse it back on reads.
    """
    target_fields = set(json_fields or CAVADALABS_PRISMA_JSON_FIELDS)
    serialized = dict(data)
    for field_name in target_fields:
        if field_name in serialized:
            serialized[field_name] = json.dumps(
                serialized[field_name],
                default=_json_default,
            )
    return serialized


def parse_prisma_json_fields(
    data: Dict[str, Any],
    *,
    json_fields: Optional[Iterable[str]] = None,
    list_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    target_fields = set(json_fields or CAVADALABS_PRISMA_JSON_FIELDS)
    list_field_names = set(list_fields or ())
    parsed_data = dict(data)
    for field_name in target_fields:
        value = parsed_data.get(field_name)
        if not isinstance(value, str):
            continue
        try:
            parsed_data[field_name] = json.loads(value)
        except json.JSONDecodeError:
            parsed_data[field_name] = [] if field_name in list_field_names else {}
    return parsed_data
