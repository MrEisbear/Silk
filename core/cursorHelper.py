import base64
from datetime import datetime
from typing import Any

def create_cursor(timestamp: datetime, row_id: int) -> str:
    """
    Converts a timestamp and ID into a base64 encoded string.
    Example: 2026-02-17 20:00:00, 84722 -> 'MjAyNi0wMi0xNyAyMDowMDowMHw4NDcyMg=='
    """
    # Using a pipe separator as it's unlikely to appear in dates/IDs
    cursor_str = f"{timestamp}|{row_id}"
    return base64.urlsafe_b64encode(cursor_str.encode()).decode().strip("=")

def parse_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
    """
    Decodes the cursor string back into (timestamp, row_id).
    Returns (None, None) if the cursor is missing or invalid.
    """
    if not cursor:
        return None, None
    
    try:
        # Re-add padding if it was stripped
        padding = len(cursor) % 4
        if padding:
            cursor += "=" * (4 - padding)
            
        decoded = base64.urlsafe_b64decode(cursor).decode().split("|")
        ts_str: str
        row_id_str: str
        ts_str, row_id_str = decoded
        return datetime.fromisoformat(ts_str), int(row_id_str)
    except Exception:
        # If someone sends a garbage string, return None to fallback to "page 1"
        return None, None