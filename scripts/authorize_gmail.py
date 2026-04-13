"""Utility to generate local OAuth credentials for one-time Gmail auth.

Usage:
  python scripts/authorize_gmail.py

This writes token.json into ./credentials on success.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import Config

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


cfg = Config.validate()

if not os.path.exists(cfg.client_secrets_file):
    raise SystemExit(f"Missing client secrets file at {cfg.client_secrets_file}")

raw_client = Path(cfg.client_secrets_file).read_text(encoding="utf-8").strip()
client = json.loads(raw_client) if raw_client else {}
if client.get("web") and cfg.redirect_uri.startswith("https://127.0.0.1:8080/"):
    raise SystemExit(
        "This repo is configured to use the web OAuth callback at "
        "https://127.0.0.1:8080/auth/callback. Start the app with "
        "scripts/run_local_https.ps1 and open https://127.0.0.1:8080/auth/start instead."
    )

flow = InstalledAppFlow.from_client_secrets_file(cfg.client_secrets_file, SCOPES)
creds = flow.run_local_server(port=0)

cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
cfg.token_path.write_text(creds.to_json(), encoding="utf-8")
print(f"Wrote token to {cfg.token_path}")
