import logging

from fastapi import APIRouter, HTTPException

from app.core.mcp_client import McpError
from app.models.schemas import LogisticsSalesWorkflowResponse
from app.workflows.logistics_sales_workflow import (
    LogisticsWorkflowError,
    logistics_sales_workflow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post(
    "/logistics/sales-to-stock-sheet",
    response_model=LogisticsSalesWorkflowResponse,
)
async def run_logistics_sales_workflow():
    """Write rolling sales for SKU 70017-3 into the stock planning workbook."""
    try:
        result = await logistics_sales_workflow.run()
        return LogisticsSalesWorkflowResponse(status="success", **result)
    except (McpError, LogisticsWorkflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=423, detail="备货表正在使用或没有写入权限") from exc
    except Exception as exc:
        logger.exception("Logistics sales workflow failed")
        raise HTTPException(status_code=500, detail="物流销量工作流执行失败") from exc
