import json
import os
import shutil
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from config import settings

def get_data_file_path() -> str:
    return settings.DATA_FILE

def load_data() -> Dict[str, Any]:
    """Load data from JSON file"""
    data_file = get_data_file_path()
    if not os.path.exists(data_file):
        # Initialize with empty structure
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
        save_data(initial_data)
        return initial_data
    
    with open(data_file, 'r') as f:
        data = json.load(f)
        # Ensure new collections exist
        if "bank_accounts" not in data:
            data["bank_accounts"] = []
        if "insurances" not in data:
            data["insurances"] = []
        if "mutual_funds" not in data:
            data["mutual_funds"] = []
        if "equities" not in data:
            data["equities"] = []
        if "goals" not in data:
            data["goals"] = []
        return data

def save_data(data: Dict[str, Any]) -> None:
    """Save data to JSON file atomically: write a temp file, then swap it into place"""
    data_file = get_data_file_path()
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    tmp_file = data_file + ".tmp"
    try:
        with open(tmp_file, 'w') as f:
            if os.path.exists(data_file):
                shutil.copymode(data_file, tmp_file)  # permissions first, so the data is never readable more widely
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, data_file)
    except BaseException:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        raise

def generate_id() -> str:
    """Generate unique ID"""
    return str(uuid.uuid4())

def get_timestamp() -> str:
    """Get current timestamp as ISO string"""
    return datetime.utcnow().isoformat()

# Row builders shared by the create_* helpers and replace_user_data
def _new_row(user_id: str, fields: Dict) -> Dict:
    now = get_timestamp()
    row = {"id": None, "user_id": None, **fields, "created_at": now, "updated_at": now}
    # Assigned after the spread so a fields dict carrying these keys can't override them; the key order is unchanged
    row["id"] = generate_id()
    row["user_id"] = user_id
    return row

def _equity_numbers(quantity: float, avg_price: float, current_price: float) -> Dict:
    """Invested amount, value and gain for a holding. The percent is 0 below one paisa invested,
    where it would be meaningless (and can overflow to infinity)."""
    invested = quantity * avg_price
    current_value = quantity * current_price
    gain_loss = current_value - invested
    return {
        "invested_amount": invested,
        "current_value": current_value,
        "gain_loss": gain_loss,
        "gain_loss_percent": gain_loss / invested * 100 if invested >= 0.01 else 0,
    }

# Optional fields a PUT may clear by sending null; any other null in an update is ignored
ASSET_CLEARABLE = frozenset({"description", "annual_change_rate", "valuation_date", "monthly_contribution",
                             "interest_rate", "quantity", "unit_price", "yearly_contribution",
                             "yearly_contribution_month", "nps_schemes", "nps_priced_through"})
LIABILITY_CLEARABLE = frozenset({"interest_rate", "description", "emi", "balance_date", "tenure_months"})
BANK_ACCOUNT_CLEARABLE = frozenset({"branch", "ifsc_code", "interest_rate", "start_date", "maturity_date",
                                    "monthly_deposit"})
MUTUAL_FUND_CLEARABLE = frozenset({"sip_amount", "sip_frequency", "sip_day", "sip_start_date", "sip_end_date",
                                   "holdings_date", "sip_units", "sip_invested", "sip_priced_through"})

def _apply_update(row: Dict, update_data: Dict, clearable: frozenset = frozenset()) -> None:
    for key, value in update_data.items():
        if value is not None or key in clearable:
            row[key] = value
    row["updated_at"] = get_timestamp()

def _new_equity_row(user_id: str, equity_data: Dict) -> Dict:
    quantity = equity_data["quantity"]
    avg_price = equity_data["avg_buy_price"]
    current_price = equity_data.get("current_price")
    if current_price is None:
        current_price = avg_price
    return _new_row(user_id, {
        "symbol": equity_data["symbol"].upper(),
        "company_name": equity_data.get("company_name"),
        "market": equity_data["market"],
        "quantity": quantity,
        "avg_buy_price": avg_price,
        "current_price": current_price,
        **_equity_numbers(quantity, avg_price, current_price),
        "notes": equity_data.get("notes"),
    })

# Breakdown maps a snapshot may carry (newer snapshots); older ones have only the totals
SNAPSHOT_BREAKDOWN = ("assets_by_category", "liabilities_by_category", "assets_by_class")

def _new_snapshot_row(user_id: str, total_assets: float, total_liabilities: float, timestamp: str,
                      breakdown: Optional[Dict] = None) -> Dict:
    return {
        "id": generate_id(),
        "user_id": user_id,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "timestamp": timestamp,
        **{key: breakdown[key] for key in SNAPSHOT_BREAKDOWN if breakdown and breakdown.get(key) is not None},
    }

def _new_goal_row(user_id: str, goal_data: Dict) -> Dict:
    return _new_row(user_id, {
        "target_amount": goal_data.get("target_amount", 100000000),  # Default 10 crore
        "name": goal_data.get("name", "Net Worth Goal"),
    })

# User operations
def get_user_by_username(username: str) -> Optional[Dict]:
    data = load_data()
    for user in data["users"]:
        if user["username"] == username:
            return user
    return None

def get_user_by_id(user_id: str) -> Optional[Dict]:
    data = load_data()
    for user in data["users"]:
        if user["id"] == user_id:
            return user
    return None

def create_user(username: str, email: str, hashed_password: str) -> Dict:
    data = load_data()
    user = {
        "id": generate_id(),
        "username": username,
        "email": email,
        "hashed_password": hashed_password,
        "created_at": get_timestamp()
    }
    data["users"].append(user)
    save_data(data)
    return user

def update_user(user_id: str, updates: Dict) -> Optional[Dict]:
    """Apply every key in updates, including None (used to clear 2FA fields)."""
    data = load_data()
    for i, user in enumerate(data["users"]):
        if user["id"] == user_id:
            data["users"][i].update(updates)
            save_data(data)
            return data["users"][i]
    return None

# Asset operations
def get_assets_by_user(user_id: str) -> List[Dict]:
    data = load_data()
    return [a for a in data["assets"] if a["user_id"] == user_id]

def get_asset_by_id(asset_id: str, user_id: str) -> Optional[Dict]:
    data = load_data()
    for asset in data["assets"]:
        if asset["id"] == asset_id and asset["user_id"] == user_id:
            return asset
    return None

def create_asset(user_id: str, asset_data: Dict) -> Dict:
    data = load_data()
    asset = _new_row(user_id, asset_data)
    data["assets"].append(asset)
    save_data(data)
    return asset

def update_asset(asset_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, asset in enumerate(data["assets"]):
        if asset["id"] == asset_id and asset["user_id"] == user_id:
            _apply_update(data["assets"][i], update_data, ASSET_CLEARABLE)
            save_data(data)
            return data["assets"][i]
    return None

def delete_asset(asset_id: str, user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["assets"])
    data["assets"] = [a for a in data["assets"] if not (a["id"] == asset_id and a["user_id"] == user_id)]
    if len(data["assets"]) < initial_length:
        save_data(data)
        return True
    return False

# Liability operations
def get_liabilities_by_user(user_id: str) -> List[Dict]:
    data = load_data()
    return [l for l in data["liabilities"] if l["user_id"] == user_id]

def get_liability_by_id(liability_id: str, user_id: str) -> Optional[Dict]:
    data = load_data()
    for liability in data["liabilities"]:
        if liability["id"] == liability_id and liability["user_id"] == user_id:
            return liability
    return None

def create_liability(user_id: str, liability_data: Dict) -> Dict:
    data = load_data()
    liability = _new_row(user_id, liability_data)
    data["liabilities"].append(liability)
    save_data(data)
    return liability

def update_liability(liability_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, liability in enumerate(data["liabilities"]):
        if liability["id"] == liability_id and liability["user_id"] == user_id:
            _apply_update(data["liabilities"][i], update_data, LIABILITY_CLEARABLE)
            save_data(data)
            return data["liabilities"][i]
    return None

def delete_liability(liability_id: str, user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["liabilities"])
    data["liabilities"] = [l for l in data["liabilities"] if not (l["id"] == liability_id and l["user_id"] == user_id)]
    if len(data["liabilities"]) < initial_length:
        save_data(data)
        return True
    return False

# Snapshot operations
def get_snapshots_by_user(user_id: str, limit: Optional[int] = 30) -> List[Dict]:
    """Newest first; limit=None returns every snapshot"""
    data = load_data()
    snapshots = [s for s in data["snapshots"] if s["user_id"] == user_id]
    snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
    return snapshots if limit is None else snapshots[:limit]

def create_snapshot(user_id: str, total_assets: float, total_liabilities: float,
                    breakdown: Optional[Dict] = None, timestamp: Optional[str] = None) -> Dict:
    data = load_data()
    # The local clock, like the month check in main.py (the other stamps stay UTC)
    snapshot = _new_snapshot_row(user_id, total_assets, total_liabilities, timestamp or datetime.now().isoformat(), breakdown)
    data["snapshots"].append(snapshot)
    save_data(data)
    return snapshot

# Bank Account operations
def get_bank_accounts_by_user(user_id: str) -> List[Dict]:
    data = load_data()
    return [a for a in data["bank_accounts"] if a["user_id"] == user_id]

def get_bank_account_by_id(account_id: str, user_id: str) -> Optional[Dict]:
    data = load_data()
    for account in data["bank_accounts"]:
        if account["id"] == account_id and account["user_id"] == user_id:
            return account
    return None

def create_bank_account(user_id: str, account_data: Dict) -> Dict:
    data = load_data()
    account = _new_row(user_id, account_data)
    data["bank_accounts"].append(account)
    save_data(data)
    return account

def update_bank_account(account_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, account in enumerate(data["bank_accounts"]):
        if account["id"] == account_id and account["user_id"] == user_id:
            _apply_update(data["bank_accounts"][i], update_data, BANK_ACCOUNT_CLEARABLE)
            save_data(data)
            return data["bank_accounts"][i]
    return None

def delete_bank_account(account_id: str, user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["bank_accounts"])
    data["bank_accounts"] = [a for a in data["bank_accounts"] if not (a["id"] == account_id and a["user_id"] == user_id)]
    if len(data["bank_accounts"]) < initial_length:
        save_data(data)
        return True
    return False

# Insurance operations
def get_insurances_by_user(user_id: str) -> List[Dict]:
    data = load_data()
    return [i for i in data["insurances"] if i["user_id"] == user_id]

def get_insurance_by_id(insurance_id: str, user_id: str) -> Optional[Dict]:
    data = load_data()
    for insurance in data["insurances"]:
        if insurance["id"] == insurance_id and insurance["user_id"] == user_id:
            return insurance
    return None

def create_insurance(user_id: str, insurance_data: Dict) -> Dict:
    data = load_data()
    insurance = _new_row(user_id, insurance_data)
    data["insurances"].append(insurance)
    save_data(data)
    return insurance

def update_insurance(insurance_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, insurance in enumerate(data["insurances"]):
        if insurance["id"] == insurance_id and insurance["user_id"] == user_id:
            for key, value in update_data.items():
                if value is not None:
                    data["insurances"][i][key] = value
            data["insurances"][i]["updated_at"] = get_timestamp()
            save_data(data)
            return data["insurances"][i]
    return None

def delete_insurance(insurance_id: str, user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["insurances"])
    data["insurances"] = [i for i in data["insurances"] if not (i["id"] == insurance_id and i["user_id"] == user_id)]
    if len(data["insurances"]) < initial_length:
        save_data(data)
        return True
    return False

# Mutual Fund operations
def get_mutual_funds_by_user(user_id: str) -> List[Dict]:
    data = load_data()
    return [m for m in data["mutual_funds"] if m["user_id"] == user_id]

def get_mutual_fund_by_id(fund_id: str, user_id: str) -> Optional[Dict]:
    data = load_data()
    for fund in data["mutual_funds"]:
        if fund["id"] == fund_id and fund["user_id"] == user_id:
            return fund
    return None

def create_mutual_fund(user_id: str, fund_data: Dict) -> Dict:
    data = load_data()
    fund = _new_row(user_id, fund_data)
    data["mutual_funds"].append(fund)
    save_data(data)
    return fund

def update_mutual_fund(fund_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, fund in enumerate(data["mutual_funds"]):
        if fund["id"] == fund_id and fund["user_id"] == user_id:
            _apply_update(data["mutual_funds"][i], update_data, MUTUAL_FUND_CLEARABLE)
            save_data(data)
            return data["mutual_funds"][i]
    return None

def delete_mutual_fund(fund_id: str, user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["mutual_funds"])
    data["mutual_funds"] = [m for m in data["mutual_funds"] if not (m["id"] == fund_id and m["user_id"] == user_id)]
    if len(data["mutual_funds"]) < initial_length:
        save_data(data)
        return True
    return False

# Equity operations
def get_equities_by_user(user_id: str) -> List[Dict]:
    data = load_data()
    return [e for e in data["equities"] if e["user_id"] == user_id]

def get_equity_by_id(equity_id: str, user_id: str) -> Optional[Dict]:
    data = load_data()
    for equity in data["equities"]:
        if equity["id"] == equity_id and equity["user_id"] == user_id:
            return equity
    return None

def create_equity(user_id: str, equity_data: Dict) -> Dict:
    data = load_data()
    equity = _new_equity_row(user_id, equity_data)
    data["equities"].append(equity)
    save_data(data)
    return equity

def update_equity(equity_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, equity in enumerate(data["equities"]):
        if equity["id"] == equity_id and equity["user_id"] == user_id:
            for key, value in update_data.items():
                if value is not None:
                    data["equities"][i][key] = value
            row = data["equities"][i]
            current_price = row.get("current_price")
            if current_price is None:
                current_price = row["avg_buy_price"]
            row.update(_equity_numbers(row["quantity"], row["avg_buy_price"], current_price))
            row["updated_at"] = get_timestamp()
            save_data(data)
            return data["equities"][i]
    return None

def update_equity_price(equity_id: str, user_id: str, current_price: float) -> Optional[Dict]:
    """Update just the current price and recalculate values"""
    data = load_data()
    for i, equity in enumerate(data["equities"]):
        if equity["id"] == equity_id and equity["user_id"] == user_id:
            data["equities"][i]["current_price"] = current_price
            data["equities"][i].update(_equity_numbers(equity["quantity"], equity["avg_buy_price"], current_price))
            data["equities"][i]["updated_at"] = get_timestamp()
            save_data(data)
            return data["equities"][i]
    return None

def delete_equity(equity_id: str, user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["equities"])
    data["equities"] = [e for e in data["equities"] if not (e["id"] == equity_id and e["user_id"] == user_id)]
    if len(data["equities"]) < initial_length:
        save_data(data)
        return True
    return False

# Goal operations
def get_goal_by_user(user_id: str) -> Optional[Dict]:
    """Get the user's net worth goal (one per user)"""
    data = load_data()
    for goal in data["goals"]:
        if goal["user_id"] == user_id:
            return goal
    return None

def create_or_update_goal(user_id: str, goal_data: Dict) -> Dict:
    """Create or update user's goal"""
    data = load_data()
    
    # Check if goal exists
    for i, goal in enumerate(data["goals"]):
        if goal["user_id"] == user_id:
            # Update existing goal
            for key, value in goal_data.items():
                if value is not None:
                    data["goals"][i][key] = value
            data["goals"][i]["updated_at"] = get_timestamp()
            save_data(data)
            return data["goals"][i]
    
    # Create new goal
    goal = _new_goal_row(user_id, goal_data)
    data["goals"].append(goal)
    save_data(data)
    return goal

def delete_goal(user_id: str) -> bool:
    data = load_data()
    initial_length = len(data["goals"])
    data["goals"] = [g for g in data["goals"] if g["user_id"] != user_id]
    if len(data["goals"]) < initial_length:
        save_data(data)
        return True
    return False

# Restore
def replace_user_data(user_id: str, cleaned: Dict) -> None:
    """Replace all of a user's financial data (items, snapshots, goal) with `cleaned`, in a single save"""
    data = load_data()
    for collection in ("assets", "liabilities", "bank_accounts", "insurances",
                       "mutual_funds", "equities", "snapshots", "goals"):
        data[collection] = [row for row in data[collection] if row["user_id"] != user_id]

    for collection in ("assets", "liabilities", "bank_accounts", "insurances", "mutual_funds"):
        data[collection].extend(_new_row(user_id, item) for item in cleaned[collection])
    data["equities"].extend(_new_equity_row(user_id, item) for item in cleaned["equities"])
    data["snapshots"].extend(
        _new_snapshot_row(user_id, s["total_assets"], s["total_liabilities"], s["timestamp"], s)
        for s in cleaned["snapshots"]
    )
    if cleaned["goal"] is not None:
        data["goals"].append(_new_goal_row(user_id, cleaned["goal"]))
    save_data(data)
