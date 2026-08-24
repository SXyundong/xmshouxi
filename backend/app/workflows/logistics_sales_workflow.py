"""Fetch rolling SKU sales from LingXing and write them into the stock workbook."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from numbers import Number
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
import smbclient

from app.config import settings
from app.core.mcp_client import McpError, StreamableHttpMcpClient


class LogisticsWorkflowError(RuntimeError):
    pass


class LogisticsSalesWorkflow:
    SKU = "70017-3"
    PRODUCT_NAME = "健腹轮（黑色）"
    PERIODS = (3, 7, 15, 30)
    SHEET_NAME = "Sheet1"
    TARGET_RANGE = "AJ156:AM156"
    SKU_CELL = "A156"
    PRODUCT_CELL = "C156"
    _write_lock = asyncio.Lock()

    def __init__(self):
        self.client = StreamableHttpMcpClient(
            settings.LINGXING_MCP_URL,
            settings.LINGXING_MCP_KEY,
        )

    async def run(self) -> dict[str, Any]:
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        sales: dict[int, int] = {}
        for index, days in enumerate(self.PERIODS):
            if index:
                # LingXing documents a per-tool QPS limit of 1.
                await asyncio.sleep(1.05)
            start = today - timedelta(days=days - 1)
            payload = await self.client.call_tool(
                "query_product_performance_asin_lists",
                {
                    "offset": 0,
                    "length": 100,
                    "start_date": start.isoformat(),
                    "end_date": today.isoformat(),
                    "date_type": "purchase",
                    "search_field": "local_sku",
                    "search_value": [self.SKU],
                    "summary_field": "sku",
                    "summary_field_level1": "sku",
                    "turn_on_summary": 1,
                    "date_view_order_type": 0,
                    "sort_field": "volume",
                    "sort_type": "desc",
                },
            )
            sales[days] = self._extract_volume(payload)

        async with self._write_lock:
            await asyncio.to_thread(self._write_workbook, sales)

        return {
            "sku": self.SKU,
            "product_name": self.PRODUCT_NAME,
            "sales": {f"days_{days}": sales[days] for days in self.PERIODS},
            "workbook": settings.STOCK_WORKBOOK_PATH.rsplit("\\", 1)[-1],
            "sheet": self.SHEET_NAME,
            "range": self.TARGET_RANGE,
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
                timespec="seconds"
            ),
        }

    def _extract_volume(self, payload: Any) -> int:
        if not isinstance(payload, dict):
            raise LogisticsWorkflowError("领星销售数据格式异常")
        if payload.get("code") not in (None, 0):
            raise LogisticsWorkflowError(payload.get("message", "领星查询失败"))

        data = payload.get("data")
        if isinstance(data, dict) and data.get("code") not in (None, 0):
            raise LogisticsWorkflowError(data.get("msg", "领星查询失败"))

        candidates: list[int] = []

        def walk(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return

            identifiers = {
                str(value.get(key, "")).strip()
                for key in ("local_sku", "sku", "localSku")
            }
            if self.SKU in identifiers:
                for key in ("volume", "sales_volume", "salesVolume", "quantity"):
                    number = value.get(key)
                    if isinstance(number, Number) and not isinstance(number, bool):
                        candidates.append(int(number))
                        break
                    if isinstance(number, str) and number.replace(".", "", 1).isdigit():
                        candidates.append(int(float(number)))
                        break
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)

        walk(data)
        if len(candidates) != 1:
            raise LogisticsWorkflowError(
                f"无法唯一确定 SKU {self.SKU} 的销量（匹配到 {len(candidates)} 条）"
            )
        if candidates[0] < 0:
            raise LogisticsWorkflowError("领星返回了负数销量，已中止写入")
        return candidates[0]

    def _write_workbook(self, sales: dict[int, int]) -> None:
        target_text = settings.STOCK_WORKBOOK_PATH
        target = Path(target_text)
        is_local = target.exists()
        if not is_local:
            self._connect_smb(target_text)

        local_fd, local_name = tempfile.mkstemp(suffix=".xlsx")
        os.close(local_fd)
        if is_local:
            shutil.copy2(target, local_name)
        else:
            try:
                with smbclient.open_file(target_text, mode="rb") as source:
                    with open(local_name, "wb") as destination:
                        shutil.copyfileobj(source, destination)
            except OSError as exc:
                raise LogisticsWorkflowError(f"无法读取备货表：{target_text}") from exc

        try:
            workbook = load_workbook(local_name)
        except Exception as exc:
            os.unlink(local_name)
            raise LogisticsWorkflowError("备货表不是可读取的 xlsx 文件") from exc
        try:
            if self.SHEET_NAME not in workbook.sheetnames:
                raise LogisticsWorkflowError(f"工作表 {self.SHEET_NAME} 不存在")
            sheet = workbook[self.SHEET_NAME]
            actual_sku = str(sheet[self.SKU_CELL].value or "").strip()
            actual_name = str(sheet[self.PRODUCT_CELL].value or "").strip()
            if actual_sku != self.SKU or actual_name != self.PRODUCT_NAME:
                raise LogisticsWorkflowError(
                    f"目标行校验失败：当前为 {actual_sku} / {actual_name}"
                )

            for column, days in zip(("AJ", "AK", "AL", "AM"), self.PERIODS):
                sheet[f"{column}156"] = sales[days]

            workbook.save(local_name)
        except Exception:
            if os.path.exists(local_name):
                os.unlink(local_name)
            raise
        finally:
            workbook.close()

        try:
            if is_local:
                temp_fd, temp_name = tempfile.mkstemp(
                    prefix=f".{target.stem}-", suffix=".xlsx", dir=target.parent
                )
                os.close(temp_fd)
                shutil.copy2(local_name, temp_name)
                try:
                    backup = target.with_suffix(".workflow-backup.xlsx")
                    shutil.copy2(target, backup)
                    os.replace(temp_name, target)
                finally:
                    if os.path.exists(temp_name):
                        os.unlink(temp_name)
            else:
                backup = target_text.rsplit(".", 1)[0] + ".workflow-backup.xlsx"
                remote_temp = target_text.rsplit("\\", 1)[0] + f"\\.workflow-{uuid.uuid4().hex}.xlsx"
                smbclient.copyfile(target_text, backup)
                try:
                    with open(local_name, "rb") as source:
                        with smbclient.open_file(remote_temp, mode="wb") as destination:
                            shutil.copyfileobj(source, destination)
                    smbclient.replace(remote_temp, target_text)
                finally:
                    try:
                        smbclient.remove(remote_temp)
                    except OSError:
                        pass
        finally:
            if os.path.exists(local_name):
                os.unlink(local_name)

    @staticmethod
    def _connect_smb(target: str) -> None:
        if not target.startswith("\\\\"):
            raise LogisticsWorkflowError(f"无法访问备货表：{target}")
        if not settings.SMB_USERNAME or not settings.SMB_PASSWORD:
            raise LogisticsWorkflowError(
                "Docker 无法继承 Windows 网络共享登录，请配置 SMB_USERNAME 和 SMB_PASSWORD"
            )
        server = target.lstrip("\\").split("\\", 1)[0]
        try:
            smbclient.register_session(
                server,
                username=settings.SMB_USERNAME,
                password=settings.SMB_PASSWORD,
            )
        except OSError as exc:
            raise LogisticsWorkflowError("连接备货表 SMB 共享失败") from exc


logistics_sales_workflow = LogisticsSalesWorkflow()


__all__ = [
    "LogisticsSalesWorkflow",
    "LogisticsWorkflowError",
    "McpError",
    "logistics_sales_workflow",
]
