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

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))).strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).strip()
LLM_MODEL = os.getenv("LLM_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")).strip()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
LLM_MOCK_ENABLED = os.getenv("LLM_MOCK_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
FEISHU_SSO_REQUIRED = os.getenv("FEISHU_SSO_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}
WORKFLOW_AUTH_URL = os.getenv(
    "WORKFLOW_AUTH_URL", "https://ergolife-feishu-workflow-production.up.railway.app"
).rstrip("/")
AGENT_SSO_SHARED_SECRET = os.getenv("AGENT_SSO_SHARED_SECRET", "").strip()
FEISHU_SESSION_SECRET = os.getenv("FEISHU_SESSION_SECRET", AGENT_SSO_SHARED_SECRET or "local-demo-session-secret")
FEISHU_SESSION_MAX_AGE = int(os.getenv("FEISHU_SESSION_MAX_AGE", "28800"))

# Backward-compatible aliases for local integrations that still import the old names.
OPENAI_API_KEY = LLM_API_KEY
OPENAI_BASE_URL = LLM_BASE_URL
MODEL = LLM_MODEL
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
# Portable workbook template used by the download-only logistics export.  The
# template is bundled with the backend image so Railway never needs access to a
# user's desktop or a private network share.
LOGISTICS_EXPORT_TEMPLATE_PATH = os.getenv(
    "LOGISTICS_EXPORT_TEMPLATE_PATH",
    "",
).strip()
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
