from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import List

from config import settings
from models import (
    UserCreate, User, Token,
    Asset, AssetCreate, AssetUpdate,
    Liability, LiabilityCreate, LiabilityUpdate,
    DashboardMetrics, NetWorthSnapshot,
    BankAccount, BankAccountCreate, BankAccountUpdate,
    Insurance, InsuranceCreate, InsuranceUpdate,
    MutualFund, MutualFundCreate, MutualFundUpdate,
    Equity, EquityCreate, EquityUpdate,
    Goal, GoalCreate, GoalUpdate
)
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user
)
import database as db
import stock_service
import exchange_service
import nav_service

app = FastAPI(
    title="Net Worth Tracker API",
    description="A professional API for tracking personal net worth",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== Auth Routes ==============

@app.post("/api/auth/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Register a new user"""
    existing_user = db.get_user_by_username(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    hashed_password = get_password_hash(user_data.password)
    user = db.create_user(user_data.username, user_data.email, hashed_password)
    
    return User(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        created_at=user["created_at"]
    )

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login and get access token"""
    user = db.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(access_token=access_token, token_type="bearer")

@app.get("/api/auth/me", response_model=User)
async def get_me(username: str = Depends(get_current_user)):
    """Get current user info"""
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return User(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        created_at=user["created_at"]
    )

# ============== Asset Routes ==============

def get_user_id(username: str = Depends(get_current_user)) -> str:
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user["id"]

@app.get("/api/assets", response_model=List[Asset])
async def get_assets(user_id: str = Depends(get_user_id)):
    """Get all assets for current user"""
    return db.get_assets_by_user(user_id)

@app.post("/api/assets", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def create_asset(asset_data: AssetCreate, user_id: str = Depends(get_user_id)):
    """Create a new asset"""
    asset = db.create_asset(user_id, asset_data.model_dump())
    return asset

@app.get("/api/assets/{asset_id}", response_model=Asset)
async def get_asset(asset_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific asset"""
    asset = db.get_asset_by_id(asset_id, user_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@app.put("/api/assets/{asset_id}", response_model=Asset)
async def update_asset(asset_id: str, update_data: AssetUpdate, user_id: str = Depends(get_user_id)):
    """Update an asset"""
    asset = db.update_asset(asset_id, user_id, update_data.model_dump(exclude_unset=True))
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@app.delete("/api/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: str, user_id: str = Depends(get_user_id)):
    """Delete an asset"""
    if not db.delete_asset(asset_id, user_id):
        raise HTTPException(status_code=404, detail="Asset not found")

# ============== Liability Routes ==============

@app.get("/api/liabilities", response_model=List[Liability])
async def get_liabilities(user_id: str = Depends(get_user_id)):
    """Get all liabilities for current user"""
    return db.get_liabilities_by_user(user_id)

@app.post("/api/liabilities", response_model=Liability, status_code=status.HTTP_201_CREATED)
async def create_liability(liability_data: LiabilityCreate, user_id: str = Depends(get_user_id)):
    """Create a new liability"""
    liability = db.create_liability(user_id, liability_data.model_dump())
    return liability

@app.get("/api/liabilities/{liability_id}", response_model=Liability)
async def get_liability(liability_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific liability"""
    liability = db.get_liability_by_id(liability_id, user_id)
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    return liability

@app.put("/api/liabilities/{liability_id}", response_model=Liability)
async def update_liability(liability_id: str, update_data: LiabilityUpdate, user_id: str = Depends(get_user_id)):
    """Update a liability"""
    liability = db.update_liability(liability_id, user_id, update_data.model_dump(exclude_unset=True))
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    return liability

@app.delete("/api/liabilities/{liability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_liability(liability_id: str, user_id: str = Depends(get_user_id)):
    """Delete a liability"""
    if not db.delete_liability(liability_id, user_id):
        raise HTTPException(status_code=404, detail="Liability not found")

# ============== Dashboard & Metrics Routes ==============

@app.get("/api/exchange-rate")
async def get_exchange_rate():
    """Get current USD to INR exchange rate"""
    rate = await exchange_service.fetch_usd_to_inr()
    return {"usd_to_inr": rate}

@app.get("/api/dashboard", response_model=DashboardMetrics)
async def get_dashboard(user_id: str = Depends(get_user_id)):
    """Get dashboard metrics and data"""
    assets = db.get_assets_by_user(user_id)
    liabilities = db.get_liabilities_by_user(user_id)
    snapshots = db.get_snapshots_by_user(user_id)
    equities = db.get_equities_by_user(user_id)
    
    # Get live USD to INR rate
    usd_to_inr = await exchange_service.fetch_usd_to_inr()
    
    total_assets = sum(a["value"] for a in assets)
    # Convert NASDAQ equities from USD to INR
    total_equities = sum(
        e["current_value"] * usd_to_inr if e.get("market") == "NASDAQ" else e["current_value"] 
        for e in equities
    )
    total_assets_with_equities = total_assets + total_equities
    total_liabilities = sum(l["amount"] for l in liabilities)
    net_worth = total_assets_with_equities - total_liabilities
    
    # Calculate debt-to-asset ratio
    debt_to_asset_ratio = (total_liabilities / total_assets_with_equities * 100) if total_assets_with_equities > 0 else 0
    
    # Group assets by category (include equities as a category)
    assets_by_category = {}
    for asset in assets:
        category = asset["category"]
        if category not in assets_by_category:
            assets_by_category[category] = 0
        assets_by_category[category] += asset["value"]
    
    # Add equities as a category if there are any
    if total_equities > 0:
        assets_by_category["equities"] = total_equities
    
    # Group liabilities by category
    liabilities_by_category = {}
    for liability in liabilities:
        category = liability["category"]
        if category not in liabilities_by_category:
            liabilities_by_category[category] = 0
        liabilities_by_category[category] += liability["amount"]
    
    return DashboardMetrics(
        total_assets=total_assets_with_equities,
        total_liabilities=total_liabilities,
        net_worth=net_worth,
        debt_to_asset_ratio=round(debt_to_asset_ratio, 2),
        assets_by_category=assets_by_category,
        liabilities_by_category=liabilities_by_category,
        net_worth_history=snapshots,
        asset_count=len(assets) + len(equities),
        liability_count=len(liabilities)
    )

@app.post("/api/snapshot", response_model=NetWorthSnapshot, status_code=status.HTTP_201_CREATED)
async def create_snapshot(user_id: str = Depends(get_user_id)):
    """Create a net worth snapshot"""
    assets = db.get_assets_by_user(user_id)
    liabilities = db.get_liabilities_by_user(user_id)
    equities = db.get_equities_by_user(user_id)
    
    # Get live USD to INR rate
    usd_to_inr = await exchange_service.fetch_usd_to_inr()
    
    # Convert NASDAQ equities from USD to INR
    total_equities = sum(
        e["current_value"] * usd_to_inr if e.get("market") == "NASDAQ" else e["current_value"] 
        for e in equities
    )
    total_assets = sum(a["value"] for a in assets) + total_equities
    total_liabilities = sum(l["amount"] for l in liabilities)
    
    snapshot = db.create_snapshot(user_id, total_assets, total_liabilities)
    return snapshot

# ============== Bank Account Routes ==============

@app.get("/api/bank-accounts", response_model=List[BankAccount])
async def get_bank_accounts(user_id: str = Depends(get_user_id)):
    """Get all bank accounts for current user"""
    return db.get_bank_accounts_by_user(user_id)

@app.post("/api/bank-accounts", response_model=BankAccount, status_code=status.HTTP_201_CREATED)
async def create_bank_account(account_data: BankAccountCreate, user_id: str = Depends(get_user_id)):
    """Create a new bank account"""
    account = db.create_bank_account(user_id, account_data.model_dump())
    return account

@app.get("/api/bank-accounts/{account_id}", response_model=BankAccount)
async def get_bank_account(account_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific bank account"""
    account = db.get_bank_account_by_id(account_id, user_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return account

@app.put("/api/bank-accounts/{account_id}", response_model=BankAccount)
async def update_bank_account(account_id: str, update_data: BankAccountUpdate, user_id: str = Depends(get_user_id)):
    """Update a bank account"""
    account = db.update_bank_account(account_id, user_id, update_data.model_dump(exclude_unset=True))
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return account

@app.delete("/api/bank-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_account(account_id: str, user_id: str = Depends(get_user_id)):
    """Delete a bank account"""
    if not db.delete_bank_account(account_id, user_id):
        raise HTTPException(status_code=404, detail="Bank account not found")

@app.get("/api/bank-accounts-summary")
async def get_bank_accounts_summary(user_id: str = Depends(get_user_id)):
    """Get total balance from all bank accounts"""
    accounts = db.get_bank_accounts_by_user(user_id)
    total_balance = sum(a["balance"] for a in accounts)
    return {"total_balance": total_balance, "account_count": len(accounts)}

# ============== Insurance Routes ==============

@app.get("/api/insurances", response_model=List[Insurance])
async def get_insurances(user_id: str = Depends(get_user_id)):
    """Get all insurances for current user"""
    return db.get_insurances_by_user(user_id)

@app.post("/api/insurances", response_model=Insurance, status_code=status.HTTP_201_CREATED)
async def create_insurance(insurance_data: InsuranceCreate, user_id: str = Depends(get_user_id)):
    """Create a new insurance"""
    insurance = db.create_insurance(user_id, insurance_data.model_dump())
    return insurance

@app.get("/api/insurances/{insurance_id}", response_model=Insurance)
async def get_insurance(insurance_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific insurance"""
    insurance = db.get_insurance_by_id(insurance_id, user_id)
    if not insurance:
        raise HTTPException(status_code=404, detail="Insurance not found")
    return insurance

@app.put("/api/insurances/{insurance_id}", response_model=Insurance)
async def update_insurance(insurance_id: str, update_data: InsuranceUpdate, user_id: str = Depends(get_user_id)):
    """Update an insurance"""
    insurance = db.update_insurance(insurance_id, user_id, update_data.model_dump(exclude_unset=True))
    if not insurance:
        raise HTTPException(status_code=404, detail="Insurance not found")
    return insurance

@app.delete("/api/insurances/{insurance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_insurance(insurance_id: str, user_id: str = Depends(get_user_id)):
    """Delete an insurance"""
    if not db.delete_insurance(insurance_id, user_id):
        raise HTTPException(status_code=404, detail="Insurance not found")

@app.get("/api/insurances-summary")
async def get_insurances_summary(user_id: str = Depends(get_user_id)):
    """Get insurance summary"""
    insurances = db.get_insurances_by_user(user_id)
    total_sum_assured = sum(i["sum_assured"] for i in insurances)
    total_premium = sum(i["premium"] for i in insurances)
    return {"total_sum_assured": total_sum_assured, "total_premium": total_premium, "policy_count": len(insurances)}

# ============== Mutual Fund Routes ==============

async def _process_mutual_fund_data(fund_dict: dict) -> dict:
    """Process mutual fund data: fetch NAV if needed, calculate avg_nav and current_value"""
    # Try to fetch current NAV if not provided
    if not fund_dict.get("current_nav") and fund_dict.get("fund_name"):
        nav_info = await nav_service.fetch_nav_by_fund_name(fund_dict["fund_name"])
        if nav_info:
            fund_dict["current_nav"] = nav_info["nav"]
            if not fund_dict.get("scheme_code"):
                fund_dict["scheme_code"] = nav_info.get("scheme_code")
    
    # Calculate avg_nav = invested_amount / units
    units = fund_dict.get("units", 0)
    invested_amount = fund_dict.get("invested_amount", 0)
    if units > 0 and invested_amount > 0:
        fund_dict["avg_nav"] = round(invested_amount / units, 4)
    else:
        fund_dict["avg_nav"] = 0
    
    # Calculate current_value if not provided
    current_nav = fund_dict.get("current_nav")
    avg_nav = fund_dict.get("avg_nav", 0)
    
    if not fund_dict.get("current_value") or fund_dict.get("current_value") == 0:
        if current_nav and units:
            fund_dict["current_value"] = round(units * current_nav, 2)
        elif avg_nav and units:
            # Fallback to avg_nav if current_nav not available
            fund_dict["current_value"] = round(units * avg_nav, 2)
        else:
            # Default to invested_amount if no NAV data
            fund_dict["current_value"] = fund_dict.get("invested_amount", 0)
    
    return fund_dict

@app.get("/api/mutual-funds", response_model=List[MutualFund])
async def get_mutual_funds(user_id: str = Depends(get_user_id), refresh_nav: bool = False):
    """Get all mutual funds for current user. Set refresh_nav=true to fetch latest NAV."""
    funds = db.get_mutual_funds_by_user(user_id)
    
    if refresh_nav and funds:
        for fund in funds:
            nav_info = await nav_service.fetch_nav_by_fund_name(fund["fund_name"])
            if nav_info:
                units = fund.get("units", 0)
                fund["current_nav"] = nav_info["nav"]
                fund["scheme_code"] = nav_info.get("scheme_code")
                if units > 0:
                    fund["current_value"] = round(units * nav_info["nav"], 2)
                # Update in database
                db.update_mutual_fund(fund["id"], fund["user_id"], {
                    "current_nav": fund["current_nav"],
                    "current_value": fund["current_value"],
                    "scheme_code": fund.get("scheme_code")
                })
    
    return funds

@app.post("/api/mutual-funds", response_model=MutualFund, status_code=status.HTTP_201_CREATED)
async def create_mutual_fund(fund_data: MutualFundCreate, user_id: str = Depends(get_user_id)):
    """Create a new mutual fund"""
    fund_dict = fund_data.model_dump()
    fund_dict = await _process_mutual_fund_data(fund_dict)
    fund = db.create_mutual_fund(user_id, fund_dict)
    return fund

@app.get("/api/mutual-funds/{fund_id}", response_model=MutualFund)
async def get_mutual_fund(fund_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific mutual fund"""
    fund = db.get_mutual_fund_by_id(fund_id, user_id)
    if not fund:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    return fund

@app.put("/api/mutual-funds/{fund_id}", response_model=MutualFund)
async def update_mutual_fund(fund_id: str, update_data: MutualFundUpdate, user_id: str = Depends(get_user_id)):
    """Update a mutual fund"""
    update_dict = update_data.model_dump(exclude_unset=True)
    
    # If fund_name is being updated or current_nav is not set, try to fetch NAV
    existing_fund = db.get_mutual_fund_by_id(fund_id, user_id)
    if existing_fund:
        merged = {**existing_fund, **update_dict}
        update_dict = await _process_mutual_fund_data(merged)
    
    fund = db.update_mutual_fund(fund_id, user_id, update_dict)
    if not fund:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    return fund

@app.delete("/api/mutual-funds/{fund_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mutual_fund(fund_id: str, user_id: str = Depends(get_user_id)):
    """Delete a mutual fund"""
    if not db.delete_mutual_fund(fund_id, user_id):
        raise HTTPException(status_code=404, detail="Mutual fund not found")

@app.get("/api/mutual-funds-summary")
async def get_mutual_funds_summary(user_id: str = Depends(get_user_id)):
    """Get mutual fund summary"""
    funds = db.get_mutual_funds_by_user(user_id)
    total_invested = sum(f["invested_amount"] for f in funds)
    total_current = sum(f.get("current_value") or 0 for f in funds)
    total_gain = total_current - total_invested
    return {
        "total_invested": total_invested, 
        "total_current_value": total_current, 
        "total_gain": total_gain,
        "fund_count": len(funds)
    }

@app.post("/api/mutual-funds/{fund_id}/refresh-nav")
async def refresh_fund_nav(fund_id: str, user_id: str = Depends(get_user_id)):
    """Refresh NAV for a specific mutual fund"""
    fund = db.get_mutual_fund_by_id(fund_id, user_id)
    if not fund:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    
    nav_info = await nav_service.fetch_nav_by_fund_name(fund["fund_name"])
    if nav_info:
        units = fund.get("units", 0)
        update_data = {
            "current_nav": nav_info["nav"],
            "scheme_code": nav_info.get("scheme_code"),
            "current_value": round(units * nav_info["nav"], 2) if units > 0 else fund.get("current_value", 0)
        }
        updated_fund = db.update_mutual_fund(fund_id, user_id, update_data)
        return {"status": "success", "nav": nav_info["nav"], "date": nav_info["date"], "fund": updated_fund}
    
    return {"status": "error", "message": "Could not fetch NAV for this fund"}

@app.get("/api/nav/search")
async def search_nav(q: str):
    """Search for mutual funds by name to get scheme codes"""
    results = await nav_service.search_mutual_fund(q)
    return results

@app.get("/api/nav/test")
async def test_nav_service():
    """Test if NAV service is working"""
    return await nav_service.test_nav_service()

# ============== Equity Routes ==============

@app.get("/api/equities", response_model=List[Equity])
async def get_equities(user_id: str = Depends(get_user_id), refresh_prices: bool = False):
    """Get all equities for current user. Set refresh_prices=true to fetch live prices."""
    equities = db.get_equities_by_user(user_id)
    
    if refresh_prices and equities:
        for equity in equities:
            price_info = stock_service.fetch_stock_price(equity["symbol"], equity["market"])
            if price_info and price_info.get("current_price"):
                db.update_equity_price(equity["id"], user_id, price_info["current_price"])
        # Reload after price updates
        equities = db.get_equities_by_user(user_id)
    
    return equities

@app.post("/api/equities", response_model=Equity, status_code=status.HTTP_201_CREATED)
async def create_equity(equity_data: EquityCreate, user_id: str = Depends(get_user_id)):
    """Create a new equity holding"""
    # Try to fetch current price
    price_info = stock_service.fetch_stock_price(equity_data.symbol, equity_data.market.value)
    
    data = equity_data.model_dump()
    if price_info:
        data["current_price"] = price_info.get("current_price", equity_data.avg_buy_price)
        if not data.get("company_name") and price_info.get("company_name"):
            data["company_name"] = price_info["company_name"]
    else:
        data["current_price"] = equity_data.avg_buy_price
    
    equity = db.create_equity(user_id, data)
    return equity

@app.get("/api/equities/{equity_id}", response_model=Equity)
async def get_equity(equity_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific equity holding"""
    equity = db.get_equity_by_id(equity_id, user_id)
    if not equity:
        raise HTTPException(status_code=404, detail="Equity not found")
    return equity

@app.put("/api/equities/{equity_id}", response_model=Equity)
async def update_equity(equity_id: str, update_data: EquityUpdate, user_id: str = Depends(get_user_id)):
    """Update an equity holding"""
    equity = db.update_equity(equity_id, user_id, update_data.model_dump(exclude_unset=True))
    if not equity:
        raise HTTPException(status_code=404, detail="Equity not found")
    return equity

@app.delete("/api/equities/{equity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equity(equity_id: str, user_id: str = Depends(get_user_id)):
    """Delete an equity holding"""
    if not db.delete_equity(equity_id, user_id):
        raise HTTPException(status_code=404, detail="Equity not found")

@app.post("/api/equities/{equity_id}/refresh-price", response_model=Equity)
async def refresh_equity_price(equity_id: str, user_id: str = Depends(get_user_id)):
    """Refresh price for a specific equity"""
    equity = db.get_equity_by_id(equity_id, user_id)
    if not equity:
        raise HTTPException(status_code=404, detail="Equity not found")
    
    price_info = stock_service.fetch_stock_price(equity["symbol"], equity["market"])
    if price_info and price_info.get("current_price"):
        equity = db.update_equity_price(equity_id, user_id, price_info["current_price"])
    
    return equity

@app.get("/api/equities-summary")
async def get_equities_summary(user_id: str = Depends(get_user_id)):
    """Get equities summary"""
    equities = db.get_equities_by_user(user_id)
    total_invested = sum(e["invested_amount"] for e in equities)
    total_current = sum(e["current_value"] for e in equities)
    total_gain = total_current - total_invested
    return {
        "total_invested": total_invested, 
        "total_current_value": total_current, 
        "total_gain": total_gain,
        "gain_percent": (total_gain / total_invested * 100) if total_invested > 0 else 0,
        "holding_count": len(equities)
    }

@app.get("/api/stock-price/{market}/{symbol}")
async def get_stock_price(market: str, symbol: str):
    """Get live stock price for a symbol"""
    price_info = stock_service.fetch_stock_price(symbol, market)
    if not price_info:
        raise HTTPException(status_code=404, detail=f"Could not fetch price for {symbol} on {market}")
    return price_info

# ============== Goal Routes ==============

@app.get("/api/goal", response_model=Goal)
async def get_goal(user_id: str = Depends(get_user_id)):
    """Get user's net worth goal"""
    goal = db.get_goal_by_user(user_id)
    if not goal:
        # Return default goal if none exists
        goal = db.create_or_update_goal(user_id, {"target_amount": 100000000, "name": "Net Worth Goal"})
    return goal

@app.post("/api/goal", response_model=Goal)
async def create_or_update_goal(goal_data: GoalCreate, user_id: str = Depends(get_user_id)):
    """Create or update user's net worth goal"""
    goal = db.create_or_update_goal(user_id, goal_data.model_dump())
    return goal

@app.put("/api/goal", response_model=Goal)
async def update_goal(goal_data: GoalUpdate, user_id: str = Depends(get_user_id)):
    """Update user's net worth goal"""
    goal = db.create_or_update_goal(user_id, goal_data.model_dump(exclude_unset=True))
    return goal

@app.delete("/api/goal", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(user_id: str = Depends(get_user_id)):
    """Delete user's net worth goal"""
    db.delete_goal(user_id)

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "networth-tracker-api"}

# Startup event to create demo data
@app.on_event("startup")
async def startup_event():
    """Create demo user and sample data on startup"""
    from auth import get_password_hash
    
    # Check if demo user exists
    demo_user = db.get_user_by_username("demo")
    if not demo_user:
        # Create demo user
        hashed_password = get_password_hash("password123")
        demo_user = db.create_user("demo", "demo@example.com", hashed_password)
        
        user_id = demo_user["id"]
        
        # Add sample assets - all categories
        sample_assets = [
            {"name": "Emergency Fund", "category": "cash", "value": 300000, "notes": "HDFC Savings account"},
            {"name": "Cash at Home", "category": "cash", "value": 50000, "notes": "Petty cash and emergency"},
            {"name": "Direct Equity Portfolio", "category": "investments", "value": 450000, "notes": "Stocks in Zerodha - TCS, Infosys, HDFC Bank"},
            {"name": "PPF Account", "category": "investments", "value": 850000, "notes": "SBI PPF - 10 years maturity"},
            {"name": "Primary Residence", "category": "real_estate", "value": 8500000, "notes": "3BHK Apartment in Bangalore"},
            {"name": "Agricultural Land", "category": "real_estate", "value": 2500000, "notes": "2 acres in native village"},
            {"name": "Honda City", "category": "vehicles", "value": 1200000, "notes": "2022 Model - ZX CVT"},
            {"name": "Royal Enfield Classic 350", "category": "vehicles", "value": 180000, "notes": "2021 Model"},
            {"name": "EPF Balance", "category": "retirement", "value": 1200000, "notes": "Employee Provident Fund"},
            {"name": "NPS Account", "category": "retirement", "value": 350000, "notes": "National Pension Scheme"},
            {"name": "Bitcoin Holdings", "category": "crypto", "value": 150000, "notes": "0.05 BTC on WazirX"},
            {"name": "Ethereum Holdings", "category": "crypto", "value": 75000, "notes": "0.5 ETH"},
            {"name": "Gold Jewelry", "category": "other", "value": 500000, "notes": "Family gold - 50 grams"},
            {"name": "MacBook Pro", "category": "other", "value": 180000, "notes": "M2 Pro - Work laptop"},
        ]
        for asset in sample_assets:
            db.create_asset(user_id, asset)
        
        # Add sample liabilities - all categories
        sample_liabilities = [
            {"name": "Home Loan - SBI", "category": "mortgage", "amount": 5000000, "interest_rate": 8.5, "notes": "15 years tenure, EMI ₹52,000"},
            {"name": "Car Loan - HDFC", "category": "car_loan", "amount": 600000, "interest_rate": 9.0, "notes": "5 years tenure, EMI ₹12,500"},
            {"name": "Education Loan - Axis", "category": "student_loan", "amount": 800000, "interest_rate": 10.5, "notes": "MBA loan - 7 years"},
            {"name": "HDFC Credit Card", "category": "credit_card", "amount": 45000, "interest_rate": 18.0, "notes": "Monthly expenses"},
            {"name": "Amazon Pay ICICI", "category": "credit_card", "amount": 28000, "interest_rate": 18.0, "notes": "Shopping dues"},
            {"name": "Personal Loan - Bajaj", "category": "personal_loan", "amount": 150000, "interest_rate": 14.0, "notes": "Home renovation - 2 years"},
            {"name": "Family Loan", "category": "other", "amount": 200000, "interest_rate": 0.0, "notes": "Borrowed from parents - no interest"},
        ]
        for liability in sample_liabilities:
            db.create_liability(user_id, liability)
    else:
        user_id = demo_user["id"]
    
    # Add sample bank accounts if none exist
    existing_accounts = db.get_bank_accounts_by_user(user_id)
    if not existing_accounts:
        sample_bank_accounts = [
            {"bank_name": "HDFC Bank", "account_number": "50100123456789", "account_type": "savings", "balance": 250000, "branch": "Koramangala Branch", "ifsc_code": "HDFC0001234"},
            {"bank_name": "SBI", "account_number": "38756432198", "account_type": "salary", "balance": 85000, "branch": "Indiranagar Branch", "ifsc_code": "SBIN0005678"},
            {"bank_name": "ICICI Bank", "account_number": "123456789012", "account_type": "current", "balance": 150000, "branch": "MG Road Branch", "ifsc_code": "ICIC0001234"},
            {"bank_name": "Axis Bank", "account_number": "918020012345678", "account_type": "fd", "balance": 500000, "branch": "HSR Layout", "ifsc_code": "UTIB0001234"},
        ]
        for account in sample_bank_accounts:
            db.create_bank_account(user_id, account)
    
    # Add sample insurances if none exist
    existing_insurances = db.get_insurances_by_user(user_id)
    if not existing_insurances:
        sample_insurances = [
            {"policy_name": "LIC Jeevan Anand", "insurance_type": "life", "provider": "LIC", "policy_number": "414253689", "premium": 48000, "sum_assured": 2500000, "start_date": "2020-04-01", "end_date": "2040-04-01", "notes": "Endowment policy"},
            {"policy_name": "HDFC Ergo Health", "insurance_type": "health", "provider": "HDFC Ergo", "policy_number": "HE123456", "premium": 25000, "sum_assured": 1000000, "start_date": "2024-01-15", "end_date": "2025-01-14", "notes": "Family floater - 4 members"},
            {"policy_name": "ICICI Lombard Motor", "insurance_type": "vehicle", "provider": "ICICI Lombard", "policy_number": "MOT789456", "premium": 15000, "sum_assured": 1200000, "start_date": "2024-03-01", "end_date": "2025-02-28", "notes": "Comprehensive cover"},
            {"policy_name": "HDFC Click 2 Protect", "insurance_type": "term", "provider": "HDFC Life", "policy_number": "TRM456789", "premium": 12000, "sum_assured": 10000000, "start_date": "2022-06-01", "end_date": "2052-06-01", "notes": "Term plan - 30 years"},
        ]
        for insurance in sample_insurances:
            db.create_insurance(user_id, insurance)
    
    # Add sample mutual funds if none exist
    existing_funds = db.get_mutual_funds_by_user(user_id)
    if not existing_funds:
        sample_mutual_funds = [
            {"fund_name": "SBI Bluechip Fund", "amc": "SBI Mutual Fund", "category": "equity", "invested_amount": 200000, "current_value": 245000, "units": 1250.50, "nav": 195.92, "folio_number": "12345678/90"},
            {"fund_name": "HDFC Mid-Cap Opportunities", "amc": "HDFC Mutual Fund", "category": "equity", "invested_amount": 150000, "current_value": 178500, "units": 980.25, "nav": 182.10, "folio_number": "98765432/10"},
            {"fund_name": "ICICI Pru Balanced Advantage", "amc": "ICICI Prudential", "category": "hybrid", "invested_amount": 100000, "current_value": 112000, "units": 1520.80, "nav": 73.65, "folio_number": "45678912/34"},
            {"fund_name": "Axis Long Term Equity (ELSS)", "amc": "Axis Mutual Fund", "category": "elss", "invested_amount": 150000, "current_value": 168000, "units": 2100.00, "nav": 80.00, "folio_number": "78912345/67"},
            {"fund_name": "Nippon India Liquid Fund", "amc": "Nippon India", "category": "liquid", "invested_amount": 100000, "current_value": 102500, "units": 19.85, "nav": 5163.22, "folio_number": "65432198/76"},
            {"fund_name": "UTI Nifty Index Fund", "amc": "UTI Mutual Fund", "category": "index", "invested_amount": 80000, "current_value": 92000, "units": 650.00, "nav": 141.54, "folio_number": "32165498/78"},
        ]
        for fund in sample_mutual_funds:
            db.create_mutual_fund(user_id, fund)
    
    # Add sample equities if none exist
    existing_equities = db.get_equities_by_user(user_id)
    if not existing_equities:
        sample_equities = [
            {"symbol": "TCS", "company_name": "Tata Consultancy Services", "market": "NSE", "quantity": 50, "avg_buy_price": 3200, "current_price": 3850, "notes": "IT sector - long term"},
            {"symbol": "INFY", "company_name": "Infosys Limited", "market": "NSE", "quantity": 100, "avg_buy_price": 1400, "current_price": 1580, "notes": "IT sector"},
            {"symbol": "HDFCBANK", "company_name": "HDFC Bank Limited", "market": "NSE", "quantity": 75, "avg_buy_price": 1550, "current_price": 1680, "notes": "Banking sector"},
            {"symbol": "RELIANCE", "company_name": "Reliance Industries", "market": "NSE", "quantity": 40, "avg_buy_price": 2400, "current_price": 2750, "notes": "Diversified"},
            {"symbol": "TATAMOTORS", "company_name": "Tata Motors", "market": "BSE", "quantity": 200, "avg_buy_price": 620, "current_price": 780, "notes": "Auto sector"},
            {"symbol": "AAPL", "company_name": "Apple Inc.", "market": "NASDAQ", "quantity": 10, "avg_buy_price": 150, "current_price": 185, "notes": "US Tech - USD"},
        ]
        for equity in sample_equities:
            db.create_equity(user_id, equity)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
