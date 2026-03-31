from __future__ import annotations

import json
import sqlite3
import numpy as np
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class MessageRecord:
    id: str
    thread_id: str
    subject: str
    sender: str
    date: str
    snippet: str
    body: str
    summary: Optional[str]
    labels: List[str]
    is_archived: bool = False
    created_at: str = ""
    embedding: Optional[np.ndarray] = None


class MessageStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              subject TEXT,
              sender TEXT,
              date TEXT,
              snippet TEXT,
              body TEXT,
              summary TEXT,
              labels TEXT,
              is_archived INTEGER DEFAULT 0,
              created_at TEXT,
              embedding BLOB
            );

            CREATE INDEX IF NOT EXISTS idx_messages_archived_date
            ON messages (is_archived, date);
            """
        )
        self.conn.commit()

    def upsert_message(self, rec: MessageRecord):
        self.conn.execute(
            """
            INSERT INTO messages (id, thread_id, subject, sender, date, snippet, body, summary, labels, is_archived, created_at, embedding)
            VALUES (:id, :thread_id, :subject, :sender, :date, :snippet, :body, :summary, :labels, :is_archived, :created_at, :embedding)
            ON CONFLICT(id) DO UPDATE SET
              thread_id=excluded.thread_id,
              subject=excluded.subject,
              sender=excluded.sender,
              date=excluded.date,
              snippet=excluded.snippet,
              body=excluded.body,
              summary=excluded.summary,
              labels=excluded.labels,
              is_archived=excluded.is_archived,
              created_at=excluded.created_at,
              embedding=excluded.embedding
            """,
            {
                "id": rec.id,
                "thread_id": rec.thread_id,
                "subject": rec.subject,
                "sender": rec.sender,
                "date": rec.date,
                "snippet": rec.snippet,
                "body": rec.body,
                "summary": rec.summary,
                "labels": json.dumps(rec.labels),
                "is_archived": 1 if rec.is_archived else 0,
                "created_at": rec.created_at or datetime.utcnow().isoformat(),
                "embedding": rec.embedding.astype(np.float32).tobytes() if rec.embedding is not None else None,
            },
        )
        self.conn.commit()

    def bulk_upsert(self, records: Iterable[MessageRecord]):
        cur = self.conn.cursor()
        for rec in records:
            cur.execute(
                """
                INSERT INTO messages (id, thread_id, subject, sender, date, snippet, body, summary, labels, is_archived, created_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  thread_id=excluded.thread_id,
                  subject=excluded.subject,
                  sender=excluded.sender,
                  date=excluded.date,
                  snippet=excluded.snippet,
                  body=excluded.body,
                  summary=excluded.summary,
                  labels=excluded.labels,
                  is_archived=excluded.is_archived,
                  created_at=excluded.created_at,
                  embedding=excluded.embedding
                """,
                (
                    rec.id,
                    rec.thread_id,
                    rec.subject,
                    rec.sender,
                    rec.date,
                    rec.snippet,
                    rec.body,
                    rec.summary,
                    json.dumps(rec.labels),
                    1 if rec.is_archived else 0,
                    rec.created_at or datetime.utcnow().isoformat(),
                    rec.embedding.astype(np.float32).tobytes() if rec.embedding is not None else None,
                ),
            )
        self.conn.commit()

    def list_messages(self, include_archived: bool = False, limit: int = 100, query: str | None = None):
        q = "SELECT * FROM messages"
        clauses = []
        if not include_archived:
            clauses.append("is_archived = 0")
        if query:
            clauses.append("(subject LIKE ? OR sender LIKE ? OR body LIKE ? OR snippet LIKE ?)")
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY datetime(date) DESC LIMIT ?"

        params = []
        if query:
            like = f"%{query}%"
            params.extend([like, like, like, like])
        params.append(limit)

        rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def set_archived(self, message_ids: list[str], archived: bool):
        if not message_ids:
            return 0
        placeholder = ",".join(["?"] * len(message_ids))
        cur = self.conn.execute(
            f"UPDATE messages SET is_archived = ? WHERE id IN ({placeholder})",
            [1 if archived else 0, *message_ids],
        )
        self.conn.commit()
        return cur.rowcount

    def get_embedding_rows(self):
        rows = self.conn.execute("SELECT id, embedding FROM messages WHERE embedding IS NOT NULL").fetchall()
        out = []
        for r in rows:
            vec = np.frombuffer(r["embedding"], dtype=np.float32)
            out.append((r["id"], vec))
        return out

    def get_messages_for_similarity(self, message_ids: Iterable[str]):
        ids = list(message_ids)
        if not ids:
            return []
        placeholder = ",".join(["?"] * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM messages WHERE id IN ({placeholder})",
            ids,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, message_id: str):
        row = self.conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def _row_to_dict(self, row):
        rec = dict(row)
        rec["labels"] = json.loads(rec["labels"]) if rec.get("labels") else []
        rec["is_archived"] = bool(rec["is_archived"])
        return rec

    def search_by_vector(self, query_vector, top_k: int = 20):
        stored = self.get_embedding_rows()
        if not stored:
            return []

        vecs = np.stack([v for _, v in stored], axis=0)
        qvec = np.array(query_vector, dtype=np.float32)
        if vecs.ndim != 2:
            return []

        # cosine similarity
        num = vecs @ qvec
        den = np.linalg.norm(vecs, axis=1) * (np.linalg.norm(qvec) + 1e-9)
        score = num / np.maximum(den, 1e-9)

        idx = np.argsort(score)[::-1][:top_k]
        top_ids = [stored[i][0] for i in idx]

        rows = self.conn.execute(
            f"SELECT * FROM messages WHERE id IN ({','.join('?' * len(top_ids))})",
            top_ids,
        ).fetchall()

        lookup = {r["id"]: dict(r) for r in rows}
        result = []
        for i in idx:
            mid = stored[i][0]
            if mid in lookup:
                payload = self._row_to_dict(lookup[mid])
                payload["score"] = float(score[i])
                result.append(payload)
        return result