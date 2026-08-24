from app.tools.base_tool import BaseTool


class LingxingSalesTool(BaseTool):
    """模拟调用领星销售 API。当前返回 mock 数据，未来替换为真实 API 即可。"""

    name = "lingxing_sales"
    description = "查询领星销售数据（mock）"

    async def execute(self, *args, **kwargs):
        # TODO: 替换为真实领星 API 调用
        return {
            "sales_amount": 10000,
            "orders": 200,
            "top_products": ["SKU001", "SKU002"],
        }
