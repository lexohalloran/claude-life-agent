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

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or "0")

# Conversation
CONVERSATION_HISTORY_LIMIT = int(os.getenv("CONVERSATION_HISTORY_LIMIT", "20"))

# Scheduler: messages overdue by more than this are dropped rather than sent
SCHEDULER_GRACE_PERIOD_HOURS = float(os.getenv("SCHEDULER_GRACE_PERIOD_HOURS", "24"))

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")
