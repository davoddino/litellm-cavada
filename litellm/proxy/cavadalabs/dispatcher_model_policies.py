from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher_projects import CavadaLabsProjectOperations
from litellm.proxy.cavadalabs.dispatcher_shared import (
    _actor_user_id,
    _is_unique_violation,
    _parse_response,
)
from litellm.proxy.cavadalabs.key_context_metadata import (
    _extract_cavadalabs_key_context,
    _metadata_to_dict,
    _optional_str,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsChatbotResponse,
    CavadaLabsProjectModelPolicyCreateRequest,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsProjectModelPolicyUpdateRequest,
    CavadaLabsProjectResponse,
)


class CavadaLabsModelPolicyOperations(CavadaLabsProjectOperations):
    async def get_project_model_policy(
        self, policy_id: str
    ) -> CavadaLabsProjectModelPolicyResponse:
        row = await self.db.cavadalabs_projectmodelpolicytable.find_unique(
            where={"policy_id": policy_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Model policy '{policy_id}' not found"},
            )
        return _parse_response(row, CavadaLabsProjectModelPolicyResponse)

    async def resolve_model_policy_for_chatbot(
        self,
        chatbot: CavadaLabsChatbotResponse,
        project: CavadaLabsProjectResponse,
        endpoint_type: str = "chat_completion",
        model_bucket: str = "default",
    ) -> Tuple[
        CavadaLabsProjectModelPolicyResponse,
        List[CavadaLabsProjectModelPolicyResponse],
    ]:
        policies = await self.list_project_model_policies(
            project_id=project.project_id,
            enabled=True,
            endpoint_type=endpoint_type,
            model_bucket=model_bucket,
        )
        policies_by_id = {policy.policy_id: policy for policy in policies}

        if chatbot.model_policy_id is not None:
            primary_policy = policies_by_id.get(chatbot.model_policy_id)
            if primary_policy is None:
                primary_policy = await self.get_project_model_policy(
                    chatbot.model_policy_id
                )
            if primary_policy.project_id != project.project_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "Chatbot model_policy_id belongs to another project"
                    },
                )
            if primary_policy.enabled is not True:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Chatbot model_policy_id is disabled"},
                )
            if (
                primary_policy.endpoint_type != endpoint_type
                or primary_policy.model_bucket != model_bucket
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "Chatbot model_policy_id does not match the requested endpoint or model bucket"
                    },
                )
            ordered_policies = [
                policy
                for policy in policies
                if policy.policy_id != primary_policy.policy_id
            ]
        else:
            if not policies:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Project has no enabled CavadaLabs model policy"},
                )
            primary_policy = policies[0]
            ordered_policies = policies[1:]

        self._ensure_model_allowed(project, primary_policy.model_alias)
        fallback_policies = []
        for policy in ordered_policies:
            self._ensure_model_allowed(project, policy.model_alias)
            if policy.fallback_enabled:
                fallback_policies.append(policy)
        return primary_policy, fallback_policies

    async def create_project_model_policy(
        self,
        data: CavadaLabsProjectModelPolicyCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectModelPolicyResponse:
        project = await self.get_project(data.project_id)
        self._ensure_project_not_archived(project, "create model policies")
        await self._validate_model_policy_key_scope(
            project=project,
            key_id=data.key_id,
        )
        self._ensure_model_allowed(project, data.model_alias)
        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "company_id": project.company_id,
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        try:
            row = await self.db.cavadalabs_projectmodelpolicytable.create(
                data=create_data
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "A model policy already uses this Project endpoint, bucket, and priority"
                    },
                )
            raise
        response = _parse_response(row, CavadaLabsProjectModelPolicyResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="model_policy",
            resource_id=response.policy_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def list_project_model_policies(
        self,
        project_id: str,
        enabled: Optional[bool] = None,
        endpoint_type: Optional[str] = None,
        model_bucket: Optional[str] = None,
        key_id: Optional[str] = None,
    ) -> List[CavadaLabsProjectModelPolicyResponse]:
        project = await self.get_project(project_id)
        await self._validate_model_policy_key_scope(project=project, key_id=key_id)
        where: Dict[str, Any] = {"project_id": project_id, "key_id": key_id}
        if enabled is not None:
            where["enabled"] = enabled
        if endpoint_type is not None:
            where["endpoint_type"] = endpoint_type
        if model_bucket is not None:
            where["model_bucket"] = model_bucket
        rows = await self.db.cavadalabs_projectmodelpolicytable.find_many(
            where=where,
            order=[
                {"endpoint_type": "asc"},
                {"model_bucket": "asc"},
                {"priority": "asc"},
            ],
        )
        return [
            _parse_response(row, CavadaLabsProjectModelPolicyResponse) for row in rows
        ]

    async def update_project_model_policy(
        self,
        policy_id: str,
        data: CavadaLabsProjectModelPolicyUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectModelPolicyResponse:
        before_row = await self.db.cavadalabs_projectmodelpolicytable.find_unique(
            where={"policy_id": policy_id}
        )
        if before_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Model policy '{policy_id}' not found"},
            )
        before = _parse_response(before_row, CavadaLabsProjectModelPolicyResponse)
        project = await self.get_project(before.project_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        next_key_id = update_data.get("key_id", before.key_id)
        await self._validate_model_policy_key_scope(
            project=project,
            key_id=next_key_id,
        )
        next_model_alias = update_data.get("model_alias", before.model_alias)
        self._ensure_model_allowed(project, next_model_alias)
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        try:
            row = await self.db.cavadalabs_projectmodelpolicytable.update(
                where={"policy_id": policy_id},
                data=update_data,
            )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "A model policy already uses this Project endpoint, bucket, and priority"
                    },
                )
            raise
        response = _parse_response(row, CavadaLabsProjectModelPolicyResponse)
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="model_policy",
            resource_id=response.policy_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def _validate_model_policy_key_scope(
        self,
        *,
        project: CavadaLabsProjectResponse,
        key_id: Optional[str],
    ) -> None:
        if key_id is None:
            return
        row = await self.db.litellm_verificationtoken.find_unique(
            where={"token": key_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Server API key '{key_id}' not found"},
            )
        company_id, project_id = _extract_cavadalabs_key_context(
            _metadata_to_dict(_row_value(row, "metadata"))
        )
        if project_id is None:
            project_from_team = await self._project_for_key_compatibility_team(row)
            if project_from_team is not None:
                project_id = project_from_team.project_id
                company_id = project_from_team.company_id
        if project_id != project.project_id or company_id != project.company_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "Model policy key_id must belong to the same Company and Project"
                },
            )

    async def _project_for_key_compatibility_team(
        self, key_row: Any
    ) -> Optional[CavadaLabsProjectResponse]:
        team_id = _optional_str(_row_value(key_row, "team_id"))
        if team_id is None:
            return None
        row = await self.db.cavadalabs_projecttable.find_unique(
            where={"litellm_team_id": team_id}
        )
        if row is None:
            return None
        return _parse_response(row, CavadaLabsProjectResponse)


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)
