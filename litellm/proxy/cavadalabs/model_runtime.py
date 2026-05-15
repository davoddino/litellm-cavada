from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.proxy.cavadalabs.dispatcher_shared import _now_utc, _parse_response
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPUResponse,
    CavadaLabsGPUStatus,
    CavadaLabsLoadedModelResponse,
    CavadaLabsModelLoadRequestResponse,
    CavadaLabsModelRuntimeStatus,
    CavadaLabsNodeResponse,
    CavadaLabsNodeStatus,
    CavadaLabsProjectModelPolicyResponse,
)

_CAVADALABS_PROVIDER = "cavadalabs"
_DEFAULT_OPENAI_COMPAT_PROVIDER = "openai"

_API_BASE_KEYS = (
    "api_base",
    "base_url",
    "openai_api_base",
    "openai_base_url",
    "litellm_api_base",
    "runtime_api_base",
)
_API_BASE_ENV_KEYS = (
    "api_base_env_var",
    "openai_api_base_env_var",
    "runtime_api_base_env_var",
)
_API_KEY_KEYS = (
    "api_key",
    "openai_api_key",
    "litellm_api_key",
    "runtime_api_key",
)
_API_KEY_ENV_KEYS = (
    "api_key_env_var",
    "openai_api_key_env_var",
    "runtime_api_key_env_var",
)
_ROUTE_MODEL_KEYS = (
    "litellm_model",
    "route_model",
    "openai_model",
    "served_model_name",
    "served_model",
    "model_name",
)
_CUSTOM_PROVIDER_KEYS = (
    "custom_llm_provider",
    "litellm_provider",
    "route_provider",
)
_REQUEST_TIMEOUT_KEYS = ("request_timeout", "timeout")
_DEPLOYMENT_KEYS = (
    "deployment_id",
    "deployment_name",
    "runtime_id",
    "loaded_model_id",
)
_PASSTHROUGH_LITELLM_KEYS = {
    "api_version",
    "organization",
    "extra_headers",
    "timeout",
    "request_timeout",
    "max_retries",
}


@dataclass(frozen=True)
class CavadaLabsHostedModelRuntime:
    loaded_model: CavadaLabsLoadedModelResponse
    node: CavadaLabsNodeResponse
    gpu: Optional[CavadaLabsGPUResponse]
    route_model: str
    custom_llm_provider: str
    api_base: str
    api_key: Optional[str]
    request_timeout: Optional[float]
    litellm_params: Dict[str, Any]

    def public_metadata(self) -> Dict[str, Any]:
        return {
            "node_id": self.node.node_id,
            "gpu_id": self.gpu.gpu_id if self.gpu is not None else None,
            "loaded_model_id": self.loaded_model.loaded_model_id,
            "model_load_request_id": self.loaded_model.load_request_id,
            "route_model": self.route_model,
            "custom_llm_provider": self.custom_llm_provider,
            "api_base": self.api_base,
            "api_key_configured": self.api_key is not None,
            "context_window": self.loaded_model.context_window,
            "capabilities": self.loaded_model.capabilities,
        }


class CavadaLabsHostedModelRuntimeService:
    def __init__(self, prisma_client: Any):
        self.prisma_client = prisma_client

    @property
    def db(self) -> Any:
        return self.prisma_client.db

    async def enrich_chat_completion_payload(
        self,
        *,
        payload: Dict[str, Any],
        policy: CavadaLabsProjectModelPolicyResponse,
        project_id: str,
    ) -> Optional[CavadaLabsHostedModelRuntime]:
        if not self._should_resolve_hosted_runtime(policy):
            return None

        runtime = await self.resolve_hosted_runtime(
            policy=policy,
            project_id=project_id,
        )
        await self.apply_hosted_runtime_to_payload(
            payload=payload,
            runtime=runtime,
        )
        return runtime

    async def apply_hosted_runtime_to_payload(
        self,
        *,
        payload: Dict[str, Any],
        runtime: CavadaLabsHostedModelRuntime,
    ) -> None:
        payload["model"] = runtime.route_model
        payload["api_base"] = runtime.api_base
        payload["custom_llm_provider"] = runtime.custom_llm_provider
        if runtime.api_key is not None:
            payload["api_key"] = runtime.api_key
        if (
            runtime.request_timeout is not None
            and "request_timeout" not in payload
            and "timeout" not in payload
        ):
            payload["request_timeout"] = runtime.request_timeout
        for key, value in runtime.litellm_params.items():
            payload.setdefault(key, value)

        self._attach_runtime_metadata(payload=payload, runtime=runtime)
        await self._mark_loaded_model_used(runtime.loaded_model.loaded_model_id)

    async def resolve_hosted_runtime(
        self,
        *,
        policy: CavadaLabsProjectModelPolicyResponse,
        project_id: str,
    ) -> CavadaLabsHostedModelRuntime:
        candidates = await self._loaded_model_candidates(policy)
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "No loaded CavadaLabs runtime is available for this model policy",
                    "policy_id": policy.policy_id,
                    "model_alias": policy.model_alias,
                    "deployment_id": policy.deployment_id,
                },
            )

        rejected_reasons: List[str] = []
        for loaded_model in candidates:
            if not self._matches_policy_capabilities(policy, loaded_model):
                rejected_reasons.append("missing_required_capabilities")
                continue

            node = await self._get_usable_node(
                node_id=loaded_model.node_id,
                project_id=project_id,
            )
            if node is None:
                rejected_reasons.append("node_unavailable")
                continue

            gpu = await self._get_usable_gpu(loaded_model.gpu_id)
            if loaded_model.gpu_id is not None and gpu is None:
                rejected_reasons.append("gpu_unavailable")
                continue

            runtime = self._runtime_from_metadata(
                policy=policy,
                loaded_model=loaded_model,
                node=node,
                gpu=gpu,
            )
            if runtime is None:
                rejected_reasons.append("missing_runtime_endpoint")
                continue
            return runtime

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Loaded CavadaLabs runtime candidates are not usable",
                "policy_id": policy.policy_id,
                "model_alias": policy.model_alias,
                "deployment_id": policy.deployment_id,
                "reasons": sorted(set(rejected_reasons)),
            },
        )

    @staticmethod
    def _should_resolve_hosted_runtime(
        policy: CavadaLabsProjectModelPolicyResponse,
    ) -> bool:
        return CavadaLabsHostedModelRuntimeService.is_hosted_policy(policy)

    @staticmethod
    def is_hosted_policy(policy: CavadaLabsProjectModelPolicyResponse) -> bool:
        return (
            policy.provider.strip().lower() == _CAVADALABS_PROVIDER
            and policy.prefer_loaded_model is True
        )

    async def ensure_model_load_request_if_loadable(
        self,
        *,
        policy: CavadaLabsProjectModelPolicyResponse,
        company_id: str,
        project_id: str,
        reason_code: str,
    ) -> Optional[CavadaLabsModelLoadRequestResponse]:
        if not self.is_hosted_policy(policy):
            return None
        if policy.metadata.get("auto_enqueue_load_request") is False:
            return None
        if not await self._has_load_capacity(policy=policy, project_id=project_id):
            return None

        existing_row = await self.db.cavadalabs_modelloadrequesttable.find_first(
            where={
                "project_id": project_id,
                "model_alias": policy.model_alias,
                "provider": policy.provider,
                "status": {
                    "in": [
                        CavadaLabsModelRuntimeStatus.QUEUED.value,
                        CavadaLabsModelRuntimeStatus.LOCKING.value,
                        CavadaLabsModelRuntimeStatus.LOADING.value,
                    ]
                },
            },
            order={"created_at": "desc"},
        )
        if existing_row is not None:
            return _parse_response(existing_row, CavadaLabsModelLoadRequestResponse)

        ttl_seconds = _int_metadata_value(
            policy.metadata,
            "model_load_request_ttl_seconds",
            "load_request_ttl_seconds",
        )
        expires_at = (
            _now_utc() + timedelta(seconds=ttl_seconds)
            if ttl_seconds is not None and ttl_seconds > 0
            else None
        )
        row = await self.db.cavadalabs_modelloadrequesttable.create(
            data={
                "company_id": company_id,
                "project_id": project_id,
                "model_alias": policy.model_alias,
                "provider": policy.provider,
                "status": CavadaLabsModelRuntimeStatus.QUEUED.value,
                "priority": policy.priority,
                "requested_by": "cavadalabs-runtime",
                "expires_at": expires_at,
                "metadata": {
                    "source": "chatbot_runtime",
                    "policy_id": policy.policy_id,
                    "deployment_id": policy.deployment_id,
                    "reason_code": reason_code,
                    "auto_enqueued": True,
                },
            }
        )
        return _parse_response(row, CavadaLabsModelLoadRequestResponse)

    async def _has_load_capacity(
        self,
        *,
        policy: CavadaLabsProjectModelPolicyResponse,
        project_id: str,
    ) -> bool:
        nodes = await self._loadable_nodes(policy=policy, project_id=project_id)
        if not nodes:
            return False
        node_ids = [node.node_id for node in nodes]
        gpus = await self._loadable_gpus(policy=policy, node_ids=node_ids)
        if not gpus:
            return False
        locked_gpu_ids = await self._active_lock_gpu_ids([gpu.gpu_id for gpu in gpus])
        for gpu in gpus:
            if gpu.gpu_id in locked_gpu_ids:
                continue
            if gpu.loaded_model_ids:
                continue
            return True
        return False

    async def _loadable_nodes(
        self,
        *,
        policy: CavadaLabsProjectModelPolicyResponse,
        project_id: str,
    ) -> List[CavadaLabsNodeResponse]:
        rows = await self.db.cavadalabs_nodetable.find_many(
            where={
                "status": {
                    "in": [
                        CavadaLabsNodeStatus.ONLINE.value,
                        CavadaLabsNodeStatus.DEGRADED.value,
                    ]
                }
            },
            order={"last_heartbeat_at": "desc"},
        )
        required_pool = _string_value(
            policy.metadata,
            ("required_pool", "pool"),
        )
        nodes = []
        for row in rows:
            node = _parse_response(row, CavadaLabsNodeResponse)
            if node.allowed_project_ids and project_id not in node.allowed_project_ids:
                continue
            if required_pool is not None and required_pool not in node.pools:
                continue
            nodes.append(node)
        return nodes

    async def _loadable_gpus(
        self,
        *,
        policy: CavadaLabsProjectModelPolicyResponse,
        node_ids: List[str],
    ) -> List[CavadaLabsGPUResponse]:
        if not node_ids:
            return []
        rows = await self.db.cavadalabs_gputable.find_many(
            where={
                "node_id": {"in": node_ids},
                "status": {
                    "in": [
                        CavadaLabsGPUStatus.AVAILABLE.value,
                        CavadaLabsGPUStatus.LOADED.value,
                    ]
                },
            },
            order={"vram_total_mb": "asc"},
        )
        required_vram_mb = _int_metadata_value(
            policy.metadata,
            "required_vram_mb",
            "min_vram_mb",
        )
        required_vendor = _string_value(policy.metadata, ("required_gpu_vendor",))
        required_model = _string_value(policy.metadata, ("required_gpu_model",))
        gpus = []
        for row in rows:
            gpu = _parse_response(row, CavadaLabsGPUResponse)
            if required_vram_mb is not None and gpu.vram_total_mb < required_vram_mb:
                continue
            if (
                required_vendor is not None
                and gpu.vendor.lower() != required_vendor.lower()
            ):
                continue
            if (
                required_model is not None
                and required_model.lower() not in gpu.model.lower()
            ):
                continue
            gpus.append(gpu)
        return gpus

    async def _active_lock_gpu_ids(self, gpu_ids: List[str]) -> set[str]:
        if not gpu_ids:
            return set()
        rows = await self.db.cavadalabs_gpulocktable.find_many(
            where={
                "gpu_id": {"in": gpu_ids},
                "status": "active",
                "expires_at": {"gt": _now_utc()},
            }
        )
        result = set()
        for row in rows:
            gpu_id = (
                row.get("gpu_id")
                if isinstance(row, dict)
                else getattr(row, "gpu_id", None)
            )
            if isinstance(gpu_id, str):
                result.add(gpu_id)
        return result

    async def _loaded_model_candidates(
        self,
        policy: CavadaLabsProjectModelPolicyResponse,
    ) -> List[CavadaLabsLoadedModelResponse]:
        rows: List[Any] = []
        if policy.deployment_id:
            exact_row = await self.db.cavadalabs_loadedmodeltable.find_unique(
                where={"loaded_model_id": policy.deployment_id}
            )
            if exact_row is not None:
                rows.append(exact_row)

        matched_rows = await self.db.cavadalabs_loadedmodeltable.find_many(
            where={
                "model_alias": policy.model_alias,
                "provider": policy.provider,
                "status": CavadaLabsModelRuntimeStatus.LOADED.value,
            },
            order={"last_used_at": "asc"},
            take=100,
        )
        rows.extend(matched_rows)

        candidates: List[CavadaLabsLoadedModelResponse] = []
        seen_loaded_model_ids = set()
        for row in rows:
            loaded_model = _parse_response(row, CavadaLabsLoadedModelResponse)
            if loaded_model.loaded_model_id in seen_loaded_model_ids:
                continue
            seen_loaded_model_ids.add(loaded_model.loaded_model_id)
            if (
                loaded_model.model_alias != policy.model_alias
                or loaded_model.provider != policy.provider
            ):
                continue
            if loaded_model.status != CavadaLabsModelRuntimeStatus.LOADED.value:
                continue
            if not self._matches_policy_deployment(policy, loaded_model):
                continue
            candidates.append(loaded_model)
        return candidates

    @staticmethod
    def _matches_policy_deployment(
        policy: CavadaLabsProjectModelPolicyResponse,
        loaded_model: CavadaLabsLoadedModelResponse,
    ) -> bool:
        if not policy.deployment_id:
            return True
        deployment_id = policy.deployment_id
        if deployment_id in {
            loaded_model.loaded_model_id,
            loaded_model.load_request_id,
        }:
            return True
        return _string_value(loaded_model.metadata, _DEPLOYMENT_KEYS) == deployment_id

    @staticmethod
    def _matches_policy_capabilities(
        policy: CavadaLabsProjectModelPolicyResponse,
        loaded_model: CavadaLabsLoadedModelResponse,
    ) -> bool:
        if not policy.required_capabilities:
            return True
        loaded_capabilities = {value.lower() for value in loaded_model.capabilities}
        return all(
            capability.lower() in loaded_capabilities
            for capability in policy.required_capabilities
        )

    async def _get_usable_node(
        self,
        *,
        node_id: str,
        project_id: str,
    ) -> Optional[CavadaLabsNodeResponse]:
        row = await self.db.cavadalabs_nodetable.find_unique(where={"node_id": node_id})
        if row is None:
            return None
        node = _parse_response(row, CavadaLabsNodeResponse)
        if node.status not in {
            CavadaLabsNodeStatus.ONLINE.value,
            CavadaLabsNodeStatus.DEGRADED.value,
        }:
            return None
        if node.allowed_project_ids and project_id not in node.allowed_project_ids:
            return None
        return node

    async def _get_usable_gpu(
        self,
        gpu_id: Optional[str],
    ) -> Optional[CavadaLabsGPUResponse]:
        if gpu_id is None:
            return None
        row = await self.db.cavadalabs_gputable.find_unique(where={"gpu_id": gpu_id})
        if row is None:
            return None
        gpu = _parse_response(row, CavadaLabsGPUResponse)
        if gpu.status in {
            CavadaLabsGPUStatus.UNHEALTHY.value,
            CavadaLabsGPUStatus.OFFLINE.value,
            CavadaLabsGPUStatus.DISABLED.value,
        }:
            return None
        return gpu

    def _runtime_from_metadata(
        self,
        *,
        policy: CavadaLabsProjectModelPolicyResponse,
        loaded_model: CavadaLabsLoadedModelResponse,
        node: CavadaLabsNodeResponse,
        gpu: Optional[CavadaLabsGPUResponse],
    ) -> Optional[CavadaLabsHostedModelRuntime]:
        metadata_chain = [loaded_model.metadata, node.metadata, policy.metadata]
        api_base = _url_metadata_value(
            metadata_chain, _API_BASE_KEYS, _API_BASE_ENV_KEYS
        )
        if api_base is None:
            return None

        custom_llm_provider = (
            _string_value_from_chain(metadata_chain, _CUSTOM_PROVIDER_KEYS)
            or _DEFAULT_OPENAI_COMPAT_PROVIDER
        )
        route_model = self._route_model(
            metadata_chain=metadata_chain,
            loaded_model=loaded_model,
            custom_llm_provider=custom_llm_provider,
        )
        request_timeout = _float_value_from_chain(metadata_chain, _REQUEST_TIMEOUT_KEYS)
        api_key = _secret_metadata_value(
            metadata_chain, _API_KEY_KEYS, _API_KEY_ENV_KEYS
        )
        litellm_params = _dict_value_from_chain(metadata_chain, "litellm_params")

        return CavadaLabsHostedModelRuntime(
            loaded_model=loaded_model,
            node=node,
            gpu=gpu,
            route_model=route_model,
            custom_llm_provider=custom_llm_provider,
            api_base=api_base,
            api_key=api_key,
            request_timeout=request_timeout,
            litellm_params={
                key: value
                for key, value in litellm_params.items()
                if key in _PASSTHROUGH_LITELLM_KEYS
            },
        )

    @staticmethod
    def _route_model(
        *,
        metadata_chain: Iterable[Dict[str, Any]],
        loaded_model: CavadaLabsLoadedModelResponse,
        custom_llm_provider: str,
    ) -> str:
        configured_model = _string_value_from_chain(metadata_chain, _ROUTE_MODEL_KEYS)
        if configured_model is not None:
            if "/" in configured_model:
                return configured_model
            return f"{custom_llm_provider}/{configured_model}"

        served_model = loaded_model.model_alias
        prefix = f"{_CAVADALABS_PROVIDER}/"
        if served_model.startswith(prefix):
            served_model = served_model[len(prefix) :]
        if "/" in served_model:
            return served_model
        return f"{custom_llm_provider}/{served_model}"

    @staticmethod
    def _attach_runtime_metadata(
        *,
        payload: Dict[str, Any],
        runtime: CavadaLabsHostedModelRuntime,
    ) -> None:
        metadata = payload.setdefault("metadata", {})
        cavadalabs_metadata = metadata.setdefault("cavadalabs", {})
        if not isinstance(cavadalabs_metadata, dict):
            cavadalabs_metadata = {}
            metadata["cavadalabs"] = cavadalabs_metadata

        runtime_metadata = runtime.public_metadata()
        metadata["cavadalabs_node_id"] = runtime.node.node_id
        metadata["cavadalabs_loaded_model_id"] = runtime.loaded_model.loaded_model_id
        if runtime.gpu is not None:
            metadata["cavadalabs_gpu_id"] = runtime.gpu.gpu_id
        if runtime.loaded_model.load_request_id is not None:
            metadata["cavadalabs_model_load_request_id"] = (
                runtime.loaded_model.load_request_id
            )
        cavadalabs_metadata.update(
            {
                "node_id": runtime.node.node_id,
                "gpu_id": runtime.gpu.gpu_id if runtime.gpu is not None else None,
                "loaded_model_id": runtime.loaded_model.loaded_model_id,
                "model_load_request_id": runtime.loaded_model.load_request_id,
                "runtime": runtime_metadata,
            }
        )

    async def _mark_loaded_model_used(self, loaded_model_id: str) -> None:
        try:
            await self.db.cavadalabs_loadedmodeltable.update(
                where={"loaded_model_id": loaded_model_id},
                data={"last_used_at": _now_utc()},
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Failed to mark CavadaLabs loaded model '%s' as used: %s",
                loaded_model_id,
                exc,
            )


def _string_value(metadata: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _string_value_from_chain(
    metadata_chain: Iterable[Dict[str, Any]],
    keys: Iterable[str],
) -> Optional[str]:
    for metadata in metadata_chain:
        value = _string_value(metadata, keys)
        if value is not None:
            return value
    return None


def _env_value(metadata: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    env_var_name = _string_value(metadata, keys)
    if env_var_name is None:
        return None
    env_value = os.getenv(env_var_name)
    if env_value is None or not env_value.strip():
        return None
    return env_value.strip()


def _secret_metadata_value(
    metadata_chain: Iterable[Dict[str, Any]],
    keys: Iterable[str],
    env_keys: Iterable[str],
) -> Optional[str]:
    for metadata in metadata_chain:
        direct_value = _string_value(metadata, keys)
        if direct_value is not None:
            return direct_value
        env_value = _env_value(metadata, env_keys)
        if env_value is not None:
            return env_value
    return None


def _url_metadata_value(
    metadata_chain: Iterable[Dict[str, Any]],
    keys: Iterable[str],
    env_keys: Iterable[str],
) -> Optional[str]:
    value = _secret_metadata_value(metadata_chain, keys, env_keys)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value.rstrip("/")


def _float_value_from_chain(
    metadata_chain: Iterable[Dict[str, Any]],
    keys: Iterable[str],
) -> Optional[float]:
    for metadata in metadata_chain:
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str) and value.strip():
                try:
                    return float(value)
                except ValueError:
                    continue
    return None


def _int_metadata_value(
    metadata: Dict[str, Any],
    *keys: str,
) -> Optional[int]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _dict_value_from_chain(
    metadata_chain: Iterable[Dict[str, Any]],
    key: str,
) -> Dict[str, Any]:
    for metadata in metadata_chain:
        value = metadata.get(key)
        if isinstance(value, dict):
            return value
    return {}
