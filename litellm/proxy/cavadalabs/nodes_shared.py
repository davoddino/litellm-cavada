from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional, Type, TypeVar
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm.proxy.cavadalabs.dispatcher import _as_aware_utc, hash_web_token
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPUStatus,
    CavadaLabsNodeStatus,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_NODE_ENROLLMENT_PREFIX = "clne"
_NODE_SIGNATURE_MAX_SKEW = timedelta(minutes=5)
_JSON_FIELDS = {"metadata", "samples", "errors", "before_value", "after_value"}
_SCHEDULABLE_NODE_STATUSES = {
    CavadaLabsNodeStatus.ONLINE.value,
    CavadaLabsNodeStatus.DEGRADED.value,
}
_SCHEDULABLE_GPU_STATUSES = {
    CavadaLabsGPUStatus.AVAILABLE.value,
    CavadaLabsGPUStatus.LOADED.value,
}


def canonical_node_signature_payload(
    *,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
) -> bytes:
    body_sha256 = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([timestamp, method.upper(), path, body_sha256])
    return canonical.encode("utf-8")


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

    for key in _JSON_FIELDS:
        value = data.get(key)
        if isinstance(value, str):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                data[key] = [] if key in {"samples", "errors"} else {}
    return data


def _parse_response(row: Any, response_model: Type[ModelT]) -> ModelT:
    return response_model.model_validate(_row_to_dict(row, response_model))


def _create_node_enrollment_secret() -> tuple[str, str, str]:
    secret_id = uuid4().hex
    secret = secrets.token_urlsafe(48)
    token = f"{_NODE_ENROLLMENT_PREFIX}-{secret_id}.{secret}"
    return token, token[:24], hash_web_token(token)


def _decode_base64(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.b64decode(padded, validate=True)
    except Exception:
        return base64.urlsafe_b64decode(padded)


def _load_ed25519_public_key(public_key: str) -> ed25519.Ed25519PublicKey:
    normalized = public_key.strip()
    try:
        loaded_key = serialization.load_pem_public_key(normalized.encode("utf-8"))
        if not isinstance(loaded_key, ed25519.Ed25519PublicKey):
            raise ValueError("Only Ed25519 node public keys are supported")
        return loaded_key
    except ValueError as exc:
        if "Only Ed25519" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": str(exc)},
            )
    except Exception:
        pass

    raw_key: Optional[bytes] = None
    try:
        raw_key = _decode_base64(normalized)
    except Exception:
        try:
            raw_key = bytes.fromhex(normalized)
        except ValueError:
            raw_key = None

    if raw_key is None or len(raw_key) != 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Node public_key must be an Ed25519 PEM, base64, or hex raw public key"
            },
        )
    return ed25519.Ed25519PublicKey.from_public_bytes(raw_key)


def public_key_fingerprint(public_key: str) -> str:
    loaded_key = _load_ed25519_public_key(public_key)
    raw = loaded_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def _decode_signature(signature: str) -> bytes:
    try:
        return _decode_base64(signature.strip())
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid node signature encoding"},
        )


def _parse_node_timestamp(timestamp: str) -> datetime:
    normalized = timestamp.strip()
    if normalized.isdigit():
        return datetime.fromtimestamp(int(normalized), tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid node signature timestamp"},
        )
    return _as_aware_utc(parsed)


def _daily_report_date(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _node_actor(node_id: str) -> str:
    return f"node:{node_id}"


def _active_gpu_lock_key(gpu_id: str) -> str:
    return f"active:{gpu_id}"


def _metadata_int(metadata: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def _metadata_string(metadata: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
