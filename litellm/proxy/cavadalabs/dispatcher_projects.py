from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.cavadalabs.compatibility import (
    ensure_company_compat_organization,
    ensure_project_compat_team,
)
from litellm.proxy.cavadalabs.dispatcher_companies import CavadaLabsCompanyOperations
from litellm.proxy.cavadalabs.dispatcher_shared import (
    _actor_user_id,
    _is_unique_violation,
    _parse_response,
    _row_to_dict,
)
from litellm.proxy.cavadalabs.prisma_json import serialize_prisma_json_fields
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsProjectCreateRequest,
    CavadaLabsProjectMemberCreateRequest,
    CavadaLabsProjectMemberDeleteResponse,
    CavadaLabsProjectMemberListResponse,
    CavadaLabsProjectMemberResponse,
    CavadaLabsProjectMemberUpdateRequest,
    CavadaLabsProjectResponse,
    CavadaLabsProjectStatus,
    CavadaLabsProjectUpdateRequest,
)

_CAVADALABS_PROJECT_ROLE_TO_TEAM_ROLE = {
    "project_admin": "admin",
    "operator": "user",
    "viewer": "user",
}


def _row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, dict):
        return row.get(field_name)
    return getattr(row, field_name, None)


def _member_row_to_response(
    row: Any, *, project: CavadaLabsProjectResponse
) -> CavadaLabsProjectMemberResponse:
    data = _row_to_dict(row, CavadaLabsProjectMemberResponse)
    data["company_id"] = project.company_id
    return CavadaLabsProjectMemberResponse.model_validate(data)


class CavadaLabsProjectOperations(CavadaLabsCompanyOperations):
    async def _ensure_creator_project_membership(
        self,
        *,
        project_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> None:
        actor_user_id = _actor_user_id(user_api_key_dict)
        if actor_user_id is None:
            return
        try:
            await self.db.cavadalabs_projectmembertable.upsert(
                where={
                    "project_id_user_id": {
                        "project_id": project_id,
                        "user_id": actor_user_id,
                    }
                },
                data={
                    "create": {
                        "project_id": project_id,
                        "user_id": actor_user_id,
                        "role": "project_admin",
                        "created_by": actor_user_id,
                        "updated_by": actor_user_id,
                    },
                    "update": {
                        "role": "project_admin",
                        "updated_by": actor_user_id,
                    },
                },
            )
        except (AttributeError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": (
                        "CavadaLabs native project membership schema is missing. "
                        "Run prisma migrate deploy before creating Projects."
                    ),
                    "missing_schema": ["cavadalabs_projectmembertable"],
                },
            ) from exc

    async def create_project(
        self,
        data: CavadaLabsProjectCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectResponse:
        company = await self.get_company(data.company_id)
        self._ensure_company_active(company, "create projects")
        litellm_organization_id = await ensure_company_compat_organization(
            self.prisma_client,
            company=company,
            user_api_key_dict=user_api_key_dict,
        )
        company = company.model_copy(
            update={"litellm_organization_id": litellm_organization_id}
        )
        create_data = serialize_prisma_json_fields(
            {
                **data.model_dump(mode="python"),
                "created_by": _actor_user_id(user_api_key_dict),
                "updated_by": _actor_user_id(user_api_key_dict),
            }
        )
        try:
            row = await self.db.cavadalabs_projecttable.create(data=create_data)
        except Exception as exc:
            if _is_unique_violation(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "Project name already exists for this company"},
                )
            raise
        response = _parse_response(row, CavadaLabsProjectResponse)
        litellm_team_id = await ensure_project_compat_team(
            self.prisma_client,
            company=company,
            project=response,
            user_api_key_dict=user_api_key_dict,
        )
        response = response.model_copy(update={"litellm_team_id": litellm_team_id})
        await self._ensure_creator_project_membership(
            project_id=response.project_id,
            user_api_key_dict=user_api_key_dict,
        )
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="created",
            resource_type="project",
            resource_id=response.project_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def get_project(self, project_id: str) -> CavadaLabsProjectResponse:
        row = await self.db.cavadalabs_projecttable.find_unique(
            where={"project_id": project_id}
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"Project '{project_id}' not found"},
            )
        return _parse_response(row, CavadaLabsProjectResponse)

    async def list_projects(
        self,
        company_id: Optional[str] = None,
        project_ids: Optional[List[str]] = None,
        status_filter: Optional[CavadaLabsProjectStatus] = None,
        take: int = 100,
        skip: int = 0,
    ) -> List[CavadaLabsProjectResponse]:
        where: Dict[str, Any] = {}
        if company_id is not None:
            where["company_id"] = company_id
        if project_ids is not None:
            if not project_ids:
                return []
            where["project_id"] = {"in": project_ids}
        if status_filter is not None:
            where["status"] = status_filter.value
        rows = await self.db.cavadalabs_projecttable.find_many(
            where=where or None,
            take=take,
            skip=skip,
            order={"created_at": "desc"},
        )
        return [_parse_response(row, CavadaLabsProjectResponse) for row in rows]

    async def update_project(
        self,
        project_id: str,
        data: CavadaLabsProjectUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectResponse:
        before = await self.get_project(project_id)
        update_data = data.model_dump(mode="python", exclude_unset=True)
        if not update_data:
            return before
        update_data["updated_by"] = _actor_user_id(user_api_key_dict)
        update_data = serialize_prisma_json_fields(update_data)
        row = await self.db.cavadalabs_projecttable.update(
            where={"project_id": project_id},
            data=update_data,
        )
        response = _parse_response(row, CavadaLabsProjectResponse)
        company = await self.get_company(response.company_id)
        litellm_organization_id = await ensure_company_compat_organization(
            self.prisma_client,
            company=company,
            user_api_key_dict=user_api_key_dict,
        )
        company = company.model_copy(
            update={"litellm_organization_id": litellm_organization_id}
        )
        litellm_team_id = await ensure_project_compat_team(
            self.prisma_client,
            company=company,
            project=response,
            user_api_key_dict=user_api_key_dict,
        )
        response = response.model_copy(update={"litellm_team_id": litellm_team_id})
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated",
            resource_type="project",
            resource_id=response.project_id,
            company_id=response.company_id,
            project_id=response.project_id,
            before_value=before.model_dump(mode="json"),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def _get_project_member(self, *, project_id: str, user_id: str) -> Any:
        try:
            return await self.db.cavadalabs_projectmembertable.find_unique(
                where={
                    "project_id_user_id": {
                        "project_id": project_id,
                        "user_id": user_id,
                    }
                }
            )
        except (AttributeError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": (
                        "CavadaLabs native project membership schema is missing. "
                        "Run prisma migrate deploy before managing Project members."
                    ),
                    "missing_schema": ["cavadalabs_projectmembertable"],
                    "migration_command": "uv run prisma migrate deploy",
                },
            ) from exc

    async def list_project_members(
        self, project_id: str
    ) -> CavadaLabsProjectMemberListResponse:
        project = await self.get_project(project_id)
        try:
            rows = await self.db.cavadalabs_projectmembertable.find_many(
                where={"project_id": project_id},
                order={"created_at": "desc"},
            )
        except (AttributeError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": (
                        "CavadaLabs native project membership schema is missing. "
                        "Run prisma migrate deploy before listing Project members."
                    ),
                    "missing_schema": ["cavadalabs_projectmembertable"],
                    "migration_command": "uv run prisma migrate deploy",
                },
            ) from exc
        members = [_member_row_to_response(row, project=project) for row in rows]
        return CavadaLabsProjectMemberListResponse(
            project_id=project.project_id,
            company_id=project.company_id,
            members=members,
            count=len(members),
        )

    async def _ensure_user_exists(self, user_id: str) -> Any:
        user = await self.db.litellm_usertable.find_unique(where={"user_id": user_id})
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"User '{user_id}' not found"},
            )
        return user

    async def _sync_project_member_to_compat_team(
        self,
        *,
        project: CavadaLabsProjectResponse,
        user_id: str,
        role: str,
    ) -> None:
        if project.litellm_team_id is None:
            return
        team = await self.db.litellm_teamtable.find_unique(
            where={"team_id": project.litellm_team_id}
        )
        if team is None:
            return
        user = await self.db.litellm_usertable.find_unique(where={"user_id": user_id})
        user_email = _row_value(user, "user_email") if user is not None else None
        members = []
        for member in _row_value(team, "members_with_roles") or []:
            if isinstance(member, dict):
                member_dict = dict(member)
            elif callable(getattr(member, "model_dump", None)):
                member_dict = dict(member.model_dump())
            else:
                member_dict = dict(getattr(member, "__dict__", {}))
            if member_dict.get("user_id") != user_id:
                members.append(member_dict)
        next_member: dict[str, Any] = {
            "user_id": user_id,
            "role": _CAVADALABS_PROJECT_ROLE_TO_TEAM_ROLE[role],
        }
        if user_email:
            next_member["user_email"] = user_email
        members.append(next_member)
        await self.db.litellm_teamtable.update(
            where={"team_id": project.litellm_team_id},
            data={"members_with_roles": json.dumps(members)},
        )
        if user is not None:
            teams = list(_row_value(user, "teams") or [])
            if project.litellm_team_id not in teams:
                await self.db.litellm_usertable.update(
                    where={"user_id": user_id},
                    data={"teams": [*teams, project.litellm_team_id]},
                )

    async def _remove_project_member_from_compat_team(
        self,
        *,
        project: CavadaLabsProjectResponse,
        user_id: str,
    ) -> None:
        if project.litellm_team_id is None:
            return
        team = await self.db.litellm_teamtable.find_unique(
            where={"team_id": project.litellm_team_id}
        )
        if team is not None:
            members = []
            for member in _row_value(team, "members_with_roles") or []:
                if isinstance(member, dict):
                    member_dict = dict(member)
                elif callable(getattr(member, "model_dump", None)):
                    member_dict = dict(member.model_dump())
                else:
                    member_dict = dict(getattr(member, "__dict__", {}))
                if member_dict.get("user_id") != user_id:
                    members.append(member_dict)
            await self.db.litellm_teamtable.update(
                where={"team_id": project.litellm_team_id},
                data={"members_with_roles": json.dumps(members)},
            )
        user = await self.db.litellm_usertable.find_unique(where={"user_id": user_id})
        if user is not None:
            teams = [
                team_id
                for team_id in list(_row_value(user, "teams") or [])
                if team_id != project.litellm_team_id
            ]
            await self.db.litellm_usertable.update(
                where={"user_id": user_id},
                data={"teams": teams},
            )
        try:
            await self.db.litellm_teammembership.delete_many(
                where={"team_id": project.litellm_team_id, "user_id": user_id}
            )
        except (AttributeError, TypeError):
            return

    async def upsert_project_member(
        self,
        project_id: str,
        data: CavadaLabsProjectMemberCreateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectMemberResponse:
        project = await self.get_project(project_id)
        await self._ensure_user_exists(data.user_id)
        try:
            row = await self.db.cavadalabs_projectmembertable.upsert(
                where={
                    "project_id_user_id": {
                        "project_id": project_id,
                        "user_id": data.user_id,
                    }
                },
                data={
                    "create": {
                        "project_id": project_id,
                        "user_id": data.user_id,
                        "role": (
                            data.role.value
                            if hasattr(data.role, "value")
                            else data.role
                        ),
                        "created_by": _actor_user_id(user_api_key_dict),
                        "updated_by": _actor_user_id(user_api_key_dict),
                    },
                    "update": {
                        "role": (
                            data.role.value
                            if hasattr(data.role, "value")
                            else data.role
                        ),
                        "updated_by": _actor_user_id(user_api_key_dict),
                    },
                },
            )
        except (AttributeError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": (
                        "CavadaLabs native project membership schema is missing. "
                        "Run prisma migrate deploy before managing Project members."
                    ),
                    "missing_schema": ["cavadalabs_projectmembertable"],
                    "migration_command": "uv run prisma migrate deploy",
                },
            ) from exc
        response = _member_row_to_response(row, project=project)
        await self._sync_project_member_to_compat_team(
            project=project,
            user_id=response.user_id,
            role=(
                response.role.value
                if hasattr(response.role, "value")
                else response.role
            ),
        )
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="upserted_member",
            resource_type="project",
            resource_id=project.project_id,
            company_id=project.company_id,
            project_id=project.project_id,
            before_value=None,
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def update_project_member(
        self,
        project_id: str,
        user_id: str,
        data: CavadaLabsProjectMemberUpdateRequest,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectMemberResponse:
        project = await self.get_project(project_id)
        existing = await self._get_project_member(
            project_id=project_id, user_id=user_id
        )
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"User '{user_id}' is not a member of this Project"},
            )
        row = await self.db.cavadalabs_projectmembertable.update(
            where={
                "project_id_user_id": {"project_id": project_id, "user_id": user_id}
            },
            data={
                "role": data.role.value if hasattr(data.role, "value") else data.role,
                "updated_by": _actor_user_id(user_api_key_dict),
            },
        )
        response = _member_row_to_response(row, project=project)
        await self._sync_project_member_to_compat_team(
            project=project,
            user_id=response.user_id,
            role=(
                response.role.value
                if hasattr(response.role, "value")
                else response.role
            ),
        )
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="updated_member",
            resource_type="project",
            resource_id=project.project_id,
            company_id=project.company_id,
            project_id=project.project_id,
            before_value=_member_row_to_response(existing, project=project).model_dump(
                mode="json"
            ),
            after_value=response.model_dump(mode="json"),
        )
        return response

    async def delete_project_member(
        self,
        project_id: str,
        user_id: str,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> CavadaLabsProjectMemberDeleteResponse:
        project = await self.get_project(project_id)
        existing = await self._get_project_member(
            project_id=project_id, user_id=user_id
        )
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": f"User '{user_id}' is not a member of this Project"},
            )
        await self.db.cavadalabs_projectmembertable.delete_many(
            where={"project_id": project_id, "user_id": user_id}
        )
        await self._remove_project_member_from_compat_team(
            project=project,
            user_id=user_id,
        )
        response = CavadaLabsProjectMemberDeleteResponse(
            project_id=project.project_id,
            company_id=project.company_id,
            user_id=user_id,
            deleted=True,
        )
        await self._audit(
            user_api_key_dict=user_api_key_dict,
            action="deleted_member",
            resource_type="project",
            resource_id=project.project_id,
            company_id=project.company_id,
            project_id=project.project_id,
            before_value=_member_row_to_response(existing, project=project).model_dump(
                mode="json"
            ),
            after_value=response.model_dump(mode="json"),
        )
        return response
