# CLAUDE.md

Personal Telegram AI agent for Lex. Full spec in SPEC.md.

## Status

All 5 feature phases complete. Phase 6 (Linux deployment + systemd) is next.

## Architecture

```
main.py            — entry point; runs Telegram bot + scheduler concurrently
telegram_bot.py    — Telegram message routing, allowlist, typing indicator
claude_client.py   — Anthropic SDK wrapper with tool-use loop and retry logic
tools.py           — tool schemas + implementations (memory + scheduling)
scheduler.py       — asyncio background loop that fires scheduled messages
conversation.py    — read/write/trim conversation_log.json
utils.py           — shared helpers: system prompt assembly, datetime formatting
config.py          — all constants loaded from .env
```

## File layout

- `config/system_prompt.md` — base agent instructions (versioned, user-edited)
- `data/` — gitignored; contains claude_notes.md, life_doc.md, conversation_log.json, schedule.json
- `.env` — secrets (API key, Telegram token, chat ID); never committed

## Key design decisions

- Every API call is stateless: system prompt + injected notes/life_doc + last N messages + new message
- System prompt is assembled dynamically in `utils.build_system_prompt()`: base + claude_notes + life_doc
- Every user message is prepended with `[Current time: ...]` so Claude always knows the time
- Scheduled triggers look like user messages with a special format (see SPEC.md § Timestamp injection)
- Tool-use loop in `claude_client.send_message`: handles multiple tool calls per response, capped at 10 rounds
- Transient API errors (connection, rate limit, 5xx) are retried once; auth errors are not
- Missed scheduled messages: fired if overdue < SCHEDULER_GRACE_PERIOD_HOURS (default 24h), else dropped

## Conventions

- No database — plain files only
- No web framework — Telegram bot + asyncio scheduler only
- One user — no multi-user abstractions
- Functions should stay under ~50 lines; split if getting long
- Log API calls, tool calls, and scheduled message firings
- Commit after each meaningful change with a descriptive message

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Anthropic API key |
| `TELEGRAM_BOT_TOKEN` | required | Token from @BotFather |
| `TELEGRAM_ALLOWED_CHAT_ID` | required | Lex's Telegram chat ID |
| `CLAUDE_MODEL` | `claude-sonnet-4-5` | Model to use |
| `CONVERSATION_HISTORY_LIMIT` | `50` | Messages kept in history |
| `TIMEZONE` | `America/Los_Angeles` | Local timezone |
| `SCHEDULER_GRACE_PERIOD_HOURS` | `24` | Max lateness before dropping a scheduled message |
