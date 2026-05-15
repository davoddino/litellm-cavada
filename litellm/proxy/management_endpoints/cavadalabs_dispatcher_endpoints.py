from __future__ import annotations

from fastapi import APIRouter

from litellm.proxy.management_endpoints.cavadalabs_chatbot_admin_endpoints import (
    router as chatbot_admin_router,
)
from litellm.proxy.management_endpoints.cavadalabs_company_endpoints import (
    router as company_router,
)
from litellm.proxy.management_endpoints.cavadalabs_model_policy_endpoints import (
    router as model_policy_router,
)
from litellm.proxy.management_endpoints.cavadalabs_project_endpoints import (
    router as project_router,
)

router = APIRouter(prefix="/cavadalabs", tags=["cavadalabs"])
router.include_router(company_router)
router.include_router(project_router)
router.include_router(chatbot_admin_router)
router.include_router(model_policy_router)
