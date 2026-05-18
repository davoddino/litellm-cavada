# What is this?
## This hook is used to manage vector stores with target_model_names support
## It allows creating vector stores across multiple models and managing them with unified IDs

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, cast

from fastapi import HTTPException

import litellm
from litellm import Router, verbose_logger
from litellm._uuid import uuid
from litellm.integrations.custom_logger import CustomLogger
from litellm.llms.base_llm.managed_resources import BaseManagedResource
from litellm.llms.base_llm.managed_resources.utils import (
    generate_unified_id_string,
    is_base64_encoded_unified_id,
)
from litellm.proxy._types import LitellmUserRoles, UserAPIKeyAuth
from litellm.proxy.vector_store_endpoints.management_endpoints import (
    _company_id_from_team,
    _get_field_value,
    _resolve_vector_store_project_context,
)
from litellm.types.vector_stores import (
    VectorStoreCreateOptionalRequestParams,
    VectorStoreCreateResponse,
)

if TYPE_CHECKING:
    from opentelemetry.trace import Span as _Span

    from litellm.proxy.utils import InternalUsageCache as _InternalUsageCache
    from litellm.proxy.utils import PrismaClient as _PrismaClient

    Span = Union[_Span, Any]
    InternalUsageCache = _InternalUsageCache
    PrismaClient = _PrismaClient
else:
    Span = Any
    InternalUsageCache = Any
    PrismaClient = Any


class _PROXY_LiteLLMManagedVectorStores(
    CustomLogger, BaseManagedResource[VectorStoreCreateResponse]
):
    """
    Managed vector stores with target_model_names support.
    
    This class provides functionality to:
    - Create vector stores across multiple models
    - Retrieve vector stores by unified ID
    - Delete vector stores from all models
    - List vector stores created by a user
    """

    def __init__(
        self, internal_usage_cache: InternalUsageCache, prisma_client: PrismaClient
    ):
        CustomLogger.__init__(self)
        BaseManagedResource.__init__(self, internal_usage_cache, prisma_client)

    @staticmethod
    def _pop_product_context(
        request_data: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        company_id = request_data.pop("company_id", None)
        project_id = request_data.pop("project_id", None)
        for field_name, value in (
            ("company_id", company_id),
            ("project_id", project_id),
        ):
            if value is not None and not isinstance(value, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"{field_name} must be a string when provided",
                )
        return company_id, project_id

    async def _company_admin_can_access_project_resource(
        self,
        *,
        project_id: Optional[str],
        user_api_key_dict: UserAPIKeyAuth,
    ) -> bool:
        if project_id is None or user_api_key_dict.user_id is None:
            return False

        project = await self.prisma_client.db.litellm_projecttable.find_unique(
            where={"project_id": project_id},
            include={"litellm_team_table": True},
        )
        if project is None:
            return False

        team = _get_field_value(project, "litellm_team_table")
        company_id = _get_field_value(project, "company_id") or _company_id_from_team(
            team
        )
        if not company_id:
            return False

        membership = (
            await self.prisma_client.db.litellm_organizationmembership.find_unique(
                where={
                    "user_id_organization_id": {
                        "user_id": user_api_key_dict.user_id,
                        "organization_id": company_id,
                    }
                }
            )
        )
        return (
            membership is not None
            and _get_field_value(membership, "user_role")
            == LitellmUserRoles.ORG_ADMIN.value
        )

    # ============================================================================
    #                     ABSTRACT METHOD IMPLEMENTATIONS
    # ============================================================================

    @property
    def resource_type(self) -> str:
        """Return the resource type identifier."""
        return "vector_store"

    @property
    def table_name(self) -> str:
        """Return the database table name for vector stores."""
        # Prisma converts model name LiteLLM_ManagedVectorStoreTable to litellm_managedvectorstoretable
        return "litellm_managedvectorstoretable"

    def get_unified_resource_id_format(
        self,
        resource_object: VectorStoreCreateResponse,
        target_model_names_list: List[str],
    ) -> str:
        """
        Generate the format string for the unified vector store ID.
        
        Format:
        litellm_proxy:vector_store;unified_id,<uuid>;target_model_names,<models>;resource_id,<vs_id>;model_id,<model_id>
        """
        # VectorStoreCreateResponse is a TypedDict, so resource_object is a dictionary
        # Extract provider resource ID from the response
        provider_resource_id = resource_object.get("id", "")
        
        # Model ID is stored in hidden params if the response object supports it
        # For TypedDict responses, we need to check if _hidden_params was added
        hidden_params: Dict[str, Any] = {}
        if hasattr(resource_object, "_hidden_params"):
            hidden_params = getattr(resource_object, "_hidden_params", {}) or {}
        model_id = hidden_params.get("model_id", "")

        return generate_unified_id_string(
            resource_type=self.resource_type,
            unified_uuid=str(uuid.uuid4()),
            target_model_names=target_model_names_list,
            provider_resource_id=provider_resource_id,
            model_id=model_id,
        )

    async def create_resource_for_model(
        self,
        llm_router: Router,
        model: str,
        request_data: Dict[str, Any],
        litellm_parent_otel_span: Span,
    ) -> VectorStoreCreateResponse:
        """
        Create a vector store for a specific model.
        
        Args:
            llm_router: LiteLLM router instance
            model: Model name to create vector store for
            request_data: Request data for vector store creation
            litellm_parent_otel_span: OpenTelemetry span for tracing
            
        Returns:
            VectorStoreCreateResponse from the provider
        """
        # Use the router to create the vector store
        response = await llm_router.avector_store_create(
            model=model, **request_data
        )
        return response

    # ============================================================================
    #                     VECTOR STORE CRUD OPERATIONS
    # ============================================================================

    async def acreate_vector_store(
        self,
        create_request: VectorStoreCreateOptionalRequestParams,
        llm_router: Router,
        target_model_names_list: List[str],
        litellm_parent_otel_span: Span,
        user_api_key_dict: UserAPIKeyAuth,
    ) -> VectorStoreCreateResponse:
        """
        Create a vector store across multiple models.
        
        Args:
            create_request: Vector store creation request parameters
            llm_router: LiteLLM router instance
            target_model_names_list: List of target model names
            litellm_parent_otel_span: OpenTelemetry span for tracing
            user_api_key_dict: User API key authentication details
            
        Returns:
            VectorStoreCreateResponse with unified ID
        """
        verbose_logger.info(
            f"Creating managed vector store for models: {target_model_names_list}"
        )

        # Create vector store for each model. Convert TypedDict to Dict[str, Any]
        # for base class compatibility and keep product tenant fields out of the
        # provider request body.
        request_data_dict: Dict[str, Any] = dict(create_request)
        company_id, project_id = self._pop_product_context(request_data_dict)
        project_team_id: Optional[str] = None
        resolved_company_id: Optional[str] = None
        project_name: Optional[str] = None
        if company_id is not None or project_id is not None:
            project_team_id, resolved_company_id, project_name = (
                await _resolve_vector_store_project_context(
                    prisma_client=self.prisma_client,
                    project_id=project_id,
                    company_id=company_id,
                    user_api_key_dict=user_api_key_dict,
                )
            )
        responses = await self.create_resource_for_each_model(
            llm_router=llm_router,
            request_data=request_data_dict,
            target_model_names_list=target_model_names_list,
            litellm_parent_otel_span=litellm_parent_otel_span,
        )

        # Generate unified ID
        unified_id = self.generate_unified_resource_id(
            resource_objects=responses,
            target_model_names_list=target_model_names_list,
        )

        # Extract model mappings from responses
        model_mappings: Dict[str, str] = {}
        for response in responses:
            hidden_params = getattr(response, "_hidden_params", {}) or {}
            model_id = hidden_params.get("model_id")
            if model_id:
                # VectorStoreCreateResponse is a TypedDict, use dict access
                model_mappings[model_id] = response["id"]

        verbose_logger.debug(
            f"Created vector stores with model mappings: {model_mappings}"
        )

        product_context: Dict[str, Any] = {}
        additional_db_fields: Dict[str, Any] = {}
        if project_team_id is not None:
            additional_db_fields["team_id"] = project_team_id
        if project_id is not None:
            additional_db_fields["project_id"] = project_id
            product_context["project_id"] = project_id
        if resolved_company_id is not None:
            product_context["company_id"] = resolved_company_id
        if project_name is not None:
            product_context["project_name"] = project_name

        resource_object = responses[0]
        if isinstance(resource_object, dict) and product_context:
            resource_object = resource_object.copy()
            resource_object.update(product_context)

        # Store in database
        await self.store_unified_resource_id(
            unified_resource_id=unified_id,
            resource_object=resource_object,  # Store first response as template
            litellm_parent_otel_span=litellm_parent_otel_span,
            model_mappings=model_mappings,
            user_api_key_dict=user_api_key_dict,
            additional_db_fields=additional_db_fields or None,
        )

        # Return response with unified ID
        # VectorStoreCreateResponse is a TypedDict, so we need to create a new dict with the unified ID
        response = responses[0].copy()
        response["id"] = unified_id
        response.update(product_context)
        
        verbose_logger.info(
            f"Successfully created managed vector store with unified ID: {unified_id}"
        )

        return response

    async def can_user_access_unified_resource_id(
        self,
        unified_resource_id: str,
        user_api_key_dict: UserAPIKeyAuth,
        litellm_parent_otel_span: Optional[Span] = None,
    ) -> bool:
        if await super().can_user_access_unified_resource_id(
            unified_resource_id=unified_resource_id,
            user_api_key_dict=user_api_key_dict,
            litellm_parent_otel_span=litellm_parent_otel_span,
        ):
            return True

        resource = await self.get_unified_resource_id(
            unified_resource_id=unified_resource_id,
            litellm_parent_otel_span=litellm_parent_otel_span,
        )
        if resource is None:
            return False
        return await self._company_admin_can_access_project_resource(
            project_id=resource.get("project_id"),
            user_api_key_dict=user_api_key_dict,
        )

    async def alist_vector_stores(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        limit: Optional[int] = None,
        after: Optional[str] = None,
        order: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List vector stores created by a user.
        
        Args:
            user_api_key_dict: User API key authentication details
            limit: Maximum number of vector stores to return
            after: Cursor for pagination
            order: Sort order ('asc' or 'desc')
            
        Returns:
            Dictionary with list of vector stores and pagination info
        """
        # Use the base class method
        return await self.list_user_resources(
            user_api_key_dict=user_api_key_dict,
            limit=limit,
            after=after,
        )

    # ============================================================================
    #                     ACCESS CONTROL
    # ============================================================================

    async def check_vector_store_access(
        self, vector_store_id: str, user_api_key_dict: UserAPIKeyAuth
    ) -> bool:
        """
        Check if user has access to a vector store.
        
        Args:
            vector_store_id: The unified vector store ID
            user_api_key_dict: User API key authentication details
            
        Returns:
            True if user has access, False otherwise
        """
        is_unified_id = is_base64_encoded_unified_id(vector_store_id)
        
        if is_unified_id:
            # Check access for managed vector store
            return await self.can_user_access_unified_resource_id(
                vector_store_id,
                user_api_key_dict,
            )
        
        # Not a managed vector store, allow access
        return True

    async def check_managed_vector_store_access(
        self, data: Dict, user_api_key_dict: UserAPIKeyAuth
    ) -> bool:
        """
        Check if user has access to a managed vector store in request data.
        
        Args:
            data: Request data containing vector_store_id
            user_api_key_dict: User API key authentication details
            
        Returns:
            True if this is a managed vector store and user has access
            
        Raises:
            HTTPException: If user doesn't have access
        """
        vector_store_id = cast(Optional[str], data.get("vector_store_id"))
        is_unified_id = (
            is_base64_encoded_unified_id(vector_store_id)
            if vector_store_id
            else False
        )
        
        if is_unified_id and vector_store_id:
            if await self.can_user_access_unified_resource_id(
                vector_store_id, user_api_key_dict
            ):
                return True
            else:
                raise HTTPException(
                    status_code=403,
                    detail=f"User {user_api_key_dict.user_id} does not have access to vector store {vector_store_id}",
                )
        
        return False

    # ============================================================================
    #                     PRE-CALL HOOK (For Router Integration)
    # ============================================================================

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: Any,
        data: Dict,
        call_type: str,
    ) -> Union[Exception, str, Dict, None]:
        """
        Pre-call hook to handle vector store operations.
        
        This hook intercepts vector store requests and:
        - Validates access for managed vector stores
        - Transforms unified IDs to provider-specific IDs
        - Adds model routing information
        
        Args:
            user_api_key_dict: User API key authentication details
            cache: Cache instance
            data: Request data
            call_type: Type of call being made
            
        Returns:
            Modified request data or None
        """
        from litellm.llms.base_llm.managed_resources.utils import (
            is_base64_encoded_unified_id,
            parse_unified_id,
        )

        # Handle vector store search operations
        if call_type == "avector_store_search":
            vector_store_id = data.get("vector_store_id")
            
            if vector_store_id:
                # Check if it's a managed vector store ID
                decoded_id = is_base64_encoded_unified_id(vector_store_id)
                
                if decoded_id:
                    verbose_logger.debug(
                        f"Processing managed vector store search: {vector_store_id}"
                    )
                    
                    # Check access
                    has_access = await self.can_user_access_unified_resource_id(
                        vector_store_id, user_api_key_dict
                    )
                    
                    if not has_access:
                        raise HTTPException(
                            status_code=403,
                            detail=f"User {user_api_key_dict.user_id} does not have access to vector store {vector_store_id}",
                        )
                    
                    # Parse the unified ID to extract components
                    parsed_id = parse_unified_id(vector_store_id)
                    
                    if parsed_id:
                        # Extract the model ID and provider resource ID
                        model_id = parsed_id.get("model_id")
                        provider_resource_id = parsed_id.get("provider_resource_id")
                        target_model_names = parsed_id.get("target_model_names", [])
                        
                        verbose_logger.debug(
                            f"Decoded vector store - model_id: {model_id}, provider_resource_id: {provider_resource_id}, target_model_names: {target_model_names}"
                        )
                        
                        # Determine which model to use for routing
                        # Priority: model_id (deployment ID) > first target_model_name
                        routing_model = None
                        if model_id:
                            routing_model = model_id
                        elif target_model_names and len(target_model_names) > 0:
                            routing_model = target_model_names[0]
                        
                        # Set the model for routing
                        if routing_model:
                            data["model"] = routing_model
                            verbose_logger.info(
                                f"Routing vector store search to model: {routing_model}"
                            )
                        
                        # Replace the unified ID with the provider-specific ID
                        if provider_resource_id:
                            data["vector_store_id"] = provider_resource_id
                            verbose_logger.debug(
                                f"Replaced unified ID with provider resource ID: {provider_resource_id}"
                            )
        
        # Handle vector store retrieve/delete operations
        elif call_type in ("avector_store_retrieve", "avector_store_delete"):
            await self.check_managed_vector_store_access(data, user_api_key_dict)
            
            # If it's a managed vector store, we'll handle it in the endpoint
            # No need to transform here as the endpoint will route to the hook
            
        return data

    # ============================================================================
    #                     POST-CALL HOOK (For Response Transformation)
    # ============================================================================

    async def async_post_call_success_hook(
        self,
        data: Dict,
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
    ) -> Any:
        """
        Post-call hook to transform responses.
        
        This hook can be used to transform responses if needed.
        For now, it just passes through the response.
        
        Args:
            data: Request data
            user_api_key_dict: User API key authentication details
            response: Response from the provider
            
        Returns:
            Potentially modified response
        """
        # Currently no transformation needed
        return response

    # ============================================================================
    #                     DEPLOYMENT FILTERING
    # ============================================================================

    async def async_filter_deployments(  # type: ignore[override]
        self,
        model: str,
        healthy_deployments: List,
        messages: Optional[List] = None,
        request_kwargs: Optional[Dict] = None,
        parent_otel_span: Optional[Span] = None,
    ) -> List[Dict]:
        """
        Filter deployments based on vector store availability.
        
        This is used by the router to select only deployments that have
        the vector store available.
        
        Note: This method signature is a compromise between CustomLogger and BaseManagedResource
        parent classes which have incompatible signatures. The type: ignore[override] is necessary
        due to this multiple inheritance conflict.
        
        Args:
            model: Model name
            healthy_deployments: List of healthy deployments
            messages: Messages (unused for vector stores, required by CustomLogger interface)
            request_kwargs: Request kwargs containing vector_store_id and mappings
            parent_otel_span: OpenTelemetry span for tracing
            
        Returns:
            Filtered list of deployments
        """
        return await BaseManagedResource.async_filter_deployments(
            self,
            model=model,
            healthy_deployments=healthy_deployments,
            request_kwargs=request_kwargs,
            parent_otel_span=parent_otel_span,
            resource_id_key="vector_store_id",
        )
