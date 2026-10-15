import json

import pytest

from restore import RestoreError, parse_backup

ASSET = {"name": "Flat", "value": 100, "category": "real_estate"}


def raw(obj):
    return json.dumps(obj).encode("utf-8")


def error_of(data: bytes):
    with pytest.raises(RestoreError) as exc:
        parse_backup(data)
    return exc.value.status_code, exc.value.detail


def test_missing_sections_are_empty_and_goal_is_none():
    cleaned = parse_backup(raw({"assets": [ASSET]}))

    assert cleaned["assets"] == [{"name": "Flat", "value": 100.0, "category": "real_estate", "description": None,
                                  "annual_change_rate": None, "valuation_date": None,
                                  "monthly_contribution": None, "interest_rate": None,
                                  "quantity": None, "unit_price": None, "yearly_contribution": None,
                                  "yearly_contribution_month": None, "nps_schemes": None}]
    for section in ("liabilities", "bank_accounts", "insurances", "mutual_funds", "equities", "snapshots"):
        assert cleaned[section] == []
    assert cleaned["goal"] is None


def test_unknown_and_server_assigned_fields_are_dropped():
    item = {**ASSET, "id": "x", "user_id": "someone", "created_at": "t", "updated_at": "t", "hacked": True}

    [asset] = parse_backup(raw({"assets": [item]}))["assets"]

    assert set(asset) == {"name", "value", "category", "description", "annual_change_rate", "valuation_date",
                          "monthly_contribution", "interest_rate", "quantity", "unit_price",
                          "yearly_contribution", "yearly_contribution_month", "nps_schemes"}


def test_equity_keeps_current_price_and_market_is_a_plain_string():
    equity = {"symbol": "KO", "market": "NYSE", "quantity": 3, "avg_buy_price": 50,
              "current_price": 61.5, "gain_loss": 999}

    [cleaned] = parse_backup(raw({"equities": [equity]}))["equities"]

    assert cleaned["current_price"] == 61.5
    assert cleaned["market"] == "NYSE"
    assert "gain_loss" not in cleaned


def test_goal_is_cleaned():
    cleaned = parse_backup(raw({"goal": {"target_amount": 5, "id": "g", "user_id": "u"}}))

    assert cleaned["goal"] == {"target_amount": 5.0, "name": "Net Worth Goal"}


def test_snapshot_needs_an_iso_timestamp():
    code, detail = error_of(raw({"snapshots": [
        {"total_assets": 1, "total_liabilities": 0, "timestamp": "last tuesday"},
    ]}))

    assert code == 400
    assert detail.startswith("snapshots[0].timestamp: ")


@pytest.mark.parametrize("data, expected", [
    (b"\xff\xfe not utf8", "Invalid JSON file"),
    (b"{not json", "Invalid JSON file"),
    (b'{"assets": [{"name": "x", "value": NaN, "category": "cash"}]}', "Invalid JSON file"),
    (b'{"assets": [{"name": "x", "value": Infinity, "category": "cash"}]}', "Invalid JSON file"),
    (b'{"assets": [{"name": "x", "value": 1e400, "category": "cash"}]}', "Invalid JSON file"),
    (b"[]", "Backup must be a JSON object"),
    (b'{"export_date": "2026-01-01"}', "This file doesn't look like a Net Worth Tracker backup"),
    (b'{"assets": {}}', "assets must be a list"),
    (b'{"assets": [5]}', "assets[0]: must be an object"),
    (b'{"goal": 5}', "goal: must be an object"),
])
def test_bad_files_are_rejected_with_a_clear_message(data, expected):
    assert error_of(data) == (400, expected)


def test_invalid_item_names_its_section_index_and_field():
    bad = {**ASSET, "value": "lots"}

    code, detail = error_of(raw({"assets": [ASSET, ASSET, ASSET, bad]}))

    assert code == 400
    assert detail.startswith("assets[3].value: Input should be a valid number")


def test_invalid_goal_names_its_field():
    code, detail = error_of(raw({"goal": {"target_amount": -5}}))

    assert code == 400
    assert detail.startswith("goal.target_amount: ")


def test_a_utf8_bom_is_ignored():
    # "UTF-8 with BOM" is what Notepad and PowerShell 5.1 write
    cleaned = parse_backup(b"\xef\xbb\xbf" + raw({"assets": [ASSET]}))

    assert len(cleaned["assets"]) == 1


def test_file_over_10mb_is_413():
    assert error_of(b" " * (10 * 1024 * 1024 + 1)) == (413, "Backup file too large (max 10MB)")


def test_json_nested_too_deeply_is_invalid():
    assert error_of(b"[" * 200_000 + b"]" * 200_000) == (400, "Invalid JSON file")


@pytest.mark.parametrize("backup, expected", [
    ({"snapshots": [{"total_assets": "NaN", "total_liabilities": 0, "timestamp": "2026-01-01T00:00:00"}]},
     "snapshots[0].total_assets: Input should be a finite number"),
    ({"snapshots": [{"total_assets": 1, "total_liabilities": "-inf", "timestamp": "2026-01-01T00:00:00"}]},
     "snapshots[0].total_liabilities: Input should be a finite number"),
    ({"assets": [{"name": "x", "value": "inf", "category": "cash"}]},
     "assets[0].value: Input should be a finite number"),
    ({"equities": [{"symbol": "KO", "market": "NYSE", "quantity": 1, "avg_buy_price": 1, "current_price": "Infinity"}]},
     "equities[0].current_price: Input should be a finite number"),
])
def test_non_finite_number_strings_are_rejected(backup, expected):
    assert error_of(raw(backup)) == (400, expected)


@pytest.mark.parametrize("backup, field", [
    # just above the share cap
    ({"equities": [{"symbol": "KO", "market": "NYSE", "quantity": 10**9 + 1, "avg_buy_price": 1}]},
     "equities[0].quantity"),
    # a quantity too large to convert to a float at all
    ({"equities": [{"symbol": "KO", "market": "NYSE", "quantity": 10**400, "avg_buy_price": 1}]},
     "equities[0].quantity"),
    # a price above the cap
    ({"equities": [{"symbol": "KO", "market": "NYSE", "quantity": 1, "avg_buy_price": 0, "current_price": 2e15}]},
     "equities[0].current_price"),
    # snapshot totals above the cap
    ({"snapshots": [{"total_assets": 2e300, "total_liabilities": 0, "timestamp": "2026-01-01T00:00:00"}]},
     "snapshots[0].total_assets"),
    ({"snapshots": [{"total_assets": 0, "total_liabilities": 2e300, "timestamp": "2026-01-01T00:00:00"}]},
     "snapshots[0].total_liabilities"),
])
def test_values_beyond_the_input_bounds_are_rejected(backup, field):
    status, detail = error_of(raw(backup))

    assert status == 400
    assert detail.startswith(f"{field}: ")


def test_a_tiny_invested_amount_is_accepted():
    # storage keeps the gain percent at 0 below one paisa invested, so restore must not refuse it
    backup = {"equities": [{"symbol": "KO", "market": "NYSE", "quantity": 1, "avg_buy_price": 1e-300,
                            "current_price": 1e15}]}

    [equity] = parse_backup(raw(backup))["equities"]

    assert equity["avg_buy_price"] == 1e-300 and equity["current_price"] == 1e15


def test_large_but_finite_values_are_accepted():
    cleaned = parse_backup(raw({
        "equities": [{"symbol": "KO", "market": "NYSE", "quantity": 10**6, "avg_buy_price": 1e10}],
        "snapshots": [{"total_assets": 1e18, "total_liabilities": 1e17, "timestamp": "2026-01-01T00:00:00"}],
    }))

    assert len(cleaned["equities"]) == 1 and len(cleaned["snapshots"]) == 1


def test_a_snapshot_total_above_1e18_is_accepted():
    # valid holdings can add up past 1e18 (1e9 shares at 1e15 each), so a user's own export must restore
    [snapshot] = parse_backup(raw({
        "snapshots": [{"total_assets": 1e24, "total_liabilities": 0, "timestamp": "2026-01-01T00:00:00"}],
    }))["snapshots"]

    assert snapshot["total_assets"] == 1e24


BANK = {"bank_name": "Test Bank", "account_number": "00001234", "account_type": "fd", "balance": 100}


def test_a_deposit_maturing_before_it_starts_is_rejected():
    backup = {"bank_accounts": [BANK, {**BANK, "start_date": "2026-01-01", "maturity_date": "2025-12-31"}]}

    assert error_of(raw(backup)) == (400, "bank_accounts[1]: Maturity date must be after the start date")


@pytest.mark.parametrize("dates", [
    {"start_date": "2026-01-01", "maturity_date": "2026-01-01"},
    {"start_date": "2026-01-01"},
    {"maturity_date": "2025-12-31"},
])
def test_deposit_dates_that_do_not_contradict_each_other_are_accepted(dates):
    [account] = parse_backup(raw({"bank_accounts": [{**BANK, **dates}]}))["bank_accounts"]

    assert all(account[key] == value for key, value in dates.items())


def test_a_dated_nps_priced_through_is_kept():
    [asset] = parse_backup(raw({"assets": [{**ASSET, "nps_priced_through": "2026-04-01"}]}))["assets"]

    assert asset["nps_priced_through"] == "2026-04-01"


def test_a_bad_date_is_reported_as_just_invalid_date():
    backup = {"assets": [{**ASSET, "valuation_date": "soon"}]}

    assert error_of(raw(backup)) == (400, "assets[0].valuation_date: Invalid date")
