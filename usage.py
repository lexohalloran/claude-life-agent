"""Per-call token usage logging.

Appends one JSON line per Anthropic API call to data/usage_log.jsonl. This is
the raw material for answering questions like "how much is prompt caching
actually saving me" and "did shrinking claude_notes.md move the needle" —
questions the Anthropic dashboard can only answer in aggregate.

Note that one user message may produce several API calls (one per tool-use
round), so lines outnumber conversations.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import config

logger = logging.getLogger(__name__)


def log_call(response: Any, source: str, round_num: int) -> None:
    """Append usage stats for one API call.

    Deliberately swallows all errors: metrics are observational and must never
    break an in-flight conversation.
    """
    try:
        u = response.usage
        entry = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "source": source,
            "model": config.MODEL,
            "round": round_num,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_creation_input_tokens": u.cache_creation_input_tokens or 0,
            "cache_read_input_tokens": u.cache_read_input_tokens or 0,
        }
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with config.USAGE_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to log usage — continuing")
