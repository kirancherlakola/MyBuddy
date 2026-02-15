from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from mybuddy.db import get_db

router = APIRouter(prefix="/actions", tags=["actions"])


def _templates(request: Request):
    return request.app.state.templates


@router.get("", response_class=HTMLResponse)
async def list_actions(request: Request, filter: str = "all"):
    with get_db() as db:
        if filter == "pending":
            rows = db.execute(
                """SELECT a.*, n.title as note_title FROM action_items a
                   JOIN notes n ON a.note_id = n.id
                   WHERE a.is_completed = 0
                   ORDER BY a.due_date, a.id""",
            ).fetchall()
        elif filter == "completed":
            rows = db.execute(
                """SELECT a.*, n.title as note_title FROM action_items a
                   JOIN notes n ON a.note_id = n.id
                   WHERE a.is_completed = 1
                   ORDER BY a.id DESC""",
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT a.*, n.title as note_title FROM action_items a
                   JOIN notes n ON a.note_id = n.id
                   ORDER BY a.is_completed, a.due_date, a.id""",
            ).fetchall()
    return _templates(request).TemplateResponse(
        request, "actions/list.html", {"actions": rows, "filter": filter, "active": "actions"}
    )


@router.post("/{action_id}/toggle", response_class=HTMLResponse)
async def toggle_action(request: Request, action_id: int):
    with get_db() as db:
        db.execute(
            "UPDATE action_items SET is_completed = NOT is_completed WHERE id = ?",
            (action_id,),
        )
        row = db.execute(
            """SELECT a.*, n.title as note_title FROM action_items a
               JOIN notes n ON a.note_id = n.id WHERE a.id = ?""",
            (action_id,),
        ).fetchone()
    if not row:
        return HTMLResponse("Not found", status_code=404)
    status = "completed" if row["is_completed"] else "pending"
    checked = "checked" if row["is_completed"] else ""
    return HTMLResponse(
        f"""<tr id="action-{action_id}">
            <td><input type="checkbox" {checked}
                       hx-post="/actions/{action_id}/toggle"
                       hx-target="#action-{action_id}"
                       hx-swap="outerHTML"></td>
            <td class="{'line-through' if row['is_completed'] else ''}">{row['description']}</td>
            <td>{row['due_date'] or '—'}</td>
            <td><a href="/notes/{row['note_id']}">{row['note_title']}</a></td>
            <td><span class="tag {status}">{status}</span></td>
        </tr>"""
    )


@router.delete("/{action_id}")
async def delete_action(request: Request, action_id: int):
    with get_db() as db:
        db.execute("DELETE FROM action_items WHERE id = ?", (action_id,))
    return HTMLResponse("")


@router.delete("")
async def delete_completed_actions(request: Request):
    with get_db() as db:
        db.execute("DELETE FROM action_items WHERE is_completed = 1")
    return HTMLResponse(headers={"HX-Redirect": "/actions"})
