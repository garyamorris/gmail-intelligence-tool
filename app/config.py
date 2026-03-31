from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from app.secrets_store import get_secret_version


@dataclass
class Config:
    project_root: Path = Path(__file__).resolve().parents[1]
    db_path: Path = Path(os.getenv("DB_PATH", "/app/data/messages.db"))
    client_secrets_file: str = os.getenv("GMAIL_CLIENT_SECRETS", str(project_root / "credentials" / "client_secret.json"))
    client_secrets_json: str = os.getenv("GMAIL_CLIENT_SECRETS_JSON", "")
    token_path: Path = Path(os.getenv("GMAIL_TOKEN_PATH", str(project_root / "credentials" / "token.json")))
    token_json: str = os.getenv("GMAIL_TOKEN_JSON", "")
    user_email: str = os.getenv("GMAIL_USER_EMAIL", "")
    redirect_uri: str = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8080/auth/callback")
    allowed_emails: list[str] = field(default_factory=list)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")
    agent_webhook: str = os.getenv("AGENT_WEBHOOK_URL", "")
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    service_name: str = os.getenv("SERVICE_NAME", "gmail-intelligence-tool")
    gmail_client_secrets_secret: str = os.getenv("GMAIL_CLIENT_SECRETS_SECRET", "gmail-client-secrets-json")
    gmail_token_secret: str = os.getenv("GMAIL_TOKEN_SECRET", "gmail-token-json")

    @classmethod
    def validate(cls) -> "Config":
        cfg = cls()
        raw_emails = os.getenv("ALLOWED_USER_EMAILS", "")
        cfg.allowed_emails = [email.strip() for email in raw_emails.split(",") if email.strip()]

        cfg.client_secrets_file = str(Path(cfg.client_secrets_file))
        Path(cfg.client_secrets_file).parent.mkdir(parents=True, exist_ok=True)
        if cfg.client_secrets_json and not Path(cfg.client_secrets_file).exists():
            Path(cfg.client_secrets_file).write_text(cfg.client_secrets_json, encoding="utf-8")
        elif not Path(cfg.client_secrets_file).exists():
            try:
                secret = get_secret_version(cfg.gmail_client_secrets_secret)
                if secret:
                    Path(cfg.client_secrets_file).write_text(secret, encoding="utf-8")
            except Exception:
                pass

        cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
        if cfg.token_json and not cfg.token_path.exists():
            cfg.token_path.write_text(cfg.token_json, encoding="utf-8")
        elif not cfg.token_path.exists():
            try:
                secret = get_secret_version(cfg.gmail_token_secret)
                if secret:
                    cfg.token_path.write_text(secret, encoding="utf-8")
            except Exception:
                pass
        return cfg
