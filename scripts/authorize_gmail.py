"""Utility to generate local OAuth credentials for one-time Gmail auth.

Usage:
  python scripts/authorize_gmail.py

This writes token.json into ./credentials on success.
"""

from __future__ import annotations

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import Config

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


cfg = Config.validate()

if not os.path.exists(cfg.client_secrets_file):
    raise SystemExit(f"Missing client secrets file at {cfg.client_secrets_file}")

flow = InstalledAppFlow.from_client_secrets_file(cfg.client_secrets_file, SCOPES)
creds = flow.run_local_server(port=0)

cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
cfg.token_path.write_text(creds.to_json(), encoding="utf-8")
print(f"Wrote token to {cfg.token_path}")
