from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class CavadaLabsModelPolicyCandidate:
    policy_id: str
    company_id: str
    project_id: str
    key_id: Optional[str]
    model_alias: str
    provider: str
    priority: int
    enabled: bool
    endpoint_type: str = "chat_completion"
    model_bucket: str = "default"
    fallback_enabled: bool = True


@dataclass(frozen=True)
class CavadaLabsModelPolicyResolution:
    model: str
    policy: CavadaLabsModelPolicyCandidate
    fallback_models: tuple[str, ...]
    model_bucket: str
    endpoint_type: str
    skipped_policies: tuple[dict, ...]


class CavadaLabsModelPolicyResolutionError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        project_id: str,
        skipped_policies: Sequence[dict],
        available_models: Iterable[str],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.project_id = project_id
        self.skipped_policies = tuple(skipped_policies)
        self.available_models = tuple(sorted(set(available_models)))

    def to_detail(self) -> dict:
        return {
            "error": self.message,
            "code": self.code,
            "project_id": self.project_id,
            "skipped_policies": list(self.skipped_policies),
            "available_models": list(self.available_models),
        }


class CavadaLabsModelPolicySchemaError(Exception):
    def __init__(self, *, missing_schema: Sequence[str], message: str) -> None:
        super().__init__(message)
        self.missing_schema = tuple(missing_schema)
        self.message = message

    def to_detail(self) -> dict:
        return {
            "error": self.message,
            "schema_status": "missing_schema",
            "missing_schema": list(self.missing_schema),
            "migration_command": "uv run prisma migrate deploy",
        }


def resolve_project_model_priority(
    *,
    project_id: str,
    policies: Sequence[CavadaLabsModelPolicyCandidate],
    available_model_names: Iterable[str],
    endpoint_type: str = "chat_completion",
    model_bucket: str = "default",
) -> CavadaLabsModelPolicyResolution:
    available_models = {model for model in available_model_names if model}
    if not available_models:
        raise CavadaLabsModelPolicyResolutionError(
            code="no_configured_models",
            message=(
                "CavadaLabs project model fallback requires at least one "
                "configured LiteLLM model"
            ),
            project_id=project_id,
            skipped_policies=[],
            available_models=available_models,
        )

    ordered_policies = sorted(
        policies,
        key=lambda policy: (policy.priority, policy.model_alias, policy.policy_id),
    )
    skipped_policies: list[dict] = []
    for index, policy in enumerate(ordered_policies):
        reason = _policy_skip_reason(
            policy=policy,
            project_id=project_id,
            endpoint_type=endpoint_type,
            model_bucket=model_bucket,
            available_models=available_models,
        )
        if reason is not None:
            skipped_policies.append(
                {
                    "policy_id": policy.policy_id,
                    "project_id": policy.project_id,
                    "key_id": policy.key_id,
                    "endpoint_type": policy.endpoint_type,
                    "model_bucket": policy.model_bucket,
                    "model_alias": policy.model_alias,
                    "priority": policy.priority,
                    "reason": reason,
                }
            )
            continue
        return CavadaLabsModelPolicyResolution(
            model=policy.model_alias,
            policy=policy,
            fallback_models=_fallback_models_after_selection(
                policies=ordered_policies,
                selected_index=index,
                project_id=project_id,
                endpoint_type=endpoint_type,
                model_bucket=model_bucket,
                available_models=available_models,
            ),
            endpoint_type=endpoint_type,
            model_bucket=model_bucket,
            skipped_policies=tuple(skipped_policies),
        )

    code = "no_enabled_model_policies" if not ordered_policies else "no_available_model"
    message = (
        "Project has no enabled CavadaLabs model policies"
        if not ordered_policies
        else "No CavadaLabs project model policy is available on this proxy"
    )
    raise CavadaLabsModelPolicyResolutionError(
        code=code,
        message=message,
        project_id=project_id,
        skipped_policies=skipped_policies,
        available_models=available_models,
    )


def _policy_skip_reason(
    *,
    policy: CavadaLabsModelPolicyCandidate,
    project_id: str,
    endpoint_type: str,
    model_bucket: str,
    available_models: set[str],
) -> Optional[str]:
    if policy.project_id != project_id:
        return "wrong_project"
    if policy.endpoint_type != endpoint_type:
        return "wrong_endpoint"
    if policy.model_bucket != model_bucket:
        return "wrong_bucket"
    if policy.enabled is not True:
        return "disabled"
    if policy.model_alias not in available_models:
        return "model_not_configured"
    return None


def _fallback_models_after_selection(
    *,
    policies: Sequence[CavadaLabsModelPolicyCandidate],
    selected_index: int,
    project_id: str,
    endpoint_type: str,
    model_bucket: str,
    available_models: set[str],
) -> tuple[str, ...]:
    fallback_models: list[str] = []
    seen = {policies[selected_index].model_alias}
    for policy in policies[selected_index + 1 :]:
        if not policy.fallback_enabled:
            continue
        if (
            _policy_skip_reason(
                policy=policy,
                project_id=project_id,
                endpoint_type=endpoint_type,
                model_bucket=model_bucket,
                available_models=available_models,
            )
            is not None
        ):
            continue
        if policy.model_alias in seen:
            continue
        fallback_models.append(policy.model_alias)
        seen.add(policy.model_alias)
    return tuple(fallback_models)
