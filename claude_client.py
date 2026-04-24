"""Wrapper around the Anthropic SDK.

send_message handles the full tool-use loop: Claude may call tools zero or
more times before producing its final text reply. Each round trip looks like:

  1. We send messages → Claude responds with tool_use blocks
  2. We execute the tools locally and send back tool_result blocks
  3. Repeat until Claude responds with stop_reason "end_turn" and a text block
"""

import logging
import time
from typing import Any

import anthropic

import config
import tools

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Safety limit — if Claude keeps calling tools without producing a reply,
# something has gone wrong. Stop and surface an error rather than looping forever.
MAX_TOOL_ROUNDS = 10

# Transient errors are retried once after a short delay.
RETRY_DELAY_SECONDS = 2
_RETRYABLE = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)


def send_message(
    system_prompt: str | list[dict[str, Any]],
    history: list[dict[str, Any]],
    user_message: str,
) -> str:
    """Send a message to Claude and return the final text response.

    Handles the tool-use loop transparently: tool calls are executed and
    fed back to Claude until it produces a plain text reply.

    Raises anthropic.APIError subclasses on failure so callers can send
    appropriate user-facing messages.
    """
    messages: list[dict[str, Any]] = history + [
        {"role": "user", "content": user_message}
    ]

    for round_num in range(MAX_TOOL_ROUNDS):
        logger.info(
            "Calling Claude API (model=%s, history_len=%d, round=%d)",
            config.MODEL, len(messages) - 1, round_num,
        )

        response = _api_call_with_retry(messages, system_prompt)

        logger.info("Claude stop_reason=%s", response.stop_reason)

        if response.stop_reason == "end_turn":
            # Extract the text block from the response
            for block in response.content:
                if block.type == "text":
                    logger.info("Claude replied (%d chars)", len(block.text))
                    return block.text
            # end_turn with no text block — shouldn't happen, but handle it
            logger.warning("end_turn with no text block")
            return "(No response)"

        if response.stop_reason == "tool_use":
            # Execute each tool Claude requested and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call: %s input=%s", block.name, block.input)
                    result = tools.dispatch(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Append Claude's response (with tool_use blocks) and our results.
            # Convert SDK content block objects to plain dicts — the API expects
            # ContentBlockParam dicts, not Pydantic model objects.
            messages.append({
                "role": "assistant",
                "content": [b.model_dump() for b in response.content],
            })
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        logger.error("Unexpected stop_reason: %s", response.stop_reason)
        return "(Unexpected response from Claude)"

    logger.error("Tool-use loop exceeded MAX_TOOL_ROUNDS=%d", MAX_TOOL_ROUNDS)
    return "(Claude made too many tool calls without responding — something went wrong)"


def _api_call_with_retry(
    messages: list[dict[str, Any]],
    system_prompt: str | list[dict[str, Any]],
) -> anthropic.types.Message:
    """Make one API call, retrying once on transient errors."""
    try:
        return _client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=tools.TOOL_SCHEMAS,
            messages=messages,
        )
    except _RETRYABLE as e:
        logger.warning("Transient API error (%s), retrying in %ds", type(e).__name__, RETRY_DELAY_SECONDS)
        time.sleep(RETRY_DELAY_SECONDS)
        return _client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=tools.TOOL_SCHEMAS,
            messages=messages,
        )
