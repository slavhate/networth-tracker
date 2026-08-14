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
