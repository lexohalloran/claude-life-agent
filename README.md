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
git clone <repo-url> /opt/life-agent
cd /opt/life-agent
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

Edit `life-agent.service` and replace `YOUR_USERNAME` with your Linux username. If you installed to a path other than `/opt/life-agent`, update `WorkingDirectory` and `ExecStart` to match.

```bash
sudo cp life-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable life-agent
sudo systemctl start life-agent
```

### Useful commands

```bash
# Check status
sudo systemctl status life-agent

# View live logs
sudo journalctl -u life-agent -f

# View recent logs
sudo journalctl -u life-agent -n 100

# Restart after config changes
sudo systemctl restart life-agent

# Stop
sudo systemctl stop life-agent
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
| `schedule.json` | Pending scheduled messages | Agent only |

You can edit `life_doc.md` directly at any time.
