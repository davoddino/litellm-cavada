import base64
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException

from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.cavadalabs.dispatcher import hash_web_token
from litellm.proxy.cavadalabs.nodes import (
    CavadaLabsNodeService,
    canonical_node_signature_payload,
    public_key_fingerprint,
)
from litellm.types.proxy.management_endpoints.cavadalabs_dispatcher import (
    CavadaLabsGPUInventoryItem,
    CavadaLabsGPUInventoryRequest,
    CavadaLabsGPULockCreateRequest,
    CavadaLabsLoadedModelUpsertRequest,
    CavadaLabsModelLoadRequestCreateRequest,
    CavadaLabsNodeCreateRequest,
    CavadaLabsNodeDailyReportRequest,
    CavadaLabsNodeEnrollmentCompleteRequest,
    CavadaLabsNodeEnrollmentCreateRequest,
    CavadaLabsNodeModelLoadWorkRequest,
    CavadaLabsSchedulerRunRequest,
)


def _admin() -> UserAPIKeyAuth:
    return UserAPIKeyAuth(
        api_key="sk-test",
        user_id="admin-user",
        user_role=LitellmUserRoles.PROXY_ADMIN,
    )


def _row(**kwargs):
    defaults = {
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": "admin-user",
        "updated_by": "admin-user",
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def _node_row(**kwargs):
    return _row(
        node_id=kwargs.pop("node_id", "node-1"),
        display_name=kwargs.pop("display_name", "Milan GPU 01"),
        hostname=kwargs.pop("hostname", "gpu-01"),
        location=kwargs.pop("location", "it-mil-1"),
        status=kwargs.pop("status", "pending"),
        public_key=kwargs.pop("public_key", None),
        public_key_fingerprint=kwargs.pop("public_key_fingerprint", None),
        agent_version=kwargs.pop("agent_version", None),
        allowed_project_ids=kwargs.pop("allowed_project_ids", ["project-1"]),
        pools=kwargs.pop("pools", ["default"]),
        default_electricity_cost_per_kwh=kwargs.pop(
            "default_electricity_cost_per_kwh", 0.2
        ),
        fixed_hourly_cost=kwargs.pop("fixed_hourly_cost", 1.0),
        hardware_amortization_hourly_cost=kwargs.pop(
            "hardware_amortization_hourly_cost", 0.5
        ),
        last_heartbeat_at=kwargs.pop("last_heartbeat_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _enrollment_row(**kwargs):
    return _row(
        enrollment_id=kwargs.pop("enrollment_id", "enrollment-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        secret_prefix=kwargs.pop("secret_prefix", "clne-prefix"),
        secret_hash=kwargs.pop("secret_hash", "secret-hash"),
        status=kwargs.pop("status", "active"),
        expires_at=kwargs.pop(
            "expires_at", datetime.now(timezone.utc) + timedelta(minutes=30)
        ),
        used_at=kwargs.pop("used_at", None),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _company_row(**kwargs):
    return _row(
        company_id=kwargs.pop("company_id", "company-1"),
        legal_name=kwargs.pop("legal_name", "ACME Spa"),
        billing_name=kwargs.pop("billing_name", None),
        vat_tax_id=kwargs.pop("vat_tax_id", None),
        billing_address=kwargs.pop("billing_address", {}),
        admin_emails=kwargs.pop("admin_emails", ["admin@acme.test"]),
        plan=kwargs.pop("plan", "production"),
        status=kwargs.pop("status", "active"),
        monthly_budget=kwargs.pop("monthly_budget", 500.0),
        metadata=kwargs.pop("metadata", {}),
        retention_policy=kwargs.pop("retention_policy", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        default_billing_settings=kwargs.pop("default_billing_settings", {}),
        **kwargs,
    )


def _project_row(**kwargs):
    return _row(
        project_id=kwargs.pop("project_id", "project-1"),
        company_id=kwargs.pop("company_id", "company-1"),
        name=kwargs.pop("name", "Support"),
        status=kwargs.pop("status", "production"),
        allowed_models=kwargs.pop("allowed_models", ["cavadalabs/qwen3-32b"]),
        allowed_rag_collections=kwargs.pop("allowed_rag_collections", []),
        default_chatbot_settings=kwargs.pop("default_chatbot_settings", {}),
        default_guardrail_policy=kwargs.pop("default_guardrail_policy", None),
        budget=kwargs.pop("budget", 250.0),
        retention_policy_override=kwargs.pop("retention_policy_override", {}),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _gpu_row(**kwargs):
    return _row(
        gpu_id=kwargs.pop("gpu_id", "gpu-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        vendor=kwargs.pop("vendor", "nvidia"),
        model=kwargs.pop("model", "RTX 6000 Ada"),
        uuid=kwargs.pop("uuid", "GPU-123"),
        vram_total_mb=kwargs.pop("vram_total_mb", 49152),
        status=kwargs.pop("status", "available"),
        loaded_model_ids=kwargs.pop("loaded_model_ids", []),
        metadata=kwargs.pop("metadata", {}),
        **kwargs,
    )


def _daily_report_row(**kwargs):
    return SimpleNamespace(
        report_id=kwargs.pop("report_id", "report-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        report_date=kwargs.pop(
            "report_date", datetime(2026, 5, 14, tzinfo=timezone.utc)
        ),
        samples=kwargs.pop("samples", []),
        total_kwh=kwargs.pop("total_kwh", 2.0),
        total_model_runtime_seconds=kwargs.pop("total_model_runtime_seconds", 3600),
        total_loaded_model_seconds=kwargs.pop("total_loaded_model_seconds", 7200),
        total_requests=kwargs.pop("total_requests", 10),
        total_tokens=kwargs.pop("total_tokens", 2000),
        node_cost_estimate=kwargs.pop("node_cost_estimate", 36.4),
        errors=kwargs.pop("errors", []),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    )


def _model_load_request_row(**kwargs):
    return SimpleNamespace(
        model_load_request_id=kwargs.pop(
            "model_load_request_id", "model-load-request-1"
        ),
        company_id=kwargs.pop("company_id", "company-1"),
        project_id=kwargs.pop("project_id", "project-1"),
        model_alias=kwargs.pop("model_alias", "cavadalabs/qwen3-32b"),
        provider=kwargs.pop("provider", "cavadalabs"),
        node_id=kwargs.pop("node_id", None),
        gpu_id=kwargs.pop("gpu_id", None),
        loaded_model_id=kwargs.pop("loaded_model_id", None),
        status=kwargs.pop("status", "queued"),
        priority=kwargs.pop("priority", 100),
        requested_by=kwargs.pop("requested_by", "admin-user"),
        requested_at=kwargs.pop("requested_at", datetime.now(timezone.utc)),
        expires_at=kwargs.pop("expires_at", None),
        last_error=kwargs.pop("last_error", None),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    )


def _loaded_model_row(**kwargs):
    return SimpleNamespace(
        loaded_model_id=kwargs.pop("loaded_model_id", "loaded-model-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        gpu_id=kwargs.pop("gpu_id", "gpu-1"),
        model_alias=kwargs.pop("model_alias", "cavadalabs/qwen3-32b"),
        provider=kwargs.pop("provider", "cavadalabs"),
        status=kwargs.pop("status", "loaded"),
        load_request_id=kwargs.pop("load_request_id", "model-load-request-1"),
        context_window=kwargs.pop("context_window", 32768),
        capabilities=kwargs.pop("capabilities", ["tools"]),
        loaded_at=kwargs.pop("loaded_at", datetime.now(timezone.utc)),
        unloaded_at=kwargs.pop("unloaded_at", None),
        last_used_at=kwargs.pop("last_used_at", None),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    )


def _gpu_lock_row(**kwargs):
    return SimpleNamespace(
        lock_id=kwargs.pop("lock_id", "lock-1"),
        node_id=kwargs.pop("node_id", "node-1"),
        gpu_id=kwargs.pop("gpu_id", "gpu-1"),
        model_id=kwargs.pop("model_id", "cavadalabs/qwen3-32b"),
        project_id=kwargs.pop("project_id", "project-1"),
        owner_type=kwargs.pop("owner_type", "model_load_request"),
        owner_id=kwargs.pop("owner_id", "model-load-request-1"),
        priority=kwargs.pop("priority", 10),
        expires_at=kwargs.pop(
            "expires_at", datetime.now(timezone.utc) + timedelta(minutes=30)
        ),
        released_at=kwargs.pop("released_at", None),
        status=kwargs.pop("status", "active"),
        metadata=kwargs.pop("metadata", {}),
        created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
        updated_at=kwargs.pop("updated_at", datetime.now(timezone.utc)),
        **kwargs,
    )


def _service():
    prisma_client = MagicMock()
    prisma_client.db = MagicMock()
    prisma_client.db.cavadalabs_nodetable = MagicMock()
    prisma_client.db.cavadalabs_gputable = MagicMock()
    prisma_client.db.cavadalabs_nodeenrollmenttable = MagicMock()
    prisma_client.db.cavadalabs_nodedailyreporttable = MagicMock()
    prisma_client.db.cavadalabs_modelloadrequesttable = MagicMock()
    prisma_client.db.cavadalabs_loadedmodeltable = MagicMock()
    prisma_client.db.cavadalabs_gpulocktable = MagicMock()
    prisma_client.db.cavadalabs_companytable = MagicMock()
    prisma_client.db.cavadalabs_projecttable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable = MagicMock()
    prisma_client.db.cavadalabs_auditlogtable.create = AsyncMock()
    return CavadaLabsNodeService(prisma_client), prisma_client


def _public_key_raw(private_key: ed25519.Ed25519PrivateKey) -> str:
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(public_key).decode("utf-8")


def _signature(
    private_key: ed25519.Ed25519PrivateKey,
    *,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
) -> str:
    canonical = canonical_node_signature_payload(
        timestamp=timestamp,
        method=method,
        path=path,
        body=body,
    )
    return base64.b64encode(private_key.sign(canonical)).decode("utf-8")


@pytest.mark.asyncio
async def test_should_create_node_and_write_cavadalabs_audit_log():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_nodetable.create = AsyncMock(return_value=_node_row())

    response = await service.create_node(
        CavadaLabsNodeCreateRequest(
            display_name="Milan GPU 01",
            hostname="gpu-01",
            allowed_project_ids=["project-1", "project-1"],
            pools=["default", "default"],
        ),
        _admin(),
    )

    assert response.node_id == "node-1"
    create_data = prisma_client.db.cavadalabs_nodetable.create.call_args.kwargs["data"]
    assert create_data["allowed_project_ids"] == ["project-1"]
    assert create_data["pools"] == ["default"]
    assert create_data["created_by"] == "admin-user"
    prisma_client.db.cavadalabs_auditlogtable.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_create_enrollment_secret_without_persisting_raw_secret():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row()
    )
    prisma_client.db.cavadalabs_nodeenrollmenttable.create = AsyncMock(
        return_value=_enrollment_row()
    )

    response = await service.create_enrollment_secret(
        "node-1",
        CavadaLabsNodeEnrollmentCreateRequest(expires_in_seconds=600),
        _admin(),
    )

    assert response.enrollment_secret.startswith("clne-")
    create_data = (
        prisma_client.db.cavadalabs_nodeenrollmenttable.create.call_args.kwargs["data"]
    )
    assert create_data["secret_hash"] == hash_web_token(response.enrollment_secret)
    assert response.enrollment_secret not in str(create_data)
    assert create_data["status"] == "active"


@pytest.mark.asyncio
async def test_should_complete_node_enrollment_once_and_store_public_key_fingerprint():
    service, prisma_client = _service()
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = _public_key_raw(private_key)
    secret = "clne-test.secret-with-production-length"
    fingerprint = public_key_fingerprint(public_key)
    prisma_client.db.cavadalabs_nodeenrollmenttable.find_unique = AsyncMock(
        return_value=_enrollment_row(secret_hash=hash_web_token(secret))
    )
    prisma_client.db.cavadalabs_nodeenrollmenttable.update_many = AsyncMock(
        return_value=1
    )
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(metadata={"rack": "a1"})
    )
    prisma_client.db.cavadalabs_nodetable.update = AsyncMock(
        return_value=_node_row(
            status="online",
            public_key=public_key,
            public_key_fingerprint=fingerprint,
            agent_version="1.0.0",
            metadata={"rack": "a1"},
        )
    )

    response = await service.complete_enrollment(
        CavadaLabsNodeEnrollmentCompleteRequest(
            enrollment_secret=secret,
            public_key=public_key,
            agent_version="1.0.0",
            hostname="gpu-01",
        )
    )

    update_many_data = (
        prisma_client.db.cavadalabs_nodeenrollmenttable.update_many.call_args.kwargs
    )
    assert update_many_data["where"]["status"] == "active"
    assert update_many_data["data"]["status"] == "used"
    node_update_data = prisma_client.db.cavadalabs_nodetable.update.call_args.kwargs[
        "data"
    ]
    assert node_update_data["public_key"] == public_key
    assert node_update_data["public_key_fingerprint"] == fingerprint
    assert response.runtime_config["signature"]["algorithm"] == "ed25519"


@pytest.mark.asyncio
async def test_should_authenticate_signed_node_request():
    service, prisma_client = _service()
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = _public_key_raw(private_key)
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online", public_key=public_key)
    )
    body = b'{"status":"online"}'
    timestamp = datetime.now(timezone.utc).isoformat()
    signature = _signature(
        private_key,
        timestamp=timestamp,
        method="POST",
        path="/cavadalabs/nodes/heartbeat",
        body=body,
    )

    response = await service.authenticate_node_request(
        node_id="node-1",
        timestamp=timestamp,
        signature=signature,
        method="POST",
        path="/cavadalabs/nodes/heartbeat",
        body=body,
    )

    assert response.node_id == "node-1"


@pytest.mark.asyncio
async def test_should_reject_invalid_node_signature():
    service, prisma_client = _service()
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = _public_key_raw(private_key)
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online", public_key=public_key)
    )
    body = b'{"status":"online"}'
    timestamp = datetime.now(timezone.utc).isoformat()
    invalid_signature = base64.b64encode(b"0" * 64).decode("utf-8")

    with pytest.raises(HTTPException) as exc:
        await service.authenticate_node_request(
            node_id="node-1",
            timestamp=timestamp,
            signature=invalid_signature,
            method="POST",
            path="/cavadalabs/nodes/heartbeat",
            body=body,
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_should_upsert_gpu_inventory_by_uuid():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online")
    )
    prisma_client.db.cavadalabs_gputable.find_first = AsyncMock(return_value=None)
    prisma_client.db.cavadalabs_gputable.create = AsyncMock(return_value=_gpu_row())
    prisma_client.db.cavadalabs_nodetable.update = AsyncMock(
        return_value=_node_row(status="online")
    )

    response = await service.upsert_gpu_inventory(
        "node-1",
        CavadaLabsGPUInventoryRequest(
            gpus=[
                CavadaLabsGPUInventoryItem(
                    vendor="nvidia",
                    model="RTX 6000 Ada",
                    uuid="GPU-123",
                    vram_total_mb=49152,
                )
            ]
        ),
    )

    assert response.count == 1
    create_data = prisma_client.db.cavadalabs_gputable.create.call_args.kwargs["data"]
    assert create_data["node_id"] == "node-1"
    assert create_data["created_by"] == "node:node-1"


@pytest.mark.asyncio
async def test_should_record_daily_report_with_node_cost_estimate():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online")
    )
    prisma_client.db.cavadalabs_nodedailyreporttable.find_first = AsyncMock(
        return_value=None
    )

    async def _create_report(*args, **kwargs):
        return _daily_report_row(**kwargs["data"])

    prisma_client.db.cavadalabs_nodedailyreporttable.create = AsyncMock(
        side_effect=_create_report
    )
    prisma_client.db.cavadalabs_nodetable.update = AsyncMock(
        return_value=_node_row(status="online")
    )

    response = await service.record_daily_report(
        "node-1",
        CavadaLabsNodeDailyReportRequest(
            report_date=date(2026, 5, 14),
            total_kwh=2.0,
            total_model_runtime_seconds=3600,
            total_loaded_model_seconds=7200,
            total_requests=10,
            total_tokens=2000,
        ),
    )

    assert response.node_cost_estimate == 36.4
    create_data = (
        prisma_client.db.cavadalabs_nodedailyreporttable.create.call_args.kwargs["data"]
    )
    assert create_data["report_date"] == datetime(2026, 5, 14, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_should_create_model_load_request_for_allowed_project():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.create = AsyncMock(
        return_value=_model_load_request_row()
    )

    response = await service.create_model_load_request(
        CavadaLabsModelLoadRequestCreateRequest(
            project_id="project-1",
            model_alias="cavadalabs/qwen3-32b",
        ),
        _admin(),
    )

    assert response.model_load_request_id == "model-load-request-1"
    create_data = (
        prisma_client.db.cavadalabs_modelloadrequesttable.create.call_args.kwargs[
            "data"
        ]
    )
    assert create_data["company_id"] == "company-1"
    assert create_data["status"] == "queued"
    assert create_data["requested_by"] == "admin-user"


@pytest.mark.asyncio
async def test_should_reject_model_load_request_for_unallowed_model():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row(allowed_models=["cavadalabs/qwen3-32b"])
    )
    prisma_client.db.cavadalabs_companytable.find_unique = AsyncMock(
        return_value=_company_row()
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_model_load_request(
            CavadaLabsModelLoadRequestCreateRequest(
                project_id="project-1",
                model_alias="openai/gpt-4.1",
            ),
            _admin(),
        )

    assert exc.value.status_code == 400
    prisma_client.db.cavadalabs_modelloadrequesttable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_upsert_loaded_model_and_sync_gpu_and_load_request():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online")
    )
    prisma_client.db.cavadalabs_gputable.find_unique = AsyncMock(
        side_effect=[
            _gpu_row(),
            _gpu_row(loaded_model_ids=[]),
        ]
    )
    prisma_client.db.cavadalabs_loadedmodeltable.create = AsyncMock(
        return_value=_loaded_model_row()
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_first = AsyncMock(
        return_value=None
    )
    prisma_client.db.cavadalabs_gputable.update = AsyncMock(
        return_value=_gpu_row(loaded_model_ids=["loaded-model-1"])
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.update = AsyncMock(
        return_value=_model_load_request_row(status="loaded")
    )

    response = await service.upsert_loaded_model(
        "node-1",
        CavadaLabsLoadedModelUpsertRequest(
            gpu_id="gpu-1",
            model_alias="cavadalabs/qwen3-32b",
            status="loaded",
            load_request_id="model-load-request-1",
            context_window=32768,
            capabilities=["Tools", "tools"],
        ),
    )

    assert response.loaded_model_id == "loaded-model-1"
    assert response.capabilities == ["tools"]
    gpu_update_data = prisma_client.db.cavadalabs_gputable.update.call_args.kwargs[
        "data"
    ]
    assert gpu_update_data["loaded_model_ids"] == ["loaded-model-1"]
    load_request_update = (
        prisma_client.db.cavadalabs_modelloadrequesttable.update.call_args.kwargs
    )
    assert load_request_update["data"]["status"] == "loaded"
    assert load_request_update["data"]["loaded_model_id"] == "loaded-model-1"


@pytest.mark.asyncio
async def test_should_create_and_release_gpu_lock():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online")
    )
    prisma_client.db.cavadalabs_gputable.find_unique = AsyncMock(
        return_value=_gpu_row(status="available")
    )
    prisma_client.db.cavadalabs_gpulocktable.create = AsyncMock(
        return_value=_gpu_lock_row()
    )
    prisma_client.db.cavadalabs_gpulocktable.find_unique = AsyncMock(
        return_value=_gpu_lock_row()
    )
    prisma_client.db.cavadalabs_gpulocktable.update = AsyncMock(
        return_value=_gpu_lock_row(
            status="released", released_at=datetime.now(timezone.utc)
        )
    )

    created = await service.create_gpu_lock(
        CavadaLabsGPULockCreateRequest(
            node_id="node-1",
            gpu_id="gpu-1",
            model_id="cavadalabs/qwen3-32b",
            project_id="project-1",
            owner_type="model_load_request",
            owner_id="model-load-request-1",
            priority=10,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ),
        _admin(),
    )
    released = await service.release_gpu_lock("lock-1", _admin())

    assert created.status == "active"
    assert released.status == "released"


@pytest.mark.asyncio
async def test_should_expire_stale_gpu_locks_and_clear_active_lock_key():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_gpulocktable.find_many = AsyncMock(
        return_value=[
            _gpu_lock_row(
                status="active",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        ]
    )
    prisma_client.db.cavadalabs_gpulocktable.update = AsyncMock(
        return_value=_gpu_lock_row(status="expired")
    )

    response = await service.expire_stale_gpu_locks()

    assert len(response) == 1
    update_data = prisma_client.db.cavadalabs_gpulocktable.update.call_args.kwargs[
        "data"
    ]
    assert update_data["status"] == "expired"
    assert update_data["lock_key"] is None


@pytest.mark.asyncio
async def test_should_schedule_queued_model_load_request_to_available_gpu():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_gpulocktable.find_many = AsyncMock(
        side_effect=[
            [],
            [],
        ]
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.find_many = AsyncMock(
        return_value=[_model_load_request_row(priority=10)]
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_nodetable.find_many = AsyncMock(
        return_value=[_node_row(status="online")]
    )
    prisma_client.db.cavadalabs_gputable.find_many = AsyncMock(
        return_value=[_gpu_row(status="available")]
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_many = AsyncMock(return_value=[])
    prisma_client.db.cavadalabs_gpulocktable.create = AsyncMock(
        return_value=_gpu_lock_row(status="active")
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.update_many = AsyncMock(
        return_value=1
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.find_unique = AsyncMock(
        return_value=_model_load_request_row(
            status="locking",
            node_id="node-1",
            gpu_id="gpu-1",
        )
    )

    response = await service.schedule_model_load_requests(
        CavadaLabsSchedulerRunRequest(take=5, lock_ttl_seconds=600),
        _admin(),
    )

    assert response.count == 1
    assert response.scheduled[0].model_load_request.status == "locking"
    lock_data = prisma_client.db.cavadalabs_gpulocktable.create.call_args.kwargs["data"]
    assert lock_data["lock_key"] == "active:gpu-1"
    assert lock_data["owner_id"] == "model-load-request-1"
    request_update = (
        prisma_client.db.cavadalabs_modelloadrequesttable.update_many.call_args.kwargs
    )
    assert request_update["where"]["status"] == "queued"
    assert request_update["data"]["node_id"] == "node-1"
    assert request_update["data"]["gpu_id"] == "gpu-1"


@pytest.mark.asyncio
async def test_should_skip_scheduler_when_all_compatible_gpus_are_locked():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_gpulocktable.find_many = AsyncMock(
        side_effect=[
            [],
            [
                _gpu_lock_row(
                    status="active",
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                )
            ],
        ]
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.find_many = AsyncMock(
        return_value=[_model_load_request_row()]
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_nodetable.find_many = AsyncMock(
        return_value=[_node_row(status="online")]
    )
    prisma_client.db.cavadalabs_gputable.find_many = AsyncMock(
        return_value=[_gpu_row(status="available")]
    )
    prisma_client.db.cavadalabs_gpulocktable.create = AsyncMock()

    response = await service.schedule_model_load_requests(
        CavadaLabsSchedulerRunRequest(take=5),
        _admin(),
    )

    assert response.count == 0
    assert response.skipped[0].reason == "all compatible GPUs are locked"
    prisma_client.db.cavadalabs_gpulocktable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_reuse_available_loaded_model_without_creating_new_gpu_lock():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_gpulocktable.find_many = AsyncMock(
        side_effect=[
            [],
            [],
        ]
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.find_many = AsyncMock(
        return_value=[_model_load_request_row()]
    )
    prisma_client.db.cavadalabs_projecttable.find_unique = AsyncMock(
        return_value=_project_row()
    )
    prisma_client.db.cavadalabs_nodetable.find_many = AsyncMock(
        return_value=[_node_row(status="online")]
    )
    prisma_client.db.cavadalabs_gputable.find_many = AsyncMock(
        return_value=[_gpu_row(status="loaded", loaded_model_ids=["loaded-model-1"])]
    )
    prisma_client.db.cavadalabs_loadedmodeltable.find_many = AsyncMock(
        return_value=[_loaded_model_row()]
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.update_many = AsyncMock(
        return_value=1
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.find_unique = AsyncMock(
        return_value=_model_load_request_row(
            status="loaded",
            node_id="node-1",
            gpu_id="gpu-1",
            loaded_model_id="loaded-model-1",
        )
    )
    prisma_client.db.cavadalabs_gpulocktable.create = AsyncMock()

    response = await service.schedule_model_load_requests(
        CavadaLabsSchedulerRunRequest(take=5),
        _admin(),
    )

    assert response.count == 1
    assert response.scheduled[0].gpu_lock is None
    assert response.scheduled[0].loaded_model.loaded_model_id == "loaded-model-1"
    prisma_client.db.cavadalabs_gpulocktable.create.assert_not_called()


@pytest.mark.asyncio
async def test_should_list_signed_node_model_load_work():
    service, prisma_client = _service()
    prisma_client.db.cavadalabs_nodetable.find_unique = AsyncMock(
        return_value=_node_row(status="online")
    )
    prisma_client.db.cavadalabs_modelloadrequesttable.find_many = AsyncMock(
        return_value=[
            _model_load_request_row(
                status="locking",
                node_id="node-1",
                gpu_id="gpu-1",
            )
        ]
    )

    response = await service.list_node_model_load_work(
        "node-1",
        CavadaLabsNodeModelLoadWorkRequest(),
    )

    assert response.count == 1
    find_many_where = (
        prisma_client.db.cavadalabs_modelloadrequesttable.find_many.call_args.kwargs[
            "where"
        ]
    )
    assert find_many_where["node_id"] == "node-1"
    assert "locking" in find_many_where["status"]["in"]
