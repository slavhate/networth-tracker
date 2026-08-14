# Serverless Migration: Lambda + S3 + CloudFront Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host the existing FastAPI/React app on AWS (Lambda + S3 + CloudFront with OAC, custom domain `nwt.shrikantlavhate.in`, $5/month budget alarm, no WAF) while keeping the local Docker Compose workflow fully intact.

**Architecture:** FastAPI runs unchanged under Mangum on Lambda; `database.py` gains an S3-backed storage path (one JSON object per user, ETag-conditional writes) selected by `STORAGE_BACKEND=s3`, while the local file path used by Docker Compose is untouched. A single CloudFormation template provisions two S3 buckets, the Lambda function + IAM-authenticated Function URL, two CloudFront-origin OACs, the CloudFront distribution, ACM cert, Route 53 record, and the AWS Budget. A deploy script builds the Lambda zip, deploys the stack, and syncs the frontend.

**Tech Stack:** FastAPI, Mangum, boto3, pytest + moto (new test coverage), AWS CloudFormation, Docker (for building the Lambda package), Vite/React (unchanged).

**Reference:** [docs/superpowers/specs/2026-08-14-lambda-s3-cloudfront-migration-design.md](../specs/2026-08-14-lambda-s3-cloudfront-migration-design.md)

**Two refinements made while planning (both preserve the spec's intent, changed only for implementation simplicity — flagged here for transparency):**
1. **S3 object key is `users/{user_id}.json`, not `users/{username}.json`.** `user_id` is already threaded through all ~25 CRUD functions in `database.py`; keying by it means zero changes to `main.py` and no per-request lookup. A small separate `username_index.json` (`username -> user_id`) is used only at login/registration, which are the only two places `username` is available without `user_id`.
2. **Concurrent-write conflicts surface as an error (HTTP 409) rather than being silently retried-and-remerged.** Safely retrying an arbitrary mutation against freshly-read data would require restructuring every CRUD function through a callback, which is disproportionate for a personal app already capped at reserved concurrency 2. A genuine conflict (the same logged-in user saving from two places at once) is rare; the client simply retries the action. `register_username` (the one place a blind retry-and-remerge *is* trivially safe — re-checking "is this username already claimed" against fresh data) still retries automatically.

All library versions below were verified installable and working in this environment (WSL, Python 3.12.3) before writing this plan: `boto3==1.43.71`, `mangum==0.21.0`, `moto==5.2.2` (confirmed its S3 mock correctly enforces `IfMatch`/`IfNoneMatch` conditional-write semantics), `cfn-flip==1.3.0`.

---

## Task 1: Storage backend config

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Add the two new settings**

In `backend/config.py`, add two fields to the `Settings` class (after `CREATE_DEMO_DATA: bool = False`):

```python
    STORAGE_BACKEND: str = "local"  # "local" (Docker Compose) or "s3" (Lambda)
    DATA_BUCKET: str = ""  # required when STORAGE_BACKEND=s3
```

- [ ] **Step 2: Verify it doesn't break local startup**

Run: `cd backend && venv/bin/python -c "from config import settings; print(settings.STORAGE_BACKEND, repr(settings.DATA_BUCKET))"`
Expected output: `local ''`
(If `backend/venv` doesn't exist yet: `python3 -m venv venv && venv/bin/pip install -r requirements.txt`)

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat: add STORAGE_BACKEND/DATA_BUCKET settings for S3-backed deploys"
```

---

## Task 2: S3 storage module

**Files:**
- Create: `backend/s3_storage.py`
- Create: `backend/tests/__init__.py` (empty, makes `tests` importable)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_s3_storage.py`
- Modify: `backend/requirements-dev.txt` (new file)

- [ ] **Step 1: Add dev/test dependencies**

Create `backend/requirements-dev.txt`:

```
pytest==9.1.1
moto==5.2.2
```

Run: `cd backend && venv/bin/pip install -r requirements-dev.txt`

- [ ] **Step 2: Write the shared test fixture**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("STORAGE_BACKEND", "s3")
os.environ.setdefault("DATA_BUCKET", "test-networth-data")
os.environ.setdefault("SECRET_KEY", "test-secret")

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

import s3_storage  # noqa: E402

BUCKET = os.environ["DATA_BUCKET"]


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        s3_storage._client = None  # force a fresh client bound to the mock
        yield client
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_s3_storage.py`:

```python
import pytest

import s3_storage


def test_load_user_data_returns_empty_shape_when_missing(s3_bucket):
    data = s3_storage.load_user_data("user-1")
    assert data["user"] is None
    assert data["assets"] == []
    assert data["_etag"] is None


def test_save_then_load_round_trips(s3_bucket):
    data = s3_storage.load_user_data("user-1")
    data["user"] = {"id": "user-1", "username": "demo"}
    data["assets"].append({"id": "a1", "value": 100})
    s3_storage.save_user_data("user-1", data)

    reloaded = s3_storage.load_user_data("user-1")
    assert reloaded["user"] == {"id": "user-1", "username": "demo"}
    assert reloaded["assets"] == [{"id": "a1", "value": 100}]
    assert reloaded["_etag"] is not None


def test_save_user_data_conflict_raises(s3_bucket):
    data = s3_storage.load_user_data("user-1")
    s3_storage.save_user_data("user-1", data)  # first write (IfNoneMatch) succeeds

    stale_copy = s3_storage.load_user_data("user-1")
    fresh_copy = s3_storage.load_user_data("user-1")

    stale_copy["assets"].append({"id": "a1"})
    s3_storage.save_user_data("user-1", stale_copy)  # succeeds; object's etag moves on

    fresh_copy["assets"].append({"id": "a2"})
    with pytest.raises(s3_storage.ConflictError):
        s3_storage.save_user_data("user-1", fresh_copy)


def test_lookup_user_id_returns_none_when_absent(s3_bucket):
    assert s3_storage.lookup_user_id("nobody") is None


def test_register_username_claims_and_rejects_duplicate(s3_bucket):
    assert s3_storage.register_username("alice", "user-1") is True
    assert s3_storage.lookup_user_id("alice") == "user-1"
    assert s3_storage.register_username("alice", "user-2") is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_s3_storage.py -v`
Expected: `ModuleNotFoundError: No module named 's3_storage'` (or collection error) — the module doesn't exist yet.

- [ ] **Step 5: Implement `s3_storage.py`**

Create `backend/s3_storage.py`:

```python
"""S3-backed storage for STORAGE_BACKEND=s3. One JSON object per user
(`users/{user_id}.json`), plus a small `username_index.json` mapping
username -> user_id used only at login/registration."""
import json
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from config import settings

_client = None


class ConflictError(Exception):
    """Raised when a conditional S3 write loses a concurrent-write race."""
    pass


def _s3():
    global _client
    if _client is None:
        _client = boto3.client("s3")
    return _client


EMPTY_COLLECTIONS = {
    "assets": [], "liabilities": [], "snapshots": [], "bank_accounts": [],
    "insurances": [], "mutual_funds": [], "equities": [], "goals": []
}


def _get_json(key: str) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (parsed_body, etag), or (None, None) if the key doesn't exist."""
    try:
        resp = _s3().get_object(Bucket=settings.DATA_BUCKET, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None, None
        raise
    body = json.loads(resp["Body"].read())
    return body, resp["ETag"]


def _put_json(key: str, body: dict, etag: Optional[str]) -> None:
    """Conditional write: If-Match the given etag, or If-None-Match '*' when
    etag is None (this key is expected not to exist yet)."""
    kwargs = {
        "Bucket": settings.DATA_BUCKET,
        "Key": key,
        "Body": json.dumps(body).encode("utf-8"),
        "ContentType": "application/json",
    }
    if etag:
        kwargs["IfMatch"] = etag
    else:
        kwargs["IfNoneMatch"] = "*"
    try:
        _s3().put_object(**kwargs)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("PreconditionFailed", "412"):
            raise ConflictError(f"Concurrent write conflict on {key}") from e
        raise


def _user_key(user_id: str) -> str:
    return f"users/{user_id}.json"


def load_user_data(user_id: str) -> Dict[str, Any]:
    """Loads this user's blob (user record + all their collections). Returns
    an empty-but-shaped blob if it doesn't exist yet. The etag travels with
    the data under `_etag` so `save_user_data` can do a conditional write."""
    body, etag = _get_json(_user_key(user_id))
    if body is None:
        data = {"user": None, **{k: list(v) for k, v in EMPTY_COLLECTIONS.items()}}
    else:
        data = body
        for key, default in EMPTY_COLLECTIONS.items():
            data.setdefault(key, list(default))
    data["_etag"] = etag
    return data


def save_user_data(user_id: str, data: Dict[str, Any]) -> None:
    """Conditionally writes this user's blob back. Raises ConflictError if
    another write happened since `data` was loaded."""
    etag = data.pop("_etag", None)
    try:
        _put_json(_user_key(user_id), data, etag)
    finally:
        data["_etag"] = etag


def lookup_user_id(username: str) -> Optional[str]:
    index, _ = _get_json("username_index.json")
    if index is None:
        return None
    return index.get(username)


def register_username(username: str, user_id: str, max_attempts: int = 3) -> bool:
    """Atomically claims `username` -> `user_id` in the shared index.
    Returns False if the username is already taken. Retries on write
    conflicts since re-reading and re-inserting into a dict is always safe
    to redo (unlike an arbitrary business mutation)."""
    for _ in range(max_attempts):
        index, etag = _get_json("username_index.json")
        if index is None:
            index = {}
        if username in index:
            return False
        index[username] = user_id
        try:
            _put_json("username_index.json", index, etag)
            return True
        except ConflictError:
            continue
    raise ConflictError(f"Could not register username '{username}' after {max_attempts} attempts")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_s3_storage.py -v`
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add backend/s3_storage.py backend/requirements-dev.txt backend/tests/__init__.py backend/tests/conftest.py backend/tests/test_s3_storage.py
git commit -m "feat: add S3-backed per-user storage module"
```

---

## Task 3: Wire `database.py` to the S3 backend

**Files:**
- Modify: `backend/database.py` (full rewrite of the top section; mechanical edit to ~25 call sites)
- Create: `backend/tests/test_database_s3_backend.py`

- [ ] **Step 1: Write the failing integration tests**

Create `backend/tests/test_database_s3_backend.py`:

```python
import pytest

import database as db


def test_create_and_fetch_user(s3_bucket):
    user = db.create_user("alice", "alice@example.com", "hashed-pw")
    assert user["username"] == "alice"

    fetched = db.get_user_by_username("alice")
    assert fetched == user


def test_duplicate_username_raises(s3_bucket):
    db.create_user("bob", "bob@example.com", "hashed-pw")
    with pytest.raises(ValueError):
        db.create_user("bob", "other@example.com", "other-hash")


def test_asset_crud_round_trip(s3_bucket):
    user = db.create_user("carol", "carol@example.com", "hashed-pw")
    user_id = user["id"]

    created = db.create_asset(user_id, {"name": "Emergency Fund", "category": "cash", "value": 1000})
    assert db.get_assets_by_user(user_id) == [created]

    updated = db.update_asset(created["id"], user_id, {"value": 2000})
    assert updated["value"] == 2000

    assert db.delete_asset(created["id"], user_id) is True
    assert db.get_assets_by_user(user_id) == []


def test_concurrent_write_conflict_surfaces_as_concurrent_write_error(s3_bucket):
    user = db.create_user("dave", "dave@example.com", "hashed-pw")
    user_id = user["id"]

    stale = db.load_data(user_id)
    fresh = db.load_data(user_id)

    stale["assets"].append({"id": "a1"})
    db.save_data(user_id, stale)

    fresh["assets"].append({"id": "a2"})
    with pytest.raises(db.ConcurrentWriteError):
        db.save_data(user_id, fresh)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_database_s3_backend.py -v`
Expected: failures — `database.py` doesn't dispatch to S3 yet (`get_user_by_username` will return `None`, `load_data`/`save_data` don't take a `user_id` arg yet, `ConcurrentWriteError` doesn't exist).

- [ ] **Step 3: Rewrite the top section of `database.py`**

Replace lines 1–86 of `backend/database.py` (everything from the imports through the end of `create_user`) with:

```python
import json
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from config import settings
import s3_storage


class ConcurrentWriteError(Exception):
    """Raised when an S3-backed write loses a conditional-write race."""
    pass


def get_data_file_path() -> str:
    return settings.DATA_FILE


def _load_local_data() -> Dict[str, Any]:
    """Load data from the local JSON file (STORAGE_BACKEND=local)."""
    data_file = get_data_file_path()
    if not os.path.exists(data_file):
        initial_data = {
            "users": [],
            "assets": [],
            "liabilities": [],
            "snapshots": [],
            "bank_accounts": [],
            "insurances": [],
            "mutual_funds": [],
            "equities": [],
            "goals": []
        }
        _save_local_data(initial_data)
        return initial_data

    with open(data_file, 'r') as f:
        data = json.load(f)
        for key in ["bank_accounts", "insurances", "mutual_funds", "equities", "goals"]:
            if key not in data:
                data[key] = []
        return data


def _save_local_data(data: Dict[str, Any]) -> None:
    """Save data to the local JSON file (STORAGE_BACKEND=local)."""
    data_file = get_data_file_path()
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2)


def load_data(user_id: str = None) -> Dict[str, Any]:
    """Load this user's data. `user_id` is ignored on the local backend,
    which keeps one shared file for all users, unchanged from before."""
    if settings.STORAGE_BACKEND == "s3":
        return s3_storage.load_user_data(user_id)
    return _load_local_data()


def save_data(user_id: str, data: Dict[str, Any]) -> None:
    """Save this user's data. `user_id` is ignored on the local backend."""
    if settings.STORAGE_BACKEND == "s3":
        try:
            s3_storage.save_user_data(user_id, data)
        except s3_storage.ConflictError as e:
            raise ConcurrentWriteError(str(e)) from e
        return
    _save_local_data(data)


def generate_id() -> str:
    """Generate unique ID"""
    return str(uuid.uuid4())


def get_timestamp() -> str:
    """Get current timestamp as ISO string"""
    return datetime.utcnow().isoformat()

# User operations
def get_user_by_username(username: str) -> Optional[Dict]:
    if settings.STORAGE_BACKEND == "s3":
        user_id = s3_storage.lookup_user_id(username)
        if user_id is None:
            return None
        blob = s3_storage.load_user_data(user_id)
        return blob.get("user")
    data = _load_local_data()
    for user in data["users"]:
        if user["username"] == username:
            return user
    return None

def create_user(username: str, email: str, hashed_password: str) -> Dict:
    if settings.STORAGE_BACKEND == "s3":
        user_id = generate_id()
        if not s3_storage.register_username(username, user_id):
            raise ValueError(f"Username '{username}' already registered")
        user = {
            "id": user_id,
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "created_at": get_timestamp()
        }
        blob = {
            "user": user,
            "assets": [], "liabilities": [], "snapshots": [], "bank_accounts": [],
            "insurances": [], "mutual_funds": [], "equities": [], "goals": []
        }
        s3_storage.save_user_data(user_id, blob)
        return user

    data = _load_local_data()
    user = {
        "id": generate_id(),
        "username": username,
        "email": email,
        "hashed_password": hashed_password,
        "created_at": get_timestamp()
    }
    data["users"].append(user)
    _save_local_data(data)
    return user
```

Note: `get_user_by_id` is deleted, not ported — confirmed unused anywhere (`grep -rn "get_user_by_id" backend/ frontend/` returns only its own definition).

- [ ] **Step 4: Mechanically update every remaining call site**

Every other function in `database.py` (asset/liability/snapshot/bank account/insurance/mutual fund/equity/goal operations) already receives `user_id` as a parameter and just needs its `load_data()`/`save_data(data)` calls updated to pass it through. Run this from the `backend/` directory:

```bash
sed -i \
  -e 's/data = load_data()/data = load_data(user_id)/g' \
  -e 's/save_data(data)/save_data(user_id, data)/g' \
  database.py
```

Then verify the count of replacements matches expectations — count remaining bare `load_data()`/`save_data(data)` calls (should be zero outside the definitions themselves):

Run: `grep -n "load_data()\|save_data(data)" backend/database.py`
Expected: no output (the only `load_data(`/`save_data(` occurrences left are the `user_id`-parameterized ones and the function definitions from Step 3, which `sed` does not match since they read `load_data(user_id: str = None)` / `save_data(user_id: str, data: ...)`, not the literal patterns above).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/ -v`
Expected: all tests pass (9 total: 5 from Task 2 + 4 from this task).

- [ ] **Step 6: Sanity-check the local backend still works unchanged**

Run:
```bash
cd backend
STORAGE_BACKEND=local DATA_FILE=/tmp/local_check.json SECRET_KEY=test CREATE_DEMO_DATA=false \
  venv/bin/python -c "
import database as db
u = db.create_user('localuser', 'l@example.com', 'hash')
a = db.create_asset(u['id'], {'name': 'Test', 'category': 'cash', 'value': 500})
print(db.get_assets_by_user(u['id']))
"
rm -f /tmp/local_check.json
```
Expected: prints a one-item list containing the created asset — confirms the local file backend behaves exactly as before.

- [ ] **Step 7: Commit**

```bash
git add backend/database.py backend/tests/test_database_s3_backend.py
git commit -m "feat: dispatch database.py storage to S3 per-user blobs when STORAGE_BACKEND=s3"
```

---

## Task 4: Surface storage conflicts as HTTP 409

**Files:**
- Modify: `backend/main.py:1-4` (import), `backend/main.py:36-43` (after CORS middleware)

- [ ] **Step 1: Add the exception handler**

In `backend/main.py`, change the fastapi import line (line 1) from:

```python
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
```

to:

```python
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Request
```

Then, immediately after the `CORSMiddleware` block (after the closing `)` that currently ends around line 43, before the `# ============== Auth Routes ==============` comment), add:

```python
@app.exception_handler(db.ConcurrentWriteError)
async def concurrent_write_handler(request: Request, exc: db.ConcurrentWriteError):
    """Only reachable with STORAGE_BACKEND=s3 - the local backend never raises this."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "This data changed elsewhere before your update was saved. Please refresh and try again."}
    )
```

(`db` and `JSONResponse` are already imported in `main.py` — no new imports needed beyond `Request` above.)

- [ ] **Step 2: Verify the app still starts**

Run: `cd backend && STORAGE_BACKEND=local DATA_FILE=/tmp/main_check.json SECRET_KEY=test CREATE_DEMO_DATA=false venv/bin/python -c "import main; print('ok')"`
Expected: `ok`

Run: `rm -f /tmp/main_check.json`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: return HTTP 409 on S3 storage write conflicts"
```

---

## Task 5: Lambda handler (Mangum)

**Files:**
- Create: `backend/lambda_handler.py`
- Create: `backend/tests/test_lambda_handler.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add runtime dependencies**

Append to `backend/requirements.txt`:

```
boto3==1.43.71
mangum==0.21.0
```

Run: `cd backend && venv/bin/pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_lambda_handler.py`:

```python
def _function_url_event(method: str, path: str, query: str = ""):
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": query,
        "headers": {"host": "example.com"},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "1.2.3.4",
                "userAgent": "test",
            },
            "domainName": "example.com",
            "requestId": "test-request-id",
            "routeKey": "$default",
            "stage": "$default",
            "time": "01/Jan/2026:00:00:00 +0000",
            "timeEpoch": 1735689600,
        },
        "isBase64Encoded": False,
    }


class FakeContext:
    function_name = "test"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    aws_request_id = "test-request-id"


def test_health_check_via_lambda_handler():
    from lambda_handler import handler

    result = handler(_function_url_event("GET", "/api/health"), FakeContext())

    assert result["statusCode"] == 200
    assert "healthy" in result["body"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && STORAGE_BACKEND=local DATA_FILE=/tmp/lambda_check.json SECRET_KEY=test CREATE_DEMO_DATA=false venv/bin/pytest tests/test_lambda_handler.py -v`
Expected: `ModuleNotFoundError: No module named 'lambda_handler'`

- [ ] **Step 4: Implement `lambda_handler.py`**

Create `backend/lambda_handler.py`:

```python
from mangum import Mangum

from main import app

handler = Mangum(app)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && STORAGE_BACKEND=local DATA_FILE=/tmp/lambda_check.json SECRET_KEY=test CREATE_DEMO_DATA=false venv/bin/pytest tests/test_lambda_handler.py -v`
Expected: 1 passed

Run: `rm -f /tmp/lambda_check.json`

- [ ] **Step 6: Commit**

```bash
git add backend/lambda_handler.py backend/tests/test_lambda_handler.py backend/requirements.txt
git commit -m "feat: add Mangum Lambda handler for the FastAPI app"
```

---

## Task 6: CloudFormation template

**Files:**
- Create: `infra/template.yaml`

- [ ] **Step 1: Write the template**

Create `infra/template.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: >
  Net Worth Tracker - serverless hosting (Lambda + S3 + CloudFront with
  Origin Access Control, custom domain via Route 53 + ACM, cost controls).

Parameters:
  DomainName:
    Type: String
    Default: nwt.shrikantlavhate.in
    Description: Custom domain the app will be served on.

  HostedZoneId:
    Type: String
    Description: >
      Route 53 Hosted Zone ID for the domain's parent zone. Find it with:
      aws route53 list-hosted-zones-by-name --dns-name shrikantlavhate.in

  NotificationEmail:
    Type: String
    Description: Email address to receive AWS Budget alerts.

  ReservedConcurrency:
    Type: Number
    Default: 2
    Description: Reserved concurrent executions for the backend Lambda function.

  LambdaArtifactsBucket:
    Type: String
    Description: >
      Name of the pre-existing S3 bucket holding the Lambda deployment
      package. Created by infra/deploy.sh, not by this stack.

  LambdaCodeS3Key:
    Type: String
    Description: >
      S3 key of the Lambda deployment zip within LambdaArtifactsBucket.
      Set by infra/deploy.sh; includes a content hash so code updates are
      detected on redeploy.

  SecretKey:
    Type: String
    NoEcho: true
    Description: >
      JWT signing secret. Generate once with:
      python3 -c "import secrets; print(secrets.token_hex(32))"
      Reuse the same value on every deploy - changing it invalidates all
      existing login sessions.

Resources:

  DataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  FrontendBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  FrontendOAC:
    Type: AWS::CloudFront::OriginAccessControl
    Properties:
      OriginAccessControlConfig:
        Name: !Sub '${AWS::StackName}-frontend-oac'
        OriginAccessControlOriginType: s3
        SigningBehavior: always
        SigningProtocol: sigv4

  LambdaOAC:
    Type: AWS::CloudFront::OriginAccessControl
    Properties:
      OriginAccessControlConfig:
        Name: !Sub '${AWS::StackName}-lambda-oac'
        OriginAccessControlOriginType: lambda
        SigningBehavior: always
        SigningProtocol: sigv4

  LambdaExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: DataBucketAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - s3:GetObject
                  - s3:PutObject
                Resource:
                  - !Sub 'arn:aws:s3:::${DataBucket}/users/*'
                  - !Sub 'arn:aws:s3:::${DataBucket}/username_index.json'

  BackendFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub '${AWS::StackName}-backend'
      Runtime: python3.12
      Handler: lambda_handler.handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Code:
        S3Bucket: !Ref LambdaArtifactsBucket
        S3Key: !Ref LambdaCodeS3Key
      MemorySize: 512
      Timeout: 25
      ReservedConcurrentExecutions: !Ref ReservedConcurrency
      Environment:
        Variables:
          STORAGE_BACKEND: s3
          DATA_BUCKET: !Ref DataBucket
          SECRET_KEY: !Ref SecretKey
          CREATE_DEMO_DATA: 'false'

  BackendFunctionUrl:
    Type: AWS::Lambda::Url
    Properties:
      TargetFunctionArn: !Ref BackendFunction
      AuthType: AWS_IAM

  AcmCertificate:
    Type: AWS::CertificateManager::Certificate
    Properties:
      DomainName: !Ref DomainName
      ValidationMethod: DNS
      DomainValidationOptions:
        - DomainName: !Ref DomainName
          HostedZoneId: !Ref HostedZoneId

  CloudFrontDistribution:
    Type: AWS::CloudFront::Distribution
    Properties:
      DistributionConfig:
        Enabled: true
        Comment: !Sub '${AWS::StackName} - networth tracker'
        Aliases:
          - !Ref DomainName
        PriceClass: PriceClass_100
        HttpVersion: http2
        DefaultRootObject: index.html
        ViewerCertificate:
          AcmCertificateArn: !Ref AcmCertificate
          SslSupportMethod: sni-only
          MinimumProtocolVersion: TLSv1.2_2021
        Origins:
          - Id: FrontendOrigin
            DomainName: !GetAtt FrontendBucket.RegionalDomainName
            S3OriginConfig:
              OriginAccessIdentity: ''
            OriginAccessControlId: !GetAtt FrontendOAC.Id
          - Id: ApiOrigin
            DomainName: !Select [2, !Split ['/', !GetAtt BackendFunctionUrl.FunctionUrl]]
            CustomOriginConfig:
              OriginProtocolPolicy: https-only
              OriginSSLProtocols:
                - TLSv1.2
            OriginAccessControlId: !GetAtt LambdaOAC.Id
        DefaultCacheBehavior:
          TargetOriginId: FrontendOrigin
          ViewerProtocolPolicy: redirect-to-https
          Compress: true
          CachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6  # AWS Managed-CachingOptimized
        CacheBehaviors:
          - PathPattern: /api/*
            TargetOriginId: ApiOrigin
            ViewerProtocolPolicy: https-only
            AllowedMethods: [GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE]
            CachedMethods: [GET, HEAD]
            CachePolicyId: 4135ea2d-6df8-44a3-9df3-4b5a84be39ad  # AWS Managed-CachingDisabled
            OriginRequestPolicyId: b689b0a8-53d0-40ab-baf2-68738e2966ac  # AWS Managed-AllViewerExceptHostHeader - VERIFY in Task 7
        CustomErrorResponses:
          - ErrorCode: 403
            ResponseCode: 200
            ResponsePagePath: /index.html
            ErrorCachingMinTTL: 10

  BackendFunctionUrlPermission:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunctionUrl
      FunctionName: !Ref BackendFunction
      Principal: cloudfront.amazonaws.com
      FunctionUrlAuthType: AWS_IAM
      SourceArn: !Sub 'arn:aws:cloudfront::${AWS::AccountId}:distribution/${CloudFrontDistribution}'

  FrontendBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref FrontendBucket
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: cloudfront.amazonaws.com
            Action: s3:GetObject
            Resource: !Sub '${FrontendBucket.Arn}/*'
            Condition:
              StringEquals:
                AWS:SourceArn: !Sub 'arn:aws:cloudfront::${AWS::AccountId}:distribution/${CloudFrontDistribution}'

  DnsRecord:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref HostedZoneId
      Name: !Ref DomainName
      Type: A
      AliasTarget:
        DNSName: !GetAtt CloudFrontDistribution.DomainName
        HostedZoneId: Z2FDTNDATAQYW2  # fixed AWS-wide CloudFront hosted zone ID
        EvaluateTargetHealth: false

  MonthlyBudget:
    Type: AWS::Budgets::Budget
    Properties:
      Budget:
        BudgetName: !Sub '${AWS::StackName}-monthly-budget'
        BudgetType: COST
        TimeUnit: MONTHLY
        BudgetLimit:
          Amount: 5
          Unit: USD
      NotificationsWithSubscribers:
        - Notification:
            NotificationType: ACTUAL
            ComparisonOperator: GREATER_THAN
            Threshold: 80
          Subscribers:
            - SubscriptionType: EMAIL
              Address: !Ref NotificationEmail
        - Notification:
            NotificationType: ACTUAL
            ComparisonOperator: GREATER_THAN
            Threshold: 100
          Subscribers:
            - SubscriptionType: EMAIL
              Address: !Ref NotificationEmail

Outputs:
  CloudFrontDomainName:
    Value: !GetAtt CloudFrontDistribution.DomainName
  DistributionId:
    Value: !Ref CloudFrontDistribution
  FrontendBucketName:
    Value: !Ref FrontendBucket
  DataBucketName:
    Value: !Ref DataBucket
  AppUrl:
    Value: !Sub 'https://${DomainName}'
```

- [ ] **Step 2: Commit**

```bash
git add infra/template.yaml
git commit -m "feat: add CloudFormation template for Lambda/S3/CloudFront hosting"
```

---

## Task 7: Validate the template

**Files:**
- No file changes — this task only runs checks against `infra/template.yaml`.

- [ ] **Step 1: Install validation tooling**

Run: `cd backend && venv/bin/pip install cfn-flip==1.3.0`

- [ ] **Step 2: Syntax-check the template**

Run: `cd backend && venv/bin/cfn-flip ../infra/template.yaml > /tmp/template-check.json && python3 -m json.tool /tmp/template-check.json > /dev/null && echo SYNTAX_OK`
Expected: `SYNTAX_OK` (this round-trips the CFN YAML — including its `!Ref`/`!Sub`/`!GetAtt`/`!Select`/`!Split` shorthand — through JSON and catches indentation/structural errors; it does not catch semantic errors like a wrong managed-policy ID).

Run: `rm -f /tmp/template-check.json`

- [ ] **Step 3: Verify the hardcoded managed CloudFront policy IDs before deploying**

This plan was written without AWS credentials available to query live values, so three IDs in `infra/template.yaml` were filled in from memory and need confirmation once you have credentials configured. `658327ea-f89d-4fab-a63d-7e88639e58f6` (CachingOptimized) and `4135ea2d-6df8-44a3-9df3-4b5a84be39ad` (CachingDisabled) are well-known and very unlikely to be wrong; `b689b0a8-53d0-40ab-baf2-68738e2966ac` (AllViewerExceptHostHeader) is the one to double-check specifically, since it's less commonly cited. Run:

```bash
aws cloudfront list-origin-request-policies --type managed \
  --query "OriginRequestPolicyList.Items[?OriginRequestPolicy.OriginRequestPolicyConfig.Name=='Managed-AllViewerExceptHostHeader'].OriginRequestPolicy.Id" \
  --output text
```

If the returned ID differs from `b689b0a8-53d0-40ab-baf2-68738e2966ac`, update `OriginRequestPolicyId` in the `ApiOrigin` cache behavior in `infra/template.yaml` before running `deploy.sh`. Optionally also confirm the other two the same way, swapping the `Name` filter and using `list-cache-policies` instead of `list-origin-request-policies`.

- [ ] **Step 4: No commit needed for this task** (validation-only; commit any fix from Step 3 with message `fix: correct CloudFront managed policy ID` if one was needed)

---

## Task 8: Deploy script

**Files:**
- Create: `infra/deploy.sh`
- Modify: `.gitignore`

- [ ] **Step 1: Write the deploy script**

Create `infra/deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Deploys the Net Worth Tracker to AWS: packages the Lambda function,
# uploads it, deploys the CloudFormation stack, builds the frontend, and
# syncs it to S3. Run this yourself after `aws configure` / SSO login -
# nothing here runs without you invoking it.
#
# Required environment variables:
#   HOSTED_ZONE_ID       Route 53 hosted zone ID for shrikantlavhate.in
#                         (aws route53 list-hosted-zones-by-name --dns-name shrikantlavhate.in)
#   NOTIFICATION_EMAIL    Email to receive AWS Budget alerts
#   SECRET_KEY            JWT signing secret (generate once, reuse every deploy):
#                          python3 -c "import secrets; print(secrets.token_hex(32))"
#
# Optional:
#   AWS_REGION            Defaults to us-east-1 (required for the CloudFront ACM cert)
#   DOMAIN_NAME           Defaults to nwt.shrikantlavhate.in
#   RESERVED_CONCURRENCY  Defaults to 2
#   STACK_NAME            Defaults to networth-tracker

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AWS_REGION="${AWS_REGION:-us-east-1}"
DOMAIN_NAME="${DOMAIN_NAME:-nwt.shrikantlavhate.in}"
RESERVED_CONCURRENCY="${RESERVED_CONCURRENCY:-2}"
STACK_NAME="${STACK_NAME:-networth-tracker}"

: "${HOSTED_ZONE_ID:?Set HOSTED_ZONE_ID to the Route 53 hosted zone ID for the domain}"
: "${NOTIFICATION_EMAIL:?Set NOTIFICATION_EMAIL for AWS Budget alerts}"
: "${SECRET_KEY:?Set SECRET_KEY (generate once with: python3 -c \"import secrets; print(secrets.token_hex(32))\")}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ARTIFACTS_BUCKET="networth-tracker-lambda-artifacts-${ACCOUNT_ID}"

echo "==> Ensuring Lambda artifacts bucket exists: ${ARTIFACTS_BUCKET}"
if ! aws s3api head-bucket --bucket "${ARTIFACTS_BUCKET}" 2>/dev/null; then
  aws s3 mb "s3://${ARTIFACTS_BUCKET}" --region "${AWS_REGION}"
fi

echo "==> Building Lambda deployment package"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

LAMBDA_SOURCE_FILES=(
  main.py models.py auth.py config.py database.py s3_storage.py
  lambda_handler.py stock_service.py exchange_service.py nav_service.py
)
mkdir -p "${BUILD_DIR}/src"
for f in "${LAMBDA_SOURCE_FILES[@]}"; do
  cp "${REPO_ROOT}/backend/${f}" "${BUILD_DIR}/src/${f}"
done
cp "${REPO_ROOT}/backend/requirements.txt" "${BUILD_DIR}/requirements.txt"

# Build inside a Lambda-runtime-compatible container so packages with C
# extensions (bcrypt, pydantic-core) are binary-compatible with Lambda.
docker run --rm \
  -v "${BUILD_DIR}:/build" \
  public.ecr.aws/sam/build-python3.12 \
  /bin/sh -c "pip install -r /build/requirements.txt -t /build/src"

ZIP_PATH="${BUILD_DIR}/backend.zip"
python3 - "${ZIP_PATH}" "${BUILD_DIR}/src" <<'PYEOF'
import os
import sys
import zipfile

zip_path, src_dir = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _, files in os.walk(src_dir):
        for name in files:
            full_path = os.path.join(root, name)
            arcname = os.path.relpath(full_path, src_dir)
            zf.write(full_path, arcname)
PYEOF

CODE_HASH="$(sha256sum "${ZIP_PATH}" | cut -c1-16)"
LAMBDA_CODE_KEY="lambda/backend-${CODE_HASH}.zip"

echo "==> Uploading Lambda package to s3://${ARTIFACTS_BUCKET}/${LAMBDA_CODE_KEY}"
aws s3 cp "${ZIP_PATH}" "s3://${ARTIFACTS_BUCKET}/${LAMBDA_CODE_KEY}"

echo "==> Deploying CloudFormation stack: ${STACK_NAME}"
aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${STACK_NAME}" \
  --template-file "${REPO_ROOT}/infra/template.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DomainName="${DOMAIN_NAME}" \
    HostedZoneId="${HOSTED_ZONE_ID}" \
    NotificationEmail="${NOTIFICATION_EMAIL}" \
    ReservedConcurrency="${RESERVED_CONCURRENCY}" \
    LambdaArtifactsBucket="${ARTIFACTS_BUCKET}" \
    LambdaCodeS3Key="${LAMBDA_CODE_KEY}" \
    SecretKey="${SECRET_KEY}"

CLOUDFRONT_DOMAIN="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomainName'].OutputValue" --output text)"
DISTRIBUTION_ID="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text)"
FRONTEND_BUCKET="$(aws cloudformation describe-stacks --region "${AWS_REGION}" --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text)"

echo "==> Building frontend"
( cd "${REPO_ROOT}/frontend" && npm install && npm run build )

echo "==> Syncing frontend to s3://${FRONTEND_BUCKET}"
aws s3 sync "${REPO_ROOT}/frontend/dist" "s3://${FRONTEND_BUCKET}" --delete

echo "==> Invalidating CloudFront cache"
aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID}" --paths "/*"

echo ""
echo "Done. App URL: https://${DOMAIN_NAME}"
echo "(CloudFront domain: ${CLOUDFRONT_DOMAIN})"
```

Run: `chmod +x infra/deploy.sh`

- [ ] **Step 2: Update `.gitignore`**

In `.gitignore`, under the `# Python` section (after `venv/` and before `ENV/`), the existing entries already cover build artifacts placed under `backend/`. Add a new section for infra build output — append at the end of the file:

```

# Infra build artifacts
infra/*.zip
```

- [ ] **Step 3: Syntax-check the script**

Run: `bash -n infra/deploy.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK`

- [ ] **Step 4: Commit**

```bash
git add infra/deploy.sh .gitignore
git commit -m "feat: add deploy script for Lambda/S3/CloudFront stack"
```

---

## Task 9: README documentation

**Files:**
- Modify: `README.md` (add a new section; insert after the existing "Production Deployment" section, before "## License")

- [ ] **Step 1: Add the AWS deployment section**

In `README.md`, insert a new section immediately before `## License`:

```markdown
## AWS Serverless Deployment (Optional)

In addition to Docker Compose (for local use), this app can be deployed to
AWS as a serverless stack: Lambda (FastAPI via Mangum) behind a CloudFront
distribution with Origin Access Control, static frontend on S3, data
persisted as one JSON object per user on S3, a custom domain with a free
ACM certificate, a $5/month AWS Budget alert, and Lambda reserved
concurrency capped at 2. No WAF - the IAM-authenticated Function URL
combined with CloudFront OAC already rejects unauthenticated traffic before
any cost is incurred. See
[`docs/superpowers/specs/2026-08-14-lambda-s3-cloudfront-migration-design.md`](docs/superpowers/specs/2026-08-14-lambda-s3-cloudfront-migration-design.md)
for the full design.

### Prerequisites

- An AWS account with credentials configured (`aws configure` or SSO login)
- A Route 53 hosted zone for your domain's parent zone
- Docker (used to build a Lambda-compatible deployment package)
- Node.js/npm (used to build the frontend)

### Deploy

```bash
export HOSTED_ZONE_ID=Z0123456789ABCDEFGHI   # aws route53 list-hosted-zones-by-name --dns-name yourdomain.in
export NOTIFICATION_EMAIL=you@example.com
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

./infra/deploy.sh
```

Re-run `./infra/deploy.sh` any time you change backend or frontend code —
it rebuilds and redeploys both. Keep `SECRET_KEY` the same across
redeploys, or every existing login session is invalidated.

### Cost controls in this deployment

| Control | Setting |
|---|---|
| Lambda reserved concurrency | 2 |
| CloudFront price class | PriceClass_100 (US/Canada/Europe edges) |
| AWS Budget alert | $5/month, email at 80% and 100% |
| WAF | Not deployed (intentional - see design spec) |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add AWS serverless deployment instructions"
```

---

## Plan Self-Review Notes

**Spec coverage:** §3 Lambda→Mangum (Task 5), §4 S3 storage+ETag concurrency (Tasks 2-4), §5 Function URL AWS_IAM + OAC (Task 6 template), §6 frontend S3+CloudFront+SPA fallback (Task 6 template), §7 domain/ACM/Route53 (Task 6 template), §8 cost controls: reserved concurrency 2, $5 budget, no WAF, PriceClass_100 (Task 6 template + Task 9 docs), §9 CloudFormation/deploy.sh (Tasks 6-8), §10 out-of-scope items respected (no CI/CD, no data-migration tooling added, docker-compose untouched — verified in Task 3 Step 6).

**Placeholder scan:** none found — every step has complete, concrete code, exact file paths, and exact commands.

**Type/name consistency check:** `ConcurrentWriteError` (database.py) wraps `s3_storage.ConflictError` consistently across Tasks 3 and 4. `load_data(user_id)`/`save_data(user_id, data)` signatures match between Task 3's rewritten header and the `sed` substitution applied to every other function. `STORAGE_BACKEND`/`DATA_BUCKET` names match between Task 1 (config.py) and Tasks 2-3 (s3_storage.py, database.py) and Task 6 (CloudFormation `Environment.Variables`). Test fixture name `s3_bucket` matches its usage in both Task 2 and Task 3 test files via the shared `conftest.py`.
