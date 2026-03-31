from __future__ import annotations

import base64
import html
import os
from datetime import datetime
from email.header import decode_header
from typing import Any, Dict

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _decode_base64(data: str | None) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="ignore"))
        else:
            out.append(part)
    return "".join(out)


def _pluck_text(payload: Dict[str, Any]) -> str:
    if not payload:
        return ""
    body = payload.get("body", {})
    txt = _decode_base64(body.get("data"))
    if txt:
        return html.unescape(txt)

    for part in payload.get("parts", []) or []:
        mime = part.get("mimeType", "")
        ptxt = _pluck_text(part)
        if ptxt:
            return ptxt
    return ""


def get_google_auth_url(client_secrets_file: str, redirect_uri: str) -> str:
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=SCOPES, redirect_uri=redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    return url


def exchange_auth_code(client_secrets_file: str, redirect_uri: str, code: str) -> Credentials:
    flow = Flow.from_client_secrets_file(client_secrets_file, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    return flow.credentials


def load_credentials(token_path: str, client_secrets_file: str, force_refresh: bool = True) -> Credentials:
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.expired and creds.refresh_token and force_refresh:
        creds.refresh(Request())

    if not creds or not creds.valid:
        raise RuntimeError("No valid Gmail token. Visit /auth/login first.")

    current = None
    if os.path.exists(token_path):
        with open(token_path, "r", encoding="utf-8") as fh:
            current = fh.read()

    if current != creds.to_json():
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def build_gmail_service(token_path: str, client_secrets_file: str):
    creds = load_credentials(token_path, client_secrets_file)
    return build("gmail", "v1", credentials=creds)


def parse_message(msg: Dict[str, Any], body: str) -> Dict[str, str]:
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    subject = _decode_header_value(headers.get("subject", ""))
    sender = _decode_header_value(headers.get("from", ""))
    date = headers.get("date") or datetime.utcnow().isoformat()

    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId", ""),
        "subject": subject,
        "sender": sender,
        "date": date,
        "snippet": msg.get("snippet", ""),
        "body": body[:4000],
        "labels": msg.get("labelIds", []) or [],
    }


def list_messages(service, query: str = "in:inbox", max_results: int = 40):
    res = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return res.get("messages", []) or []


def fetch_full_message(service, message_id: str):
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    body = _pluck_text(msg.get("payload", {}))
    return parse_message(msg, body)


def archive_messages(service, message_ids: list[str]):
    if not message_ids:
        return 0
    body = {"removeLabelIds": ["INBOX"], "ids": message_ids}
    service.users().messages().batchModify(userId="me", body=body).execute()
    return len(message_ids)
