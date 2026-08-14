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


def _put_json(key: str, body: dict, etag: Optional[str]) -> str:
    """Conditional write: If-Match the given etag, or If-None-Match '*' when
    etag is None (this key is expected not to exist yet). Returns the new
    ETag on success."""
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
        resp = _s3().put_object(**kwargs)
        return resp["ETag"]
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
        new_etag = _put_json(_user_key(user_id), data, etag)
        data["_etag"] = new_etag
    except ConflictError:
        data["_etag"] = etag
        raise


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
