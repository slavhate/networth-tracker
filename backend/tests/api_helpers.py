"""Shared API-level helpers for tests."""
import asyncio

import httpx

import main
from totp_helpers import NOW_STEP, code_for


def enable_2fa(client, headers, password="secret123"):
    """Run setup + enable at NOW_STEP. Later TOTP uses must be NOW_STEP + 1 (replay protection).

    The default password is that of the auth_headers fixture's user "tester".
    """
    setup = client.post("/api/auth/2fa/setup", headers=headers).json()
    body = {"password": password, "code": code_for(setup["secret"], NOW_STEP)}
    resp = client.post("/api/auth/2fa/enable", headers=headers, json=body)
    assert resp.status_code == 200
    return setup["secret"], resp.json()["backup_codes"]


def fire_concurrently(requests):
    """Send (path, headers, json) requests all at once through the ASGI app; return the responses."""
    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*[ac.post(path, headers=h, json=body) for path, h, body in requests])

    return asyncio.run(run())
