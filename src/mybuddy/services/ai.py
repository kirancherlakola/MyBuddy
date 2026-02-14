from __future__ import annotations

import base64
import json
import logging
import os
import re

import anthropic

from mybuddy.db import get_db

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
Analyze the following note and extract structured information as JSON.

Return a JSON object with these keys:
- "action_items": list of objects with "description" (string) and "due_date" (string, ISO date or empty)
- "contacts": list of objects with "name" (string), "phone" (string or empty), "email" (string or empty)
- "reminders": list of objects with "contact_name" (string, must match a contact name), "type" ("call" or "follow_up"), "message" (string), "due_date" (string, ISO date or empty)

Rules:
- Only extract information explicitly mentioned or strongly implied in the note
- For due dates, interpret relative dates like "Monday" or "next week" relative to today
- If no items found for a category, return an empty list
- Return ONLY valid JSON, no markdown fences or extra text

Note title: {title}
Note content:
{content}
"""

# Patterns for rule-based fallback
_ACTION_PATTERNS = [
    r"(?i)\b(need\s+to\b\s+.+?)(?:\.|$)",
    r"(?i)\b(should\b\s+.+?)(?:\.|$)",
    r"(?i)\b(have\s+to\b\s+.+?)(?:\.|$)",
    r"(?i)\b(must\b\s+.+?)(?:\.|$)",
    r"(?i)\btodo\b[:\s]+(.+?)(?:\.|$)",
    r"(?i)\b(follow\s*up\b\s*(?:with\s+)?.+?)(?:\.|$)",
    r"(?i)\b(touch\s+base\b\s*.+?)(?:\.|$)",
    r"(?i)\b(keep\s+in\s+touch\b.+?)(?:\.|$)",
    r"(?i)\bremind(?:er)?\b[:\s]+(.+?)(?:\.|$)",
    r"(?i)\b(schedule\b\s+.+?)(?:\.|$)",
    r"(?i)\b(send\b\s+.+?)(?:\.|$)",
    r"(?i)\b(review\b\s+.+?)(?:\.|$)",
    r"(?i)\b(call\b\s+.+?)(?:\.|$)",
]

_CALL_PATTERNS = [
    r"(?i)\bcall\b\s+(\w+)",
    r"(?i)\bphone\b\s+(\w+)",
    r"(?i)\bring\b\s+(\w+)",
]

_FOLLOWUP_PATTERNS = [
    r"(?i)\bfollow\s*up\b\s*(?:with\s+)?(\w+)",
    r"(?i)\btouch\s+base\b\s*(?:with\s+)?(\w+)",
    r"(?i)\bkeep\s+in\s+touch\b.*?(?:with\s+)?(\w+)",
    r"(?i)\bcheck\s+(?:in|back)\b\s*(?:with\s+)?(\w+)",
]

# Words that look like names but aren't
_STOP_WORDS = {
    "me", "him", "her", "them", "us", "it", "this", "that", "the", "a", "an",
    "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "about",
    "back", "up", "out", "my", "your", "his", "their", "our", "via", "email",
    "phone", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "tomorrow", "today", "next", "week", "month", "year", "asap",
}


def _extract_name_from_title(title: str) -> str | None:
    """Try to extract a person's name from 'Meeting with X' style titles."""
    m = re.search(r"(?i)\bwith\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", title)
    if m:
        return m.group(1)
    return None


def _rule_based_extract(title: str, content: str) -> dict:
    """Fallback extraction using regex patterns."""
    text = f"{title}\n{content}"
    data: dict = {"action_items": [], "contacts": [], "reminders": []}
    seen_actions: set[str] = set()

    # Extract action items
    for pattern in _ACTION_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE):
            desc = m.group(1).strip().rstrip(".,;!").strip()
            if not desc or len(desc) <= 3:
                continue
            lower = desc.lower()
            # Skip if duplicate or substring of an already-captured item
            if any(lower in s or s in lower for s in seen_actions):
                continue
            # Remove existing items that are substrings of this new one
            seen_actions = {s for s in seen_actions if s not in lower}
            data["action_items"] = [
                a for a in data["action_items"] if a["description"].lower() not in lower
            ]
            seen_actions.add(lower)
            data["action_items"].append({"description": desc, "due_date": ""})

    # Extract contacts from title
    contact_names: set[str] = set()
    title_name = _extract_name_from_title(title)
    if title_name:
        contact_names.add(title_name)

    # Extract contacts from call/followup patterns
    for pattern in _CALL_PATTERNS + _FOLLOWUP_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE):
            name = m.group(1).strip()
            if name.lower() not in _STOP_WORDS and name[0].isupper():
                contact_names.add(name)

    for name in contact_names:
        data["contacts"].append({"name": name, "phone": "", "email": ""})

    # Extract reminders
    for pattern in _CALL_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE):
            name = m.group(1).strip()
            if name.lower() not in _STOP_WORDS and name[0].isupper():
                line = m.group(0).strip()
                data["reminders"].append(
                    {"contact_name": name, "type": "call", "message": line, "due_date": ""}
                )

    for pattern in _FOLLOWUP_PATTERNS:
        for m in re.finditer(pattern, text, re.MULTILINE):
            name = m.group(1).strip()
            if name.lower() not in _STOP_WORDS and name[0].isupper():
                line = m.group(0).strip()
                data["reminders"].append(
                    {"contact_name": name, "type": "follow_up", "message": line, "due_date": ""}
                )

    # If we found contacts but no specific call/followup lines, check full sentences
    if contact_names and not data["action_items"]:
        for line in text.splitlines():
            line = line.strip()
            if line and len(line) > 5:
                data["action_items"].append({"description": line, "due_date": ""})

    return data


async def extract_from_note(note_id: int, title: str, content: str) -> None:
    """Extract action items, contacts, and reminders. Uses Claude if available, else regex fallback."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    data = None
    if api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(title=title, content=content),
                    }
                ],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                raw = raw.rsplit("```", 1)[0]
            data = json.loads(raw)
        except Exception:
            logger.exception("AI extraction failed, falling back to rule-based extraction")

    if data is None:
        logger.info("Using rule-based extraction")
        data = _rule_based_extract(title, content)

    _save_extractions(note_id, data)


def _save_extractions(note_id: int, data: dict) -> None:
    """Persist extracted action items, contacts, and reminders."""
    with get_db() as db:
        # Action items
        for item in data.get("action_items", []):
            db.execute(
                "INSERT INTO action_items (note_id, description, due_date) VALUES (?, ?, ?)",
                (note_id, item["description"], item.get("due_date", "")),
            )

        # Contacts — upsert by name
        contact_map: dict[str, int] = {}
        for c in data.get("contacts", []):
            name = c["name"]
            existing = db.execute(
                "SELECT id FROM contacts WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                cid = existing["id"]
                if c.get("phone"):
                    db.execute(
                        "UPDATE contacts SET phone = ? WHERE id = ? AND phone = ''",
                        (c["phone"], cid),
                    )
                if c.get("email"):
                    db.execute(
                        "UPDATE contacts SET email = ? WHERE id = ? AND email = ''",
                        (c["email"], cid),
                    )
            else:
                cur = db.execute(
                    "INSERT INTO contacts (name, phone, email) VALUES (?, ?, ?)",
                    (name, c.get("phone", ""), c.get("email", "")),
                )
                cid = cur.lastrowid
            contact_map[name] = cid

            db.execute(
                "INSERT OR IGNORE INTO note_contacts (note_id, contact_id) VALUES (?, ?)",
                (note_id, cid),
            )

        # Reminders
        for r in data.get("reminders", []):
            contact_name = r.get("contact_name", "")
            cid = contact_map.get(contact_name)
            if not cid:
                row = db.execute(
                    "SELECT id FROM contacts WHERE name = ?", (contact_name,)
                ).fetchone()
                if row:
                    cid = row["id"]
            if cid:
                db.execute(
                    "INSERT INTO reminders (contact_id, reminder_type, message, due_date) VALUES (?, ?, ?, ?)",
                    (cid, r.get("type", "follow_up"), r.get("message", ""), r.get("due_date", "")),
                )


async def extract_text_from_image(image_bytes: bytes, media_type: str) -> str:
    """Use Claude vision API to extract text from an image."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for image text extraction")

    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all text from this image. Preserve the original "
                            "structure, line breaks, and formatting as closely as possible. "
                            "Return only the extracted text with no additional commentary."
                        ),
                    },
                ],
            }
        ],
    )
    return message.content[0].text
