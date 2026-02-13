from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mybuddy.db import get_db, init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_schema_creation(db_path):
    with get_db(db_path) as db:
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = [t["name"] for t in tables]
    assert "notes" in names
    assert "contacts" in names
    assert "action_items" in names
    assert "note_contacts" in names
    assert "reminders" in names


def test_note_crud(db_path):
    with get_db(db_path) as db:
        cur = db.execute(
            "INSERT INTO notes (title, content) VALUES (?, ?)",
            ("Test Note", "Some content"),
        )
        note_id = cur.lastrowid

    with get_db(db_path) as db:
        note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        assert note["title"] == "Test Note"
        assert note["content"] == "Some content"

    with get_db(db_path) as db:
        db.execute(
            "UPDATE notes SET title = ? WHERE id = ?", ("Updated", note_id)
        )

    with get_db(db_path) as db:
        note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        assert note["title"] == "Updated"

    with get_db(db_path) as db:
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    with get_db(db_path) as db:
        note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        assert note is None


def test_cascade_delete_action_items(db_path):
    with get_db(db_path) as db:
        cur = db.execute("INSERT INTO notes (title, content) VALUES (?, ?)", ("N", "C"))
        note_id = cur.lastrowid
        db.execute(
            "INSERT INTO action_items (note_id, description) VALUES (?, ?)",
            (note_id, "Do something"),
        )

    with get_db(db_path) as db:
        items = db.execute("SELECT * FROM action_items WHERE note_id = ?", (note_id,)).fetchall()
        assert len(items) == 1

    with get_db(db_path) as db:
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    with get_db(db_path) as db:
        items = db.execute("SELECT * FROM action_items WHERE note_id = ?", (note_id,)).fetchall()
        assert len(items) == 0


def test_cascade_delete_note_contacts(db_path):
    with get_db(db_path) as db:
        cur = db.execute("INSERT INTO notes (title, content) VALUES (?, ?)", ("N", "C"))
        note_id = cur.lastrowid
        cur2 = db.execute("INSERT INTO contacts (name) VALUES (?)", ("Alice",))
        contact_id = cur2.lastrowid
        db.execute(
            "INSERT INTO note_contacts (note_id, contact_id) VALUES (?, ?)",
            (note_id, contact_id),
        )

    with get_db(db_path) as db:
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    with get_db(db_path) as db:
        links = db.execute("SELECT * FROM note_contacts WHERE note_id = ?", (note_id,)).fetchall()
        assert len(links) == 0
        # Contact itself still exists (not cascaded from note)
        contact = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        assert contact is not None


def test_cascade_delete_reminders_from_contact(db_path):
    with get_db(db_path) as db:
        cur = db.execute("INSERT INTO contacts (name) VALUES (?)", ("Bob",))
        contact_id = cur.lastrowid
        db.execute(
            "INSERT INTO reminders (contact_id, reminder_type, message) VALUES (?, ?, ?)",
            (contact_id, "call", "Call Bob"),
        )

    with get_db(db_path) as db:
        db.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))

    with get_db(db_path) as db:
        reminders = db.execute(
            "SELECT * FROM reminders WHERE contact_id = ?", (contact_id,)
        ).fetchall()
        assert len(reminders) == 0


def test_contact_unique_name(db_path):
    with get_db(db_path) as db:
        db.execute("INSERT INTO contacts (name) VALUES (?)", ("Alice",))

    with pytest.raises(Exception):
        with get_db(db_path) as db:
            db.execute("INSERT INTO contacts (name) VALUES (?)", ("Alice",))
