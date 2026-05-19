from __future__ import annotations

from typing import Any, Optional, Sequence

from fastapi import HTTPException, status

from litellm.proxy.cavadalabs.chatbot_schema import get_required_response
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGuardrailPolicyResponse,
    CavadaLabsProjectModelPolicyResponse,
    CavadaLabsRAGCollectionResponse,
)


async def validate_chatbot_project_references(
    db: Any,
    *,
    company_id: str,
    project_id: str,
    chatbot_id: Optional[str] = None,
    model_policy_id: Optional[str] = None,
    expected_policy_endpoint_type: Optional[str] = None,
    expected_policy_model_bucket: Optional[str] = None,
    assigned_rag_collection_ids: Optional[Sequence[str]] = None,
    assigned_guardrail_policy: Optional[str] = None,
) -> None:
    if model_policy_id:
        await _validate_model_policy(
            db,
            company_id=company_id,
            project_id=project_id,
            policy_id=model_policy_id,
            expected_endpoint_type=expected_policy_endpoint_type,
            expected_model_bucket=expected_policy_model_bucket,
        )

    for collection_id in assigned_rag_collection_ids or []:
        await _validate_rag_collection(
            db,
            company_id=company_id,
            project_id=project_id,
            collection_id=collection_id,
        )

    if assigned_guardrail_policy:
        await _validate_guardrail_policy(
            db,
            company_id=company_id,
            project_id=project_id,
            chatbot_id=chatbot_id,
            policy_id=assigned_guardrail_policy,
        )


async def _validate_model_policy(
    db: Any,
    *,
    company_id: str,
    project_id: str,
    policy_id: str,
    expected_endpoint_type: Optional[str],
    expected_model_bucket: Optional[str],
) -> None:
    policy = await get_required_response(
        db,
        delegate_name="cavadalabs_projectmodelpolicytable",
        where={"policy_id": policy_id},
        response_model=CavadaLabsProjectModelPolicyResponse,
        resource_name="Project model policy",
        resource_id=policy_id,
    )
    _require_same_project(
        resource_name="Project model policy",
        resource_id=policy_id,
        resource_company_id=policy.company_id,
        resource_project_id=policy.project_id,
        company_id=company_id,
        project_id=project_id,
    )
    if (
        expected_endpoint_type is not None
        and policy.endpoint_type != expected_endpoint_type
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Project model policy does not match the selected endpoint",
                "policy_id": policy_id,
                "endpoint_type": expected_endpoint_type,
            },
        )
    if (
        expected_model_bucket is not None
        and policy.model_bucket != expected_model_bucket
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Project model policy does not match the selected model bucket",
                "policy_id": policy_id,
                "model_bucket": expected_model_bucket,
            },
        )


async def _validate_rag_collection(
    db: Any,
    *,
    company_id: str,
    project_id: str,
    collection_id: str,
) -> None:
    collection = await get_required_response(
        db,
        delegate_name="cavadalabs_ragcollectiontable",
        where={"collection_id": collection_id},
        response_model=CavadaLabsRAGCollectionResponse,
        resource_name="RAG collection",
        resource_id=collection_id,
    )
    _require_same_company(
        resource_name="RAG collection",
        resource_id=collection_id,
        resource_company_id=collection.company_id,
        company_id=company_id,
    )
    if collection.project_id is not None and collection.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "RAG collection does not belong to this project",
                "collection_id": collection_id,
                "project_id": project_id,
            },
        )


async def _validate_guardrail_policy(
    db: Any,
    *,
    company_id: str,
    project_id: str,
    chatbot_id: Optional[str],
    policy_id: str,
) -> None:
    guardrail = await get_required_response(
        db,
        delegate_name="cavadalabs_guardrailpolicytable",
        where={"policy_id": policy_id},
        response_model=CavadaLabsGuardrailPolicyResponse,
        resource_name="Guardrail policy",
        resource_id=policy_id,
    )
    _require_same_company(
        resource_name="Guardrail policy",
        resource_id=policy_id,
        resource_company_id=guardrail.company_id,
        company_id=company_id,
    )
    if guardrail.project_id is not None and guardrail.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Guardrail policy does not belong to this project",
                "policy_id": policy_id,
                "project_id": project_id,
            },
        )
    if guardrail.chatbot_id is not None and guardrail.chatbot_id != chatbot_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Guardrail policy is scoped to a different chatbot",
                "policy_id": policy_id,
                "chatbot_id": chatbot_id,
            },
        )


def _require_same_company(
    *,
    resource_name: str,
    resource_id: str,
    resource_company_id: str,
    company_id: str,
) -> None:
    if resource_company_id == company_id:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": f"{resource_name} does not belong to this company",
            "resource_id": resource_id,
            "company_id": company_id,
        },
    )


def _require_same_project(
    *,
    resource_name: str,
    resource_id: str,
    resource_company_id: str,
    resource_project_id: str,
    company_id: str,
    project_id: str,
) -> None:
    _require_same_company(
        resource_name=resource_name,
        resource_id=resource_id,
        resource_company_id=resource_company_id,
        company_id=company_id,
    )
    if resource_project_id == project_id:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": f"{resource_name} does not belong to this project",
            "resource_id": resource_id,
            "project_id": project_id,
        },
    )
