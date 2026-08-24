import logging

from fastapi import APIRouter, HTTPException

from app.core.mcp_client import McpError
from app.models.schemas import (
    LogisticsSalesExecuteRequest,
    LogisticsSalesExecuteResponse,
    LogisticsSalesPreviewResponse,
)
from app.workflows.logistics_sales_workflow import (
    LogisticsWorkflowError,
    logistics_sales_workflow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post(
    "/logistics/sales-to-stock-sheet/preview",
    response_model=LogisticsSalesPreviewResponse,
)
async def preview_logistics_sales_workflow():
    """Build a read-only A-F matched sales update preview."""
    try:
        result = await logistics_sales_workflow.preview()
        return LogisticsSalesPreviewResponse(status="preview", **result)
    except (McpError, LogisticsWorkflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Logistics sales workflow preview failed")
        raise HTTPException(status_code=500, detail="物流销量预览生成失败") from exc


@router.post(
    "/logistics/sales-to-stock-sheet/execute",
    response_model=LogisticsSalesExecuteResponse,
)
async def execute_logistics_sales_workflow(request: LogisticsSalesExecuteRequest):
    """Write a previously confirmed preview into the local workbook copy."""
    try:
        result = await logistics_sales_workflow.execute(request.preview_id)
        return LogisticsSalesExecuteResponse(status="success", **result)
    except (McpError, LogisticsWorkflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=423, detail="本地测试表正在使用或没有写入权限") from exc
    except Exception as exc:
        logger.exception("Logistics sales workflow execution failed")
        raise HTTPException(status_code=500, detail="物流销量写入失败") from exc
