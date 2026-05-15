from __future__ import annotations

from litellm.proxy.cavadalabs.nodes_admin import CavadaLabsNodeAdminOperations
from litellm.proxy.cavadalabs.nodes_base import CavadaLabsNodeBase
from litellm.proxy.cavadalabs.nodes_helpers import CavadaLabsNodeHelperOperations
from litellm.proxy.cavadalabs.nodes_model_load import CavadaLabsNodeModelLoadOperations
from litellm.proxy.cavadalabs.nodes_runtime import CavadaLabsNodeRuntimeOperations
from litellm.proxy.cavadalabs.nodes_scheduler import CavadaLabsNodeSchedulerOperations
from litellm.proxy.cavadalabs.nodes_shared import (
    _active_gpu_lock_key,
    _create_node_enrollment_secret,
    _daily_report_date,
    _decode_base64,
    _decode_signature,
    _load_ed25519_public_key,
    _metadata_int,
    _metadata_string,
    _node_actor,
    _parse_node_timestamp,
    _parse_response,
    _row_to_dict,
    canonical_node_signature_payload,
    public_key_fingerprint,
)


class CavadaLabsNodeService(
    CavadaLabsNodeAdminOperations,
    CavadaLabsNodeRuntimeOperations,
    CavadaLabsNodeModelLoadOperations,
    CavadaLabsNodeSchedulerOperations,
    CavadaLabsNodeHelperOperations,
    CavadaLabsNodeBase,
):
    pass


__all__ = [
    "CavadaLabsNodeService",
    "_active_gpu_lock_key",
    "_create_node_enrollment_secret",
    "_daily_report_date",
    "_decode_base64",
    "_decode_signature",
    "_load_ed25519_public_key",
    "_metadata_int",
    "_metadata_string",
    "_node_actor",
    "_parse_node_timestamp",
    "_parse_response",
    "_row_to_dict",
    "canonical_node_signature_payload",
    "public_key_fingerprint",
]
