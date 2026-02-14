# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                          # Install dependencies
uv run mybuddy serve             # Start web server at http://127.0.0.1:8000
uv run mybuddy serve --reload    # Start with auto-reload for development
uv run mybuddy remind            # Show pending action items and reminders in terminal
uv run pytest tests/ -v          # Run all tests
uv run pytest tests/test_db.py -v                    # Run only DB tests
uv run pytest tests/test_routes.py::test_toggle_action -v  # Run a single test
```

Set `ANTHROPIC_API_KEY` in `.env` for Claude-powered extraction. Without it, a rule-based regex fallback is used.

## Architecture

**Entry points:** `cli.py` defines two Typer commands — `serve` launches the FastAPI app via uvicorn, `remind` queries the DB directly and renders Rich tables.

**Web app factory:** `web.py:create_app()` initializes the DB, mounts static files and Jinja2 templates, and includes three routers from `routes/`.

**Request flow for note creation/update:**
1. `routes/notes.py` handles the form POST
2. Calls `services/ai.py:extract_from_note()` which tries the Claude API, falls back to regex patterns
3. `_save_extractions()` upserts contacts (by unique name), inserts action items and reminders
4. On update, old extractions are cleared before re-extracting

**Database:** SQLite in `~/.mybuddy/mybuddy.db` with WAL mode. Foreign keys with CASCADE deletes: deleting a note removes its action_items and note_contacts links. Deleting a contact removes its reminders. The `notes.py` delete route also cleans up orphaned contacts.

**Frontend:** Server-rendered Jinja2 templates with Pico CSS (classless) and HTMX for in-place interactions (action item toggle, delete buttons). No JavaScript build step.

## Testing

Route tests mock `extract_from_note` with `AsyncMock` and use `monkeypatch` to redirect `db.DB_PATH` to a temp directory. The `use_temp_db` fixture is `autouse=True`. DB functions use `None` defaults (not `DB_PATH`) so monkeypatching the module attribute works at runtime.
