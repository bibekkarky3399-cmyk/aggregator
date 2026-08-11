# Deploy scripts

## macOS

```bash
./deploy/run-mac.sh
```

## Windows (recommended)

Double-click or run in **Command Prompt / PowerShell**:

```bat
deploy\run.bat
```

## Git Bash / WSL on Windows

```bash
bash deploy/run.sh
```

Or:

```bash
chmod +x deploy/run.sh
./deploy/run.sh
```

## What the scripts do

1. Clear Python caches (`__pycache__`, `.pytest_cache`, `*.pyc`, …)
2. Create `.venv` if missing
3. Install `requirements.txt`
4. Copy `.env.example` → `.env` if `.env` is missing
5. Start the API with uvicorn on port **8000** (`--reload`)

## URLs

- API / health: http://127.0.0.1:8000/health
- Admin: http://127.0.0.1:8000/admin
- Swagger: http://127.0.0.1:8000/docs

Default admin: `admin` / `admin123`
