$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$certDir = Join-Path $repoRoot "credentials"
$certFile = Join-Path $certDir "dev-cert.pem"
$keyFile = Join-Path $certDir "dev-key.pem"

if (-not (Test-Path $python)) {
    throw "Virtualenv missing at $python. Run 'python -m venv .venv' and install requirements first."
}

New-Item -ItemType Directory -Force -Path $certDir | Out-Null

if (-not (Test-Path $certFile) -or -not (Test-Path $keyFile)) {
    & openssl req -x509 -nodes -newkey rsa:2048 `
        -keyout $keyFile `
        -out $certFile `
        -days 365 `
        -subj "/CN=127.0.0.1" `
        -addext "subjectAltName = IP:127.0.0.1,DNS:localhost"
}

Set-Location $repoRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --ssl-certfile $certFile --ssl-keyfile $keyFile
