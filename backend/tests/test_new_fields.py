import pytest
from pydantic import ValidationError

import database as db
from models import AssetCreate, BankAccountCreate, LiabilityCreate


@pytest.fixture(autouse=True)
def data_file(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))


@pytest.mark.parametrize("value", ["2026-02-30", "1899-12-31", "2026-10-14T10:00", "soon"])
def test_bad_dates_are_rejected(value):
    with pytest.raises(ValidationError, match="Invalid date"):
        AssetCreate(name="Test car", value=1, category="vehicles", valuation_date=value)


def test_dates_are_normalized():
    assert AssetCreate(name="Test car", value=1, category="vehicles", valuation_date="20261014").valuation_date == "2026-10-14"


def test_new_fields_have_their_bounds():
    with pytest.raises(ValidationError):
        AssetCreate(name="Test car", value=1, category="vehicles", annual_change_rate=-100)
    with pytest.raises(ValidationError):
        LiabilityCreate(name="Test loan", amount=1, category="mortgage", emi=0)
    with pytest.raises(ValidationError):
        LiabilityCreate(name="Test loan", amount=1, category="mortgage", tenure_months=601)
    with pytest.raises(ValidationError):
        BankAccountCreate(bank_name="Test Bank", account_number="00001234", account_type="rd", balance=0,
                          monthly_deposit=0)


@pytest.mark.parametrize("create, update, field, value", [
    ("create_asset", "update_asset", "annual_change_rate", -15),
    ("create_liability", "update_liability", "emi", 5000),
    ("create_bank_account", "update_bank_account", "maturity_date", "2027-01-01"),
])
def test_clearable_fields_can_be_cleared(create, update, field, value):
    base = {
        "create_asset": {"name": "Test car", "value": 5, "category": "vehicles"},
        "create_liability": {"name": "Test loan", "amount": 5, "category": "mortgage"},
        "create_bank_account": {"bank_name": "Test Bank", "account_number": "00001234", "account_type": "fd",
                                "balance": 5},
    }[create]
    row = getattr(db, create)("me", {**base, field: value})

    updated = getattr(db, update)(row["id"], "me", {field: None})

    assert updated[field] is None


def test_none_for_a_field_that_is_not_clearable_is_still_ignored():
    row = db.create_asset("me", {"name": "Test car", "value": 5, "category": "vehicles"})

    updated = db.update_asset(row["id"], "me", {"name": None, "value": 7})

    assert updated["name"] == "Test car" and updated["value"] == 7
