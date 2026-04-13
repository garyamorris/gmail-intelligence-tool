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

            CREATE TABLE IF NOT EXISTS sender_preferences (
              sender TEXT PRIMARY KEY,
              classification TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL
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

    def _sender_unsubscribe_links(self, sender: str, include_archived: bool = True, limit: int = 5):
        q = "SELECT DISTINCT unsubscribe_url FROM messages WHERE sender = ? AND unsubscribe_url != ''"
        params = [sender]
        if not include_archived:
            q += " AND is_archived = 0"
        q += " ORDER BY unsubscribe_url LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(q, params).fetchall()
        return [r["unsubscribe_url"] for r in rows]

    def _sender_primary_cluster(self, sender: str, include_archived: bool = True):
        q = """
        SELECT cluster_label, COUNT(*) as message_count, MAX(date) as latest_date
        FROM messages
        WHERE sender = ?
        """
        params = [sender]
        if not include_archived:
            q += " AND is_archived = 0"
        q += """
        GROUP BY cluster_label
        ORDER BY message_count DESC, datetime(latest_date) DESC
        LIMIT 1
        """
        return self.conn.execute(q, params).fetchone()

    def _sender_recent_subjects(self, sender: str, include_archived: bool = True, limit: int = 3):
        q = "SELECT subject FROM messages WHERE sender = ?"
        params = [sender]
        if not include_archived:
            q += " AND is_archived = 0"
        q += " ORDER BY datetime(date) DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(q, params).fetchall()
        subjects: list[str] = []
        for row in rows:
            subject = (row["subject"] or "").strip()
            if subject and subject not in subjects:
                subjects.append(subject)
        return subjects

    def set_sender_classification(self, sender: str, classification: str, note: str = ""):
        updated_at = datetime.utcnow().isoformat()
        self.conn.execute(
            """
            INSERT INTO sender_preferences (sender, classification, note, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sender) DO UPDATE SET
              classification=excluded.classification,
              note=excluded.note,
              updated_at=excluded.updated_at
            """,
            (sender, classification, note, updated_at),
        )
        self.conn.commit()

    def get_sender_preferences(self, senders: Iterable[str]):
        sender_list = [sender for sender in senders if sender]
        if not sender_list:
            return {}
        placeholder = ",".join(["?"] * len(sender_list))
        rows = self.conn.execute(
            f"SELECT sender, classification, note, updated_at FROM sender_preferences WHERE sender IN ({placeholder})",
            sender_list,
        ).fetchall()
        return {row["sender"]: dict(row) for row in rows}

    def _junk_signal_rollup(self, sender_row: dict):
        avg_noise = float(sender_row.get("avg_noise_score") or 0.0)
        avg_actionability = float(sender_row.get("avg_actionability_score") or 0.0)
        message_count = int(sender_row.get("message_count") or 0)
        active_count = int(sender_row.get("active_count") or 0)
        archived_count = int(sender_row.get("archived_count") or 0)
        unsubscribe_link_count = int(sender_row.get("unsubscribe_link_count") or 0)

        signals: list[str] = []
        if message_count >= 5:
            signals.append(f"{message_count} stored messages")
        if avg_noise >= 1.5:
            signals.append(f"avg noise {avg_noise:.1f}")
        if unsubscribe_link_count > 0:
            signals.append(f"{unsubscribe_link_count} unsubscribe links")
        if archived_count > 0:
            signals.append(f"{archived_count} already archived")
        if active_count >= 5:
            signals.append(f"{active_count} still active")

        score = min(30.0, message_count * 2.0)
        score += min(25.0, avg_noise * 8.0)
        score += min(20.0, unsubscribe_link_count * 10.0)
        score += min(15.0, archived_count * 1.2)
        score -= min(20.0, avg_actionability * 6.0)
        return round(max(0.0, score), 1), signals

    def _classify_repeat_sender(self, sender_row: dict, manual_classification: str = ""):
        avg_noise = float(sender_row.get("avg_noise_score") or 0.0)
        avg_actionability = float(sender_row.get("avg_actionability_score") or 0.0)
        unsubscribe_link_count = int(sender_row.get("unsubscribe_link_count") or 0)
        active_count = int(sender_row.get("active_count") or 0)
        archived_count = int(sender_row.get("archived_count") or 0)
        junk_score = float(sender_row.get("junk_score") or 0.0)

        if manual_classification == "junk":
            return (
                "junk-sender",
                "Marked as junk manually. Treat this sender as bulk clutter.",
            )
        if junk_score >= 45:
            return (
                "junk-suspect",
                "Heavy repeat volume with strong junk signals across the mailbox.",
            )

        if unsubscribe_link_count > 0 and avg_noise >= 1.5:
            return (
                "subscription-heavy",
                "Recurring sender with unsubscribe links and mostly low-signal mail.",
            )
        if avg_actionability >= 2.5 and avg_actionability > avg_noise:
            return (
                "priority-repeat",
                "Recurring sender with a higher concentration of actionable mail.",
            )
        if archived_count > active_count and avg_noise >= 1.0:
            return (
                "mostly-cleared",
                "Historically noisy sender that is already mostly archived.",
            )
        if unsubscribe_link_count > 0:
            return (
                "marketing-or-updates",
                "Recurring sender with unsubscribe options and mixed importance.",
            )
        return (
            "mixed-repeat",
            "Recurring sender with mixed signal across the mailbox.",
        )

    def list_repeat_senders(self, include_archived: bool = False, min_count: int = 2, limit: int = 25):
        q = """
        SELECT sender,
               COUNT(*) as message_count,
               SUM(CASE WHEN is_archived = 0 THEN 1 ELSE 0 END) as active_count,
               SUM(CASE WHEN is_archived = 1 THEN 1 ELSE 0 END) as archived_count,
               COUNT(DISTINCT thread_id) as thread_count,
               MAX(date) as latest_date,
               SUM(actionability_score) as total_actionability,
               SUM(noise_score) as total_noise,
               AVG(actionability_score) as avg_actionability_score,
               AVG(noise_score) as avg_noise_score,
               COUNT(DISTINCT CASE WHEN unsubscribe_url != '' THEN unsubscribe_url END) as unsubscribe_link_count,
               MAX(CASE WHEN unsubscribe_url != '' THEN unsubscribe_url END) as unsubscribe_url
        FROM messages
        """
        clauses = []
        clauses.append("sender != ''")
        if not include_archived:
            clauses.append("is_archived = 0")
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " GROUP BY sender HAVING COUNT(*) >= ? ORDER BY message_count DESC, datetime(latest_date) DESC LIMIT ?"
        rows = self.conn.execute(q, (min_count, limit)).fetchall()
        preferences = self.get_sender_preferences([row["sender"] for row in rows])
        senders = []
        for row in rows:
            sender_row = dict(row)
            preference = preferences.get(sender_row["sender"], {})
            sender_row["avg_actionability_score"] = round(float(sender_row.get("avg_actionability_score") or 0.0), 2)
            sender_row["avg_noise_score"] = round(float(sender_row.get("avg_noise_score") or 0.0), 2)
            sender_row["unsubscribe_links"] = self._sender_unsubscribe_links(sender_row["sender"], include_archived=include_archived)
            primary_cluster = self._sender_primary_cluster(sender_row["sender"], include_archived=include_archived)
            sender_row["primary_cluster"] = primary_cluster["cluster_label"] if primary_cluster else ""
            sender_row["recent_subjects"] = self._sender_recent_subjects(sender_row["sender"], include_archived=include_archived)
            junk_score, junk_signals = self._junk_signal_rollup(sender_row)
            sender_row["junk_score"] = junk_score
            sender_row["junk_signals"] = junk_signals
            sender_row["manual_classification"] = preference.get("classification", "")
            sender_row["manual_note"] = preference.get("note", "")
            category, reason = self._classify_repeat_sender(
                sender_row,
                manual_classification=sender_row["manual_classification"],
            )
            sender_row["sender_category"] = category
            sender_row["sender_reason"] = reason
            sender_row["sort_score"] = round(
                float(sender_row["message_count"])
                + float(sender_row["active_count"]) * 0.4
                + float(sender_row["unsubscribe_link_count"]) * 2.0
                + float(sender_row["avg_noise_score"]) * 1.5,
                2,
            )
            if sender_row["manual_classification"] == "junk":
                sender_row["sort_score"] += 25
            else:
                sender_row["sort_score"] += sender_row["junk_score"] * 0.35
            senders.append(sender_row)

        senders.sort(
            key=lambda row: (
                row.get("sort_score", 0),
                row.get("message_count", 0),
                row.get("active_count", 0),
            ),
            reverse=True,
        )
        return senders

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
