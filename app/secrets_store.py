from __future__ import annotations

import os
from google.cloud import secretmanager


def _project_id(project_id: str | None = None) -> str:
    project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if not project:
        raise RuntimeError("No Google Cloud project available for Secret Manager")
    return project


def add_secret_version(secret_name: str, payload: str, project_id: str | None = None) -> str:
    project = _project_id(project_id)
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project}/secrets/{secret_name}"
    response = client.add_secret_version(
        request={
            "parent": parent,
            "payload": {"data": payload.encode("utf-8")},
        }
    )
    return response.name


def get_secret_version(secret_name: str, version: str = "latest", project_id: str | None = None) -> str:
    project = _project_id(project_id)
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{secret_name}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")
