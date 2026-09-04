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
        start_date, end_date = _resolve_date_range(message, dates)
        msku = _extract_msku(message, dates)
        session = SessionLocal()
        try:
            return summarize(session, start_date, end_date, msku)
        finally:
            session.close()


def _resolve_date_range(message: str, date_tokens: list[str] | None = None) -> tuple[date, date]:
    date_tokens = date_tokens or re.findall(r"20\d{2}-\d{2}-\d{2}", message)
    if len(date_tokens) >= 2:
        return date.fromisoformat(date_tokens[0]), date.fromisoformat(date_tokens[-1])
    if len(date_tokens) == 1:
        parsed = date.fromisoformat(date_tokens[0])
        return parsed, parsed
    today = date.today()
    if re.search(r"昨天|昨日", message):
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    if re.search(r"今天|今日", message):
        return today, today
    return today - timedelta(days=30), today


def _extract_msku(message: str, date_tokens: list[str] | None = None) -> str | None:
    date_tokens = date_tokens or re.findall(r"20\d{2}-\d{2}-\d{2}", message)
    for match in re.finditer(r"\b[A-Za-z0-9][A-Za-z0-9._-]{5,}\b", message):
        candidate = match.group(0)
        if candidate in date_tokens:
            continue
        if any(char.isdigit() for char in candidate):
            return candidate
    return None
