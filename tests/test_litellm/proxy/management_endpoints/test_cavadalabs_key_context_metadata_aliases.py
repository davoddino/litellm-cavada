import json
from typing import Any

from litellm.proxy._types import GenerateKeyResponse, LiteLLM_VerificationToken
from litellm.proxy.cavadalabs.key_context_metadata import (
    _extract_cavadalabs_key_context,
)
from litellm.proxy.management_endpoints.key_management_endpoints import (
    _build_key_filter_conditions,
)


def test_build_key_filter_conditions_matches_cavadalabs_metadata_aliases():
    where = _build_key_filter_conditions(
        user_id="user-1",
        team_id=None,
        organization_id=None,
        key_alias=None,
        key_hash=None,
        exclude_team_id=None,
        admin_team_ids=None,
        cavadalabs_company_id="company-1",
        cavadalabs_project_id="project-1",
    )

    assert _collect_metadata_paths(where) >= {
        ("cavadalabs_company_id",),
        ("company_id",),
        ("cavadalabs", "cavadalabs_company_id"),
        ("cavadalabs", "company_id"),
        ("spend_logs_metadata", "cavadalabs_company_id"),
        ("spend_logs_metadata", "company_id"),
        ("cavadalabs_project_id",),
        ("project_id",),
        ("cavadalabs", "cavadalabs_project_id"),
        ("cavadalabs", "project_id"),
        ("spend_logs_metadata", "cavadalabs_project_id"),
        ("spend_logs_metadata", "project_id"),
    }


def test_extract_cavadalabs_key_context_reads_metadata_aliases():
    company_id, project_id = _extract_cavadalabs_key_context(
        {
            "cavadalabs": {
                "cavadalabs_company_id": "company-nested",
            },
            "spend_logs_metadata": {
                "project_id": "project-spend",
            },
        }
    )

    assert company_id == "company-nested"
    assert project_id == "project-spend"


def test_verification_token_reads_cavadalabs_context_from_generic_spend_metadata_aliases():
    token = LiteLLM_VerificationToken(
        token="hashed-token",
        metadata={
            "spend_logs_metadata": {
                "company_id": "company-legacy",
                "project_id": "project-legacy",
            }
        },
    )

    assert token.cavadalabs_company_id == "company-legacy"
    assert token.cavadalabs_project_id == "project-legacy"


def test_generate_key_response_reads_cavadalabs_context_from_nested_canonical_aliases():
    response = GenerateKeyResponse(
        key="sk-test",
        metadata=json.dumps(
            {
                "cavadalabs": {
                    "cavadalabs_company_id": "company-legacy",
                    "cavadalabs_project_id": "project-legacy",
                }
            }
        ),
    )

    assert response.cavadalabs_company_id == "company-legacy"
    assert response.cavadalabs_project_id == "project-legacy"


def _collect_metadata_paths(value: Any) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    if isinstance(value, dict):
        metadata = value.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), list):
            paths.add(tuple(metadata["path"]))
        for item in value.values():
            paths.update(_collect_metadata_paths(item))
    if isinstance(value, list):
        for item in value:
            paths.update(_collect_metadata_paths(item))
    return paths
