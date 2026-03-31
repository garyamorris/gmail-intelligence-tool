from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import List


@dataclass
class Config:
    # Core service settings
    project_root: Path = Path(__file__).resolve().parents[1]
    db_path: Path = Path(os.getenv("DB_PATH", "/app/data/messages.db"))
    client_secrets_file: str = os.getenv("GMAIL_CLIENT_SECRETS", str(project_root / "credentials" / "client_secret.json"))
    token_path: Path = Path(os.getenv("GMAIL_TOKEN_PATH", str(project_root / "credentials" / "token.json")))
    user_email: str = os.getenv("GMAIL_USER_EMAIL", "")
    redirect_uri: str = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8080/auth/callback")
    allowed_emails: List[str] = os.getenv("ALLOWED_USER_EMAILS", "").split(",") if os.getenv("ALLOWED_USER_EMAILS") else []

    # Embeddings
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "models/embedding-001")

    # Agent/webhook integrations
    agent_webhook: str = os.getenv("AGENT_WEBHOOK_URL", "")

    # App
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    service_name: str = os.getenv("SERVICE_NAME", "gmail-intelligence-tool")

    @classmethod
    def validate(cls) -> "Config":
        cfg = cls()
        if cfg.token_path:
            cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
        return cfg
