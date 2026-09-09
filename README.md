# Life Agent

A personal Telegram AI assistant that can initiate conversations on a schedule, maintain a persistent life doc and notes, and run as a systemd service on an always-on Linux machine.

## Prerequisites

- Python 3.11+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (send a message to [@userinfobot](https://t.me/userinfobot))
- An Anthropic API key

## Installation

### 1. Get the code

```bash
git clone <repo-url> ~/services/claude-life-agent
cd ~/services/claude-life-agent
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
nano .env  # fill in your API keys and chat ID
```

### 4. Create the data directory

```bash
mkdir -p data
```

The agent will create its files (`claude_notes.md`, `life_doc.md`, `conversation_log.json`, `schedule.json`) here on first run. You can pre-populate `data/life_doc.md` with context about yourself if you want.

### 5. Test it

```bash
venv/bin/python main.py
```

Send yourself a message on Telegram. Ctrl+C to stop once it's working.

## Systemd setup

### Install and enable the service

Edit `claude-life-agent.service` and replace `YOUR_USERNAME` with your Linux username. If you installed to a path other than `~/services/claude-life-agent`, update `WorkingDirectory` and `ExecStart` to match.

```bash
sudo cp claude-life-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable claude-life-agent
sudo systemctl start claude-life-agent
```

### Useful commands

```bash
# Check status
sudo systemctl status claude-life-agent

# View live logs
sudo journalctl -u claude-life-agent -f

# View recent logs
sudo journalctl -u claude-life-agent -n 100

# Restart after config changes
sudo systemctl restart claude-life-agent

# Stop
sudo systemctl stop claude-life-agent
```

### Log retention

Logs go to the system journal (journald). Journal size is governed by `/etc/systemd/journald.conf` — the default cap is 10% of filesystem size. To set an explicit limit:

```bash
sudo nano /etc/systemd/journald.conf
# Set: SystemMaxUse=500M
sudo systemctl restart systemd-journald
```

## Configuration

All configuration is via `.env`. See `.env.example` for available variables.

The agent's personality and scheduling behavior are in `config/system_prompt.md` — edit this directly to change how it behaves. It is not writable by the agent itself.

## Data files

All data lives in `data/` (gitignored):

| File | Purpose | Who edits |
|------|---------|-----------|
| `claude_notes.md` | Agent's notes about you | Agent only |
| `life_doc.md` | Ongoing life context | You and the agent |
| `conversation_log.json` | Message history | Agent only |
| `conversation_summaries.md` | One summary per past day | Agent only |
| `schedule.json` | Pending scheduled messages | Agent only |
| `maintenance_state.json` | Date the daily pass last ran | Agent only |
| `usage_log.jsonl` | Token usage, one line per API call | Agent only |

You can edit `life_doc.md` directly at any time.

## Daily maintenance

Once a day at `MAINTENANCE_HOUR` (default 4am local), the scheduler wakes the
agent for a housekeeping pass. It reviews pending scheduled messages against
recent conversation, writes a summary of the previous day into
`conversation_summaries.md`, and consolidates `claude_notes.md` to keep it from
growing without bound.

The pass runs whether or not the agent remembers to schedule it — it is driven
by the scheduler loop, not by the agent's own scheduling tools, so it cannot
drift or be cancelled by mistake.

Its text output is discarded. It reaches you only if it decides something needs
saying (most notably, when it has cancelled a reminder), so silence from it is
the normal case.

## Inspecting cost

`usage_log.jsonl` records every API call. To see how much prompt caching is
actually saving:

```bash
jq -s 'group_by(.source)[] | {source: .[0].source, calls: length,
  cache_write: (map(.cache_creation_input_tokens) | add),
  cache_read: (map(.cache_read_input_tokens) | add),
  uncached: (map(.input_tokens) | add)}' data/usage_log.jsonl
```

Cache reads cost 10% of base rate and writes cost 125%, so writes that are
never read back are worse than not caching at all.
