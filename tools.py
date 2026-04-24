"""Tool definitions and implementations for the life agent.

Each tool has two parts:
  - A schema dict (passed to the Anthropic API so Claude knows what's available)
  - An implementation function (called locally when Claude invokes the tool)

Phase 4 tools: read/append life_doc, read/edit claude_notes.
Phase 5 tools: schedule_message, cancel_scheduled_message, list_scheduled_messages.
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas (passed to the API)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_life_doc",
        "description": (
            "Read the full contents of the user's life doc — current life context, "
            "priorities, and ongoing situations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "append_to_life_doc",
        "description": (
            "Append a new entry to the user's life doc. Use this to record something "
            "worth keeping in the persistent life context. A timestamp header is "
            "added automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The markdown content to append.",
                }
            },
            "required": ["content"],
        },
    },
    {
        "name": "read_claude_notes",
        "description": (
            "Read the full contents of your notes about the user — preferences, "
            "patterns, and things worth remembering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "edit_claude_notes",
        "description": (
            "Replace the full contents of your notes about the user. Use this to "
            "add, update, or remove notes. You must include all notes you want "
            "to keep — this overwrites the file entirely."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "new_content": {
                    "type": "string",
                    "description": "The complete new contents of the notes file.",
                }
            },
            "required": ["new_content"],
        },
    },
    {
        "name": "schedule_message",
        "description": (
            "Schedule a proactive message to the user at a future time. "
            "Use the current timestamp (injected at the top of every message) "
            "to reason about when the message should fire. "
            "Maximum 1 year in the future."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "when": {
                    "type": "string",
                    "description": "ISO 8601 datetime string for when to send the message.",
                },
                "context": {
                    "type": "string",
                    "description": (
                        "A note to your future self about why this was scheduled "
                        "and what to say or ask."
                    ),
                },
            },
            "required": ["when", "context"],
        },
    },
    {
        "name": "cancel_scheduled_message",
        "description": "Cancel a previously scheduled message by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The ID of the scheduled message to cancel.",
                }
            },
            "required": ["id"],
        },
    },
    {
        "name": "list_scheduled_messages",
        "description": "List all pending scheduled messages.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Phase 4 implementations: life doc and notes
# ---------------------------------------------------------------------------

def read_life_doc() -> str:
    logger.info("Tool call: read_life_doc")
    try:
        content = config.LIFE_DOC_FILE.read_text(encoding="utf-8")
        return content if content.strip() else "(Life doc is empty)"
    except FileNotFoundError:
        return "(Life doc does not exist yet)"


def append_to_life_doc(content: str) -> str:
    logger.info("Tool call: append_to_life_doc (%d chars)", len(content))
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    entry = f"\n\n---\n*Added {timestamp}*\n\n{content.strip()}\n"
    with config.LIFE_DOC_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)
    return f"Appended to life doc ({len(content)} chars)."


def read_claude_notes() -> str:
    logger.info("Tool call: read_claude_notes")
    try:
        content = config.CLAUDE_NOTES_FILE.read_text(encoding="utf-8")
        return content if content.strip() else "(Notes file is empty)"
    except FileNotFoundError:
        return "(Notes file does not exist yet)"


def edit_claude_notes(new_content: str) -> str:
    logger.info("Tool call: edit_claude_notes (%d chars)", len(new_content))
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.CLAUDE_NOTES_FILE.write_text(new_content, encoding="utf-8")
    return f"Notes updated ({len(new_content)} chars)."


# ---------------------------------------------------------------------------
# Phase 5 implementations: scheduling
# ---------------------------------------------------------------------------

def schedule_message(when: str, context: str) -> str:
    logger.info("Tool call: schedule_message when=%s", when)

    # Parse and validate the requested time
    try:
        fire_at = datetime.fromisoformat(when)
        if fire_at.tzinfo is None:
            # Assume local timezone if none provided
            fire_at = fire_at.replace(tzinfo=ZoneInfo(config.TIMEZONE))
    except ValueError:
        return f"Error: could not parse '{when}' as an ISO 8601 datetime."

    now = datetime.now(timezone.utc)

    if fire_at <= now:
        return "Error: scheduled time must be in the future."

    if fire_at > now + timedelta(days=365):
        return "Error: cannot schedule more than 1 year in the future."

    # Enforce minimum 10-minute gap between scheduled messages
    schedule = _read_schedule()
    for entry in schedule:
        existing = datetime.fromisoformat(entry["when"])
        gap = abs((fire_at - existing).total_seconds())
        if gap < 600:
            existing_local = existing.astimezone(ZoneInfo(config.TIMEZONE))
            return (
                f"Error: too close to an existing scheduled message at "
                f"{existing_local.strftime('%Y-%m-%d %H:%M %Z')} "
                f"(minimum gap is 10 minutes). Please choose a different time."
            )

    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "when": fire_at.isoformat(),
        "context": context,
        "scheduled_at": now.isoformat(),
    }
    schedule.append(entry)
    _write_schedule(schedule)

    fire_local = fire_at.astimezone(ZoneInfo(config.TIMEZONE))
    logger.info("Scheduled message id=%s for %s", entry["id"], fire_local)
    return f"Scheduled. ID: {entry['id']}. Will fire at {fire_local.strftime('%Y-%m-%d %H:%M %Z')}."


def cancel_scheduled_message(message_id: str) -> str:
    logger.info("Tool call: cancel_scheduled_message id=%s", message_id)
    schedule = _read_schedule()
    updated = [e for e in schedule if e["id"] != message_id]
    if len(updated) == len(schedule):
        return f"Error: no scheduled message with ID '{message_id}'."
    _write_schedule(updated)
    return f"Cancelled scheduled message {message_id}."


def list_scheduled_messages() -> str:
    logger.info("Tool call: list_scheduled_messages")
    schedule = _read_schedule()
    if not schedule:
        return "No messages currently scheduled."
    tz = ZoneInfo(config.TIMEZONE)
    lines = []
    for entry in sorted(schedule, key=lambda e: e["when"]):
        fire_at = datetime.fromisoformat(entry["when"]).astimezone(tz)
        lines.append(
            f"- ID {entry['id']}\n"
            f"  When: {fire_at.strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"  Context: {entry['context']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schedule file helpers
# ---------------------------------------------------------------------------

def _read_schedule() -> list[dict[str, Any]]:
    if not config.SCHEDULE_FILE.exists():
        return []
    try:
        text = config.SCHEDULE_FILE.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else []
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read schedule file: %s", e)
        return []


def _write_schedule(schedule: list[dict[str, Any]]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SCHEDULE_FILE.write_text(
        json.dumps(schedule, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Call the named tool with the given input and return a string result."""
    match tool_name:
        case "read_life_doc":
            return read_life_doc()
        case "append_to_life_doc":
            return append_to_life_doc(tool_input["content"])
        case "read_claude_notes":
            return read_claude_notes()
        case "edit_claude_notes":
            return edit_claude_notes(tool_input["new_content"])
        case "schedule_message":
            return schedule_message(tool_input["when"], tool_input["context"])
        case "cancel_scheduled_message":
            return cancel_scheduled_message(tool_input["id"])
        case "list_scheduled_messages":
            return list_scheduled_messages()
        case _:
            logger.warning("Unknown tool called: %s", tool_name)
            return f"Error: unknown tool '{tool_name}'"
