# Gmail Intelligence Tool

A lightweight FastAPI + embeddings mail triage app that:

- pulls Gmail messages via Gmail API
- embeds messages using Gemini embeddings
- stores message content + vector in SQLite
- surfaces semantic search and simple actionability scoring
- lets you archive noise in bulk (query-based or selected IDs)
- can hand off selected messages to an external agent webhook

## Why this exists

You asked for a personal Gmail tool that helps:

1. **Read + embed** Gmail messages into a searchable memory
2. **View and understand** what's actionable
3. **Bulk archive** noise
4. Run in Google Cloud with Cloud Build

---

## Quick Start (Local)

```bash
# from this repo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # copy and fill values
mkdir -p credentials
```

Set up Google OAuth creds (`client_secret.json`) from your Google Cloud OAuth consent screen.

```bash
python scripts/authorize_gmail.py
```

This runs a local auth flow and writes `credentials/token.json` for user:
`gary.a.morris@gmail.com`.

Then:

```bash
uvicorn app.main:app --reload --port 8080
```

Open: <http://localhost:8080>.

## Environment Variables

- `GMAIL_CLIENT_SECRETS` (default: `./credentials/client_secret.json`)
- `GMAIL_CLIENT_SECRETS_JSON` (optional alternative: provide OAuth client JSON directly)
- `GMAIL_TOKEN_PATH` (default: `./credentials/token.json`)
- `GMAIL_TOKEN_JSON` (optional alternative: provide serialized token JSON directly)
- `GMAIL_USER_EMAIL` (default: optional, set to `gary.a.morris@gmail.com`)
- `GEMINI_API_KEY` (required for embeddings)
- `EMBEDDING_MODEL` (default: `models/embedding-001`)
- `AGENT_WEBHOOK_URL` (optional, for agent handoff)
- `REDIRECT_URI` (default: `http://localhost:8080/auth/callback`)
- `DB_PATH` (default: `/app/data/messages.db`)
- `CORS_ORIGINS` (default: `*`)

## Endpoints

- `GET /` UI dashboard
- `GET /api/messages` list stored messages
- `GET /api/search?q=...` semantic search
- `POST /api/sync` fetch latest Gmail messages + upsert embeddings
- `POST /api/archive` archive selected message IDs
- `POST /api/bulk_archive_by_query` archive by local DB query
- `POST /api/analyze` actionability heuristic
- `POST /api/agent/handoff` forward selected message IDs + instruction to webhook
- `GET /auth/login` and `GET /auth/callback` (web OAuth)
- `GET /health`

## Deployment (Google Cloud)

### 0) Add required Gmail OAuth secrets in Secret Manager

Create/update these two secrets in Google Secret Manager for project `cognerys-site`:

- `gmail-client-secrets-json` (Google OAuth client config JSON)
- `gmail-token-json` (optional initial token JSON)

```bash
# placeholder creation done for you; replace with real values:
gcloud secrets versions add gmail-client-secrets-json --project=cognerys-site --data-file=path/to/client_secret.json
gcloud secrets versions add gmail-token-json --project=cognerys-site --data-file=path/to/token.json

# rebind latest secret values if needed
gcloud run services update gmail-intelligence-tool \
  --project=cognerys-site --region=europe-west1 \
  --set-secrets=GMAIL_CLIENT_SECRETS_JSON=gmail-client-secrets-json:latest,GMAIL_TOKEN_JSON=gmail-token-json:latest
```

### 1) Build image locally and push via Cloud Build

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _SERVICE_NAME=gmail-intelligence-tool,_REGION=europe-west1,_GMAIL_USER_EMAIL=gary.a.morris@gmail.com \
  .
```

### 2) Store secrets

Use Secret Manager for secrets, then inject at runtime:

- `GEMINI_API_KEY`
- `GMAIL_CLIENT_SECRETS`
- `GMAIL_TOKEN_JSON` (or mount token from Secret Manager)

### 3) Deploy command equivalent (if needed)

```bash
gcloud run deploy gmail-intelligence-tool \
  --image gcr.io/<PROJECT_ID>/gmail-intelligence-tool \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated
```

### 4) Optional: mount Cloud Storage for DB persistence

`/app/data/messages.db` is currently local to container; for durable history use Cloud SQL or managed storage.

## Security Note

This app requires Gmail OAuth credentials and tokens scoped to modify mailbox. Keep secrets in Secret Manager and never commit credentials/token files.

## GitHub push

Create a repo (example `gmail-intelligence-tool`), add remote, and push:

```bash
git init
git add .
git commit -m "feat: initial gmail intelligence tool with embeddings and bulk archive"
git remote add origin git@github.com:<your-org-or-user>/gmail-intelligence-tool.git
git push -u origin main
```

Then wire Cloud Build trigger to repo + branch.
## Live service

URL: https://gmail-intelligence-tool-3pzvgh7ssq-ew.a.run.app

