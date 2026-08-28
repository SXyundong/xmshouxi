"""集中管理配置。所有配置从 .env 读取，未来可替换为配置文件或配置中心。"""

import os

from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(value: str) -> str:
    """Use the installed psycopg 3 driver for Railway's plain URL format."""
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    return value

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
DATABASE_URL = _normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://ecommerce:ecommerce@localhost:5432/ecommerce_agent",
    ).strip()
)
DB_ECHO = os.getenv("DB_ECHO", "false").lower() in {"1", "true", "yes", "on"}
LINGXING_MCP_URL = os.getenv(
    "LINGXING_MCP_URL",
    "https://openmcp.lingxing.com/mcp-servers/lingxing-mcp",
)
LINGXING_MCP_KEY = os.getenv("LINGXING_MCP_KEY", "")
STOCK_WORKBOOK_PATH = os.getenv(
    "STOCK_WORKBOOK_PATH",
    r"C:\Users\Administrator\Desktop\物流工作流测试3\备货逻辑看板表.xlsx",
)
# Deprecated: retained only for backward-compatible local tooling. The runtime
# sales cache is now stored in PostgreSQL.
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
