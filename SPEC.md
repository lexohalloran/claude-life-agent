# Personal Agent Project Spec

## Overview

This project builds a personal AI agent that acts as a life-management assistant for one user (Lex). The agent is accessed through Telegram, runs on an always-on Linux machine, and uses the Anthropic Claude API. Unlike the Claude.ai chat interface, this agent has:

- Proactive capability: it can send messages on a schedule, including schedules it sets for itself
- Custom long-term memory in the form of a life doc and a notes file
- Tool-based ability to modify its own schedule, edit its notes, and read/append to the life doc
- Awareness of wall-clock time (timestamps injected into every message)

The agent is for one user only. There is no multi-user support, no authentication beyond the Telegram chat ID allowlist, and no cloud deployment — it runs on the user's own hardware.

This is a hobby project. Prioritize simplicity, readability, and plain-file storage over production-grade engineering. The user is a software developer acting primarily as an architect/reviewer, with Claude Code doing most of the implementation. Assume the user will read and understand the code but may not write most of it line-by-line.

## Tech stack

- **Language**: Python 3.11+
- **AI**: Anthropic Python SDK, model `claude-opus-4-7` (or whatever is current — check product-self-knowledge skill or the Anthropic docs)
- **Messaging**: Telegram via `python-telegram-bot` library
- **Storage**: plain files on disk (markdown for human-readable content, JSON for structured data). No database.
- **Process management**: systemd services (set up in the final phase)
- **Config**: `.env` file loaded via `python-dotenv`

## File structure

```
lex-agent/
├── .env                        # API keys, Telegram tokens, chat ID (gitignored)
├── .env.example                # template showing required vars
├── .gitignore
├── requirements.txt
├── README.md                   # setup instructions for future Lex
├── SPEC.md                     # this file
│
├── config.py                   # loads .env, defines constants
├── claude_client.py            # wraps API calls, handles tool-use loop
├── tools.py                    # tool definitions and implementations
├── conversation.py             # reads/writes conversation log, history strategy
├── telegram_bot.py             # send/receive via Telegram
├── scheduler.py                # background loop for scheduled messages
├── main.py                     # entry point, runs bot + scheduler concurrently
│
└── data/
    ├── system_prompt.md        # core instructions (user-edited only)
    ├── claude_notes.md         # Claude's working model of the user (Claude-edited)
    ├── life_doc.md             # current life context (both edit)
    ├── conversation_log.json   # running conversation history
    └── schedule.json           # queue of scheduled messages
```

## The three memory/context files

This is the most important design decision in the project. Read this section carefully.

### `data/system_prompt.md` (user-edited only)

Defines the agent's purpose, capabilities, scheduling rules, and behavioral guidelines. This file is loaded and prepended to every API call as the system prompt.

**Claude does not have write access to this file.** This is a safety boundary: Claude should not be able to modify its own core instructions.

The file should cover:
- The agent's purpose (life-management assistant for Lex)
- Its capabilities (can schedule messages, edit notes, read life doc)
- Scheduling behavior guidelines (when to proactively reach out, quiet hours, tone)
- User preferences that should never change (honest evaluation over validation, no animal products unless raised by user, standard capitalization, avoid unnecessary doctor suggestions, etc. — copy from user's existing Claude.ai preferences)
- Instruction to read `claude_notes.md` and `life_doc.md` at the start of processing each message (these are provided in the system prompt as loaded file contents, not actively fetched)

A draft of this file's content should be generated as part of Phase 1 setup, but it's expected to evolve. Lex will hand-edit it over time.

### `data/claude_notes.md` (Claude-edited)

Claude's accumulated understanding of the user — preferences, patterns, things worth remembering but not urgent enough to be in the life doc. Claude has a tool to edit this file.

Example content:
- "Lex prefers to process emotions before diving into tasks"
- "Lex uses they/them pronouns"
- "Lex finds overly long replies overwhelming — keep things focused"

This file is freeform markdown. No enforced structure yet — we can add structure later if it becomes unwieldy.

### `data/life_doc.md` (both edit)

Current life context — what's going on, what's top of mind, what the user is working toward. Claude has tools to read and append to it. The user can open and edit it directly at any time.

Starts freeform but will likely grow sections over time (e.g., "Current priorities," "Ongoing situations," "Someday/maybe"). **Do not enforce structure yet.** Start with just a markdown file and plain read/append operations. We'll add section-aware tools in a later phase if and when they're needed.

## Tools (functions Claude can call via API)

Implement these in `tools.py`. Each has a schema definition (for the API) and an implementation function.

### Phase 4 tools (minimum viable set)

- `read_life_doc()` → returns full content of `life_doc.md`
- `append_to_life_doc(content: str)` → appends a string to `life_doc.md` with a timestamp header
- `read_claude_notes()` → returns full content of `claude_notes.md`
- `edit_claude_notes(new_content: str)` → **replaces** the full contents of `claude_notes.md`. This is simpler than diff-based editing and works fine while the file is small. We'll upgrade later if needed.

### Phase 5 tools (scheduling)

- `schedule_message(when: str, context: str)` → adds an entry to `schedule.json`. Returns the ID of the scheduled message.
  - `when`: ISO 8601 datetime string (Claude should reason about this from the injected current timestamp)
  - `context`: a note to Claude's future self about why this message was scheduled and what to ask/say
- `cancel_scheduled_message(id: str)` → removes an entry from `schedule.json`
- `list_scheduled_messages()` → returns all pending scheduled messages

### Scheduling guardrails (enforced in the tool implementation, not just prompted)

- **Minimum 10 minutes between any two scheduled messages.** If Claude tries to schedule a message within 10 minutes of an existing one, reject with a clear error message so Claude can retry.
- **Maximum 1 year in the future.** Reject schedules further out than that.
- Quiet hours and "when to reach out" guidance lives in the system prompt, not in tool logic. The tool permits it; the prompt discourages it.

Note: the 10-minute minimum applies to *scheduled* messages. Messages sent in response to the user messaging the bot are unscheduled and not subject to this limit.

## The scheduler process

`scheduler.py` is a background loop that:
1. Reads `schedule.json`
2. Finds the earliest pending message
3. Sleeps until that time (or until it needs to recheck — say, every 60 seconds at most so newly-scheduled messages are picked up quickly)
4. When a message fires: loads context (system prompt, notes, life doc, recent conversation, the `context` field from the scheduled entry), calls the Claude API, sends the response via Telegram, appends to conversation log, removes the scheduled entry from the queue

Scheduled message firings are themselves appended to `conversation_log.json` as if they were a "user message" from the scheduler (e.g., with a special role or marker) followed by Claude's response. This keeps the conversation history continuous whether messages come from Lex or from a scheduled trigger.

## Timestamp injection

Every user message sent to the Claude API should be prepended with a timestamp line. Format:

```
[Current time: Monday, April 20, 2026, 2:32 PM PDT]
[Message from Lex]: <actual message content>
```

The same applies to scheduled-message triggers:

```
[Current time: Monday, April 20, 2026, 2:32 PM PDT]
[Scheduled trigger, originally set at 8:00 AM this morning]
[Context note to self]: <the context field from the scheduled entry>
```

Timezone should be configurable in `config.py` — default to America/Los_Angeles (Lex is in the SF Bay Area).

## Conversation history strategy

**Phase 3**: keep the last N messages (N configurable, default 50). When history exceeds N, drop oldest. Simple and predictable.

**Future phase**: summarize older history periodically. Defer this until it's actually a problem.

Conversation log format: JSON array of message objects, each with `role`, `content`, `timestamp`, and optional metadata like `source: "scheduled"` for non-user-initiated turns.

## Phased implementation plan

Build these phases in order. Each phase should end in a working, testable system. Do not skip ahead.

### Phase 1: Minimum API call

- Set up project structure, `.env`, `requirements.txt`
- Write `config.py` and `claude_client.py`
- Write a one-off test script `test_phase1.py` that sends a hardcoded message to Claude and prints the response
- Done when: running the test script produces a sensible response

### Phase 2: Telegram echo bot with Claude

- Set up a Telegram bot (instructions in README for Lex to do this manually — involves chatting with @BotFather)
- Write `telegram_bot.py`
- Modify `main.py` to listen for Telegram messages, send each one to Claude (no history yet), reply via Telegram
- Allowlist: only respond to messages from Lex's chat ID (set in `.env`)
- Done when: Lex can message the bot on their phone and get Claude's response back. Each message is still isolated (no memory).

### Phase 3: Conversation memory

- Write `conversation.py` with load/append/trim logic
- Modify `main.py` to include recent history on every API call
- Include the initial system prompt from `data/system_prompt.md`
- Done when: the bot remembers previous messages in the same conversation.

### Phase 4: Life doc and notes tools

- Create starter `life_doc.md` and `claude_notes.md` (empty or with minimal placeholder content)
- Write `tools.py` with the four Phase 4 tools
- Extend `claude_client.py` to handle the tool-use loop (Claude may make multiple tool calls before producing a final text response)
- Done when: Lex can ask the bot "what do you know about me?" and it reads the notes file; Lex can ask it to "remember that I prefer X" and it updates the notes.

### Phase 5: Scheduling

- Add the three scheduling tools to `tools.py`
- Write `scheduler.py`
- Modify `main.py` to run both the Telegram listener and the scheduler concurrently (use `asyncio`)
- Done when: Lex can say "message me in 15 minutes to ask how my meeting went" and it works. Also: Claude can proactively decide to schedule a follow-up based on conversation context.

### Phase 6: Deployment

- Write systemd service files for the main process
- Set up on the Linux machine (Lex will handle the physical setup of the always-on machine)
- Configure log rotation, auto-restart on crash, startup on boot
- Done when: machine can be rebooted and the agent comes back up automatically

## Conventions and constraints

- **No databases.** Everything is files on disk. If you catch yourself reaching for SQLite, stop and reconsider.
- **No web framework.** This is a Telegram bot plus a scheduler, not a web app.
- **One user.** Do not build multi-user abstractions.
- **Use the official Anthropic SDK**, not raw HTTP calls.
- **Use type hints** where they aid readability. Don't go overboard with generics.
- **Keep functions small.** If something is getting past ~50 lines, consider splitting it.
- **Log important events** to stdout/stderr (systemd will capture). Log each API call, each tool call, each scheduled message firing.
- **Commit after each phase.** Git log should tell the story of the project.
- **Secrets in `.env` only.** Never hardcode an API key. Provide `.env.example` so future setup is clear.

## What NOT to build yet

Explicitly out of scope for the current project:

- Voice messages (text only)
- Image understanding
- Web search (interesting future addition)
- Calendar integration (interesting future addition — probably via Google Calendar API)
- Multiple agents / multi-user support
- Encryption at rest for conversation logs
- A web UI
- Section-aware life doc editing (freeform markdown only for now)
- Periodic conversation summarization (use last-N-messages only)
- Intelligent message deduplication or threading
- Cross-device sync of any files (Lex can handle that separately if desired)

## Open questions / things to decide during build

These don't need to block starting — flag them when you encounter them and we'll decide.

1. Exact wording/content of `system_prompt.md`. Generate a reasonable first draft; Lex will iterate.
2. What happens if the Telegram bot is offline when a scheduled message fires? Options: (a) fire it anyway, queued for next startup; (b) fire it if within N minutes late, else drop; (c) always fire the most recent missed one. Probably (a) with a "sorry I'm late" indicator in the context.
3. Error handling when Claude API fails mid-conversation: retry? Notify Lex? Silently log? Probably: retry once, then send Lex a plain Telegram message saying something broke.
4. How should `append_to_life_doc` handle conflicts if Lex is editing the file at the same moment? Probably fine to ignore for single-user use; worst case, one of the edits is lost. Don't over-engineer this.

## Future capabilities (for reference, not current scope)

Things Lex has expressed interest in eventually:

- Calendar access (read and possibly write to Google Calendar)
- Web search
- Section-aware life doc editing as the life doc grows structure
- Conversation summarization for very long histories
- Possibly bridging context with Lex's Claude.ai memory

Don't build these now. Don't design for them in ways that add complexity. The current file-based architecture can accommodate them later without major refactoring.

## A note on working with Lex

Lex is a software developer who's using this project to practice the "architect/reviewer" mode of working with AI rather than writing most code themselves. That means:

- When you (Claude Code) make design decisions, briefly explain the reasoning so Lex can review.
- Flag genuine tradeoffs; don't just pick one silently.
- When something is ambiguous in this spec, ask rather than guess at complex logic.
- Small implementation details (variable names, function ordering, etc.) — just make reasonable choices.
- Commit messages should be descriptive. Lex will be reading the git log to understand what was built.
- Lex prefers standard capitalization and Claude's natural voice in prose (not mirroring their casual lowercase style).
- Lex appreciates pushback when they're wrong about something technical.