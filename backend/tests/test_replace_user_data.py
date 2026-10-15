import pytest

import database as db

EMPTY = {
    "assets": [], "liabilities": [], "bank_accounts": [], "insurances": [],
    "mutual_funds": [], "equities": [], "snapshots": [], "goal": None,
}


@pytest.fixture(autouse=True)
def data_file(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))


def backup(**sections):
    return {**EMPTY, **sections}


def test_create_helpers_still_build_the_same_rows():
    asset = db.create_asset("me", {"name": "Cash", "value": 5, "category": "cash", "description": None})
    assert asset["user_id"] == "me" and asset["value"] == 5 and len(asset["id"]) == 36

    equity = db.create_equity("me", {"symbol": "infy", "market": "NSE", "quantity": 4, "avg_buy_price": 10.0})
    assert equity["symbol"] == "INFY"
    assert equity["current_price"] == 10.0
    assert equity["invested_amount"] == 40.0 and equity["gain_loss"] == 0

    snapshot = db.create_snapshot("me", 10, 4)
    assert snapshot["net_worth"] == 6

    goal = db.create_or_update_goal("me", {})
    assert goal["target_amount"] == 100000000 and goal["name"] == "Net Worth Goal"


def test_new_rows_ignore_id_and_user_id_in_the_fields():
    asset = db.create_asset("me", {"id": "evil", "user_id": "other", "name": "x", "value": 1,
                                   "category": "cash", "description": None})

    assert asset["user_id"] == "me"
    assert asset["id"] != "evil"
    assert list(asset)[:2] == ["id", "user_id"]
    assert db.get_assets_by_user("other") == []


def test_replaces_only_this_users_rows():
    db.create_asset("me", {"name": "Old car", "value": 1, "category": "vehicles", "description": None})
    db.create_asset("other", {"name": "Their flat", "value": 2, "category": "real_estate", "description": None})
    db.create_snapshot("me", 10, 5)
    db.create_or_update_goal("me", {"target_amount": 5})
    db.create_or_update_goal("other", {"target_amount": 7})

    db.replace_user_data("me", backup(assets=[
        {"name": "New flat", "value": 3, "category": "real_estate", "description": None},
    ]))

    assert [a["name"] for a in db.get_assets_by_user("me")] == ["New flat"]
    assert [a["name"] for a in db.get_assets_by_user("other")] == ["Their flat"]
    assert db.get_snapshots_by_user("me") == []
    assert db.get_goal_by_user("me") is None
    assert db.get_goal_by_user("other")["target_amount"] == 7


def test_rows_get_a_fresh_id_and_this_user():
    db.replace_user_data("me", backup(liabilities=[
        {"name": "Loan", "amount": 100, "category": "mortgage", "interest_rate": 8.5, "description": None},
    ]))

    [row] = db.get_liabilities_by_user("me")
    assert row["user_id"] == "me"
    assert len(row["id"]) == 36
    assert row["created_at"] == row["updated_at"]


def test_snapshots_keep_their_timestamp_and_recompute_net_worth():
    db.replace_user_data("me", backup(snapshots=[
        {"total_assets": 100.0, "total_liabilities": 30.0, "timestamp": "2025-01-31T10:00:00"},
    ]))

    [snapshot] = db.get_snapshots_by_user("me")
    assert snapshot["timestamp"] == "2025-01-31T10:00:00"
    assert snapshot["net_worth"] == 70.0


def test_equity_values_are_recomputed_and_a_null_price_uses_the_average():
    db.replace_user_data("me", backup(equities=[
        {"symbol": "tcs", "company_name": None, "market": "NSE", "quantity": 2,
         "avg_buy_price": 100.0, "current_price": 150.0, "notes": None},
        {"symbol": "KO", "company_name": None, "market": "NYSE", "quantity": 3,
         "avg_buy_price": 50.0, "current_price": None, "notes": None},
    ]))

    by_symbol = {e["symbol"]: e for e in db.get_equities_by_user("me")}
    assert by_symbol["TCS"]["current_value"] == 300.0
    assert by_symbol["TCS"]["gain_loss"] == 100.0
    assert by_symbol["KO"]["current_price"] == 50.0
    assert by_symbol["KO"]["current_value"] == 150.0


def test_goal_is_restored():
    db.replace_user_data("me", backup(goal={"target_amount": 100000000.0, "name": "10 Cr"}))

    assert db.get_goal_by_user("me")["name"] == "10 Cr"


def test_replace_saves_exactly_once(monkeypatch):
    db.load_data()  # create the data file first, so only replace_user_data's own save is counted
    saves = []
    real_save = db.save_data
    monkeypatch.setattr(db, "save_data", lambda data: (saves.append(1), real_save(data)))

    db.replace_user_data("me", backup(
        assets=[{"name": "A", "value": 1, "category": "cash", "description": None}],
        snapshots=[{"total_assets": 1.0, "total_liabilities": 0.0, "timestamp": "2025-01-01T00:00:00"}],
    ))

    assert len(saves) == 1


def test_snapshot_limit_none_returns_every_snapshot_newest_first():
    for day in range(1, 36):
        db.create_snapshot("me", day, 0)

    assert len(db.get_snapshots_by_user("me")) == 30
    every = db.get_snapshots_by_user("me", limit=None)
    assert len(every) == 35
    assert every[0]["timestamp"] >= every[-1]["timestamp"]
