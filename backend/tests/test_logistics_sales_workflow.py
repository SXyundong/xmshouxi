import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from app.workflows.logistics_sales_workflow import (
    LogisticsSalesWorkflow,
    LogisticsWorkflowError,
)


class LogisticsSalesWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = LogisticsSalesWorkflow()

    def test_extracts_single_exact_sku_volume(self):
        payload = {
            "code": 0,
            "data": {"list": [{"local_sku": "70017-3", "volume": 163}]},
        }
        self.assertEqual(self.workflow._extract_volume(payload), 163)

    def test_rejects_lingxing_permission_error(self):
        payload = {
            "code": 0,
            "data": {"code": 8002, "msg": "暂无产品表现查看权限"},
        }
        with self.assertRaisesRegex(LogisticsWorkflowError, "暂无产品表现查看权限"):
            self.workflow._extract_volume(payload)

    def test_writes_only_target_cells_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "备货逻辑看板表.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Sheet1"
            sheet["A156"] = "70017-3"
            sheet["C156"] = "健腹轮（黑色）"
            sheet["B156"] = "must-stay"
            workbook.save(target)
            workbook.close()

            sales = {3: 10, 7: 20, 15: 30, 30: 40}
            with patch(
                "app.workflows.logistics_sales_workflow.settings.STOCK_WORKBOOK_PATH",
                str(target),
            ):
                self.workflow._write_workbook(sales)

            result = load_workbook(target, data_only=False)
            try:
                sheet = result["Sheet1"]
                self.assertEqual(
                    [sheet[cell].value for cell in ("AJ156", "AK156", "AL156", "AM156")],
                    [10, 20, 30, 40],
                )
                self.assertEqual(sheet["B156"].value, "must-stay")
            finally:
                result.close()
            self.assertTrue(target.with_suffix(".workflow-backup.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
