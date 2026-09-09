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
import tools

logger = logging.getLogger(__name__)


def load_history() -> list[dict[str, Any]]:
    """Return every message not yet covered by a day summary.

    Summarized days are carried in the system prompt instead, so the split is
    driven by what the maintenance pass has actually written rather than by a
    message count. Yesterday isn't summarized until the pass runs the following
    morning, so between midnight and then its messages are still sent verbatim —
    and if the pass fails for a few days, its days keep being sent rather than
    silently vanishing.

    Returns {"role", "content"} dicts with no extra fields.
    """
    raw = _read_log()
    if not raw:
        return []

    cutoff = tools.last_summarized_date()
    if cutoff is None:
        trimmed = raw
    else:
        start = next(
            (i for i, m in enumerate(raw) if (d := _local_date(m)) and d > cutoff),
            len(raw),
        )
        trimmed = raw[start:]

    # Runaway guard: a long maintenance outage would otherwise send every
    # message since it broke.
    trimmed = trimmed[-config.CONVERSATION_MAX_MESSAGES:]

    # The API rejects a first message that isn't a user turn. Messages are
    # logged in user/assistant pairs, but a pair can straddle midnight and put
    # an assistant turn first.
    while trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]

    return [{"role": m["role"], "content": m["content"]} for m in trimmed]


def messages_for_date(date_iso: str) -> list[dict[str, Any]]:
    """Return every logged message whose local timestamp falls on `date_iso`.

    Used by the daily maintenance pass to summarize a day. Entries predating
    timestamped logging, or with unparseable timestamps, are skipped.
    """
    return [m for m in _read_log() if _local_date(m) == date_iso]


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


def _local_date(message: dict[str, Any]) -> str | None:
    """Local calendar date of a logged message, or None if it has no usable stamp."""
    stamp = message.get("timestamp")
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).astimezone().date().isoformat()
    except ValueError:
        return None


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
