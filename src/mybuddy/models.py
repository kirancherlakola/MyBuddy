from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Note:
    id: int = 0
    title: str = ""
    content: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Contact:
    id: int = 0
    name: str = ""
    phone: str = ""
    email: str = ""


@dataclass
class ActionItem:
    id: int = 0
    note_id: int = 0
    description: str = ""
    is_completed: bool = False
    due_date: str = ""
    # joined field
    note_title: str = ""


@dataclass
class Reminder:
    id: int = 0
    contact_id: int = 0
    reminder_type: str = ""  # "call" or "follow_up"
    message: str = ""
    is_dismissed: bool = False
    due_date: str = ""
    # joined fields
    contact_name: str = ""
