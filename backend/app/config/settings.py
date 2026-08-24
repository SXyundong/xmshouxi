"""集中管理配置。所有配置从 .env 读取，未来可替换为配置文件或配置中心。"""

import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
