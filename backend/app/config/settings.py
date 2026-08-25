"""集中管理配置。所有配置从 .env 读取，未来可替换为配置文件或配置中心。"""

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
LINGXING_MCP_URL = os.getenv(
    "LINGXING_MCP_URL",
    "https://openmcp.lingxing.com/mcp-servers/lingxing-mcp",
)
LINGXING_MCP_KEY = os.getenv("LINGXING_MCP_KEY", "")
STOCK_WORKBOOK_PATH = os.getenv(
    "STOCK_WORKBOOK_PATH",
    r"C:\Users\Administrator\Desktop\物流工作流测试1\备货逻辑看板表.xlsx",
)
LOGISTICS_SALES_DB_PATH = os.getenv(
    "LOGISTICS_SALES_DB_PATH",
    r"C:\Users\Administrator\Desktop\物流工作流测试\logistics_sales.sqlite3",
)
LOGISTICS_INITIAL_SYNC_DAYS = int(os.getenv("LOGISTICS_INITIAL_SYNC_DAYS", "60"))
LOGISTICS_LOOKBACK_DAYS = int(os.getenv("LOGISTICS_LOOKBACK_DAYS", "30"))
NETWORK_WORKBOOK_WRITE_ENABLED = os.getenv(
    "NETWORK_WORKBOOK_WRITE_ENABLED",
    "false",
).lower() in {"1", "true", "yes", "on"}
