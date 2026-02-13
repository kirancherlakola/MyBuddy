from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from mybuddy.db import get_db

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _templates(request: Request):
    return request.app.state.templates


@router.get("", response_class=HTMLResponse)
async def list_contacts(request: Request):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM contacts ORDER BY name"
        ).fetchall()
    return _templates(request).TemplateResponse(
        request, "contacts/list.html", {"contacts": rows, "active": "contacts"}
    )


@router.get("/{contact_id}", response_class=HTMLResponse)
async def contact_detail(request: Request, contact_id: int):
    with get_db() as db:
        contact = db.execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if not contact:
            return HTMLResponse("Contact not found", status_code=404)
        notes = db.execute(
            """SELECT n.id, n.title, n.created_at FROM notes n
               JOIN note_contacts nc ON n.id = nc.note_id
               WHERE nc.contact_id = ?
               ORDER BY n.created_at DESC""",
            (contact_id,),
        ).fetchall()
        reminders = db.execute(
            """SELECT * FROM reminders WHERE contact_id = ? ORDER BY due_date""",
            (contact_id,),
        ).fetchall()
    return _templates(request).TemplateResponse(
        request,
        "contacts/detail.html",
        {
            "contact": contact,
            "notes": notes,
            "reminders": reminders,
            "active": "contacts",
        },
    )


@router.delete("/{contact_id}")
async def delete_contact(request: Request, contact_id: int):
    with get_db() as db:
        db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    return HTMLResponse(headers={"HX-Redirect": "/contacts"})
