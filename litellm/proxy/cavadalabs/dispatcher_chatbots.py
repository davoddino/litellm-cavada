from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.chatbot_references import (
    validate_chatbot_project_references,
)
from litellm.proxy.cavadalabs.chatbot_token_metadata import (
    build_chatbot_token_metadata,
)
from litellm.proxy.cavadalabs.dispatcher_projects import CavadaLabsProjectOperations
from litellm.proxy.cavadalabs.dispatcher_shared import (
    _MAX_BROWSER_TOKEN_TTL,
    _actor_user_id,
    _as_aware_utc,
    _create_browser_token,
    _domain_matches,
    _is_unique_violation,
    _now_utc,
    _origin_host,
    _parse_response,
    hash_web_token,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotCreateRequest,
    CavadaLabsChatbotResponse,
    CavadaLabsChatbotStatus,
    CavadaLabsChatbotUpdateRequest,
    CavadaLabsWebTokenCreateRequest,
    CavadaLabsWebTokenCreateResponse,
    CavadaLabsWebTokenResponse,
    CavadaLabsWebTokenStatus,
    CavadaLabsWebTokenValidationResult,
)


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


def _chatbot_default_model_bucket(metadata: Any) -> str:
    for key in ("default_model_bucket", "model_bucket"):
        value = _metadata_string(metadata, key)
        if value is not None:
            return value.strip().lower()
    return "default"


class CavadaLabsChatbotOperations(CavadaLabsProjectOperations):
    async def create_chatbot(
        self,
        data: CavadaLabsChatbotCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsChatbotResponse:
        project = await self.get_project(data.project_id)
        if project.company_id != data.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "project_id does not belong to company_id"},
            )
        company = await self.get_company(data.company_id)
        self._ensure_company_active(company, "create chatbots")
        self._ensure_project_not_archived(project, "create chatbots")
        await validate_chatbot_project_references(
            self.db,
            company_id=data.company_id,
            project_id=data.project_id,
            model_policy_id=data.model_policy_id,
            expected_policy_endpoint_type="chat_completion",
            expected_policy_model_bucket=_chatbot_default_model_bucket(data.metadata),
            assigned_rag_collection_ids=data.assigned_rag_collections,
            assigned_guardrail_policy=data.assigned_guardrail_policy,
        )
        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        try:
            row = await self.db.cavadalabs_chatbottable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Chatbot name already exists for this project"},
                )
            raise
        response = _parse_response(row, CavadaLabsChatbotResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="chatbot",
            resource_id=response.chatbot_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_chatbot(self, chatbot_id: str) -> CavadaLabsChatbotResponse:
        row = await self.db.cavadalabs_chatbottable.find_unique(
            where={"chatbot_id": chatbot_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Chatbot '{chatbot_id}' not found"},
            )
        return _parse_response(row, CavadaLabsChatbotResponse)

    async def list_chatbots(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        status_filter: Optional[CavadaLabsChatbotStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsChatbotResponse]:
        if company_ids == [] or project_ids == []:
            return []

        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        elif company_ids is not None:
            if not company_ids:
                return []
            where["company_id"] = {"in": sorted(set(company_ids))}
        if project_id is not None:
            where["project_id"] = project_id
        elif project_ids is not None:
            if not project_ids:
                return []
            where["project_id"] = {"in": sorted(set(project_ids))}
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_chatbottable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsChatbotResponse) for row in rows]

    async def update_chatbot(
        self,
        chatbot_id: str,
        data: CavadaLabsChatbotUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsChatbotResponse:
        before = await self.get_chatbot(chatbot_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        next_prompt = update_data.get("system_prompt", before.system_prompt)
        next_status = update_data.get("status", before.status)
        if next_status == CavadaLabsChatbotStatus.PUBLISHED.value and not next_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "published chatbots require a system_prompt"},
            )
        effective_model_policy_id = (
            update_data["model_policy_id"]
            if "model_policy_id" in update_data
            else before.model_policy_id
        )
        effective_metadata = update_data.get("metadata", before.metadata)
        await validate_chatbot_project_references(
            self.db,
            company_id=before.company_id,
            project_id=before.project_id,
            chatbot_id=before.chatbot_id,
            model_policy_id=effective_model_policy_id,
            expected_policy_endpoint_type="chat_completion",
            expected_policy_model_bucket=_chatbot_default_model_bucket(
                effective_metadata
            ),
            assigned_rag_collection_ids=update_data.get("assigned_rag_collections"),
            assigned_guardrail_policy=update_data.get("assigned_guardrail_policy"),
        )
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_chatbottable.update(
            where={"chatbot_id": chatbot_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsChatbotResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="chatbot",
            resource_id=response.chatbot_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def create_web_token(
        self,
        data: CavadaLabsWebTokenCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsWebTokenCreateResponse:
        company = await self.get_company(data.company_id)
        project = await self.get_project(data.project_id)
        chatbot = await self.get_chatbot(data.chatbot_id)
        if (
            project.company_id != data.company_id
            or chatbot.company_id != data.company_id
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "company_id, project_id and chatbot_id are inconsistent"
                },
            )
        if chatbot.project_id != data.project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "chatbot_id does not belong to project_id"},
            )
        self._ensure_company_active(company, "create web tokens")
        self._ensure_project_not_archived(project, "create web tokens")
        if chatbot.status != CavadaLabsChatbotStatus.PUBLISHED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "web tokens can only be created for published chatbots"
                },
            )

        expires_at = data.expires_at or (
            _now_utc() + timedelta(seconds=data.expires_in_seconds)
        )
        expires_at = _as_aware_utc(expires_at)
        if expires_at <= _now_utc():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "expires_at must be in the future"},
            )
        if expires_at - _now_utc() > _MAX_BROWSER_TOKEN_TTL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "browser web tokens cannot live longer than 24 hours"},
            )

        token, token_prefix, token_hash = _create_browser_token()
        allowed_domains = data.allowed_domains or chatbot.allowed_domains
        data_metadata = build_chatbot_token_metadata(
            data.metadata,
            company_id=data.company_id,
            project_id=data.project_id,
            chatbot_id=data.chatbot_id,
        )
        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(
                    mode="python", exclude={"expires_in_seconds", "expires_at"}
                ),
                "allowed_domains": allowed_domains,
                "metadata": data_metadata,
                "token_prefix": token_prefix,
                "token_hash": token_hash,
                "status": CavadaLabsWebTokenStatus.ACTIVE.value,
                "expires_at": expires_at,
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        row = await self.db.cavadalabs_webtokentable.create(data=create_data)
        web_token = _parse_response(row, CavadaLabsWebTokenResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="web_token",
            resource_id=web_token.web_token_id,
            company_id=web_token.company_id,
            project_id=web_token.project_id,
            before_value=None,
            after_value=self._redact_web_token(web_token.model_dump(mode="json")),
        )
        return CavadaLabsWebTokenCreateResponse(web_token=web_token, token=token)

    async def list_web_tokens(
        self,
        company_id: Optional[str] = None,
        company_ids: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        chatbot_id: Optional[str] = None,
        status_filter: Optional[CavadaLabsWebTokenStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsWebTokenResponse]:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        elif company_ids is not None:
            if not company_ids:
                return []
            where["company_id"] = {"in": sorted(set(company_ids))}
        if project_id is not None:
            where["project_id"] = project_id
        elif project_ids is not None:
            if not project_ids:
                return []
            where["project_id"] = {"in": sorted(set(project_ids))}
        if chatbot_id is not None:
            where["chatbot_id"] = chatbot_id
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_webtokentable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsWebTokenResponse) for row in rows]

    async def revoke_web_token(
        self,
        web_token_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsWebTokenResponse:
        before_row = await self.db.cavadalabs_webtokentable.find_unique(
            where={"web_token_id": web_token_id}
        )
        if before_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Web token '{web_token_id}' not found"},
            )
        before = _parse_response(before_row, CavadaLabsWebTokenResponse)
        row = await self.db.cavadalabs_webtokentable.update(
            where={"web_token_id": web_token_id},
            data={
                "status": CavadaLabsWebTokenStatus.REVOKED.value,
                "revoked_at": _now_utc(),
                "updated_by": _actor_user_id(user_api_key_dict),
            },
        )
        response = _parse_response(row, CavadaLabsWebTokenResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="revoked",
            resource_type="web_token",
            resource_id=response.web_token_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=self._redact_web_token(before.model_dump(mode="json")),
            after_value=self._redact_web_token(response.model_dump(mode="json")),
        )
        return response

    async def validate_web_token(
        self,
        token: str,
        route: str,
        origin: Optional[str] = None,
    ) -> CavadaLabsWebTokenValidationResult:
        row = await self.db.cavadalabs_webtokentable.find_unique(
            where={"token_hash": hash_web_token(token)}
        )
        if row is None:
            return CavadaLabsWebTokenValidationResult(
                active=False, reason="token_not_found"
            )
        web_token = _parse_response(row, CavadaLabsWebTokenResponse)
        if web_token.status != CavadaLabsWebTokenStatus.ACTIVE.value:
            return CavadaLabsWebTokenValidationResult(
                active=False, reason=f"token_{web_token.status}"
            )
        if _as_aware_utc(web_token.expires_at) <= _now_utc():
            await self.db.cavadalabs_webtokentable.update(
                where={"web_token_id": web_token.web_token_id},
                data={"status": CavadaLabsWebTokenStatus.EXPIRED.value},
            )
            return CavadaLabsWebTokenValidationResult(
                active=False, reason="token_expired"
            )
        if route not in web_token.route_allowlist:
            return CavadaLabsWebTokenValidationResult(
                active=False, reason="route_not_allowed"
            )
        if web_token.allowed_origins and origin not in web_token.allowed_origins:
            return CavadaLabsWebTokenValidationResult(
                active=False, reason="origin_not_allowed"
            )
        if not _domain_matches(_origin_host(origin), web_token.allowed_domains):
            return CavadaLabsWebTokenValidationResult(
                active=False, reason="domain_not_allowed"
            )
        await self.db.cavadalabs_webtokentable.update(
            where={"web_token_id": web_token.web_token_id},
            data={"last_used_at": _now_utc()},
        )
        return CavadaLabsWebTokenValidationResult(
            active=True,
            company_id=web_token.company_id,
            project_id=web_token.project_id,
            chatbot_id=web_token.chatbot_id,
            web_token_id=web_token.web_token_id,
        )

    async def get_web_token(self, web_token_id: str) -> CavadaLabsWebTokenResponse:
        row = await self.db.cavadalabs_webtokentable.find_unique(
            where={"web_token_id": web_token_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Web token '{web_token_id}' not found"},
            )
        return _parse_response(row, CavadaLabsWebTokenResponse)
