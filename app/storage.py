from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np


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
    intent: str = "reply_needed"
    suggested_action: str = "review"
    cluster_label: str = "Uncategorized"
    actionability_score: int = 0
    noise_score: int = 0
    reason_codes: List[str] = field(default_factory=list)
    unsubscribe_url: str = ""
    is_archived: bool = False
    created_at: str = ""
    embedding: Optional[object] = None


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
              intent TEXT DEFAULT 'reply_needed',
              suggested_action TEXT DEFAULT 'review',
              cluster_label TEXT DEFAULT 'Uncategorized',
              actionability_score INTEGER DEFAULT 0,
              noise_score INTEGER DEFAULT 0,
              reason_codes TEXT DEFAULT '[]',
              unsubscribe_url TEXT DEFAULT '',
              is_archived INTEGER DEFAULT 0,
              created_at TEXT,
              embedding BLOB
            );

            CREATE INDEX IF NOT EXISTS idx_messages_archived_date
            ON messages (is_archived, date);

            CREATE INDEX IF NOT EXISTS idx_messages_thread_id
            ON messages (thread_id);

            CREATE INDEX IF NOT EXISTS idx_messages_sender
            ON messages (sender);

            CREATE TABLE IF NOT EXISTS action_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              message_id TEXT NOT NULL,
              item TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL,
              FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()
        self._ensure_optional_columns()


    def _ensure_optional_columns(self):
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "unsubscribe_url" not in cols:
            self.conn.execute("ALTER TABLE messages ADD COLUMN unsubscribe_url TEXT DEFAULT ''")
            self.conn.commit()

    def _embedding_bytes(self, embedding):
        if embedding is None:
            return None
        arr = np.asarray(embedding, dtype=np.float32)
        return arr.tobytes()

    def upsert_message(self, rec: MessageRecord):
        self.conn.execute(
            """
            INSERT INTO messages (id, thread_id, subject, sender, date, snippet, body, summary, labels, intent, suggested_action, cluster_label, actionability_score, noise_score, reason_codes, unsubscribe_url, is_archived, created_at, embedding)
            VALUES (:id, :thread_id, :subject, :sender, :date, :snippet, :body, :summary, :labels, :intent, :suggested_action, :cluster_label, :actionability_score, :noise_score, :reason_codes, :unsubscribe_url, :is_archived, :created_at, :embedding)
            ON CONFLICT(id) DO UPDATE SET
              thread_id=excluded.thread_id,
              subject=excluded.subject,
              sender=excluded.sender,
              date=excluded.date,
              snippet=excluded.snippet,
              body=excluded.body,
              summary=excluded.summary,
              labels=excluded.labels,
              intent=excluded.intent,
              suggested_action=excluded.suggested_action,
              cluster_label=excluded.cluster_label,
              actionability_score=excluded.actionability_score,
              noise_score=excluded.noise_score,
              reason_codes=excluded.reason_codes,
              unsubscribe_url=excluded.unsubscribe_url,
              is_archived=excluded.is_archived,
              created_at=excluded.created_at,
              embedding=excluded.embedding
            """,
            self._record_params(rec),
        )
        self.conn.commit()

    def bulk_upsert(self, records: Iterable[MessageRecord]):
        cur = self.conn.cursor()
        for rec in records:
            cur.execute(
                """
                INSERT INTO messages (id, thread_id, subject, sender, date, snippet, body, summary, labels, intent, suggested_action, cluster_label, actionability_score, noise_score, reason_codes, unsubscribe_url, is_archived, created_at, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  thread_id=excluded.thread_id,
                  subject=excluded.subject,
                  sender=excluded.sender,
                  date=excluded.date,
                  snippet=excluded.snippet,
                  body=excluded.body,
                  summary=excluded.summary,
                  labels=excluded.labels,
                  intent=excluded.intent,
                  suggested_action=excluded.suggested_action,
                  cluster_label=excluded.cluster_label,
                  actionability_score=excluded.actionability_score,
                  noise_score=excluded.noise_score,
                  reason_codes=excluded.reason_codes,
                  unsubscribe_url=excluded.unsubscribe_url,
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
                    rec.intent,
                    rec.suggested_action,
                    rec.cluster_label,
                    int(rec.actionability_score),
                    int(rec.noise_score),
                    json.dumps(rec.reason_codes or []),
                    rec.unsubscribe_url,
                    1 if rec.is_archived else 0,
                    rec.created_at or datetime.utcnow().isoformat(),
                    self._embedding_bytes(rec.embedding),
                ),
            )
        self.conn.commit()

    def add_action_items(self, message_id: str, items: list[str]):
        if not items:
            return 0
        created_at = datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        for item in items:
            cur.execute(
                "INSERT INTO action_items (message_id, item, created_at) VALUES (?, ?, ?)",
                (message_id, item, created_at),
            )
        self.conn.commit()
        return cur.rowcount

    def list_action_items(self, limit: int = 50):
        rows = self.conn.execute(
            """
            SELECT ai.*, m.subject, m.sender, m.cluster_label
            FROM action_items ai
            JOIN messages m ON m.id = ai.message_id
            ORDER BY datetime(ai.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_messages(self, include_archived: bool = False, limit: int = 100, query: str | None = None):
        q = "SELECT * FROM messages"
        clauses = []
        if not include_archived:
            clauses.append("is_archived = 0")
        if query:
            clauses.append("(subject LIKE ? OR sender LIKE ? OR body LIKE ? OR snippet LIKE ? OR cluster_label LIKE ? OR intent LIKE ?)")
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY datetime(date) DESC LIMIT ?"

        params = []
        if query:
            like = f"%{query}%"
            params.extend([like, like, like, like, like, like])
        params.append(limit)

        rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_topics(self, include_archived: bool = False, limit: int = 50):
        q = """
        SELECT cluster_label, COUNT(*) as message_count,
               SUM(CASE WHEN is_archived = 0 THEN 1 ELSE 0 END) as active_count,
               MAX(date) as latest_date,
               MAX(sender) as latest_sender,
               SUM(actionability_score) as total_actionability,
               SUM(noise_score) as total_noise
        FROM messages
        """
        if not include_archived:
            q += " WHERE is_archived = 0"
        q += " GROUP BY cluster_label ORDER BY latest_date DESC LIMIT ?"
        rows = self.conn.execute(q, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def list_repeat_senders(self, include_archived: bool = False, min_count: int = 2, limit: int = 25):
        q = """
        SELECT sender,
               COUNT(*) as message_count,
               SUM(CASE WHEN is_archived = 1 THEN 1 ELSE 0 END) as archived_count,
               MAX(date) as latest_date,
               SUM(actionability_score) as total_actionability,
               SUM(noise_score) as total_noise
        FROM messages
        """
        clauses = []
        if not include_archived:
            clauses.append("is_archived = 0")
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " GROUP BY sender HAVING COUNT(*) >= ? ORDER BY latest_date DESC LIMIT ?"
        rows = self.conn.execute(q, (min_count, limit)).fetchall()
        return [dict(r) for r in rows]

    def messages_by_sender(self, sender: str, include_archived: bool = False, limit: int = 100):
        q = "SELECT * FROM messages WHERE sender = ?"
        if not include_archived:
            q += " AND is_archived = 0"
        q += " ORDER BY datetime(date) DESC LIMIT ?"
        rows = self.conn.execute(q, (sender, limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def recent_briefing(self, limit: int = 10):
        rows = self.conn.execute(
            """
            SELECT id, subject, sender, date, cluster_label, intent, suggested_action, actionability_score, noise_score, is_archived
            FROM messages
            WHERE is_archived = 0
            ORDER BY actionability_score DESC, datetime(date) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

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

    def _record_params(self, rec: MessageRecord):
        return {
            "id": rec.id,
            "thread_id": rec.thread_id,
            "subject": rec.subject,
            "sender": rec.sender,
            "date": rec.date,
            "snippet": rec.snippet,
            "body": rec.body,
            "summary": rec.summary,
            "labels": json.dumps(rec.labels),
            "intent": rec.intent,
            "suggested_action": rec.suggested_action,
            "cluster_label": rec.cluster_label,
            "actionability_score": int(rec.actionability_score),
            "noise_score": int(rec.noise_score),
            "reason_codes": json.dumps(rec.reason_codes or []),
            "unsubscribe_url": rec.unsubscribe_url,
            "is_archived": 1 if rec.is_archived else 0,
            "created_at": rec.created_at or datetime.utcnow().isoformat(),
            "embedding": self._embedding_bytes(rec.embedding),
        }

    def _row_to_dict(self, row):
        rec = dict(row)
        rec.pop("embedding", None)
        rec["labels"] = json.loads(rec["labels"]) if rec.get("labels") else []
        rec["reason_codes"] = json.loads(rec["reason_codes"]) if rec.get("reason_codes") else []
        rec["unsubscribe_url"] = rec.get("unsubscribe_url") or ""
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

        num = vecs @ qvec
        den = np.linalg.norm(vecs, axis=1) * (np.linalg.norm(qvec) + 1e-9)
        score = num / np.maximum(den, 1e-9)

        idx = np.argsort(score)[::-1][:top_k]
        top_ids = [stored[i][0] for i in idx]
        if not top_ids:
            return []

        rows = self.conn.execute(
            f"SELECT * FROM messages WHERE id IN ({','.join('?' for _ in top_ids)})",
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
