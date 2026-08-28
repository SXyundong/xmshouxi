import logging

from fastapi import APIRouter, HTTPException

from app.core.mcp_client import McpError
from app.models.schemas import (
    LogisticsSalesExecuteRequest,
    LogisticsSalesExecuteResponse,
    LogisticsSalesJobResponse,
    LogisticsSalesPreviewRequest,
    LogisticsSalesPreviewResponse,
)
from app.workflows.logistics_sales_workflow import (
    LogisticsWorkflowError,
    logistics_sales_workflow,
)
from app.workflows.cached_logistics_sales_workflow import (
    cached_logistics_sales_workflow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post(
    "/logistics/sales-to-stock-sheet/preview",
    response_model=LogisticsSalesJobResponse,
)
async def preview_logistics_sales_workflow(
    request: LogisticsSalesPreviewRequest | None = None,
):
    """Start an asynchronous cache refresh and preview job."""
    try:
        return await cached_logistics_sales_workflow.start_preview(
            force_refresh=bool(request and request.force_refresh)
        )
    except (McpError, LogisticsWorkflowError) as exc:
        detail = str(exc) or "物流销量预览失败，请检查领星 MCP 配置和权限"
        logger.warning("Logistics sales workflow preview rejected: %s", detail)
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:
        logger.exception("Logistics sales workflow preview failed")
        raise HTTPException(status_code=500, detail="物流销量预览生成失败") from exc


@router.get(
    "/logistics/sales-to-stock-sheet/preview/{job_id}",
    response_model=LogisticsSalesJobResponse,
)
async def logistics_sales_preview_status(job_id: str):
    try:
        return await cached_logistics_sales_workflow.job_status(job_id)
    except LogisticsWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/logistics/sales-to-stock-sheet/execute",
    response_model=LogisticsSalesJobResponse,
)
async def execute_logistics_sales_workflow(request: LogisticsSalesExecuteRequest):
    """Queue writing a previously confirmed preview into the local workbook copy."""
    try:
        return await cached_logistics_sales_workflow.start_execute(request.preview_id)
    except (McpError, LogisticsWorkflowError) as exc:
        detail = str(exc) or "物流销量写入前校验失败"
        logger.warning("Logistics sales workflow execution rejected: %s", detail)
        raise HTTPException(status_code=422, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=423, detail="本地测试表正在使用或没有写入权限") from exc
    except Exception as exc:
        logger.exception("Logistics sales workflow execution failed")
        raise HTTPException(status_code=500, detail="物流销量写入失败") from exc


@router.get(
    "/logistics/sales-to-stock-sheet/execute/{job_id}",
    response_model=LogisticsSalesJobResponse,
)
async def logistics_sales_execute_status(job_id: str):
    try:
        return await cached_logistics_sales_workflow.job_status(job_id)
    except LogisticsWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
