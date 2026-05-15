from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import (
    CavadaLabsDispatcherService,
    CavadaLabsRuntimeContext,
    _actor_key_hash,
    _actor_user_id,
    _is_unique_violation,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatCompletionRequest,
    CavadaLabsGuardrailDecision,
    CavadaLabsGuardrailDecisionLogListResponse,
    CavadaLabsGuardrailDecisionLogResponse,
    CavadaLabsGuardrailEnforcementMode,
    CavadaLabsGuardrailEvaluateRequest,
    CavadaLabsGuardrailEvaluationResult,
    CavadaLabsGuardrailPhase,
    CavadaLabsGuardrailPolicyCreateRequest,
    CavadaLabsGuardrailPolicyListResponse,
    CavadaLabsGuardrailPolicyResponse,
    CavadaLabsGuardrailPolicyScope,
    CavadaLabsGuardrailPolicyStatus,
    CavadaLabsGuardrailPolicyUpdateRequest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_FIELDS = {
    "rules",
    "redaction_patterns",
    "triggered_rules",
    "redaction_summary",
    "metadata",
}
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d .-]{7,}\d)(?!\d)")
_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
_PROMPT_INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal the system prompt",
    "show the system prompt",
    "print the system prompt",
    "developer message",
    "bypass safety",
    "jailbreak",
)


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
                data[key] = [] if key == "triggered_rules" else {}
    return data


def _parse_response(row: Any, response_model: Type[ModelT]) -> ModelT:
    return response_model.model_validate(_row_to_dict(row, response_model))


def _message_text(messages: Sequence[Any]) -> str:
    parts: List[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
    return "\n".join(parts)


def _replace_message_text(
    messages: Sequence[Any], replacements: Dict[str, str]
) -> List[Any]:
    next_messages: List[Any] = []
    for message in messages:
        if not isinstance(message, dict):
            next_messages.append(message)
            continue
        next_message = dict(message)
        content = next_message.get("content")
        if isinstance(content, str):
            next_message["content"] = _apply_replacements(content, replacements)
        elif isinstance(content, list):
            next_content = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    next_item = dict(item)
                    next_item["text"] = _apply_replacements(item["text"], replacements)
                    next_content.append(next_item)
                else:
                    next_content.append(item)
            next_message["content"] = next_content
        next_messages.append(next_message)
    return next_messages


def _apply_replacements(text: str, replacements: Dict[str, str]) -> str:
    redacted = text
    for pattern, replacement in replacements.items():
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
    return redacted


def _safe_regex_search(pattern: str, text: str) -> Optional[re.Match[str]]:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE)
    except re.error:
        return None


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


class CavadaLabsGuardrailService:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def create_policy(
        self,
        data: CavadaLabsGuardrailPolicyCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsGuardrailPolicyResponse:
        await self._validate_policy_scope(
            company_id=data.company_id,
            project_id=data.project_id,
            chatbot_id=data.chatbot_id,
            scope=data.scope,
        )
        create_data = serialize_prisma_json_fields(data.model_dump(mode="python"))
        create_data["created_by"] = _actor_user_id(user_api_key_dict)
        create_data["updated_by"] = _actor_user_id(user_api_key_dict)
        try:
            row = await self.db.cavadalabs_guardrailpolicytable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Guardrail policy version already exists"},
                )
            raise
        response = _parse_response(row, CavadaLabsGuardrailPolicyResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="guardrail_policy",
            resource_id=response.policy_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_policies(
        self,
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
        chatbot_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsGuardrailPolicyStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> CavadaLabsGuardrailPolicyListResponse:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if project_id is not None:
            where["project_id"] = project_id
        if chatbot_id is not None:
            where["chatbot_id"] = chatbot_id
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_guardrailpolicytable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"updated_at": "desc"},
        )
        policies = [
            _parse_response(row, CavadaLabsGuardrailPolicyResponse) for row in rows
        ]
        return CavadaLabsGuardrailPolicyListResponse(
            guardrail_policies=policies, count=len(policies)
        )

    async def get_policy(self, policy_id: str) -> CavadaLabsGuardrailPolicyResponse:
        row = await self.db.cavadalabs_guardrailpolicytable.find_unique(
            where={"policy_id": policy_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Guardrail policy '{policy_id}' not found"},
            )
        return _parse_response(row, CavadaLabsGuardrailPolicyResponse)

    async def update_policy(
        self,
        policy_id: str,
        data: CavadaLabsGuardrailPolicyUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsGuardrailPolicyResponse:
        before = await self.get_policy(policy_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_guardrailpolicytable.update(
            where={"policy_id": policy_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsGuardrailPolicyResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="guardrail_policy",
            resource_id=response.policy_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def evaluate_text(
        self,
        data: CavadaLabsGuardrailEvaluateRequest,
    ) -> CavadaLabsGuardrailEvaluationResult:
        started_at = time.monotonic()
        policies = await self._active_policies_for_context(
            company_id=data.company_id,
            project_id=data.project_id,
            chatbot_id=data.chatbot_id,
        )
        text = data.text or ""
        redacted_text = text
        decision_logs: List[CavadaLabsGuardrailDecisionLogResponse] = []
        overall_decision = CavadaLabsGuardrailDecision.ALLOW
        reason_code: Optional[str] = None
        all_triggered_rules: List[Dict[str, Any]] = []

        for policy in policies:
            decision, policy_redacted_text, triggered_rules = self._evaluate_policy(
                policy, redacted_text
            )
            if policy.enforcement_mode == CavadaLabsGuardrailEnforcementMode.LOG_ONLY:
                action = CavadaLabsGuardrailDecision.LOG_ONLY
            else:
                action = decision
                if decision == CavadaLabsGuardrailDecision.BLOCK:
                    overall_decision = CavadaLabsGuardrailDecision.BLOCK
                elif (
                    decision == CavadaLabsGuardrailDecision.REDACT
                    and overall_decision != CavadaLabsGuardrailDecision.BLOCK
                ):
                    overall_decision = CavadaLabsGuardrailDecision.REDACT
                    redacted_text = policy_redacted_text

            if triggered_rules and reason_code is None:
                reason_code = str(triggered_rules[0].get("reason_code") or "matched")
            all_triggered_rules.extend(triggered_rules)
            decision_logs.append(
                await self._create_decision_log(
                    policy=policy,
                    data=data,
                    decision=decision,
                    action=action,
                    triggered_rules=triggered_rules,
                    redaction_summary={
                        "changed": policy_redacted_text != text,
                        "characters_before": len(text),
                        "characters_after": len(policy_redacted_text),
                    },
                    latency_ms=int((time.monotonic() - started_at) * 1000),
                )
            )

        blocked = overall_decision == CavadaLabsGuardrailDecision.BLOCK
        return CavadaLabsGuardrailEvaluationResult(
            decision=overall_decision,
            action=overall_decision,
            blocked=blocked,
            redacted_text=redacted_text if redacted_text != text else None,
            reason_code=reason_code,
            triggered_rules=all_triggered_rules,
            decisions=decision_logs,
        )

    async def evaluate_chat_request(
        self,
        *,
        context: CavadaLabsRuntimeContext,
        request_data: CavadaLabsChatCompletionRequest,
    ) -> Tuple[CavadaLabsGuardrailEvaluationResult, CavadaLabsChatCompletionRequest]:
        result = await self.evaluate_text(
            CavadaLabsGuardrailEvaluateRequest(
                company_id=context.company.company_id,
                project_id=context.project.project_id,
                chatbot_id=context.chatbot.chatbot_id,
                web_token_id=context.web_token.web_token_id,
                session_id=request_data.session_id,
                request_id=request_data.client_request_id,
                phase=CavadaLabsGuardrailPhase.PRE_CALL,
                text=_message_text(request_data.messages),
                metadata={
                    "runtime": "chatbot",
                    "model_policy_id": context.primary_policy.policy_id,
                },
            )
        )
        if result.redacted_text is None:
            return result, request_data

        replacements = await self._runtime_redaction_replacements(
            company_id=context.company.company_id,
            project_id=context.project.project_id,
            chatbot_id=context.chatbot.chatbot_id,
        )
        if not replacements:
            return result, request_data

        next_messages = _replace_message_text(request_data.messages, replacements)
        return result, request_data.model_copy(update={"messages": next_messages})

    async def list_decision_logs(
        self,
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
        chatbot_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        decision: Optional[CavadaLabsGuardrailDecision] = None,
        take: int = 100,
        skip: int = 0,
    ) -> CavadaLabsGuardrailDecisionLogListResponse:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if project_id is not None:
            where["project_id"] = project_id
        if chatbot_id is not None:
            where["chatbot_id"] = chatbot_id
        if policy_id is not None:
            where["policy_id"] = policy_id
        if decision is not None:
            where["decision"] = _enum_value(decision)
        rows = await self.db.cavadalabs_guardraildecisionlogtable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        decisions = [
            _parse_response(row, CavadaLabsGuardrailDecisionLogResponse) for row in rows
        ]
        return CavadaLabsGuardrailDecisionLogListResponse(
            guardrail_decisions=decisions, count=len(decisions)
        )

    async def _active_policies_for_context(
        self,
        *,
        company_id: str,
        project_id: Optional[str],
        chatbot_id: Optional[str],
    ) -> List[CavadaLabsGuardrailPolicyResponse]:
        policy_rows = []
        policy_rows.extend(
            await self.db.cavadalabs_guardrailpolicytable.find_many(
                where={
                    "company_id": company_id,
                    "scope": CavadaLabsGuardrailPolicyScope.COMPANY.value,
                    "status": CavadaLabsGuardrailPolicyStatus.ACTIVE.value,
                },
                order={"version": "desc"},
            )
        )
        if project_id is not None:
            policy_rows.extend(
                await self.db.cavadalabs_guardrailpolicytable.find_many(
                    where={
                        "company_id": company_id,
                        "project_id": project_id,
                        "scope": CavadaLabsGuardrailPolicyScope.PROJECT.value,
                        "status": CavadaLabsGuardrailPolicyStatus.ACTIVE.value,
                    },
                    order={"version": "desc"},
                )
            )
        if chatbot_id is not None:
            policy_rows.extend(
                await self.db.cavadalabs_guardrailpolicytable.find_many(
                    where={
                        "company_id": company_id,
                        "chatbot_id": chatbot_id,
                        "scope": CavadaLabsGuardrailPolicyScope.CHATBOT.value,
                        "status": CavadaLabsGuardrailPolicyStatus.ACTIVE.value,
                    },
                    order={"version": "desc"},
                )
            )
        return [
            _parse_response(row, CavadaLabsGuardrailPolicyResponse)
            for row in policy_rows
        ]

    def _evaluate_policy(
        self,
        policy: CavadaLabsGuardrailPolicyResponse,
        text: str,
    ) -> Tuple[CavadaLabsGuardrailDecision, str, List[Dict[str, Any]]]:
        triggered_rules: List[Dict[str, Any]] = []
        redacted_text = text

        for pattern in policy.blocked_patterns:
            if _safe_regex_search(pattern, text):
                triggered_rules.append(
                    {
                        "type": "blocked_pattern",
                        "pattern": pattern,
                        "decision": CavadaLabsGuardrailDecision.BLOCK.value,
                        "reason_code": "blocked_pattern",
                    }
                )

        for term in policy.rules.get("blocked_terms", []):
            if isinstance(term, str) and term.lower() in text.lower():
                triggered_rules.append(
                    {
                        "type": "blocked_term",
                        "term": term,
                        "decision": CavadaLabsGuardrailDecision.BLOCK.value,
                        "reason_code": "blocked_term",
                    }
                )

        if policy.prompt_injection_detection_enabled:
            lowered = text.lower()
            for phrase in _PROMPT_INJECTION_PHRASES:
                if phrase in lowered:
                    triggered_rules.append(
                        {
                            "type": "prompt_injection",
                            "phrase": phrase,
                            "decision": CavadaLabsGuardrailDecision.BLOCK.value,
                            "reason_code": "prompt_injection",
                        }
                    )
                    break

        replacements = self._policy_redaction_replacements(policy)
        redacted_text = _apply_replacements(redacted_text, replacements)
        if redacted_text != text:
            triggered_rules.append(
                {
                    "type": "redaction",
                    "decision": CavadaLabsGuardrailDecision.REDACT.value,
                    "reason_code": "redaction",
                }
            )

        if any(
            rule.get("decision") == CavadaLabsGuardrailDecision.BLOCK.value
            for rule in triggered_rules
        ):
            return CavadaLabsGuardrailDecision.BLOCK, redacted_text, triggered_rules
        if redacted_text != text:
            return CavadaLabsGuardrailDecision.REDACT, redacted_text, triggered_rules
        return CavadaLabsGuardrailDecision.ALLOW, redacted_text, triggered_rules

    def _policy_redaction_replacements(
        self, policy: CavadaLabsGuardrailPolicyResponse
    ) -> Dict[str, str]:
        replacements = dict(policy.redaction_patterns)
        if policy.pii_detection_enabled:
            replacements.setdefault(_EMAIL_PATTERN.pattern, "[redacted-email]")
            replacements.setdefault(_PHONE_PATTERN.pattern, "[redacted-phone]")
            replacements.setdefault(_CARD_PATTERN.pattern, "[redacted-card]")
        return replacements

    async def _runtime_redaction_replacements(
        self,
        *,
        company_id: str,
        project_id: Optional[str],
        chatbot_id: Optional[str],
    ) -> Dict[str, str]:
        replacements: Dict[str, str] = {}
        policies = await self._active_policies_for_context(
            company_id=company_id,
            project_id=project_id,
            chatbot_id=chatbot_id,
        )
        for policy in policies:
            replacements.update(self._policy_redaction_replacements(policy))
        return replacements

    async def _create_decision_log(
        self,
        *,
        policy: CavadaLabsGuardrailPolicyResponse,
        data: CavadaLabsGuardrailEvaluateRequest,
        decision: CavadaLabsGuardrailDecision,
        action: CavadaLabsGuardrailDecision,
        triggered_rules: List[Dict[str, Any]],
        redaction_summary: Dict[str, Any],
        latency_ms: int,
    ) -> CavadaLabsGuardrailDecisionLogResponse:
        metadata = dict(data.metadata)
        if policy.log_raw_content:
            metadata["raw_text"] = data.text
        row = await self.db.cavadalabs_guardraildecisionlogtable.create(
            data=serialize_prisma_json_fields(
                {
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "company_id": data.company_id,
                "project_id": data.project_id,
                "chatbot_id": data.chatbot_id,
                "web_token_id": data.web_token_id,
                "session_id": data.session_id,
                "request_id": data.request_id,
                "phase": _enum_value(data.phase),
                "decision": _enum_value(decision),
                "action": _enum_value(action),
                "confidence": 1.0 if triggered_rules else None,
                "reason_code": (
                    str(triggered_rules[0].get("reason_code"))
                    if triggered_rules
                    else None
                ),
                "triggered_rules": triggered_rules,
                "redaction_summary": redaction_summary,
                "latency_ms": latency_ms,
                "metadata": metadata,
                }
            )
        )
        return _parse_response(row, CavadaLabsGuardrailDecisionLogResponse)

    async def _validate_policy_scope(
        self,
        *,
        company_id: str,
        project_id: Optional[str],
        chatbot_id: Optional[str],
        scope: CavadaLabsGuardrailPolicyScope,
    ) -> None:
        dispatcher = CavadaLabsDispatcherService(self.prisma_client)
        await dispatcher.get_company(company_id)
        if project_id is not None:
            project = await dispatcher.get_project(project_id)
            if project.company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Guardrail project does not belong to company"},
                )
        if chatbot_id is not None:
            chatbot = await dispatcher.get_chatbot(chatbot_id)
            if chatbot.company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Guardrail chatbot does not belong to company"},
                )
            if project_id is not None and chatbot.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Guardrail chatbot does not belong to project"},
                )
        if scope == CavadaLabsGuardrailPolicyScope.PROJECT and project_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "project-scoped guardrail policies require project_id"
                },
            )
        if scope == CavadaLabsGuardrailPolicyScope.CHATBOT and chatbot_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "chatbot-scoped guardrail policies require chatbot_id"
                },
            )

    async def _audit(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        action: str,
        resource_type: str,
        resource_id: str,
        before_value: Optional[Dict[str, Any]],
        after_value: Optional[Dict[str, Any]],
        company_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        try:
            await self.db.cavadalabs_auditlogtable.create(
                data=serialize_prisma_json_fields(
                    {
                    "actor_user_id": _actor_user_id(user_api_key_dict),
                    "actor_api_key_hash": _actor_key_hash(user_api_key_dict),
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "company_id": company_id,
                    "project_id": project_id,
                    "before_value": before_value,
                    "after_value": after_value,
                    }
                )
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Failed to write CavadaLabs audit log for %s/%s: %s",
                resource_type,
                resource_id,
                exc,
            )
