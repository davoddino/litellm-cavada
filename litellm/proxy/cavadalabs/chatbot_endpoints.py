from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from jsonschema import ValidationError, validate  # type: ignore[import-untyped]
from pydantic import BaseModel

from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
)
from litellm.proxy.cavadalabs.guardrails import CavadaLabsGuardrailService
from litellm.proxy.cavadalabs.rag_runtime import CavadaLabsRAGRuntimeService
from litellm.proxy.cavadalabs.chatbot_runtime_auth import (
    build_chatbot_runtime_user_api_key,
)
from litellm.proxy.common_request_processing import ProxyBaseLLMRequestProcessing
from litellm.proxy.utils import model_dump_with_preserved_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatCompletionRequest,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs"])
_CHATBOT_MESSAGES_ROUTE = "/cavadalabs/chatbots/messages"
_THINKING_TAG_PATTERN = re.compile(
    r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL
)


class CavadaLabsInvalidJSONOutputError(Exception):
    pass


def _service() -> CavadaLabsDispatcherService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs chatbot runtime"},
        )
    return CavadaLabsDispatcherService(proxy_server.prisma_client)


def _rag_runtime_service() -> CavadaLabsRAGRuntimeService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs RAG runtime"},
        )
    return CavadaLabsRAGRuntimeService(proxy_server.prisma_client)


def _guardrail_service() -> CavadaLabsGuardrailService:
    from litellm.proxy import proxy_server

    if proxy_server.prisma_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Database is required for CavadaLabs guardrail runtime"},
        )
    return CavadaLabsGuardrailService(proxy_server.prisma_client)


def _extract_web_token(
    authorization: Optional[str],
    x_cavadalabs_web_token: Optional[str],
) -> str:
    if x_cavadalabs_web_token:
        return x_cavadalabs_web_token.strip()

    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "Missing CavadaLabs browser web token"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _request_origin(request: Request) -> Optional[str]:
    origin = request.headers.get("origin")
    if origin:
        return origin

    referer = request.headers.get("referer")
    if not referer:
        return None

    from urllib.parse import urlparse

    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip() or "unknown"

    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _runtime_general_settings() -> Dict[str, Any]:
    from litellm.proxy import proxy_server

    general_settings = dict(proxy_server.general_settings or {})
    general_settings.pop("completion_model", None)
    return general_settings


def _should_bypass_router(payload: Dict[str, Any]) -> bool:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return False
    cavadalabs_metadata = metadata.get("cavadalabs")
    return isinstance(cavadalabs_metadata, dict) and isinstance(
        cavadalabs_metadata.get("runtime"), dict
    )


def _cavadalabs_payload_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    cavadalabs_metadata = metadata.get("cavadalabs")
    return cavadalabs_metadata if isinstance(cavadalabs_metadata, dict) else {}


def _response_message(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    return message if isinstance(message, dict) else None


def _strip_reasoning_from_message(message: Dict[str, Any]) -> None:
    for key in ("reasoning", "reasoning_content", "thinking", "thinking_blocks"):
        message.pop(key, None)


def _decode_json_document(content: str, *, repair: bool) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        if not repair:
            raise CavadaLabsInvalidJSONOutputError(str(exc)) from exc

    decoder = json.JSONDecoder()
    for start_index, character in enumerate(content):
        if character not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(content[start_index:])
            return value
        except json.JSONDecodeError:
            continue
    raise CavadaLabsInvalidJSONOutputError("response did not contain valid JSON")


def _finalize_chatbot_result(result: Any, payload: Dict[str, Any]) -> Any:
    if isinstance(result, BaseModel):
        result = model_dump_with_preserved_fields(result, exclude_unset=True)
    if not isinstance(result, dict):
        return result

    cavadalabs_metadata = _cavadalabs_payload_metadata(payload)
    if payload.get("stream") is True:
        return result

    message = _response_message(result)
    if message is None:
        return result

    if cavadalabs_metadata.get("hide_reasoning") is True:
        _strip_reasoning_from_message(message)

    content = message.get("content")
    if (
        isinstance(content, str)
        and cavadalabs_metadata.get("strip_thinking_tags") is True
    ):
        content = _THINKING_TAG_PATTERN.sub("", content).strip()
        message["content"] = content

    json_required = (
        cavadalabs_metadata.get("require_json_output") is True
        or cavadalabs_metadata.get("force_json_output") is True
        or cavadalabs_metadata.get("has_json_schema") is True
    )
    if json_required:
        if not isinstance(content, str):
            raise CavadaLabsInvalidJSONOutputError("response content is not a string")
        value = _decode_json_document(
            content,
            repair=cavadalabs_metadata.get("repair_invalid_json") is True,
        )
        json_schema = cavadalabs_metadata.get("json_schema")
        if isinstance(json_schema, dict):
            try:
                validate(instance=value, schema=json_schema)
            except ValidationError as exc:
                raise CavadaLabsInvalidJSONOutputError(exc.message) from exc
        message["content"] = json.dumps(
            value, separators=(",", ":"), ensure_ascii=False
        )
    return result


def _should_retry_invalid_json(payload: Dict[str, Any]) -> bool:
    cavadalabs_metadata = _cavadalabs_payload_metadata(payload)
    return (
        payload.get("stream") is not True
        and cavadalabs_metadata.get("retry_on_invalid_json") is True
    )


def _add_json_retry_instruction(payload: Dict[str, Any], reason: str) -> None:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return
    messages.insert(
        1,
        {
            "role": "system",
            "content": (
                "The previous model response failed CavadaLabs JSON validation. "
                f"Return only valid JSON that satisfies the configured schema. Reason: {reason}"
            ),
        },
    )


@router.post(
    "/chatbots/messages",
    responses={
        200: {"description": "Successful CavadaLabs chatbot response"},
        401: {"description": "Missing, expired, revoked, or unknown web token"},
        403: {"description": "Web token origin, domain, or route is not allowed"},
        429: {"description": "CavadaLabs web token rate or budget limit reached"},
    },
)
async def create_chatbot_message(
    request_data: CavadaLabsChatCompletionRequest,
    request: Request,
    fastapi_response: Response,
    authorization: Optional[str] = Header(default=None),
    x_cavadalabs_web_token: Optional[str] = Header(
        default=None, alias="x-cavadalabs-web-token"
    ),
):
    from litellm.proxy import proxy_server

    token = _extract_web_token(
        authorization=authorization,
        x_cavadalabs_web_token=x_cavadalabs_web_token,
    )
    origin = _request_origin(request)
    request_ip = _request_ip(request)

    service = _service()
    context = await service.resolve_runtime_context(
        token=token,
        route=_CHATBOT_MESSAGES_ROUTE,
        origin=origin,
    )
    await service.enforce_runtime_limits(
        context=context,
        session_id=request_data.session_id,
        request_ip=request_ip,
        internal_usage_cache=proxy_server.proxy_logging_obj.internal_usage_cache,
    )
    (
        guardrail_result,
        guarded_request_data,
    ) = await _guardrail_service().evaluate_chat_request(
        context=context,
        request_data=request_data,
    )
    if guardrail_result.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "CavadaLabs guardrail blocked this request",
                "reason_code": guardrail_result.reason_code,
                "triggered_rules": guardrail_result.triggered_rules,
            },
        )
    request_data = guarded_request_data
    rag_context = await _rag_runtime_service().retrieve_context(
        context=context,
        request_data=request_data,
    )

    payload = await service.prepare_chat_completion_payload(
        request_data=request_data,
        context=context,
        origin=origin,
        request_ip=request_ip,
        rag_context=rag_context,
    )
    user_api_key_dict = build_chatbot_runtime_user_api_key(
        context=context,
        token=token,
        payload=payload,
    )
    llm_router = None if _should_bypass_router(payload) else proxy_server.llm_router
    max_attempts = 2 if _should_retry_invalid_json(payload) else 1
    last_invalid_json_error: Optional[str] = None
    for attempt in range(max_attempts):
        attempt_payload = copy.deepcopy(payload)
        if attempt > 0 and last_invalid_json_error is not None:
            _add_json_retry_instruction(attempt_payload, last_invalid_json_error)

        base_llm_response_processor = ProxyBaseLLMRequestProcessing(
            data=attempt_payload
        )
        try:
            result = await base_llm_response_processor.base_process_llm_request(
                request=request,
                fastapi_response=fastapi_response,
                user_api_key_dict=user_api_key_dict,
                route_type="acompletion",
                proxy_logging_obj=proxy_server.proxy_logging_obj,
                llm_router=llm_router,
                general_settings=_runtime_general_settings(),
                proxy_config=proxy_server.proxy_config,
                select_data_generator=proxy_server.select_data_generator,
                model=None,
                user_model=None,
                user_temperature=None,
                user_request_timeout=None,
                user_max_tokens=None,
                user_api_base=None,
                version=proxy_server.version,
            )
            return _finalize_chatbot_result(result, attempt_payload)
        except CavadaLabsInvalidJSONOutputError as exc:
            last_invalid_json_error = str(exc)
            if attempt + 1 < max_attempts:
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "CavadaLabs JSON output policy validation failed",
                    "reason": last_invalid_json_error,
                },
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise await base_llm_response_processor._handle_llm_api_exception(
                e=exc,
                user_api_key_dict=user_api_key_dict,
                proxy_logging_obj=proxy_server.proxy_logging_obj,
                version=proxy_server.version,
            )
