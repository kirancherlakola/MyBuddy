# MyBuddy

Personal assistant web app that collects notes, uses AI to extract action items, contacts, and reminders, and provides terminal reminders for follow-ups.

## Quick Start

```bash
# Install dependencies
uv sync

# (Optional) Set your Anthropic API key for AI-powered extraction
# Without it, a rule-based regex fallback is used
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env

# Start the web server
uv run mybuddy serve

# Check pending action items and reminders in the terminal
uv run mybuddy remind
```

Open http://127.0.0.1:8000 in your browser.

## How It Works

1. **Create a note** — write anything, e.g. "Call Sarah on Monday about the contract review"
2. **AI extracts structured data** — action items, contacts, and call/follow-up reminders are pulled from the note automatically
3. **Track actions** — view and toggle action items on the Actions page
4. **Manage contacts** — contacts are extracted and linked to notes automatically
5. **Terminal reminders** — run `mybuddy remind` to see a summary of pending items

## Tech Stack

- **Python 3.12** with **uv**
- **FastAPI** + **Jinja2** + **HTMX** (server-rendered, no JS build step)
- **Pico CSS** (classless CSS framework via CDN)
- **SQLite** (WAL mode, stored in `~/.mybuddy/mybuddy.db`)
- **Anthropic SDK** (Claude for AI extraction, with regex fallback)
- **Typer** + **Rich** (CLI)

## CLI Commands

| Command | Description |
|---|---|
| `mybuddy serve` | Start web server (default: 127.0.0.1:8000) |
| `mybuddy serve --reload` | Start with auto-reload for development |
| `mybuddy serve --port 3000` | Start on a custom port |
| `mybuddy remind` | Show pending action items and reminders |

## Running Tests

```bash
uv run pytest tests/ -v
```

## Project Structure

```
src/mybuddy/
  cli.py              # Typer CLI: serve + remind commands
  web.py              # FastAPI app factory
  db.py               # SQLite schema and connection helpers
  models.py           # Dataclasses (Note, Contact, ActionItem, Reminder)
  routes/
    notes.py          # Notes CRUD
    actions.py        # Action items list/toggle
    contacts.py       # Contacts list/detail
  services/
    ai.py             # Claude API extraction + regex fallback
  templates/          # Jinja2 templates (base, notes, actions, contacts)
  static/style.css    # Custom styles
tests/
  test_db.py          # Database schema, CRUD, cascade deletes
  test_routes.py      # Route responses with mocked AI extraction
```
