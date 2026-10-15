# Security Hardening & Docker Hub Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the networth-tracker app against its most meaningful security vulnerabilities and push Docker images to Docker Hub.

**Architecture:** Surgical edits to 7 existing files. No new dependencies, no auth flow changes, no database changes. Backend gets env-based secrets, gated demo data, tighter CORS, and import size limits. Frontend gets nginx security headers. Both Dockerfiles get non-root users. Images pushed as `shri32msi/network-tracker:backend` and `:frontend`.

**Tech Stack:** Python/FastAPI, React/Vite, Nginx, Docker, docker-compose

**Project root:** `<repo>`

**Note:** This project may not have git initialized. Skip commit steps if `git status` fails.

---

### Task 1: Fix Hardcoded JWT Secret Key

**Files:**
- Modify: `backend/config.py` (entire file, 13 lines)

- [ ] **Step 1: Replace config.py with env-based secret key**

Replace the entire contents of `backend/config.py` with:

```python
from pydantic_settings import BaseSettings
import os
import secrets
import logging

logger = logging.getLogger(__name__)

def _default_secret_key() -> str:
    key = secrets.token_hex(32)
    logger.warning(
        "SECRET_KEY not set — using auto-generated key. "
        "Tokens will not survive restarts. "
        "Set SECRET_KEY env var for persistent sessions."
    )
    return key

class Settings(BaseSettings):
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    DATA_FILE: str = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
    CREATE_DEMO_DATA: bool = False

    class Config:
        env_file = ".env"

settings = Settings()

if not settings.SECRET_KEY:
    settings.SECRET_KEY = _default_secret_key()
```

Key changes:
- `SECRET_KEY` defaults to empty string (not a hardcoded secret)
- If empty, auto-generates a random 64-char hex key and logs a warning
- Added `CREATE_DEMO_DATA` setting (defaults `False`) — used in Task 3
- `_default_secret_key()` is a plain function, not a Pydantic default, because we need to log

- [ ] **Step 2: Verify config.py loads without errors**

Run from `backend/` directory:
```bash
cd <repo>/backend && python -c "from config import settings; print('SECRET_KEY length:', len(settings.SECRET_KEY)); print('CREATE_DEMO_DATA:', settings.CREATE_DEMO_DATA)"
```

Expected output:
```
WARNING:__main__:SECRET_KEY not set — using auto-generated key...
SECRET_KEY length: 64
CREATE_DEMO_DATA: False
```

---

### Task 2: Tighten CORS Configuration

**Files:**
- Modify: `backend/main.py:37-43`

- [ ] **Step 1: Replace CORS middleware block**

In `backend/main.py`, replace lines 37-43:

```python
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

With:

```python
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

### Task 3: Gate Demo User Behind Env Var

**Files:**
- Modify: `backend/main.py:726-827`

- [ ] **Step 1: Add env var check to startup_event**

In `backend/main.py`, replace the startup event function (lines 727-827). The current function starts with:

```python
@app.on_event("startup")
async def startup_event():
    """Create demo user and sample data on startup"""
    from auth import get_password_hash
    
    # Check if demo user exists
    demo_user = db.get_user_by_username("demo")
```

Replace just the first few lines (727-733) to add the gate. Change:

```python
@app.on_event("startup")
async def startup_event():
    """Create demo user and sample data on startup"""
    from auth import get_password_hash
    
    # Check if demo user exists
    demo_user = db.get_user_by_username("demo")
```

To:

```python
@app.on_event("startup")
async def startup_event():
    """Create demo user and sample data on startup (only if CREATE_DEMO_DATA=true)"""
    if not settings.CREATE_DEMO_DATA:
        return
    
    from auth import get_password_hash
    
    # Check if demo user exists
    demo_user = db.get_user_by_username("demo")
```

The rest of the function (lines 734-827) stays exactly the same.

---

### Task 4: Add Import Endpoint Size Limit

**Files:**
- Modify: `backend/main.py:208-217`

- [ ] **Step 1: Add size check to import handler**

In `backend/main.py`, the import handler currently reads:

```python
@app.post("/api/import")
async def import_user_data(file: UploadFile = File(...), user_id: str = Depends(get_user_id)):
    """Import data from a backup JSON file into the current user's account"""
    try:
        content = await file.read()
        import_data = json.loads(content.decode('utf-8'))
```

Replace those lines with:

```python
@app.post("/api/import")
async def import_user_data(file: UploadFile = File(...), user_id: str = Depends(get_user_id)):
    """Import data from a backup JSON file into the current user's account"""
    MAX_IMPORT_SIZE = 10 * 1024 * 1024  # 10MB
    try:
        content = await file.read()
        if len(content) > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="Import file too large (max 10MB)")
        import_data = json.loads(content.decode('utf-8'))
```

---

### Task 5: Update .gitignore

**Files:**
- Modify: `.gitignore:32-33`

- [ ] **Step 1: Uncomment data/*.json**

In `.gitignore`, replace:

```
# Data (keep structure, ignore actual data for git)
# data/*.json
```

With:

```
# Data (keep structure, ignore actual data for git)
data/*.json
```

---

### Task 6: Add Security Headers to Nginx

**Files:**
- Modify: `frontend/nginx.conf:1-6`

- [ ] **Step 1: Add security headers to server block**

In `frontend/nginx.conf`, replace the opening of the server block:

```nginx
server {
    listen 3000;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;
```

With:

```nginx
server {
    listen 3000;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
```

---

### Task 7: Harden Backend Dockerfile

**Files:**
- Modify: `backend/Dockerfile` (entire file)

- [ ] **Step 1: Replace backend Dockerfile**

Replace the entire contents of `backend/Dockerfile` with:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user and data directory
RUN adduser --disabled-password --no-create-home appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Changes from original:
- Added `adduser` to create `appuser` (no password, no home dir)
- `chown` the data directory to `appuser`
- Added `HEALTHCHECK` matching docker-compose definition
- Added `USER appuser` before CMD

---

### Task 8: Harden Frontend Dockerfile

**Files:**
- Modify: `frontend/Dockerfile` (production stage only)

- [ ] **Step 1: Add file permissions to frontend Dockerfile**

Replace the entire contents of `frontend/Dockerfile` with:

```dockerfile
# Build stage
FROM node:20-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets with correct permissions
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod -R 755 /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
```

Change from original: added `RUN chmod -R 755` after copying built assets.

---

### Task 9: Fix Docker Compose Environment

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Replace docker-compose.yml**

Replace the entire contents of `docker-compose.yml` with:

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: networth-backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      # Generate a strong key: python -c "import secrets; print(secrets.token_hex(32))"
      # - SECRET_KEY=${SECRET_KEY}   # read from your shell or a .env file next to docker-compose.yml
      - CREATE_DEMO_DATA=true
      - DATA_FILE=/app/data/data.json
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - VITE_API_URL=
    container_name: networth-frontend
    ports:
      - "3000:3000"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

networks:
  default:
    name: networth-network
```

Changes from original:
- `SECRET_KEY` line is commented out with generation instructions
- Added `CREATE_DEMO_DATA=true` for dev convenience
- Kept `DATA_FILE` env var

---

### Task 10: Verify — Rebuild and Test in WSL

- [ ] **Step 1: Stop any existing containers**

```bash
cd /mnt/c/<path-to>/networth-tracker && docker compose down
```

- [ ] **Step 2: Rebuild and start**

```bash
docker compose up --build -d
```

Wait for both containers to be healthy.

- [ ] **Step 3: Verify backend health**

```bash
curl -s http://localhost:8000/api/health
```

Expected: `{"status":"healthy","service":"networth-tracker-api"}`

- [ ] **Step 4: Verify frontend loads**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

Expected: `200`

- [ ] **Step 5: Verify nginx security headers**

```bash
curl -sI http://localhost:3000 | grep -iE "(x-frame|x-content-type|x-xss|referrer-policy|permissions-policy)"
```

Expected: all 5 security headers present.

- [ ] **Step 6: Verify demo login works**

```bash
curl -s -X POST http://localhost:3000/api/auth/login -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "username=demo" --data-urlencode "password=$DEMO_PASSWORD"
```

Expected: JSON with `access_token` (since `CREATE_DEMO_DATA=true` in docker-compose).

- [ ] **Step 7: Verify CORS headers**

```bash
curl -sI -H "Origin: http://localhost:3000" http://localhost:8000/api/health | grep -i "access-control"
```

Expected: `access-control-allow-origin: http://localhost:3000`

- [ ] **Step 8: Stop containers**

```bash
docker compose down
```

---

### Task 11: Build and Push to Docker Hub

- [ ] **Step 1: Build backend image**

```bash
cd /mnt/c/<path-to>/networth-tracker && docker build -t shri32msi/network-tracker:backend ./backend
```

Expected: successful build.

- [ ] **Step 2: Build frontend image**

```bash
docker build -t shri32msi/network-tracker:frontend --build-arg VITE_API_URL= ./frontend
```

Expected: successful build.

- [ ] **Step 3: Login to Docker Hub (if not already logged in)**

```bash
docker login
```

User will need to enter credentials if not already logged in.

- [ ] **Step 4: Push backend image**

```bash
docker push shri32msi/network-tracker:backend
```

- [ ] **Step 5: Push frontend image**

```bash
docker push shri32msi/network-tracker:frontend
```

- [ ] **Step 6: Verify images exist on Docker Hub**

```bash
docker manifest inspect shri32msi/network-tracker:backend > /dev/null && echo "backend: OK"
docker manifest inspect shri32msi/network-tracker:frontend > /dev/null && echo "frontend: OK"
```

Expected: both print OK.
