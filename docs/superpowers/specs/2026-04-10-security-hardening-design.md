# Security Hardening & Docker Hub Deployment — Design Spec

**Date:** 2026-04-10
**Context:** Personal/hobby project — practical hardening without over-engineering
**Docker Hub:** `shri32msi/network-tracker:backend` and `shri32msi/network-tracker:frontend`

---

## 1. Backend Security Fixes

### 1.1 Hardcoded JWT Secret Key (config.py)

**Problem:** `SECRET_KEY` is hardcoded in `config.py`. Anyone who reads the source can forge JWT tokens for any user.

**Fix:** Read `SECRET_KEY` from `os.environ`. If not set, auto-generate a random 64-char hex string at startup and log a warning. Tokens won't survive restarts without a configured key, which is acceptable for personal use.

### 1.2 Demo User Auto-Creation (main.py)

**Problem:** A demo user `demo` with a fixed, publicly known password is created on every startup unconditionally. This is a known weak credential.

**Fix:** Gate demo data seeding behind env var `CREATE_DEMO_DATA`. Only create demo data when `CREATE_DEMO_DATA=true`. Default is `false`.

### 1.3 CORS Tightening (main.py)

**Problem:** `allow_methods=["*"]` and `allow_headers=["*"]` with `allow_credentials=True` is overly permissive.

**Fix:**
- `allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
- `allow_headers=["Authorization", "Content-Type"]`
- Keep existing `allow_origins` unchanged (localhost variants are fine for personal use)

### 1.4 Import Endpoint Size Limit (main.py)

**Problem:** `/api/import` accepts arbitrary-size JSON payloads with no limit, enabling DoS via large uploads.

**Fix:** Check `Content-Length` and read size at the top of the import handler. Reject payloads over 10MB with HTTP 413.

### 1.5 .gitignore Update

**Problem:** `data/*.json` is commented out, so financial data (hashed passwords, account numbers) can be accidentally committed.

**Fix:** Uncomment `data/*.json` in `.gitignore`.

---

## 2. Frontend/Infrastructure Security Fixes

### 2.1 Nginx Security Headers (nginx.conf)

**Problem:** No security headers served, leaving the app vulnerable to clickjacking, MIME-sniffing, and referrer leakage.

**Fix:** Add to the nginx server block:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### 2.2 Non-Root User in Backend Dockerfile

**Problem:** Container runs as root, which means a container escape gives root on the host.

**Fix:**
- Add `adduser` to create `appuser`
- `chown` the `/app/data` directory to `appuser`
- Switch to `USER appuser` before `CMD`

### 2.3 Frontend Dockerfile Hardening

**Problem:** No explicit ownership/permissions set for static files in the production stage.

**Fix:** In the production stage, ensure copied static files have correct permissions (`chmod -R 755`) so nginx can serve them. The nginx alpine image already runs the worker processes as the `nginx` user, so no user switch is needed — just ensure file readability.

### 2.4 Backend Dockerfile HEALTHCHECK

**Problem:** No HEALTHCHECK in the Dockerfile itself (only in docker-compose).

**Fix:** Add `HEALTHCHECK` instruction matching the docker-compose definition.

### 2.5 Docker Compose Secret Fix (docker-compose.yml)

**Problem:** The `SECRET_KEY` value in `docker-compose.yml` is a placeholder that will be used as-is.

**Fix:**
- Remove the insecure placeholder, leave it commented with instructions
- Add `CREATE_DEMO_DATA=true` for dev convenience

---

## 3. Docker Hub Deployment

### 3.1 Build and Push

- Build backend: `docker build -t shri32msi/network-tracker:backend ./backend`
- Build frontend: `docker build -t shri32msi/network-tracker:frontend --build-arg VITE_API_URL= ./frontend`
- Push both tags to Docker Hub

### 3.2 Verification

- Rebuild app using `docker compose up --build` in WSL
- Verify:
  - Backend health endpoint responds at `http://localhost:8000/api/health`
  - Frontend loads at `http://localhost:3000`
  - Login works (demo user if `CREATE_DEMO_DATA=true`)
  - Nginx security headers present in response
  - CORS headers correct on API responses

---

## 4. What Is NOT Changing

- No new dependencies
- No auth flow changes (localStorage token stays)
- No database schema changes
- No rate limiting (overkill for personal use)
- No token-to-cookie migration
- All existing functionality preserved

---

## Summary Table

| File | Change |
|------|--------|
| `backend/config.py` | Env-based secret key with auto-generate fallback |
| `backend/main.py` | Demo user gated by env var, CORS tightened, import size limit |
| `backend/Dockerfile` | Non-root user, HEALTHCHECK |
| `frontend/nginx.conf` | 5 security headers |
| `frontend/Dockerfile` | Non-root user verification |
| `.gitignore` | Uncomment `data/*.json` |
| `docker-compose.yml` | Proper secret key, demo data flag |
| Docker Hub | Push `shri32msi/network-tracker:backend` and `:frontend` |
