from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mybuddy.db import get_db
from mybuddy.services.ai import extract_from_note

router = APIRouter(prefix="/notes", tags=["notes"])


def _templates(request: Request):
    return request.app.state.templates


@router.get("", response_class=HTMLResponse)
async def list_notes(request: Request):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, title, created_at FROM notes ORDER BY updated_at DESC"
        ).fetchall()
    return _templates(request).TemplateResponse(
        request, "notes/list.html", {"notes": rows, "active": "notes"}
    )


@router.get("/new", response_class=HTMLResponse)
async def new_note(request: Request):
    return _templates(request).TemplateResponse(
        request, "notes/form.html", {"note": None, "active": "notes"}
    )


@router.post("")
async def create_note(request: Request, title: str = Form(...), content: str = Form("")):
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO notes (title, content) VALUES (?, ?)", (title, content)
        )
        note_id = cur.lastrowid

    # AI extraction (best-effort)
    await extract_from_note(note_id, title, content)

    return RedirectResponse(url=f"/notes/{note_id}", status_code=303)


@router.get("/{note_id}", response_class=HTMLResponse)
async def detail_note(request: Request, note_id: int):
    with get_db() as db:
        note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not note:
            return HTMLResponse("Note not found", status_code=404)
        action_items = db.execute(
            "SELECT * FROM action_items WHERE note_id = ?", (note_id,)
        ).fetchall()
        contacts = db.execute(
            """SELECT c.* FROM contacts c
               JOIN note_contacts nc ON c.id = nc.contact_id
               WHERE nc.note_id = ?""",
            (note_id,),
        ).fetchall()
        reminders = db.execute(
            """SELECT r.*, c.name as contact_name FROM reminders r
               JOIN contacts c ON r.contact_id = c.id
               JOIN note_contacts nc ON nc.contact_id = c.id AND nc.note_id = ?""",
            (note_id,),
        ).fetchall()
    return _templates(request).TemplateResponse(
        request,
        "notes/detail.html",
        {
            "note": note,
            "action_items": action_items,
            "contacts": contacts,
            "reminders": reminders,
            "active": "notes",
        },
    )


@router.get("/{note_id}/edit", response_class=HTMLResponse)
async def edit_note(request: Request, note_id: int):
    with get_db() as db:
        note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not note:
            return HTMLResponse("Note not found", status_code=404)
    return _templates(request).TemplateResponse(
        request, "notes/form.html", {"note": note, "active": "notes"}
    )


@router.post("/{note_id}/update")
async def update_note(
    request: Request, note_id: int, title: str = Form(...), content: str = Form("")
):
    with get_db() as db:
        db.execute(
            "UPDATE notes SET title = ?, content = ?, updated_at = datetime('now') WHERE id = ?",
            (title, content, note_id),
        )
        # Clear old extractions for this note
        db.execute("DELETE FROM action_items WHERE note_id = ?", (note_id,))
        # Get contact ids linked to this note for reminder cleanup
        contact_ids = [
            r["contact_id"]
            for r in db.execute(
                "SELECT contact_id FROM note_contacts WHERE note_id = ?", (note_id,)
            ).fetchall()
        ]
        # Delete reminders linked to these contacts (from this note only)
        for cid in contact_ids:
            # Only delete if contact isn't linked to other notes
            other = db.execute(
                "SELECT 1 FROM note_contacts WHERE contact_id = ? AND note_id != ?",
                (cid, note_id),
            ).fetchone()
            if not other:
                db.execute("DELETE FROM reminders WHERE contact_id = ?", (cid,))
        db.execute("DELETE FROM note_contacts WHERE note_id = ?", (note_id,))

    # Re-extract
    await extract_from_note(note_id, title, content)

    return RedirectResponse(url=f"/notes/{note_id}", status_code=303)


@router.delete("/{note_id}")
async def delete_note(request: Request, note_id: int):
    with get_db() as db:
        # Collect contacts only linked to this note
        orphan_contacts = db.execute(
            """SELECT contact_id FROM note_contacts
               WHERE note_id = ? AND contact_id NOT IN (
                   SELECT contact_id FROM note_contacts WHERE note_id != ?
               )""",
            (note_id, note_id),
        ).fetchall()
        # Cascade handles action_items, note_contacts
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        # Clean up orphaned contacts (reminders cascade from contacts)
        for row in orphan_contacts:
            db.execute("DELETE FROM contacts WHERE id = ?", (row["contact_id"],))
    return HTMLResponse(headers={"HX-Redirect": "/notes"})
