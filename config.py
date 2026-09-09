import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

SYSTEM_PROMPT_FILE = CONFIG_DIR / "system_prompt.md"
CLAUDE_NOTES_FILE = DATA_DIR / "claude_notes.md"
LIFE_DOC_FILE = DATA_DIR / "life_doc.md"
CONVERSATION_LOG_FILE = DATA_DIR / "conversation_log.json"
SCHEDULE_FILE = DATA_DIR / "schedule.json"
USAGE_LOG_FILE = DATA_DIR / "usage_log.jsonl"
CONVERSATION_SUMMARIES_FILE = DATA_DIR / "conversation_summaries.md"
MAINTENANCE_STATE_FILE = DATA_DIR / "maintenance_state.json"

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or "0")

# Conversation: history is every message not yet covered by a day summary.
# This is only a runaway guard for when the maintenance pass has been failing.
CONVERSATION_MAX_MESSAGES = int(os.getenv("CONVERSATION_MAX_MESSAGES", "200"))

# How many past days of summaries to carry in the system prompt
CONVERSATION_SUMMARY_DAYS = int(os.getenv("CONVERSATION_SUMMARY_DAYS", "14"))

# Scheduler: messages overdue by more than this are dropped rather than sent
SCHEDULER_GRACE_PERIOD_HOURS = float(os.getenv("SCHEDULER_GRACE_PERIOD_HOURS", "24"))

# Daily maintenance pass runs at the first tick on or after this local hour
MAINTENANCE_HOUR = int(os.getenv("MAINTENANCE_HOUR", "4"))

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")
