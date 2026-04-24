"""Shared utility functions."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import config

logger = logging.getLogger(__name__)

_FALLBACK_SYSTEM_PROMPT = "You are a helpful personal assistant."


def build_system_prompt() -> list[dict[str, Any]]:
    """Assemble the system prompt as a list of cached content blocks.

    Each section (base, notes, life doc) gets its own cache_control breakpoint.
    This means a change to the life doc only invalidates the life doc cache entry —
    the base prompt and notes remain cache hits, paying ~10% of normal input cost.
    """
    base = _read_file(config.SYSTEM_PROMPT_FILE, _FALLBACK_SYSTEM_PROMPT)
    notes = _read_file(config.CLAUDE_NOTES_FILE, "")
    life_doc = _read_file(config.LIFE_DOC_FILE, "")

    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": base,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if notes.strip():
        blocks.append({
            "type": "text",
            "text": "\n\n---\n\n## Your notes on the user\n\n" + notes,
            "cache_control": {"type": "ephemeral"},
        })
    if life_doc.strip():
        blocks.append({
            "type": "text",
            "text": "\n\n---\n\n## Life doc\n\n" + life_doc,
            "cache_control": {"type": "ephemeral"},
        })

    return blocks


def format_datetime(dt: datetime) -> str:
    """Format a datetime as 'Monday, April 20, 2026, 2:32 PM PDT'.

    Uses explicit day/hour integers to avoid platform differences with
    strftime's %-d and %-I directives (not available on Windows).
    """
    hour = dt.hour % 12 or 12
    am_pm = "AM" if dt.hour < 12 else "PM"
    return (
        f"{dt.strftime('%A, %B')} {dt.day}, {dt.year}, "
        f"{hour}:{dt.strftime('%M')} {am_pm} {dt.strftime('%Z')}"
    )


def now_local() -> datetime:
    """Return the current time in the configured local timezone."""
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _read_file(path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("%s not found, using fallback", path.name)
        return fallback
