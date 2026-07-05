"""
Chat history for the AI Assistant.
Stored in the same directory as transcript history.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "carefulwhisper" / "chat_history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_created ON messages (created_at ASC);
"""

@dataclass
class ChatMessage:
    id: int
    created_at: str
    role: str
    content: str


class ChatHistoryStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def add_message(self, role: str, content: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO messages (created_at, role, content) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), role, content),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def get_messages(self, limit: int = 100) -> list[ChatMessage]:
        # Return recent messages, ordered by time
        # To get the latest N messages in chronological order, we can query DESC, limit, and reverse in python
        cur = self._conn.execute(
            "SELECT id, created_at, role, content FROM messages ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        msgs = [
            ChatMessage(
                id=r["id"],
                created_at=r["created_at"],
                role=r["role"],
                content=r["content"],
            )
            for r in rows
        ]
        msgs.reverse()
        return msgs

    def clear(self) -> None:
        self._conn.execute("DELETE FROM messages")
        self._conn.commit()
