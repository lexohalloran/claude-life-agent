"""Conversation log: load, append, and trim message history.

Storage format (conversation_log.json): a JSON array of objects:
  {
    "role": "user" | "assistant",
    "content": "...",
    "timestamp": "2026-04-20T14:32:00-07:00",
    "source": "telegram" | "scheduled"   # optional
  }

The API only wants role + content; timestamps and metadata are for our
own record-keeping.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import config

logger = logging.getLogger(__name__)


def load_history() -> list[dict[str, Any]]:
    """Return the last N messages from the log, ready to pass to the API.

    Returns a list of {"role": ..., "content": ...} dicts with no extra fields,
    trimmed to CONVERSATION_HISTORY_LIMIT.
    """
    raw = _read_log()
    trimmed = raw[-config.CONVERSATION_HISTORY_LIMIT:]
    return [{"role": m["role"], "content": m["content"]} for m in trimmed]


def append_message(role: str, content: str, source: str | None = None) -> None:
    """Append a single message to the conversation log."""
    raw = _read_log()
    entry: dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": _now_iso(),
    }
    if source:
        entry["source"] = source
    raw.append(entry)
    _write_log(raw)
    logger.debug("Appended %s message to log (total=%d)", role, len(raw))


def _read_log() -> list[dict[str, Any]]:
    if not config.CONVERSATION_LOG_FILE.exists():
        return []
    try:
        text = config.CONVERSATION_LOG_FILE.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else []
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read conversation log: %s", e)
        return []


def _write_log(messages: list[dict[str, Any]]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.CONVERSATION_LOG_FILE.write_text(
        json.dumps(messages, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()
