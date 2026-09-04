import re
from datetime import date, timedelta

from app.db.session import SessionLocal
from app.services.lingxing_analysis_queries import summarize
from app.tools.base_tool import BaseTool


class LingxingSalesTool(BaseTool):
    """Provide Agent-safe summaries from the local LingXing analysis views."""

    name = "lingxing_sales"
    description = "查询本地领星销量、利润和库存汇总"

    async def execute(self, *args, **kwargs):
        message = str(args[0] if args else kwargs.get("message", ""))
        dates = re.findall(r"20\d{2}-\d{2}-\d{2}", message)
        end_date = date.fromisoformat(dates[-1]) if dates else date.today()
        start_date = date.fromisoformat(dates[0]) if len(dates) >= 2 else end_date - timedelta(days=30)
        msku = _extract_msku(message, dates)
        session = SessionLocal()
        try:
            return summarize(session, start_date, end_date, msku)
        finally:
            session.close()


def _extract_msku(message: str, date_tokens: list[str] | None = None) -> str | None:
    date_tokens = date_tokens or re.findall(r"20\d{2}-\d{2}-\d{2}", message)
    for match in re.finditer(r"\b[A-Za-z0-9][A-Za-z0-9._-]{5,}\b", message):
        candidate = match.group(0)
        if candidate in date_tokens:
            continue
        if any(char.isdigit() for char in candidate):
            return candidate
    return None
