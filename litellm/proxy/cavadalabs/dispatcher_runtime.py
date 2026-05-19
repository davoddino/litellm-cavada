from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import HTTPException, status

from litellm.proxy.cavadalabs.dispatcher_chatbots import CavadaLabsChatbotOperations
from litellm.proxy.cavadalabs.dispatcher_model_policies import (
    CavadaLabsModelPolicyOperations,
)
from litellm.proxy.cavadalabs.dispatcher_shared import (
    CavadaLabsRuntimeContext,
    _month_start_utc,
    _rate_limit_window,
    _unique_strings,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatCompletionRequest,
    CavadaLabsChatbotStatus,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsWebTokenResponse,
)

if TYPE_CHECKING:
    from litellm.proxy.cavadalabs.model_runtime import CavadaLabsHostedModelRuntime
    from litellm.proxy.cavadalabs.rag_runtime import CavadaLabsRAGContext


def _metadata_string(metadata: Any, key: str) -> Optional[str]:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value
    cavadalabs_metadata = metadata.get("cavadalabs")
    if isinstance(cavadalabs_metadata, dict):
        value = cavadalabs_metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


class CavadaLabsRuntimeOperations(
    CavadaLabsChatbotOperations,
    CavadaLabsModelPolicyOperations,
):
    async def resolve_runtime_context(
        self,
        token: str,
        route: str,
        origin: Optional[str],
        model_bucket: Optional[str] = None,
    ) -> CavadaLabsRuntimeContext:
        validation_result = await self.validate_web_token(
            token=token,
            route=route,
            origin=origin,
        )
        if not validation_result.active:
            reason = validation_result.reason or "token_invalid"
            status_code = (
                status.HTTP_403_FORBIDDEN
                if reason
                in {"route_not_allowed", "origin_not_allowed", "domain_not_allowed"}
                else status.HTTP_401_UNAUTHORIZED
            )
            raise HTTPException(
                status_code=status_code,
                detail={"error": f"CavadaLabs web token rejected: {reason}"},
            )

        company = await self.get_company(validation_result.company_id or "")
        project = await self.get_project(validation_result.project_id or "")
        chatbot = await self.get_chatbot(validation_result.chatbot_id or "")
        web_token = await self.get_web_token(validation_result.web_token_id or "")

        if (
            project.company_id != company.company_id
            or chatbot.company_id != company.company_id
            or chatbot.project_id != project.project_id
            or web_token.company_id != company.company_id
            or web_token.project_id != project.project_id
            or web_token.chatbot_id != chatbot.chatbot_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "CavadaLabs runtime ownership is inconsistent"},
            )

        self._ensure_company_active(company, "run chatbot messages")
        self._ensure_project_not_archived(project, "run chatbot messages")
        if chatbot.status != CavadaLabsChatbotStatus.PUBLISHED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "Chatbot is not published"},
            )

        resolved_model_bucket = self._chatbot_model_bucket(
            requested_model_bucket=model_bucket,
            chatbot_metadata=chatbot.metadata,
            web_token_metadata=web_token.metadata,
        )
        primary_policy, fallback_policies = await self.resolve_model_policy_for_chatbot(
            chatbot=chatbot,
            project=project,
            endpoint_type="chat_completion",
            model_bucket=resolved_model_bucket,
        )
        return CavadaLabsRuntimeContext(
            company=company,
            project=project,
            chatbot=chatbot,
            web_token=web_token,
            primary_policy=primary_policy,
            fallback_policies=fallback_policies,
        )

    @staticmethod
    def _chatbot_model_bucket(
        *,
        requested_model_bucket: Optional[str],
        chatbot_metadata: Any,
        web_token_metadata: Any,
    ) -> str:
        for value in (
            requested_model_bucket,
            _metadata_string(web_token_metadata, "model_bucket"),
            _metadata_string(chatbot_metadata, "default_model_bucket"),
            _metadata_string(chatbot_metadata, "model_bucket"),
        ):
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return "default"

    async def enforce_runtime_limits(
        self,
        context: CavadaLabsRuntimeContext,
        session_id: str,
        request_ip: str,
        internal_usage_cache: Any,
    ) -> None:
        await self._enforce_runtime_budgets(
            context=context,
            session_id=session_id,
        )
        await self._enforce_runtime_rate_limits(
            web_token=context.web_token,
            session_id=session_id,
            request_ip=request_ip,
            internal_usage_cache=internal_usage_cache,
        )

    async def _enforce_runtime_budgets(
        self,
        context: CavadaLabsRuntimeContext,
        session_id: str,
    ) -> None:
        month_start = _month_start_utc()
        if context.company.monthly_budget is not None:
            company_spend = await self._sum_request_ledger_spend(
                by_field="company_id",
                entity_id=context.company.company_id,
                since=month_start,
            )
            if company_spend >= context.company.monthly_budget:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "CavadaLabs company monthly budget has been reached"
                    },
                )

        if context.project.budget is not None:
            project_spend = await self._sum_request_ledger_spend(
                by_field="project_id",
                entity_id=context.project.project_id,
                since=month_start,
            )
            if project_spend >= context.project.budget:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "CavadaLabs project monthly budget has been reached"
                    },
                )

        if context.web_token.session_budget is not None:
            session_spend = await self._sum_session_ledger_spend(
                web_token_id=context.web_token.web_token_id,
                session_id=session_id,
            )
            if session_spend >= context.web_token.session_budget:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "CavadaLabs web token session budget has been reached"
                    },
                )

    async def _sum_request_ledger_spend(
        self,
        by_field: str,
        entity_id: str,
        since: datetime,
    ) -> float:
        rows = await self.db.cavadalabs_requestledgertable.group_by(
            by=[by_field],
            where={by_field: entity_id, "created_at": {"gte": since}},
            sum={"spend": True},
        )
        return self._extract_grouped_spend(rows)

    async def _sum_session_ledger_spend(
        self,
        web_token_id: str,
        session_id: str,
    ) -> float:
        rows = await self.db.cavadalabs_requestledgertable.group_by(
            by=["web_token_id"],
            where={"web_token_id": web_token_id, "session_id": session_id},
            sum={"spend": True},
        )
        return self._extract_grouped_spend(rows)

    async def _enforce_runtime_rate_limits(
        self,
        web_token: CavadaLabsWebTokenResponse,
        session_id: str,
        request_ip: str,
        internal_usage_cache: Any,
    ) -> None:
        if internal_usage_cache is None:
            if (
                web_token.ip_rpm_limit is not None
                or web_token.session_rpm_limit is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"error": "CavadaLabs runtime rate limiter is unavailable"},
                )
            return

        window, retry_after = _rate_limit_window()
        if web_token.ip_rpm_limit is not None:
            await self._increment_runtime_rate_limit(
                internal_usage_cache=internal_usage_cache,
                cache_key=(
                    "cavadalabs:web-token:"
                    f"{web_token.web_token_id}:ip:{request_ip}:{window}:rpm"
                ),
                limit=web_token.ip_rpm_limit,
                retry_after=retry_after,
                label="ip_rpm_limit",
            )
        if web_token.session_rpm_limit is not None:
            await self._increment_runtime_rate_limit(
                internal_usage_cache=internal_usage_cache,
                cache_key=(
                    "cavadalabs:web-token:"
                    f"{web_token.web_token_id}:session:{session_id}:{window}:rpm"
                ),
                limit=web_token.session_rpm_limit,
                retry_after=retry_after,
                label="session_rpm_limit",
            )

    async def _increment_runtime_rate_limit(
        self,
        internal_usage_cache: Any,
        cache_key: str,
        limit: int,
        retry_after: int,
        label: str,
    ) -> None:
        current = await internal_usage_cache.async_increment_cache(
            key=cache_key,
            value=1,
            ttl=max(retry_after + 5, 60),
            litellm_parent_otel_span=None,
        )
        if current is not None and int(current) > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": f"CavadaLabs web token {label} exceeded"},
                headers={"retry-after": str(retry_after)},
            )

    def build_chat_completion_payload(
        self,
        request_data: CavadaLabsChatCompletionRequest,
        context: CavadaLabsRuntimeContext,
        origin: Optional[str],
        request_ip: str,
        rag_context: Optional["CavadaLabsRAGContext"] = None,
    ) -> Dict[str, Any]:
        primary_policy = context.primary_policy
        payload = request_data.model_dump(
            mode="python",
            exclude_none=True,
            exclude={"client_request_id", "metadata", "session_id", "model_bucket"},
        )
        payload["model"] = primary_policy.model_alias
        messages = [
            {"role": "system", "content": context.chatbot.system_prompt},
        ]
        if rag_context is not None and rag_context.has_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use the following CavadaLabs RAG context when it is relevant. "
                        "Cite the numbered source labels when answering. If the answer is "
                        "not present in the context, say that the available knowledge base "
                        "does not contain enough information.\n\n"
                        f"{rag_context.context_text}"
                    ),
                }
            )
        messages.extend(payload["messages"])
        payload["messages"] = messages
        payload["user"] = request_data.user or request_data.session_id

        fallback_models = _unique_strings(
            [
                policy.model_alias
                for policy in context.fallback_policies
                if policy.fallback_enabled
                and policy.model_alias != primary_policy.model_alias
            ]
        )
        if fallback_models:
            payload["fallbacks"] = fallback_models

        self._apply_output_format_policy(payload, primary_policy)
        self._apply_reasoning_policy(payload, primary_policy)

        guardrails = _unique_strings(
            [
                context.chatbot.assigned_guardrail_policy,
                context.project.default_guardrail_policy,
                context.company.default_guardrail_policy,
            ]
        )
        if guardrails:
            payload["guardrails"] = guardrails

        rag_metadata = rag_context.metadata() if rag_context is not None else None
        output_controls = self._output_control_metadata(primary_policy)
        payload["metadata"] = {
            **request_data.metadata,
            "session_id": request_data.session_id,
            "cavadalabs_company_id": context.company.company_id,
            "cavadalabs_project_id": context.project.project_id,
            "cavadalabs_chatbot_id": context.chatbot.chatbot_id,
            "cavadalabs_web_token_id": context.web_token.web_token_id,
            "cavadalabs_metadata_authenticated": True,
            "cavadalabs_metadata_source": "chatbot_runtime",
            "cavadalabs_policy_id": primary_policy.policy_id,
            "cavadalabs_provider": primary_policy.provider,
            "cavadalabs_endpoint_type": primary_policy.endpoint_type,
            "cavadalabs_model_bucket": primary_policy.model_bucket,
            "cavadalabs": {
                "company_id": context.company.company_id,
                "project_id": context.project.project_id,
                "chatbot_id": context.chatbot.chatbot_id,
                "web_token_id": context.web_token.web_token_id,
                "session_id": request_data.session_id,
                "policy_id": primary_policy.policy_id,
                "fallback_policy_ids": [
                    policy.policy_id for policy in context.fallback_policies
                ],
                "endpoint_type": primary_policy.endpoint_type,
                "model_bucket": primary_policy.model_bucket,
                "model_alias": primary_policy.model_alias,
                "deployment_id": primary_policy.deployment_id,
                "provider": primary_policy.provider,
                "prompt_version": context.chatbot.prompt_version,
                "default_language": context.chatbot.default_language,
                "assigned_rag_collections": context.chatbot.assigned_rag_collections,
                "rag": rag_metadata,
                "guardrails": guardrails,
                "origin": origin,
                "request_ip": request_ip,
                "client_request_id": request_data.client_request_id,
                **output_controls,
            },
        }
        return payload

    def _apply_output_format_policy(
        self,
        payload: Dict[str, Any],
        primary_policy: CavadaLabsProjectModelPolicyResponse,
    ) -> None:
        if primary_policy.json_schema is not None:
            if payload.get("response_format") is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "Selected CavadaLabs model policy owns response_format"
                    },
                )
            schema_name = str(
                primary_policy.metadata.get("json_schema_name") or "cavadalabs_output"
            )
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": primary_policy.json_schema,
                    "strict": primary_policy.strict_json,
                },
            }
            return

        if primary_policy.require_json_output or primary_policy.force_json_output:
            response_format = payload.get("response_format")
            if response_format is None:
                payload["response_format"] = {"type": "json_object"}
            elif response_format.get("type") not in {"json_object", "json_schema"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "Selected CavadaLabs model policy requires JSON output"
                    },
                )

    @staticmethod
    def _apply_reasoning_policy(
        payload: Dict[str, Any],
        primary_policy: CavadaLabsProjectModelPolicyResponse,
    ) -> None:
        reasoning_mode: Optional[str] = primary_policy.reasoning_mode
        if primary_policy.require_no_think or primary_policy.no_think:
            reasoning_mode = "none"
        if reasoning_mode is not None:
            payload["reasoning_effort"] = reasoning_mode

    @staticmethod
    def _output_control_metadata(
        primary_policy: CavadaLabsProjectModelPolicyResponse,
    ) -> Dict[str, Any]:
        return {
            "require_json_output": primary_policy.require_json_output,
            "force_json_output": primary_policy.force_json_output,
            "has_json_schema": primary_policy.json_schema is not None,
            "json_schema": primary_policy.json_schema,
            "strict_json": primary_policy.strict_json,
            "repair_invalid_json": primary_policy.repair_invalid_json,
            "retry_on_invalid_json": primary_policy.retry_on_invalid_json,
            "require_no_think": primary_policy.require_no_think,
            "no_think": primary_policy.no_think,
            "reasoning_mode": primary_policy.reasoning_mode,
            "hide_reasoning": primary_policy.hide_reasoning,
            "strip_thinking_tags": primary_policy.strip_thinking_tags,
        }

    async def prepare_chat_completion_payload(
        self,
        request_data: CavadaLabsChatCompletionRequest,
        context: CavadaLabsRuntimeContext,
        origin: Optional[str],
        request_ip: str,
        rag_context: Optional["CavadaLabsRAGContext"] = None,
    ) -> Dict[str, Any]:
        (
            selected_policy,
            runtime,
            remaining_fallback_policies,
            routing_metadata,
        ) = await self._select_chat_completion_policy(context)
        selected_context = replace(
            context,
            primary_policy=selected_policy,
            fallback_policies=remaining_fallback_policies,
        )
        payload = self.build_chat_completion_payload(
            request_data=request_data,
            context=selected_context,
            origin=origin,
            request_ip=request_ip,
            rag_context=rag_context,
        )
        if routing_metadata:
            payload["metadata"]["cavadalabs"]["routing"] = routing_metadata

        from litellm.proxy.cavadalabs.model_runtime import (
            CavadaLabsHostedModelRuntimeService,
        )

        if runtime is not None:
            await CavadaLabsHostedModelRuntimeService(
                self.prisma_client
            ).apply_hosted_runtime_to_payload(
                payload=payload,
                runtime=runtime,
            )
        return payload

    async def _select_chat_completion_policy(
        self,
        context: CavadaLabsRuntimeContext,
    ) -> tuple[
        CavadaLabsProjectModelPolicyResponse,
        Optional["CavadaLabsHostedModelRuntime"],
        list[CavadaLabsProjectModelPolicyResponse],
        Dict[str, Any],
    ]:
        from litellm.proxy.cavadalabs.model_runtime import (
            CavadaLabsHostedModelRuntimeService,
        )

        runtime_service = CavadaLabsHostedModelRuntimeService(self.prisma_client)
        policies = [context.primary_policy, *context.fallback_policies]
        skipped_policies: list[Dict[str, Any]] = []
        queued_load_requests: list[Dict[str, Any]] = []

        for index, policy in enumerate(policies):
            if not runtime_service.is_hosted_policy(policy):
                return (
                    policy,
                    None,
                    self._remaining_runtime_fallbacks(policies, index),
                    {
                        "selected_policy_id": policy.policy_id,
                        "selected_model_alias": policy.model_alias,
                        "selected_provider": policy.provider,
                        "skipped_policies": skipped_policies,
                        "queued_model_load_requests": queued_load_requests,
                    },
                )
            try:
                runtime = await runtime_service.resolve_hosted_runtime(
                    policy=policy,
                    project_id=context.project.project_id,
                )
                return (
                    policy,
                    runtime,
                    self._remaining_runtime_fallbacks(policies, index),
                    {
                        "selected_policy_id": policy.policy_id,
                        "selected_model_alias": policy.model_alias,
                        "selected_provider": policy.provider,
                        "skipped_policies": skipped_policies,
                        "queued_model_load_requests": queued_load_requests,
                    },
                )
            except HTTPException as exc:
                reason_codes = self._runtime_failure_reason_codes(exc)
                load_request = None
                if self._should_enqueue_after_runtime_failure(reason_codes):
                    load_request = (
                        await runtime_service.ensure_model_load_request_if_loadable(
                            policy=policy,
                            company_id=context.company.company_id,
                            project_id=context.project.project_id,
                            reason_code=reason_codes[0],
                        )
                    )
                if load_request is not None:
                    queued_load_requests.append(
                        {
                            "policy_id": policy.policy_id,
                            "model_alias": policy.model_alias,
                            "model_load_request_id": (
                                load_request.model_load_request_id
                            ),
                            "status": load_request.status,
                        }
                    )
                skipped_policies.append(
                    {
                        "policy_id": policy.policy_id,
                        "model_alias": policy.model_alias,
                        "provider": policy.provider,
                        "reason_codes": reason_codes,
                    }
                )
                continue

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "No CavadaLabs model policy is currently routable",
                "skipped_policies": skipped_policies,
                "queued_model_load_requests": queued_load_requests,
            },
            headers={"retry-after": "30"} if queued_load_requests else None,
        )

    @staticmethod
    def _remaining_runtime_fallbacks(
        policies: list[CavadaLabsProjectModelPolicyResponse],
        selected_index: int,
    ) -> list[CavadaLabsProjectModelPolicyResponse]:
        return [
            policy
            for policy in policies[selected_index + 1 :]
            if policy.fallback_enabled
        ]

    @staticmethod
    def _runtime_failure_reason_codes(exc: HTTPException) -> list[str]:
        detail = exc.detail
        if isinstance(detail, dict):
            reasons = detail.get("reasons")
            if isinstance(reasons, list):
                result = [reason for reason in reasons if isinstance(reason, str)]
                if result:
                    return result
            error = detail.get("error")
            if isinstance(error, str) and "No loaded" in error:
                return ["no_loaded_runtime"]
        return ["runtime_unavailable"]

    @staticmethod
    def _should_enqueue_after_runtime_failure(reason_codes: list[str]) -> bool:
        non_recoverable = {
            "missing_required_capabilities",
            "missing_runtime_endpoint",
        }
        return not any(reason in non_recoverable for reason in reason_codes)
