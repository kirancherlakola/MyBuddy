from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import typer
from rich.console import Console
from rich.table import Table

from mybuddy.db import get_db, init_db

app = typer.Typer(help="MyBuddy — Personal Assistant")
console = Console()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
) -> None:
    """Start the MyBuddy web server."""
    import uvicorn

    uvicorn.run("mybuddy.web:create_app", host=host, port=port, reload=reload, factory=True)


@app.command()
def remind() -> None:
    """Show pending action items and call reminders."""
    init_db()

    with get_db() as db:
        actions = db.execute(
            """SELECT a.description, a.due_date, n.title as note_title
               FROM action_items a
               JOIN notes n ON a.note_id = n.id
               WHERE a.is_completed = 0
               ORDER BY a.due_date, a.id"""
        ).fetchall()

        reminders = db.execute(
            """SELECT r.reminder_type, r.message, r.due_date, c.name as contact_name
               FROM reminders r
               JOIN contacts c ON r.contact_id = c.id
               WHERE r.is_dismissed = 0
               ORDER BY r.due_date, r.id"""
        ).fetchall()

    if not actions and not reminders:
        console.print("[green]All clear! No pending items.[/green]")
        return

    if actions:
        table = Table(title="Pending Action Items")
        table.add_column("Description", style="cyan")
        table.add_column("Due Date", style="yellow")
        table.add_column("From Note", style="dim")
        for a in actions:
            table.add_row(a["description"], a["due_date"] or "—", a["note_title"])
        console.print(table)

    if reminders:
        table = Table(title="Call / Follow-up Reminders")
        table.add_column("Type", style="magenta")
        table.add_column("Contact", style="cyan")
        table.add_column("Message", style="white")
        table.add_column("Due Date", style="yellow")
        for r in reminders:
            table.add_row(r["reminder_type"], r["contact_name"], r["message"], r["due_date"] or "—")
        console.print(table)
