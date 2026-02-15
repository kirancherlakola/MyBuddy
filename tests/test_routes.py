from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from mybuddy.db import get_db, init_db, DB_PATH
import mybuddy.db as db_module


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)
    init_db(test_db)
    return test_db


@pytest.fixture
def client():
    from mybuddy.web import create_app

    app = create_app()
    return TestClient(app)


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_index_redirects_to_notes(mock_extract, client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/notes"


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_notes_list_empty(mock_extract, client):
    resp = client.get("/notes")
    assert resp.status_code == 200
    assert "No notes yet" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_create_and_view_note(mock_extract, client):
    resp = client.post(
        "/notes",
        data={"title": "Test Note", "content": "Call Sarah on Monday"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    mock_extract.assert_called_once()

    # Follow redirect to note detail
    location = resp.headers["location"]
    resp = client.get(location)
    assert resp.status_code == 200
    assert "Test Note" in resp.text
    assert "Call Sarah on Monday" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_edit_note(mock_extract, client):
    # Create
    client.post("/notes", data={"title": "Old", "content": "old"}, follow_redirects=True)

    # Edit form
    resp = client.get("/notes/1/edit")
    assert resp.status_code == 200
    assert "Old" in resp.text

    # Update
    resp = client.post(
        "/notes/1/update",
        data={"title": "New", "content": "new"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    resp = client.get("/notes/1")
    assert "New" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_delete_note(mock_extract, client):
    client.post("/notes", data={"title": "Delete Me", "content": "bye"}, follow_redirects=True)

    resp = client.delete("/notes/1")
    assert resp.status_code == 200

    resp = client.get("/notes/1")
    assert resp.status_code == 404


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_actions_list(mock_extract, client, use_temp_db):
    # Insert test data directly
    with get_db(use_temp_db) as db:
        cur = db.execute("INSERT INTO notes (title, content) VALUES (?, ?)", ("N", "C"))
        note_id = cur.lastrowid
        db.execute(
            "INSERT INTO action_items (note_id, description) VALUES (?, ?)",
            (note_id, "Review proposal"),
        )

    resp = client.get("/actions")
    assert resp.status_code == 200
    assert "Review proposal" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_delete_all_actions(mock_extract, client, use_temp_db):
    with get_db(use_temp_db) as db:
        cur = db.execute("INSERT INTO notes (title, content) VALUES (?, ?)", ("N", "C"))
        note_id = cur.lastrowid
        db.execute("INSERT INTO action_items (note_id, description) VALUES (?, ?)", (note_id, "Task 1"))
        db.execute("INSERT INTO action_items (note_id, description) VALUES (?, ?)", (note_id, "Task 2"))

    resp = client.delete("/actions")
    assert resp.status_code == 200

    # Verify all action items are gone
    with get_db(use_temp_db) as db:
        count = db.execute("SELECT COUNT(*) as c FROM action_items").fetchone()["c"]
    assert count == 0


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_toggle_action(mock_extract, client, use_temp_db):
    with get_db(use_temp_db) as db:
        cur = db.execute("INSERT INTO notes (title, content) VALUES (?, ?)", ("N", "C"))
        note_id = cur.lastrowid
        db.execute(
            "INSERT INTO action_items (note_id, description) VALUES (?, ?)",
            (note_id, "Task 1"),
        )

    resp = client.post("/actions/1/toggle")
    assert resp.status_code == 200
    assert "checked" in resp.text

    resp = client.post("/actions/1/toggle")
    assert resp.status_code == 200
    assert "checked" not in resp.text or resp.text.count("checked") == 0


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_contacts_list(mock_extract, client, use_temp_db):
    with get_db(use_temp_db) as db:
        db.execute("INSERT INTO contacts (name, phone) VALUES (?, ?)", ("Sarah", "555-1234"))

    resp = client.get("/contacts")
    assert resp.status_code == 200
    assert "Sarah" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_contact_detail(mock_extract, client, use_temp_db):
    with get_db(use_temp_db) as db:
        db.execute("INSERT INTO contacts (name, phone) VALUES (?, ?)", ("Sarah", "555-1234"))

    resp = client.get("/contacts/1")
    assert resp.status_code == 200
    assert "Sarah" in resp.text
    assert "555-1234" in resp.text


# --- OCR image upload tests ---

@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_ocr_missing_api_key(mock_extract, client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    resp = client.post(
        "/notes/ocr-image",
        files={"file": ("test.png", fake_image, "image/png")},
    )
    assert resp.status_code == 422
    assert "OPENAI_API_KEY" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_ocr_invalid_file_type(mock_extract, client):
    fake_file = io.BytesIO(b"%PDF-1.4 fake pdf content")
    resp = client.post(
        "/notes/ocr-image",
        files={"file": ("test.pdf", fake_file, "application/pdf")},
    )
    assert resp.status_code == 422
    assert "Unsupported file type" in resp.text


@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_ocr_file_too_large(mock_extract, client, monkeypatch):
    monkeypatch.setattr("mybuddy.routes.notes._MAX_IMAGE_SIZE", 100)
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    resp = client.post(
        "/notes/ocr-image",
        files={"file": ("test.png", fake_image, "image/png")},
    )
    assert resp.status_code == 422
    assert "too large" in resp.text


@patch("mybuddy.routes.notes.extract_text_from_image", new_callable=AsyncMock)
@patch("mybuddy.routes.notes.extract_from_note", new_callable=AsyncMock)
def test_ocr_successful_extraction(mock_extract, mock_ocr, client):
    mock_ocr.return_value = "Hello from handwritten notes"
    fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    resp = client.post(
        "/notes/ocr-image",
        files={"file": ("test.png", fake_image, "image/png")},
    )
    assert resp.status_code == 200
    assert "Hello from handwritten notes" in resp.text
    assert "ocr-success" in resp.text
