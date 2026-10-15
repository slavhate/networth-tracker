import asyncio
import logging
import re

import pytest

import database as db
import main
from config import settings
from credentials import PASSWORD, _name

pytestmark = pytest.mark.usefixtures("offline_markets", "frozen_today")


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)


def start_app():
    asyncio.run(main.startup_event())


def login(client, username, password):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def password_warnings(caplog):
    return [r for r in caplog.records if r.name == "main" and "generated password" in r.getMessage()]


def test_configured_demo_password_logs_in(client, monkeypatch, demo_on):
    monkeypatch.setattr(settings, "DEMO_PASSWORD", PASSWORD)
    start_app()

    resp = login(client, settings.DEMO_USERNAME, PASSWORD)

    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_configured_demo_password_is_not_logged(client, monkeypatch, demo_on, caplog):
    monkeypatch.setattr(settings, "DEMO_PASSWORD", PASSWORD)
    with caplog.at_level(logging.DEBUG):
        start_app()

    assert PASSWORD not in caplog.text
    assert password_warnings(caplog) == []


def test_generated_demo_password_is_logged_once_and_logs_in(client, monkeypatch, demo_on, caplog):
    monkeypatch.setattr(settings, "DEMO_PASSWORD", "")
    with caplog.at_level(logging.WARNING, logger="main"):
        start_app()

    [record] = password_warnings(caplog)
    assert record.levelno == logging.WARNING
    username, password = record.args
    assert username == settings.DEMO_USERNAME
    assert len(password) >= 12
    assert f"Created demo user {username!r} with a generated password: {password}" in record.getMessage()
    assert "DEMO_PASSWORD" in record.getMessage()
    assert login(client, username, password).status_code == 200
    assert login(client, username, PASSWORD).status_code == 401


def test_two_fresh_data_files_get_different_generated_passwords(client, tmp_path, monkeypatch, demo_on, caplog):
    monkeypatch.setattr(settings, "DEMO_PASSWORD", "")
    passwords = []
    for name in ("first.json", "second.json"):
        monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / name))
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="main"):
            start_app()
        [record] = password_warnings(caplog)
        passwords.append(record.args[1])

    assert passwords[0] != passwords[1]


def test_demo_username_is_configurable(client, monkeypatch, demo_on, caplog):
    name = _name()
    monkeypatch.setattr(settings, "DEMO_USERNAME", name)
    monkeypatch.setattr(settings, "DEMO_PASSWORD", PASSWORD)
    start_app()

    user = db.get_user_by_username(name)
    assert user["email"] == f"{name}@example.com"
    assert db.get_user_by_username("demo") is None
    assert login(client, name, PASSWORD).status_code == 200
    assert db.get_assets_by_user(user["id"])  # the sample data went to that user


def test_demo_username_defaults_to_demo(client, demo_on):
    start_app()

    assert settings.DEMO_USERNAME == "demo"
    assert db.get_user_by_username("demo")["email"].startswith("demo@")


def test_second_startup_leaves_the_existing_demo_user_alone(client, monkeypatch, demo_on, caplog):
    monkeypatch.setattr(settings, "DEMO_PASSWORD", "")
    with caplog.at_level(logging.WARNING, logger="main"):
        start_app()
    [record] = password_warnings(caplog)
    password = record.args[1]
    users_before = len(db.load_data()["users"])

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        start_app()

    assert password not in caplog.text
    assert password_warnings(caplog) == []
    assert len(db.load_data()["users"]) == users_before
    assert login(client, settings.DEMO_USERNAME, password).status_code == 200


def test_changing_demo_password_setting_does_not_touch_an_existing_user(client, monkeypatch, demo_on):
    monkeypatch.setattr(settings, "DEMO_PASSWORD", PASSWORD)
    start_app()
    monkeypatch.setattr(settings, "DEMO_PASSWORD", "")
    start_app()

    assert login(client, settings.DEMO_USERNAME, PASSWORD).status_code == 200


def test_no_demo_user_unless_asked_for(client, monkeypatch):
    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", False)
    start_app()

    assert db.get_user_by_username(settings.DEMO_USERNAME) is None
