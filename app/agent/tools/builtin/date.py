from datetime import datetime

from app.agent.tools.registry import tool


@tool(name="date")
def get_date() -> str:
    """Get the current local date, time, and timezone (e.g. '2026-04-06 14:30:00 ICT')."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
