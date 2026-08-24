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
    r"\\192.168.12.158\e\备货逻辑看板表.xlsx",
)
SMB_USERNAME = os.getenv("SMB_USERNAME", "")
SMB_PASSWORD = os.getenv("SMB_PASSWORD", "")
