import json as jsonlib


def _function_url_event(method: str, path: str, query: str = "", headers=None, body=None):
    event = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": query,
        "headers": headers or {"host": "example.com"},
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
    if body is not None:
        event["body"] = body
    return event


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


def test_register_login_and_authenticated_request_via_lambda_handler(monkeypatch, tmp_path):
    from config import settings
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", False)

    from lambda_handler import handler

    register_event = _function_url_event(
        "POST", "/api/auth/register",
        headers={"host": "example.com", "content-type": "application/json"},
        body=jsonlib.dumps({"username": "lambdauser", "email": "l@example.com", "password": "pw12345"}),
    )
    register_result = handler(register_event, FakeContext())
    assert register_result["statusCode"] == 201

    login_event = _function_url_event(
        "POST", "/api/auth/login",
        headers={"host": "example.com", "content-type": "application/x-www-form-urlencoded"},
        body="username=lambdauser&password=pw12345",
    )
    login_result = handler(login_event, FakeContext())
    assert login_result["statusCode"] == 200
    token = jsonlib.loads(login_result["body"])["access_token"]

    me_event = _function_url_event(
        "GET", "/api/auth/me",
        headers={"host": "example.com", "authorization": f"Bearer {token}"},
    )
    me_result = handler(me_event, FakeContext())
    assert me_result["statusCode"] == 200
    assert jsonlib.loads(me_result["body"])["username"] == "lambdauser"
