import json
import os
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
    """Save data to JSON file"""
    data_file = get_data_file_path()
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2)

def generate_id() -> str:
    """Generate unique ID"""
    return str(uuid.uuid4())

def get_timestamp() -> str:
    """Get current timestamp as ISO string"""
    return datetime.utcnow().isoformat()

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
    asset = {
        "id": generate_id(),
        "user_id": user_id,
        **asset_data,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    data["assets"].append(asset)
    save_data(data)
    return asset

def update_asset(asset_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, asset in enumerate(data["assets"]):
        if asset["id"] == asset_id and asset["user_id"] == user_id:
            for key, value in update_data.items():
                if value is not None:
                    data["assets"][i][key] = value
            data["assets"][i]["updated_at"] = get_timestamp()
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
    liability = {
        "id": generate_id(),
        "user_id": user_id,
        **liability_data,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    data["liabilities"].append(liability)
    save_data(data)
    return liability

def update_liability(liability_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, liability in enumerate(data["liabilities"]):
        if liability["id"] == liability_id and liability["user_id"] == user_id:
            for key, value in update_data.items():
                if value is not None:
                    data["liabilities"][i][key] = value
            data["liabilities"][i]["updated_at"] = get_timestamp()
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
def get_snapshots_by_user(user_id: str, limit: int = 30) -> List[Dict]:
    data = load_data()
    snapshots = [s for s in data["snapshots"] if s["user_id"] == user_id]
    snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
    return snapshots[:limit]

def create_snapshot(user_id: str, total_assets: float, total_liabilities: float) -> Dict:
    data = load_data()
    snapshot = {
        "id": generate_id(),
        "user_id": user_id,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "timestamp": get_timestamp()
    }
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
    account = {
        "id": generate_id(),
        "user_id": user_id,
        **account_data,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    data["bank_accounts"].append(account)
    save_data(data)
    return account

def update_bank_account(account_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, account in enumerate(data["bank_accounts"]):
        if account["id"] == account_id and account["user_id"] == user_id:
            for key, value in update_data.items():
                if value is not None:
                    data["bank_accounts"][i][key] = value
            data["bank_accounts"][i]["updated_at"] = get_timestamp()
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
    insurance = {
        "id": generate_id(),
        "user_id": user_id,
        **insurance_data,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
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
    fund = {
        "id": generate_id(),
        "user_id": user_id,
        **fund_data,
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
    data["mutual_funds"].append(fund)
    save_data(data)
    return fund

def update_mutual_fund(fund_id: str, user_id: str, update_data: Dict) -> Optional[Dict]:
    data = load_data()
    for i, fund in enumerate(data["mutual_funds"]):
        if fund["id"] == fund_id and fund["user_id"] == user_id:
            for key, value in update_data.items():
                if value is not None:
                    data["mutual_funds"][i][key] = value
            data["mutual_funds"][i]["updated_at"] = get_timestamp()
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
    invested = equity_data["quantity"] * equity_data["avg_buy_price"]
    current_price = equity_data.get("current_price", equity_data["avg_buy_price"])
    current_value = equity_data["quantity"] * current_price
    gain_loss = current_value - invested
    gain_loss_percent = (gain_loss / invested * 100) if invested > 0 else 0
    
    equity = {
        "id": generate_id(),
        "user_id": user_id,
        "symbol": equity_data["symbol"].upper(),
        "company_name": equity_data.get("company_name"),
        "market": equity_data["market"],
        "quantity": equity_data["quantity"],
        "avg_buy_price": equity_data["avg_buy_price"],
        "current_price": current_price,
        "invested_amount": invested,
        "current_value": current_value,
        "gain_loss": gain_loss,
        "gain_loss_percent": gain_loss_percent,
        "notes": equity_data.get("notes"),
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
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
            # Recalculate values
            qty = data["equities"][i]["quantity"]
            avg_price = data["equities"][i]["avg_buy_price"]
            current_price = data["equities"][i].get("current_price", avg_price)
            invested = qty * avg_price
            current_value = qty * current_price
            data["equities"][i]["invested_amount"] = invested
            data["equities"][i]["current_value"] = current_value
            data["equities"][i]["gain_loss"] = current_value - invested
            data["equities"][i]["gain_loss_percent"] = ((current_value - invested) / invested * 100) if invested > 0 else 0
            data["equities"][i]["updated_at"] = get_timestamp()
            save_data(data)
            return data["equities"][i]
    return None

def update_equity_price(equity_id: str, user_id: str, current_price: float) -> Optional[Dict]:
    """Update just the current price and recalculate values"""
    data = load_data()
    for i, equity in enumerate(data["equities"]):
        if equity["id"] == equity_id and equity["user_id"] == user_id:
            qty = equity["quantity"]
            avg_price = equity["avg_buy_price"]
            invested = qty * avg_price
            current_value = qty * current_price
            data["equities"][i]["current_price"] = current_price
            data["equities"][i]["current_value"] = current_value
            data["equities"][i]["gain_loss"] = current_value - invested
            data["equities"][i]["gain_loss_percent"] = ((current_value - invested) / invested * 100) if invested > 0 else 0
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
    goal = {
        "id": generate_id(),
        "user_id": user_id,
        "target_amount": goal_data.get("target_amount", 100000000),  # Default 10 crore
        "name": goal_data.get("name", "Net Worth Goal"),
        "created_at": get_timestamp(),
        "updated_at": get_timestamp()
    }
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
