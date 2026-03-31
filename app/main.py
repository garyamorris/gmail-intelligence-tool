from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import json

from fastapi.responses import RedirectResponse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import httpx

from app.config import Config
from app.embeddings import EmbeddingService
from app.gmail_service import (
    archive_messages,
    build_gmail_service,
    exchange_auth_code,
    fetch_full_message,
    get_google_auth_url,
    list_messages,
)
from app.storage import MessageRecord, MessageStore
from app.secrets_store import add_secret_version


config = Config.validate()
store = MessageStore(config.db_path)
embedder: EmbeddingService | None = None


def _get_embedder() -> EmbeddingService:
    global embedder
    if embedder is None:
        embedder = EmbeddingService(config.embedding_model)
    return embedder


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    MessageStore(config.db_path)
    yield


app = FastAPI(title="Gmail Intelligence Tool", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/messages")
def list_api(limit: int = 50, include_archived: bool = False, q: Optional[str] = None):
    return store.list_messages(include_archived=include_archived, limit=limit, query=q)


@app.get("/api/search")
def search_api(q: str, k: int = 20):
    if not q:
        raise HTTPException(status_code=400, detail="q is required")

    vector = _get_embedder().embed_query(q)
    if not vector:
        return []
    return store.search_by_vector(vector, top_k=k)


@app.post("/api/sync")
def sync_api(payload: dict):
    max_results = int(payload.get("max_results", 40))
    query = payload.get("query", "in:inbox")

    svc = build_gmail_service(str(config.token_path), config.client_secrets_file)
    msg_refs = list_messages(svc, query=query, max_results=max_results)

    embed = _get_embedder()
    records: List[MessageRecord] = []

    for ref in msg_refs:
        msg = fetch_full_message(svc, ref["id"])
        text_for_embedding = f"Subject: {msg['subject']}\nFrom: {msg['sender']}\n\n{msg['snippet']}\n{msg['body']}"
        vector = embed.embed([text_for_embedding])[0]
        records.append(
            MessageRecord(
                id=msg["id"],
                thread_id=msg["thread_id"],
                subject=msg["subject"],
                sender=msg["sender"],
                date=msg["date"],
                snippet=msg["snippet"],
                body=msg["body"],
                summary=None,
                labels=msg["labels"],
                embedding=vector,
            )
        )

    if records:
        store.bulk_upsert(records)

    return {"synced": len(records)}


@app.post("/api/archive")
def archive_api(payload: dict):
    message_ids = payload.get("message_ids", [])
    if not isinstance(message_ids, list) or not message_ids:
        raise HTTPException(status_code=400, detail="message_ids must be a non-empty list")

    svc = build_gmail_service(str(config.token_path), config.client_secrets_file)
    archived = archive_messages(svc, message_ids=message_ids)
    store.set_archived(message_ids, True)
    return {"archived": archived}


@app.post("/api/bulk_archive_by_query")
def bulk_archive_by_query(payload: dict):
    q = payload.get("query", "")
    if not q:
        raise HTTPException(status_code=400, detail="query required")

    limit = int(payload.get("limit", 20))
    rows = store.list_messages(include_archived=False, limit=limit, query=q)
    ids = [r["id"] for r in rows]
    if not ids:
        return {"archived": 0}

    svc = build_gmail_service(str(config.token_path), config.client_secrets_file)
    archived = archive_messages(svc, message_ids=ids)
    store.set_archived(ids, True)
    return {"archived": archived, "message_ids": ids}


@app.post("/api/analyze")
def analyze_api(payload: dict):
    """Very lightweight actionability signal (heuristic).

    For stricter triage, call an agent webhook with /api/agent/handoff.
    """
    message_id = payload.get("message_id")
    if not message_id:
        raise HTTPException(status_code=400, detail="message_id required")

    row = store.get_by_id(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")

    body = (row["snippet"] + "\n" + row["body"]).lower()
    action_words = ["action", "required", "needed", "please", "reply", "urgent", "approve", "sign", "confirm", "invoice", "meeting"]
    score = sum(1 for w in action_words if w in body)

    return {
        "message_id": message_id,
        "subject": row["subject"],
        "sender": row["sender"],
        "suggested_actionable": score > 1,
        "actionability_score": score,
    }


@app.get("/auth/login")
def auth_login(mode: str = "json"):
    path = Path(config.client_secrets_file)
    if not path.exists():
        raise HTTPException(status_code=400, detail="GMAIL_CLIENT_SECRETS file missing")

    raw = path.read_text(encoding="utf-8").strip()
    if not raw or raw == "{}":
        raise HTTPException(
            status_code=400,
            detail="OAuth client secret is empty placeholder. Replace gmail-client-secrets-json with a real Google OAuth client_secret.json",
        )

    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="GMAIL_CLIENT_SECRETS is not valid JSON")

    if not payload.get("installed") and not payload.get("web"):
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth client type. Create a Web or Installed app client in Google Cloud OAuth credentials.",
        )

    try:
        auth_url = get_google_auth_url(config.client_secrets_file, config.redirect_uri)
        if mode == "redirect":
            return RedirectResponse(url=auth_url, status_code=302)
        return {"auth_url": auth_url}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create auth URL from client secret: {exc}",
        )


@app.get("/auth/start")
def auth_start():
    # One-tap path for phone users: open this URL and it jumps straight to Google consent.
    return auth_login(mode="redirect")


@app.get("/auth/callback")
def auth_callback(code: str):
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    try:
        creds = exchange_auth_code(config.client_secrets_file, config.redirect_uri, code)
        token_json = creds.to_json()
        Path(config.token_path).write_text(token_json, encoding="utf-8")
        try:
            add_secret_version("gmail-token-json", token_json)
        except Exception:
            pass
        return {"ok": True, "message": "Token saved. You can now use /api/sync"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {exc}")


@app.post("/api/agent/handoff")
async def agent_handoff(payload: dict):
    url = config.agent_webhook
    if not url:
        raise HTTPException(status_code=400, detail="AGENT_WEBHOOK_URL not configured")

    payload_json = {
        "source": "gmail-intelligence-tool",
        "message_ids": payload.get("message_ids", []),
        "instruction": payload.get("instruction", "Review and summarize messages"),
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload_json)
    return JSONResponse(content={"status": resp.status_code, "response": resp.text})
