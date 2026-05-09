"""
Transcript history — lightweight SQLite store.
Each transcription is stored with timestamp, backend used, duration, and word count.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "carefulwhisper" / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    language    TEXT,
    backend     TEXT,
    duration_s  REAL,
    word_count  INTEGER,
    profile     TEXT DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_created ON transcripts (created_at DESC);
"""


@dataclass
class Transcript:
    id: int
    created_at: str
    text: str
    language: str
    backend: str
    duration_s: float
    word_count: int
    profile: str


class HistoryStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def add(
        self,
        text: str,
        language: str = "en",
        backend: str = "",
        duration_s: float = 0.0,
        profile: str = "default",
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO transcripts (created_at, text, language, backend, duration_s, word_count, profile)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                text,
                language,
                backend,
                duration_s,
                len(text.split()),
                profile,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str = "",
    ) -> list[Transcript]:
        if search:
            rows = self._conn.execute(
                "SELECT * FROM transcripts WHERE text LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (f"%{search}%", limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM transcripts ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [Transcript(**dict(r)) for r in rows]

    def delete(self, transcript_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM transcripts WHERE id = ?", (transcript_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        self._conn.execute("DELETE FROM transcripts")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
