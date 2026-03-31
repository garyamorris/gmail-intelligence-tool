from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import json

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

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
from app.intelligence import IntelligenceEngine
from app.storage import MessageRecord, MessageStore
from app.secrets_store import add_secret_version


config = Config.validate()
store = MessageStore(config.db_path)
embedder: EmbeddingService | None = None
intel = IntelligenceEngine()


def _get_embedder() -> EmbeddingService:
    global embedder
    if embedder is None:
        embedder = EmbeddingService(config.embedding_model)
    return embedder


def _sync_messages(max_results: int = 40, query: str = "in:inbox") -> int:
    svc = build_gmail_service(str(config.token_path), config.client_secrets_file)
    msg_refs = list_messages(svc, query=query, max_results=max_results)

    embed = _get_embedder()
    records: List[MessageRecord] = []

    for ref in msg_refs:
        msg = fetch_full_message(svc, ref["id"])
        analysis = intel.analyze(msg["subject"], msg["sender"], msg["snippet"], msg["body"])
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
                summary=analysis.summary,
                labels=msg["labels"],
                intent=analysis.intent,
                suggested_action=analysis.suggested_action,
                cluster_label=analysis.cluster_label,
                actionability_score=analysis.actionability_score,
                noise_score=analysis.noise_score,
                reason_codes=analysis.reason_codes,
                embedding=vector,
            )
        )
        for item in intel.action_items(msg["subject"], msg["body"]):
            store.add_action_items(msg["id"], [item])

    if records:
        store.bulk_upsert(records)
    return len(records)


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


@app.get("/api/topics")
def topics_api(limit: int = 50, include_archived: bool = False):
    return store.list_topics(include_archived=include_archived, limit=limit)


@app.get("/api/briefing")
def briefing_api(limit: int = 10):
    return {
        "top_messages": store.recent_briefing(limit=limit),
        "action_items": store.list_action_items(limit=limit),
    }


@app.get("/api/lane/{lane}")
def lane_api(lane: str, limit: int = 50):
    lane = lane.lower().strip()
    rows = store.list_messages(include_archived=False, limit=500)
    if lane == "waiting":
        rows = [r for r in rows if r.get("intent") in {"follow_up", "acknowledgement"} or r.get("suggested_action") in {"set_follow_up", "quiet"}]
    elif lane == "decision":
        rows = [r for r in rows if r.get("intent") in {"approval", "finance"} or r.get("actionability_score", 0) >= 3]
    elif lane == "noise":
        rows = [r for r in rows if r.get("noise_score", 0) >= 2 or r.get("suggested_action") in {"archive", "quiet"}]
    elif lane == "reply":
        rows = [r for r in rows if r.get("suggested_action") in {"reply", "draft_schedule_reply", "review_and_route"}]
    else:
        raise HTTPException(status_code=400, detail="Unknown lane")
    return rows[:limit]


@app.get("/api/message/{message_id}")
def message_api(message_id: str):
    row = store.get_by_id(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    items = [i for i in store.list_action_items(limit=100) if i["message_id"] == message_id]
    row["action_items"] = items
    row["draft_reply"] = intel.draft_reply(row["subject"], row["sender"], row.get("summary", ""), row.get("intent", "reply_needed"))
    return row


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
    synced = _sync_messages(max_results=max_results, query=query)
    return {"synced": synced}


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


@app.post("/api/draft_reply")
def draft_reply_api(payload: dict):
    message_id = payload.get("message_id")
    tone = payload.get("tone", "concise")
    if not message_id:
        raise HTTPException(status_code=400, detail="message_id required")
    row = store.get_by_id(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    draft = intel.draft_reply(row["subject"], row["sender"], row.get("summary", ""), row.get("intent", "reply_needed"), tone=tone)
    return {"message_id": message_id, "draft": draft}


@app.post("/api/analyze")
def analyze_api(payload: dict):
    message_id = payload.get("message_id")
    if not message_id:
        raise HTTPException(status_code=400, detail="message_id required")

    row = store.get_by_id(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")

    return row


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
        try:
            _sync_messages(max_results=25, query="in:inbox")
        except Exception:
            pass
        return RedirectResponse(url="/?auth=ok&synced=1", status_code=302)
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
