import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

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


@router.post(
    "/logistics/sales-to-stock-sheet/export",
    response_model=LogisticsSalesJobResponse,
)
async def export_logistics_sales_workbook(
    request: LogisticsSalesPreviewRequest | None = None,
):
    """Generate a temporary workbook from PostgreSQL, without a local file path."""
    try:
        return await cached_logistics_sales_workflow.start_export(
            force_refresh=bool(request and request.force_refresh)
        )
    except (McpError, LogisticsWorkflowError) as exc:
        detail = str(exc) or "物流销量 Excel 导出失败，请检查数据库和领星配置"
        logger.warning("Logistics sales workbook export rejected: %s", detail)
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:
        logger.exception("Logistics sales workbook export failed")
        raise HTTPException(status_code=500, detail="物流销量 Excel 导出失败") from exc


@router.get(
    "/logistics/sales-to-stock-sheet/export/{job_id}",
    response_model=LogisticsSalesJobResponse,
)
async def logistics_sales_export_status(job_id: str):
    try:
        return await cached_logistics_sales_workflow.job_status(job_id)
    except LogisticsWorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/logistics/sales-to-stock-sheet/export/{job_id}/download",
)
async def download_logistics_sales_workbook(job_id: str):
    artifact = cached_logistics_sales_workflow.get_export_file(job_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Excel 文件不存在或已过期，请重新生成")
    content, filename = artifact
    encoded_filename = quote(filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="logistics-stock-export.xlsx"; '
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "no-store, max-age=0",
        },
    )
