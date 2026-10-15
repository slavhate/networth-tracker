"""Login hardening: failed-login limits, timing for unknown usernames, control characters, closed registration,
the SECRET_KEY check, and bcrypt kept off the event loop."""
import asyncio
import logging
import threading
from datetime import timedelta

import httpx
import jwt
import pytest

import auth
import config
import database as db
import login_limiter
import main
import two_factor as tf
from config import settings
from credentials import EMAIL, OTHER_EMAIL, OTHER_USERNAME, PASSWORD, USERNAME, WRONG_PASSWORD
from totp_helpers import NOW, NOW_STEP, wrong_code


def register(client, username=USERNAME, password=PASSWORD, email=EMAIL):
    return client.post("/api/auth/register", json={"username": username, "password": password, "email": email})


def login(client, username=USERNAME, password=PASSWORD, ip=None):
    headers = {"X-Real-IP": ip} if ip else {}
    return client.post("/api/auth/login", data={"username": username, "password": password}, headers=headers)


@pytest.fixture
def user(client):
    assert register(client).status_code == 201


# ---------- Failed-login limit ----------

def test_five_wrong_passwords_lock_the_username_for_fifteen_minutes(client, user, clock):
    for _ in range(5):
        assert login(client, password=WRONG_PASSWORD).status_code == 401

    locked = login(client)  # even the right password: the limit is checked first

    assert locked.status_code == 429
    assert locked.json()["detail"] == "Too many attempts. Try again in 15 minutes."
    assert locked.headers["Retry-After"] == str(15 * 60)

    clock["now"] = NOW + timedelta(minutes=15)
    assert login(client).status_code == 200


def test_a_successful_login_clears_the_usernames_count(client, user, clock):
    for _ in range(4):
        login(client, password=WRONG_PASSWORD)
    assert login(client).status_code == 200

    for _ in range(4):
        assert login(client, password=WRONG_PASSWORD).status_code == 401
    assert login(client).status_code == 200


def test_the_limit_is_per_username(client, user, clock):
    register(client, OTHER_USERNAME, PASSWORD, OTHER_EMAIL)
    for _ in range(5):
        login(client, password=WRONG_PASSWORD)

    assert login(client).status_code == 429
    assert login(client, OTHER_USERNAME).status_code == 200


def test_unknown_usernames_count_too(client, clock):
    for _ in range(5):
        assert login(client, OTHER_USERNAME, WRONG_PASSWORD).status_code == 401
    assert login(client, OTHER_USERNAME, WRONG_PASSWORD).status_code == 429


def test_one_address_trying_many_usernames_is_limited(client, clock):
    for i in range(login_limiter.MAX_FAILURES_PER_IP):
        assert login(client, f"nobody_{i}", WRONG_PASSWORD).status_code == 401

    assert login(client, "nobody_else", WRONG_PASSWORD).status_code == 429


def client_ip_of(peer, **headers):
    class Client:
        host = peer

    class Request:
        client = Client()

    Request.headers = {key.replace("_", "-"): value for key, value in headers.items()}
    return main._client_ip(Request())


def test_the_bundled_nginx_names_the_client_by_default():
    # The compose network's nginx is in Docker's bridge range, the default TRUSTED_PROXIES
    assert client_ip_of("172.18.0.3", x_real_ip="203.0.113.7") == "203.0.113.7"
    assert client_ip_of("172.18.0.3", x_forwarded_for="203.0.113.7, 172.18.0.9") == "203.0.113.7"
    assert client_ip_of("172.18.0.3", x_real_ip="not-an-address") == "172.18.0.3"


@pytest.mark.parametrize("peer", ["1.2.3.4", "127.0.0.1", "192.168.1.20", "10.0.0.5"])
def test_an_untrusted_peer_is_counted_as_itself_whatever_it_sends(peer):
    assert client_ip_of(peer, x_real_ip="203.0.113.7", x_forwarded_for="203.0.113.8") == peer


def test_trusted_proxies_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "192.168.1.20, 2001:db8::/32, junk")

    assert client_ip_of("192.168.1.20", x_real_ip="203.0.113.7") == "203.0.113.7"
    assert client_ip_of("2001:db8::5", x_real_ip="203.0.113.7") == "203.0.113.7"
    assert client_ip_of("172.18.0.3", x_real_ip="203.0.113.7") == "172.18.0.3"  # no longer in the list


def test_forwarded_for_skips_every_trusted_hop(monkeypatch):
    # A proxy in front of nginx: nginx sets X-Real-IP to that proxy unless configured with real_ip_header, so without
    # X-Real-IP the chain is read right to left past every trusted proxy; what a client put first is not believed
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "172.16.0.0/12,10.0.0.0/8")
    assert client_ip_of("172.18.0.3", x_forwarded_for="6.6.6.6, 203.0.113.7, 10.0.0.2") == "203.0.113.7"


@pytest.fixture
def client_header(monkeypatch):
    """Requests name their client address in an X-Test-Client header (the test client has no real address)."""
    monkeypatch.setattr(main, "_client_ip", lambda request: request.headers.get("x-test-client", "testclient"))


def login_from(client, address, password=PASSWORD):
    return client.post("/api/auth/login", data={"username": USERNAME, "password": password},
                       headers={"X-Test-Client": address})


def test_a_guesser_elsewhere_cannot_lock_the_owner_out(client, user, clock, client_header):
    for _ in range(5):
        assert login_from(client, "203.0.113.5", WRONG_PASSWORD).status_code == 401
    assert login_from(client, "203.0.113.5").status_code == 429

    assert login_from(client, "198.51.100.7").status_code == 200


def test_a_usernames_total_across_clients_is_limited(client, user, clock, client_header, monkeypatch):
    monkeypatch.setattr(login_limiter, "MAX_FAILURES_PER_USERNAME", 8)  # 50 in production; fewer bcrypt rounds here
    for address in ("203.0.113.1", "203.0.113.2"):
        for _ in range(4):
            assert login_from(client, address, WRONG_PASSWORD).status_code == 401

    assert login_from(client, "203.0.113.3").status_code == 429


def test_ipv6_clients_are_counted_by_their_64(client, clock, client_header):
    for i in range(login_limiter.MAX_FAILURES_PER_IP):
        resp = client.post("/api/auth/login", data={"username": f"nobody_{i}", "password": WRONG_PASSWORD},
                           headers={"X-Test-Client": f"2001:db8:1:2::{i + 1:x}"})
        assert resp.status_code == 401

    def attempt(address):
        return client.post("/api/auth/login", data={"username": "nobody_else", "password": WRONG_PASSWORD},
                           headers={"X-Test-Client": address}).status_code

    assert attempt("2001:db8:1:2:ffff::1") == 429  # same /64, new address
    assert attempt("2001:db8:1:3::1") == 401  # the next /64 is another client


def test_client_ids():
    assert login_limiter.client_id("2001:db8:1:2:aaaa::1") == login_limiter.client_id("2001:db8:1:2:bbbb::9")
    assert login_limiter.client_id("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert login_limiter.client_id("::ffff:203.0.113.7") == "203.0.113.7"
    assert login_limiter.client_id("203.0.113.7") == "203.0.113.7"
    assert login_limiter.client_id("testclient") == "testclient"


def test_parallel_guesses_cannot_all_slip_past_the_limit(client, user):
    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*[
                ac.post("/api/auth/login", data={"username": USERNAME, "password": WRONG_PASSWORD})
                for _ in range(12)])

    statuses = sorted(r.status_code for r in asyncio.run(run()))

    assert statuses == [401] * 5 + [429] * 7


def test_wrong_2fa_codes_count_towards_the_username_limit(client, user, clock):
    record = db.get_user_by_username(USERNAME)
    secret = tf.generate_secret()
    db.update_user(record["id"], {"totp_enabled": True, "totp_secret": secret})
    for _ in range(3):
        login(client, password=WRONG_PASSWORD)
    mfa_token = login(client).json()["mfa_token"]  # the right password clears the count

    for _ in range(4):
        resp = client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": wrong_code(secret, NOW_STEP)})
        assert resp.status_code == 401
    # The 2FA lockout (5 failures) is separate; the login limit sees the same 4 failures plus this password
    assert login(client, password=WRONG_PASSWORD).status_code == 401
    assert login(client).status_code == 429


def test_invalid_2fa_sessions_count_against_the_address(client, clock):
    for _ in range(login_limiter.MAX_FAILURES_PER_IP):
        assert client.post("/api/auth/login/2fa", json={"mfa_token": "garbage", "code": "123456"}).status_code == 401
    assert client.post("/api/auth/login/2fa", json={"mfa_token": "garbage", "code": "123456"}).status_code == 429


def test_the_limiter_forgets_the_oldest_keys_beyond_its_cap(monkeypatch):
    monkeypatch.setattr(login_limiter, "MAX_KEYS", 3)
    login_limiter.record_failure(["a", "b", "c", "d"])
    assert list(login_limiter._failures) == ["b", "c", "d"]


# ---------- Unknown usernames take as long as wrong passwords ----------

def test_an_unknown_username_is_checked_against_a_dummy_hash(client, monkeypatch):
    checked = []
    real_verify = main.verify_password

    def spy(password, hashed):
        checked.append(hashed)
        return real_verify(password, hashed)

    monkeypatch.setattr(main, "verify_password", spy)

    assert login(client, OTHER_USERNAME, WRONG_PASSWORD).status_code == 401
    assert checked == [auth.dummy_password_hash()]


# ---------- Control characters ----------

@pytest.mark.parametrize("username, password", [
    (USERNAME, "a\x00" + PASSWORD),
    (USERNAME, PASSWORD + "\n"),
    ("a\x00b" + USERNAME, PASSWORD),
])
def test_control_characters_in_a_login_are_422_not_500(client, user, username, password):
    assert login(client, username, password).status_code == 422


@pytest.mark.parametrize("field, value", [("password", "a\x00" + PASSWORD), ("username", USERNAME + "\x1b")])
def test_control_characters_in_a_registration_are_422(client, field, value):
    body = {"username": USERNAME, "password": PASSWORD, "email": EMAIL, field: value}
    assert client.post("/api/auth/register", json=body).status_code == 422
    assert db.get_user_by_username(USERNAME) is None


def test_a_new_password_with_a_nul_is_422(client, auth_headers):
    resp = client.post("/api/auth/password", headers=auth_headers,
                       json={"current_password": PASSWORD, "new_password": "a\x00" + PASSWORD})
    assert resp.status_code == 422


def test_verify_password_refuses_a_nul_instead_of_raising():
    assert auth.verify_password("a\x00b", auth.dummy_password_hash()) is False


# ---------- Registration switch ----------

def test_registration_can_be_turned_off(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)

    resp = register(client)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Registration is disabled"
    assert db.get_user_by_username(USERNAME) is None


def test_existing_users_still_log_in_with_registration_off(client, user, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_REGISTRATION", False)
    assert login(client).status_code == 200


def test_two_registrations_of_one_name_racing_create_one_user(client):
    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            body = {"username": USERNAME, "password": PASSWORD, "email": EMAIL}
            return await asyncio.gather(*[ac.post("/api/auth/register", json=body) for _ in range(3)])

    statuses = sorted(r.status_code for r in asyncio.run(run()))

    assert statuses == [201, 400, 400]
    assert sum(1 for u in db.load_data()["users"] if u["username"] == USERNAME) == 1


# ---------- SECRET_KEY ----------

def test_a_short_secret_key_logs_a_warning(caplog):
    short = config.Settings(SECRET_KEY="x" * 16)
    with caplog.at_level(logging.WARNING, logger="config"):
        config.check_secret_key(short)
    assert any("SECRET_KEY is only 16 characters long" in r.getMessage() for r in caplog.records)
    assert short.SECRET_KEY == "x" * 16  # kept: a warning, not a refusal to start


def test_a_long_enough_secret_key_is_quiet(caplog):
    with caplog.at_level(logging.WARNING, logger="config"):
        config.check_secret_key(config.Settings(SECRET_KEY="x" * 32))
    assert not caplog.records


def test_a_missing_secret_key_is_generated_with_a_single_worker_warning(caplog):
    unset = config.Settings(SECRET_KEY="")
    with caplog.at_level(logging.WARNING, logger="config"):
        config.check_secret_key(unset)
    assert len(unset.SECRET_KEY) == 64
    assert any("single worker" in r.getMessage() for r in caplog.records)


# ---------- Tokens (PyJWT) ----------

def test_a_token_signed_with_another_algorithm_is_rejected():
    forged = jwt.encode({"sub": USERNAME, "exp": 9_999_999_999}, settings.SECRET_KEY, algorithm="HS512")
    assert auth.decode_token(forged) is None


def test_an_unsigned_token_is_rejected():
    forged = jwt.encode({"sub": USERNAME, "exp": 9_999_999_999}, None, algorithm="none")
    assert auth.decode_token(forged) is None


def test_a_token_without_an_expiry_is_rejected():
    forged = jwt.encode({"sub": USERNAME}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert auth.decode_token(forged) is None


def test_an_expired_access_token_is_rejected():
    token = auth.create_access_token({"sub": USERNAME}, expires_delta=timedelta(minutes=-1))
    assert auth.decode_token(token) is None


# ---------- bcrypt off the event loop ----------

def test_a_password_check_does_not_hold_up_other_requests(client, user, monkeypatch):
    """The health check answers while a login's password check is still running: the check is in a worker thread."""
    health_answered = threading.Event()
    real_verify = main.verify_password

    def slow_verify(password, hashed):
        # Waits for the health check, which can only answer if this isn't blocking the event loop
        waited = health_answered.wait(timeout=5)
        return waited and real_verify(password, hashed)

    monkeypatch.setattr(main, "verify_password", slow_verify)

    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            async def health():
                resp = await ac.get("/api/health")
                health_answered.set()
                return resp

            return await asyncio.gather(
                ac.post("/api/auth/login", data={"username": USERNAME, "password": PASSWORD}), health())

    logged_in, healthy = asyncio.run(run())

    assert healthy.status_code == 200
    assert logged_in.status_code == 200
