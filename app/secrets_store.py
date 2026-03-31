from __future__ import annotations

import os
from google.cloud import secretmanager


def add_secret_version(secret_name: str, payload: str, project_id: str | None = None) -> str:
    project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if not project:
        raise RuntimeError("No Google Cloud project available for Secret Manager write")

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project}/secrets/{secret_name}"
    response = client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": payload.encode("utf-8")},
        }
    )
    return response.name
