from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from datetime import date, datetime, timedelta, timezone
import logging
import secrets
from typing import List, Optional, Tuple

from config import settings
from models import (
    UserCreate, User, Token, MfaLoginRequest,
    TwoFactorEnable, TwoFactorDisable, TwoFactorStatus, TwoFactorSetup, TwoFactorBackupCodes, PasswordChange,
    Asset, AssetCreate, AssetUpdate, NpsSchemeOption,
    Liability, LiabilityCreate, LiabilityUpdate,
    DashboardMetrics, NetWorthSnapshot, SnapshotSettings, SnapshotSettingsView,
    BankAccount, BankAccountCreate, BankAccountUpdate,
    Insurance, InsuranceCreate, InsuranceUpdate,
    MutualFund, MutualFundCreate, MutualFundUpdate,
    Equity, EquityCreate, EquityUpdate,
    Goal, GoalCreate, GoalUpdate,
    USD_MARKETS, MAX_AMOUNT
)
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, create_mfa_token, decode_mfa_token, token_version_of
)
import database as db
import two_factor
import stock_service
import exchange_service
import nav_service
import nps_service
import restore
import user_warnings
import valuation

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Net Worth Tracker API",
    description="A professional API for tracking personal net worth",
    version="1.0.0"
)

# Middleware order: the one added last is outermost. The warnings middleware is added first so that the CORS
# middleware below wraps it and its responses still carry the CORS headers (incl. Access-Control-Expose-Headers).
@app.middleware("http")
async def send_user_warnings(request, call_next):
    """Warnings collected while handling the request (e.g. an unreachable NAV source) go back in X-Warnings."""
    token = user_warnings.start()
    try:
        response = await call_next(request)
        found = user_warnings.collected()
        if found:
            response.headers["X-Warnings"] = user_warnings.header_value(found)  # ASCII JSON, within a byte budget
        return response
    finally:
        user_warnings.stop(token)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Warnings"],
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

def _now() -> datetime:
    """Naive UTC; patched in tests."""
    return datetime.utcnow()

def _access_token_for(user: dict) -> Token:
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"], "ver": token_version_of(user)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return Token(access_token=access_token, token_type="bearer")

def _too_many_attempts(user: dict, now: datetime) -> HTTPException:
    minutes = two_factor.lock_minutes_remaining(user, now)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many attempts. Try again in {minutes} minutes."
    )

@app.post("/api/auth/login", response_model=Token, response_model_exclude_none=True)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login and get an access token, or a 2FA challenge token if 2FA is enabled"""
    user = db.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.get("totp_enabled"):
        return Token(
            token_type="mfa",
            mfa_required=True,
            mfa_token=create_mfa_token(user["username"], user["id"], token_version_of(user))
        )

    return _access_token_for(user)

@app.post("/api/auth/login/2fa", response_model=Token, response_model_exclude_none=True)
async def login_2fa(request: MfaLoginRequest):
    """Complete a 2FA login with an authenticator or backup code"""
    payload = decode_mfa_token(request.mfa_token)
    user = db.get_user_by_id(payload["user_id"]) if payload else None
    if not user or not user.get("totp_enabled") or payload.get("ver", 0) != token_version_of(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired login session"
        )

    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)

    ok, updates = two_factor.verify_second_factor(user, request.code, now)
    db.update_user(user["id"], updates)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication code"
        )

    return _access_token_for(user)

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

# ============== Two-Factor Auth Routes ==============
# Wrong passwords/codes here return 400, not 401: the frontend treats a 401 as an expired session.

def get_current_user_record(username: str = Depends(get_current_user)) -> dict:
    # Sync dependency: FastAPI runs it in a worker thread BEFORE the async route body, so concurrent
    # requests can all receive the same stale record. Routes that read-modify-write the user
    # re-read it as their first statement.
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/api/auth/2fa/status", response_model=TwoFactorStatus)
async def two_factor_status(user: dict = Depends(get_current_user_record)):
    """Whether 2FA is enabled and how many backup codes remain"""
    return TwoFactorStatus(
        enabled=bool(user.get("totp_enabled")),
        backup_codes_remaining=len(user.get("backup_code_hashes") or [])
    )

@app.post("/api/auth/2fa/setup", response_model=TwoFactorSetup)
async def two_factor_setup(user: dict = Depends(get_current_user_record)):
    """Start enrollment: issue a pending secret for the authenticator app"""
    user = db.get_user_by_id(user["id"])  # fresh copy: no await between this read and the write below
    if user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled")
    secret = two_factor.generate_secret()
    db.update_user(user["id"], {"totp_pending_secret": secret})
    return TwoFactorSetup(secret=secret, otpauth_uri=two_factor.provisioning_uri(secret, user["username"]))

@app.post("/api/auth/2fa/enable", response_model=TwoFactorBackupCodes)
async def two_factor_enable(request: TwoFactorEnable, user: dict = Depends(get_current_user_record)):
    """Confirm enrollment with the password and a code; returns backup codes (shown only this once)"""
    user = db.get_user_by_id(user["id"])  # fresh copy: no await between this read and the write below
    if user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled")
    pending = user.get("totp_pending_secret")
    if not pending:
        raise HTTPException(status_code=400, detail="Start setup first")
    # The password stops a stolen session from enrolling its own authenticator and locking the owner out.
    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)
    if not verify_password(request.password, user["hashed_password"]):
        db.update_user(user["id"], two_factor.record_failure(user, now))
        raise HTTPException(status_code=400, detail="Incorrect password")
    step = two_factor.verify_totp(pending, request.code, None, now)
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid authentication code")

    codes = two_factor.generate_backup_codes()
    db.update_user(user["id"], {
        **two_factor.DISABLED_FIELDS,
        "totp_enabled": True,
        "totp_secret": pending,
        "totp_last_used_step": step,
        "backup_code_hashes": [two_factor.hash_backup_code(c) for c in codes],
    })
    return TwoFactorBackupCodes(backup_codes=codes)

@app.post("/api/auth/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def two_factor_disable(request: TwoFactorDisable, user: dict = Depends(get_current_user_record)):
    """Turn off 2FA; requires the password and a current authenticator or backup code"""
    user = db.get_user_by_id(user["id"])  # fresh copy: lockout counters must not be stale under concurrent requests
    if not user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled")
    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)
    if not verify_password(request.password, user["hashed_password"]):
        db.update_user(user["id"], two_factor.record_failure(user, now))
        raise HTTPException(status_code=400, detail="Incorrect password")

    ok, updates = two_factor.verify_second_factor(user, request.code, now)
    if not ok:
        db.update_user(user["id"], updates)
        raise HTTPException(status_code=400, detail="Invalid authentication code")

    db.update_user(user["id"], two_factor.DISABLED_FIELDS)

# ============== Password Routes ==============

@app.post("/api/auth/password", response_model=Token, response_model_exclude_none=True)
async def change_password(request: PasswordChange, user: dict = Depends(get_current_user_record)):
    """Change the current user's password; signs out every other session"""
    user = db.get_user_by_id(user["id"])  # fresh copy: lockout counters must not be stale under concurrent requests
    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)
    if not verify_password(request.current_password, user["hashed_password"]):
        db.update_user(user["id"], two_factor.record_failure(user, now))
        raise HTTPException(status_code=400, detail="Incorrect password")
    # Checked before the 2FA step so a backup code is never spent on a change that would fail anyway.
    if verify_password(request.new_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    second_factor_updates = {}
    if user.get("totp_enabled"):
        if not request.code:
            raise HTTPException(status_code=400, detail="Authentication code required")
        ok, second_factor_updates = two_factor.verify_second_factor(user, request.code, now)
        if not ok:
            db.update_user(user["id"], second_factor_updates)
            raise HTTPException(status_code=400, detail="Invalid authentication code")

    # Bumping token_version revokes every token issued before this change, including this request's.
    updated = db.update_user(user["id"], {
        **second_factor_updates,
        "hashed_password": get_password_hash(request.new_password),
        "token_version": token_version_of(user) + 1,
        "totp_failed_attempts": 0,
        "totp_locked_until": None,
    })
    return _access_token_for(updated)

# ============== Warnings for failed sources ==============
# A price or NAV that can't be fetched is reported to the user (the X-Warnings header, see user_warnings) while the
# app carries on with what it already knows. Only a fetch that was tried and failed warns, never cached data.

def _listed(names: List[str], limit: int = 5) -> str:
    """Names for a warning, capped so one message stays short enough to read."""
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")


def _warn_stock_price(symbol: str) -> None:
    user_warnings.warn(f"Couldn't fetch the price of {symbol}; its value uses the last known price.")


def _warn_stock_prices(symbols: List[str]) -> None:
    """One warning for a refresh that missed several holdings"""
    symbols = list(dict.fromkeys(symbols))
    if len(symbols) == 1:
        _warn_stock_price(symbols[0])
    elif symbols:
        user_warnings.warn(f"Couldn't fetch the prices of {len(symbols)} stocks: {_listed(symbols)}. "
                           "Their values use the last known prices.")


def _warn_funds_not_refreshed(names: List[str]) -> None:
    """One warning for a list refresh that missed several funds"""
    names = list(dict.fromkeys(names))
    if names:
        many = len(names) > 1
        user_warnings.warn(f"Couldn't refresh the NAV for {len(names)} {'funds' if many else 'fund'} from mfapi.in: "
                           f"{_listed(names)}. {'Their values use' if many else 'Its value uses'} the last fetched NAV.")


def _warn_sip_not_priced(name: str) -> None:
    user_warnings.warn(f"Couldn't price the SIP installments of {name} with NAVs from mfapi.in; "
                       "they count at cost until a refresh works.")


def _warn_sips_not_priced(names: List[str]) -> None:
    """One warning for a list refresh that couldn't price several SIPs"""
    names = list(dict.fromkeys(names))
    if len(names) == 1:
        _warn_sip_not_priced(names[0])
    elif names:
        user_warnings.warn(f"Couldn't price the SIP installments of {len(names)} funds with NAVs from mfapi.in: "
                           f"{_listed(names)}. They count at cost until a refresh works.")


def _warn_if_rate_not_live() -> None:
    """Call right after fetching the USD→INR rate: warns when it was a stale cached rate or the fallback."""
    if not exchange_service.last_rate_was_live():
        user_warnings.warn("Couldn't fetch the USD→INR rate; US stock values use the last known rate.")


async def _usd_rate_if_needed(equities: List[dict]) -> Optional[float]:
    """valuation.usd_rate_if_needed, which warns when the rate it fetched wasn't a live one. No rate needed, no warning."""
    rate = await valuation.usd_rate_if_needed(equities)
    if rate is not None:
        _warn_if_rate_not_live()
    return rate

# ============== Write-time defaults ==============

def _today_iso() -> str:
    return valuation.today().isoformat()


def _asset_defaults(row: dict) -> dict:
    """An asset that changes by itself (yearly rate, provident-fund interest or contributions) carries the date
    its value was true."""
    changes_by_itself = any(row.get(key) is not None
                            for key in ("annual_change_rate", "interest_rate", "monthly_contribution",
                                        "yearly_contribution", "nps_schemes"))
    if changes_by_itself and not row.get("valuation_date"):
        return {"valuation_date": _today_iso()}
    return {}


def _value_from_quantity(row: dict) -> dict:
    """Quantity × price holdings store their product as the value."""
    quantity, unit_price = row.get("quantity"), row.get("unit_price")
    if quantity is None or unit_price is None:
        return {}
    value = round(quantity * unit_price, 2)
    if not value <= MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="Quantity × price is above the allowed maximum")
    return {"value": value}


def _liability_defaults(row: dict) -> dict:
    """An EMI needs a balance date to count payments from."""
    if row.get("emi") and not row.get("balance_date"):
        return {"balance_date": _today_iso()}
    return {}


def _merged(current: dict, changes: dict, clearable: frozenset) -> dict:
    """The row an update will leave in storage: a null replaces a value only in a clearable field."""
    return {**current, **{key: value for key, value in changes.items() if value is not None or key in clearable}}


def _emi_from_tenure(changes: dict, current: dict) -> dict:
    """When a tenure is given without an EMI, derive the EMI from the balance and rate."""
    if changes.get("tenure_months") and not changes.get("emi"):
        merged = _merged(current, changes, db.LIABILITY_CLEARABLE)
        emi = valuation.emi_for_tenure(merged["amount"], merged.get("interest_rate") or 0, changes["tenure_months"])
        if not 0 < emi <= MAX_AMOUNT:
            raise HTTPException(status_code=400, detail="The EMI worked out from the tenure is out of range")
        return {"emi": emi}
    return {}


def _check_deposit_dates(row: dict) -> None:
    start, maturity = row.get("start_date"), row.get("maturity_date")
    if start and maturity and maturity < start:
        raise HTTPException(status_code=400, detail="Maturity date must be after the start date")


# Inputs an NPS asset's units depend on; when one changes, its schemes are priced again
NPS_PRICING_FIELDS = ("value", "valuation_date", "monthly_contribution", "yearly_contribution",
                      "yearly_contribution_month", "nps_schemes", "category")


async def _nps_pricing(row: dict, on) -> Tuple[Optional[dict], Optional[str]]:
    """Units and NAVs for an NPS asset's schemes: (pricing, None) when priced; (None, None) when a NAV history can't
    be fetched right now; (None, why) when the histories were fetched but can't price the asset, which is no fault
    of the source (e.g. a scheme with no NAV on or before the balance date)."""
    histories = {}
    for scheme in row.get("nps_schemes") or []:
        history = await nps_service.fetch_history(scheme["scheme_code"])
        if not history:
            return None, None
        histories[scheme["scheme_code"]] = history
    priced = valuation.nps_price(row, histories, on)
    return priced, None if priced else valuation.nps_price_problem(row, histories, on)


async def _nps_changes(row: dict) -> dict:
    """What to store once an NPS asset's inputs changed: fresh pricing, or the schemes without any (saving never
    fails because of the NAV service or its data)."""
    stale = {"nps_priced_through": None} if row.get("nps_priced_through") else {}
    if row.get("category") != "nps" or not row.get("nps_schemes"):
        return stale
    priced, problem = await _nps_pricing(row, valuation.today())
    name = row.get("name") or "an NPS asset"
    if problem:
        user_warnings.warn(f"Couldn't price {name}: {problem}.")
    elif not priced:
        user_warnings.warn(f"Couldn't fetch NPS NAVs from npsnav.in for {name}; "
                           "its contributions count at cost until a refresh works.")
    # Old pricing is cleared only where there is some: an unpriced row then looks like a freshly created one
    return priced or {"nps_schemes": valuation.nps_scheme_inputs(row["nps_schemes"]), **stale}


def _nps_inputs(row: dict) -> dict:
    return {key: valuation.nps_scheme_inputs(row[key]) if key == "nps_schemes" and row.get(key) else row.get(key)
            for key in NPS_PRICING_FIELDS}

# ============== Asset Routes ==============

def get_user_id(username: str = Depends(get_current_user)) -> str:
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user["id"]

@app.get("/api/assets", response_model=List[Asset])
async def get_assets(user_id: str = Depends(get_user_id)):
    """Get all assets for current user, valued as of today"""
    on = valuation.today()
    return [valuation.asset_view(a, on) for a in db.get_assets_by_user(user_id)]

@app.post("/api/assets", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def create_asset(asset_data: AssetCreate, user_id: str = Depends(get_user_id)):
    """Create a new asset"""
    data = asset_data.model_dump()
    data.update(_value_from_quantity(data))
    data.update(_asset_defaults(data))
    data.update(await _nps_changes(data))
    return valuation.asset_view(db.create_asset(user_id, data), valuation.today())

@app.get("/api/assets/{asset_id}", response_model=Asset)
async def get_asset(asset_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific asset"""
    asset = db.get_asset_by_id(asset_id, user_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return valuation.asset_view(asset, valuation.today())

@app.put("/api/assets/{asset_id}", response_model=Asset)
async def update_asset(asset_id: str, update_data: AssetUpdate, user_id: str = Depends(get_user_id)):
    """Update an asset"""
    current = db.get_asset_by_id(asset_id, user_id)
    if not current:
        raise HTTPException(status_code=404, detail="Asset not found")
    changes = update_data.model_dump(exclude_unset=True)
    changes.update(_value_from_quantity(_merged(current, changes, db.ASSET_CLEARABLE)))
    changes.update(_asset_defaults(_merged(current, changes, db.ASSET_CLEARABLE)))
    merged = _merged(current, changes, db.ASSET_CLEARABLE)
    if _nps_inputs(merged) != _nps_inputs(current):
        changes.update(await _nps_changes(merged))
    elif "nps_schemes" in changes:
        changes["nps_schemes"] = current.get("nps_schemes")  # same inputs: keep what pricing worked out
    asset = db.update_asset(asset_id, user_id, changes)
    if not asset:  # deleted while the NAVs were being fetched
        raise HTTPException(status_code=404, detail="Asset not found")
    return valuation.asset_view(asset, valuation.today())

@app.delete("/api/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: str, user_id: str = Depends(get_user_id)):
    """Delete an asset"""
    if not db.delete_asset(asset_id, user_id):
        raise HTTPException(status_code=404, detail="Asset not found")

@app.post("/api/assets/{asset_id}/refresh-nav", response_model=Asset)
async def refresh_asset_nav(asset_id: str, user_id: str = Depends(get_user_id)):
    """Price an NPS asset's schemes again with the latest NAVs"""
    asset = db.get_asset_by_id(asset_id, user_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.get("category") != "nps" or not asset.get("nps_schemes"):
        raise HTTPException(status_code=400, detail="Only an NPS asset with investment options has NAVs to refresh")
    on = valuation.today()
    pricing, problem = await _nps_pricing(asset, on)
    if problem:  # the NAVs came back but can't price these inputs: the user can fix that, the source isn't down
        raise HTTPException(status_code=422, detail=problem[:1].upper() + problem[1:])
    if pricing is None:
        user_warnings.warn("Couldn't fetch NPS NAVs from npsnav.in right now; values use the last fetched NAVs.")
        raise HTTPException(status_code=502, detail="Couldn't fetch NPS NAVs right now")
    # Fetching takes a while; the row may have been edited or deleted meanwhile, and pricing worked out from the
    # old inputs must not overwrite the new ones
    fresh = db.get_asset_by_id(asset_id, user_id)
    if not fresh:
        raise HTTPException(status_code=404, detail="Asset not found")
    if _nps_inputs(fresh) != _nps_inputs(asset):
        return valuation.asset_view(fresh, on)
    return valuation.asset_view(db.update_asset(asset_id, user_id, pricing), on)

@app.get("/api/nps/schemes", response_model=List[NpsSchemeOption])
async def get_nps_schemes(user_id: str = Depends(get_user_id)):
    """Every NPS scheme with its latest NAV, for choosing investment options"""
    schemes = await nps_service.list_schemes()
    if not schemes:
        user_warnings.warn("Couldn't load the NPS scheme list from npsnav.in right now.")
        raise HTTPException(status_code=502, detail="Couldn't fetch the NPS scheme list right now")
    return schemes

# ============== Liability Routes ==============

@app.get("/api/liabilities", response_model=List[Liability])
async def get_liabilities(user_id: str = Depends(get_user_id)):
    """Get all liabilities for current user, with today's outstanding balance"""
    on = valuation.today()
    return [valuation.liability_view(l, on) for l in db.get_liabilities_by_user(user_id)]

@app.post("/api/liabilities", response_model=Liability, status_code=status.HTTP_201_CREATED)
async def create_liability(liability_data: LiabilityCreate, user_id: str = Depends(get_user_id)):
    """Create a new liability"""
    data = liability_data.model_dump()
    data.update(_emi_from_tenure(data, {}))
    data.update(_liability_defaults(data))
    return valuation.liability_view(db.create_liability(user_id, data), valuation.today())

@app.get("/api/liabilities/{liability_id}", response_model=Liability)
async def get_liability(liability_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific liability"""
    liability = db.get_liability_by_id(liability_id, user_id)
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    return valuation.liability_view(liability, valuation.today())

@app.get("/api/liabilities/{liability_id}/schedule")
async def get_liability_schedule(liability_id: str, user_id: str = Depends(get_user_id)):
    """Remaining EMI payments grouped by year"""
    liability = db.get_liability_by_id(liability_id, user_id)
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    on = valuation.today()
    status_now = valuation.loan_status(liability, on)
    if not status_now["amortized"]:
        raise HTTPException(status_code=400, detail="This liability has no EMI set")
    return {
        "rows": valuation.loan_schedule(liability, on),
        "months_remaining": status_now["months_remaining"],
        "payoff_date": status_now["payoff_date"],
        "interest_remaining": status_now["interest_remaining"],
    }

@app.put("/api/liabilities/{liability_id}", response_model=Liability)
async def update_liability(liability_id: str, update_data: LiabilityUpdate, user_id: str = Depends(get_user_id)):
    """Update a liability"""
    current = db.get_liability_by_id(liability_id, user_id)
    if not current:
        raise HTTPException(status_code=404, detail="Liability not found")
    changes = update_data.model_dump(exclude_unset=True)
    changes.update(_emi_from_tenure(changes, current))
    liability = db.update_liability(liability_id, user_id, changes)
    extra = _liability_defaults(liability)
    if extra:
        liability = db.update_liability(liability_id, user_id, extra)
    return valuation.liability_view(liability, valuation.today())

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
    _warn_if_rate_not_live()
    return {"usd_to_inr": rate}

@app.get("/api/export")
async def export_user_data(user_id: str = Depends(get_user_id)):
    """Export all user data as JSON for backup"""
    
    # Gather all user data
    export_data = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "assets": db.get_assets_by_user(user_id),
        "liabilities": db.get_liabilities_by_user(user_id),
        "bank_accounts": db.get_bank_accounts_by_user(user_id),
        "insurances": db.get_insurances_by_user(user_id),
        "mutual_funds": db.get_mutual_funds_by_user(user_id),
        "equities": db.get_equities_by_user(user_id),
        "snapshots": db.get_snapshots_by_user(user_id, limit=None),
        "goal": db.get_goal_by_user(user_id)
    }
    
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f"attachment; filename=networth_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        }
    )

@app.post("/api/restore")
async def restore_user_data(file: UploadFile = File(...), user_id: str = Depends(get_user_id)):
    """Replace all of the current user's data with a backup file. Nothing is written unless the whole file is valid."""
    try:
        cleaned = restore.parse_backup(await file.read())
    except restore.RestoreError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    # The write-time rules of POST /api/assets: a restored backup must not hold what the API would refuse or leave undated.
    for i, asset in enumerate(cleaned["assets"]):
        try:
            asset.update(_value_from_quantity(asset))
        except HTTPException as e:
            raise HTTPException(status_code=400, detail=f"assets[{i}]: {e.detail}")
        asset.update(_asset_defaults(asset))
    db.replace_user_data(user_id, cleaned)
    counts = {section: len(cleaned[section]) for section in restore.LIST_SECTIONS}
    return {"status": "success", "restored": {**counts, "goal": cleaned["goal"] is not None}}

async def _portfolio_totals(user_id: str, on, usd_to_inr: Optional[float] = None) -> dict:
    """usd_to_inr is the live rate (fetched only when a holding is in USD) unless the caller supplies one"""
    equities = db.get_equities_by_user(user_id)
    return valuation.portfolio_totals(
        assets=db.get_assets_by_user(user_id),
        liabilities=db.get_liabilities_by_user(user_id),
        bank_accounts=db.get_bank_accounts_by_user(user_id),
        mutual_funds=db.get_mutual_funds_by_user(user_id),
        equities=equities,
        usd_to_inr=usd_to_inr if usd_to_inr is not None else await _usd_rate_if_needed(equities),
        on=on,
    )

def _snapshot_breakdown(totals: dict) -> dict:
    return {key: totals[key] for key in db.SNAPSHOT_BREAKDOWN}

def _snapshot_frequency(user_id: str) -> str:
    user = db.get_user_by_id(user_id) or {}
    return user.get("snapshot_frequency") or valuation.DEFAULT_SNAPSHOT_FREQUENCY

def _snapshot_timestamps(user_id: str) -> List[str]:
    return [s["timestamp"] for s in db.get_snapshots_by_user(user_id, limit=None)]

def _ensure_auto_snapshot(user_id: str, totals: dict, on, frequency: str) -> None:
    """A snapshot saved the first time the dashboard is opened once one is due at the user's frequency
    (manual snapshots count). Empty accounts are skipped."""
    if not totals["total_assets"] and not totals["total_liabilities"]:
        return
    if not valuation.snapshot_due(frequency, _snapshot_timestamps(user_id), on):
        return
    try:
        db.create_snapshot(user_id, totals["total_assets"], totals["total_liabilities"],
                           breakdown=_snapshot_breakdown(totals), timestamp=f"{on.isoformat()}T00:00:00")
    except OSError:
        # The dashboard is a read; a full or read-only disk must not break it. The next visit tries again.
        logger.warning("Could not save the automatic snapshot", exc_info=True)

def _snapshot_timestamp(on) -> str:
    """Now on the app clock: the valuation date (from valuation.today(), the same date the automatic
    snapshot check uses) with the local time of day"""
    return datetime.combine(on, datetime.now().time()).isoformat()

@app.get("/api/dashboard", response_model=DashboardMetrics)
async def get_dashboard(user_id: str = Depends(get_user_id)):
    """Get dashboard metrics, valued as of today"""
    on = valuation.today()
    totals = await _portfolio_totals(user_id, on)
    frequency = _snapshot_frequency(user_id)
    _ensure_auto_snapshot(user_id, totals, on, frequency)
    # The totals are already rounded to the paisa, so this is belt and braces: it keeps the ratio finite
    # for a total below one paisa, where dividing would overflow
    ratio = totals["total_liabilities"] / totals["total_assets"] * 100 if totals["total_assets"] >= 0.01 else 0
    return DashboardMetrics(
        **totals,
        debt_to_asset_ratio=round(ratio, 2),
        net_worth_history=db.get_snapshots_by_user(user_id, limit=None),
        maturities=valuation.upcoming_maturities(db.get_bank_accounts_by_user(user_id), on),
        snapshot_frequency=frequency,
        next_snapshot_on=valuation.next_snapshot_date(frequency, _snapshot_timestamps(user_id), on).isoformat(),
    )

@app.post("/api/snapshot", response_model=NetWorthSnapshot, status_code=status.HTTP_201_CREATED)
async def create_snapshot(user_id: str = Depends(get_user_id)):
    """Create a net worth snapshot"""
    # One date for both, so a save that spans midnight is valued and stamped on the same day
    on = valuation.today()
    totals = await _portfolio_totals(user_id, on)
    return db.create_snapshot(user_id, totals["total_assets"], totals["total_liabilities"],
                              breakdown=_snapshot_breakdown(totals), timestamp=_snapshot_timestamp(on))

def _snapshot_settings(user_id: str) -> dict:
    frequency = _snapshot_frequency(user_id)
    next_on = valuation.next_snapshot_date(frequency, _snapshot_timestamps(user_id), valuation.today())
    return {"frequency": frequency, "next_snapshot_on": next_on.isoformat()}

@app.get("/api/settings/snapshots", response_model=SnapshotSettingsView)
async def get_snapshot_settings(user_id: str = Depends(get_user_id)):
    """How often the dashboard saves an automatic snapshot, and when the next one is due"""
    return _snapshot_settings(user_id)

@app.put("/api/settings/snapshots", response_model=SnapshotSettingsView)
async def update_snapshot_settings(body: SnapshotSettings, user_id: str = Depends(get_user_id)):
    """Change how often the dashboard saves an automatic snapshot"""
    db.update_user(user_id, {"snapshot_frequency": body.frequency})
    return _snapshot_settings(user_id)

# ============== Bank Account Routes ==============

@app.get("/api/bank-accounts", response_model=List[BankAccount])
async def get_bank_accounts(user_id: str = Depends(get_user_id)):
    """Get all bank accounts for current user, FDs/RDs valued as of today"""
    on = valuation.today()
    return [valuation.bank_account_view(a, on) for a in db.get_bank_accounts_by_user(user_id)]

@app.post("/api/bank-accounts", response_model=BankAccount, status_code=status.HTTP_201_CREATED)
async def create_bank_account(account_data: BankAccountCreate, user_id: str = Depends(get_user_id)):
    """Create a new bank account"""
    data = account_data.model_dump()
    _check_deposit_dates(data)
    return valuation.bank_account_view(db.create_bank_account(user_id, data), valuation.today())

@app.get("/api/bank-accounts/{account_id}", response_model=BankAccount)
async def get_bank_account(account_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific bank account"""
    account = db.get_bank_account_by_id(account_id, user_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return valuation.bank_account_view(account, valuation.today())

@app.put("/api/bank-accounts/{account_id}", response_model=BankAccount)
async def update_bank_account(account_id: str, update_data: BankAccountUpdate, user_id: str = Depends(get_user_id)):
    """Update a bank account"""
    current = db.get_bank_account_by_id(account_id, user_id)
    if not current:
        raise HTTPException(status_code=404, detail="Bank account not found")
    changes = update_data.model_dump(exclude_unset=True)
    _check_deposit_dates(_merged(current, changes, db.BANK_ACCOUNT_CLEARABLE))
    account = db.update_bank_account(account_id, user_id, changes)
    return valuation.bank_account_view(account, valuation.today())

@app.delete("/api/bank-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_account(account_id: str, user_id: str = Depends(get_user_id)):
    """Delete a bank account"""
    if not db.delete_bank_account(account_id, user_id):
        raise HTTPException(status_code=404, detail="Bank account not found")

@app.get("/api/bank-accounts-summary")
async def get_bank_accounts_summary(user_id: str = Depends(get_user_id)):
    """Get the total value of all bank accounts (FDs/RDs include interest earned so far)"""
    on = valuation.today()
    accounts = db.get_bank_accounts_by_user(user_id)
    total = sum(valuation.deposit_status(a, on)["current_value"] for a in accounts)
    return {"total_balance": round(total, 2), "account_count": len(accounts)}

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
        else:
            user_warnings.warn(f"Couldn't fetch the latest NAV for {fund_dict['fund_name']} from mfapi.in; "
                               "its value uses the purchase NAV until a refresh works.")
    
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

def _reject_oversized_fund(fund_dict: dict) -> None:
    """The computed numbers are stored, so they must stay within the input limits: responses and restore enforce them."""
    # `not (value <= MAX_AMOUNT)` also catches a NaN, e.g. a NAV fetched from the external API. The invested amount
    # is computed too when a SIP change folds the installments into it.
    values = (fund_dict.get(key) for key in ("avg_nav", "current_nav", "current_value", "invested_amount"))
    if any(value is not None and not (value <= MAX_AMOUNT) for value in values):
        raise HTTPException(status_code=422, detail="The fund's computed value is too large")

def _nav_fits(units: float, nav: float) -> bool:
    """Whether a refreshed NAV, and the value it gives for these units, stay within the input limits."""
    return nav <= MAX_AMOUNT and units * nav <= MAX_AMOUNT

# Inputs a fund's SIP units depend on; when one changes, the SIP is priced again
SIP_PRICING_FIELDS = ("sip_amount", "sip_frequency", "sip_day", "sip_start_date", "sip_end_date", "holdings_date",
                      "units", "fund_name", "scheme_code")
SIP_UNPRICED = {"sip_units": None, "sip_invested": None, "sip_priced_through": None}


def _sip_defaults(row: dict) -> dict:
    """A fund with a SIP carries the dates its installments count from, a frequency and (monthly or quarterly)
    the day each installment lands."""
    if not row.get("sip_amount"):
        return {}
    changes = {}
    holdings = row.get("holdings_date") or _today_iso()
    start = row.get("sip_start_date") or holdings
    frequency = row.get("sip_frequency") or "monthly"
    if not row.get("holdings_date"):
        changes["holdings_date"] = holdings
    if not row.get("sip_start_date"):
        changes["sip_start_date"] = start
    if not row.get("sip_frequency"):
        changes["sip_frequency"] = frequency
    if frequency != "weekly" and not row.get("sip_day"):
        changes["sip_day"] = date.fromisoformat(start).day
    return changes


def _check_sip_dates(row: dict) -> None:
    start, end = row.get("sip_start_date"), row.get("sip_end_date")
    if start and end and end < start:
        raise HTTPException(status_code=422, detail="SIP end date must be on or after its start date")


async def _sip_pricing(fund: dict, on, look_up_code: bool = True, warn: bool = True) -> Optional[dict]:
    """SIP units and the fund's NAV and value as of `on`, or None when NAVs can't be fetched or used right now.
    A fund without a scheme code finds it by name, unless the caller just tried that and failed. A failure warns
    unless the caller warns for several funds at once."""
    code = fund.get("scheme_code")
    if not code and look_up_code:
        info = await nav_service.fetch_nav_by_fund_name(fund["fund_name"])
        code = info.get("scheme_code") if info else None
    history = await nav_service.fetch_history(code) if code else None
    priced = valuation.sip_price(fund, history, on) if history else None
    if not priced:
        if warn:
            _warn_sip_not_priced(fund["fund_name"])
    elif not fund.get("scheme_code"):
        priced["scheme_code"] = code
    return priced


async def _sip_changes(row: dict) -> dict:
    """What to store once a fund's SIP inputs changed: fresh pricing, or none (saving never waits on NAVs)."""
    if not valuation.sip_active(row):
        return dict(SIP_UNPRICED)
    return await _sip_pricing(row, valuation.today()) or dict(SIP_UNPRICED)


# A change to one of these (stopping the SIP included) applies from today; the start and end dates are corrections
SIP_SCHEDULE_FIELDS = ("sip_amount", "sip_frequency", "sip_day")
# What a statement gives: a request that changes one of these re-bases the holding itself
SIP_HOLDING_FIELDS = ("units", "invested_amount", "holdings_date")


def _sip_rescheduled(existing: dict, merged: dict, sent: dict) -> bool:
    """Whether an update changes an active SIP's schedule without restating the holding (a null is no statement:
    the form sends one for the as-of date when a SIP is stopped)."""
    if not valuation.sip_active(existing):
        return False
    if all(merged.get(key) == existing.get(key) for key in SIP_SCHEDULE_FIELDS):
        return False
    return not any(sent.get(key) is not None and sent[key] != existing.get(key) for key in SIP_HOLDING_FIELDS)


async def _sip_folded(fund: dict, on) -> Optional[dict]:
    """The holding with the SIP's installments up to `on` folded in: units and invested amount as of `on`, valued at
    the latest NAV, and the SIP's own pricing cleared. None when the NAVs this needs can't be fetched or used."""
    on_iso = on.isoformat()
    holdings = valuation.parse_date(fund["holdings_date"])
    if not valuation.sip_installments(fund, holdings, on):
        # Nothing bought since the holdings date: no NAV needed (and a holdings date after `on` stays as it is)
        return {"holdings_date": max(holdings, on).isoformat(), **SIP_UNPRICED}
    priced = await _sip_pricing(fund, on)
    if not priced:
        return None
    units = round((fund.get("units") or 0) + priced["sip_units"], 4)
    folded = {"units": units, "invested_amount": round((fund.get("invested_amount") or 0) + priced["sip_invested"], 2),
              "holdings_date": on_iso, "current_nav": priced["current_nav"],
              "current_value": round(units * priced["current_nav"], 2), **SIP_UNPRICED}
    if priced.get("scheme_code"):
        folded["scheme_code"] = priced["scheme_code"]
    return folded


async def _sip_refresh_pricing(fund: dict, nav_info: Optional[dict], on, warn: bool = True) -> Optional[dict]:
    """A SIP fund's pricing from the NAV history up to `on`; None when the fund has no SIP or its NAVs can't be used
    right now. The history needs only the scheme code, so this works even when the latest-NAV lookup by name just
    failed (and is not repeated here)."""
    if not valuation.sip_active(fund):
        return None
    if nav_info:
        fund = {**fund, "scheme_code": nav_info.get("scheme_code")}
    return await _sip_pricing(fund, on, look_up_code=False, warn=warn)


# What a refresh works its numbers out from; if one changed while the NAVs were fetched, the refresh stores nothing
REFRESH_INPUT_FIELDS = (*SIP_PRICING_FIELDS, "invested_amount")


def _store_refresh(fund: dict, nav_info: Optional[dict], pricing: Optional[dict]) -> Optional[dict]:
    """Store what a refresh fetched for `fund` (the row as read before fetching) and return the row as stored now;
    None when it was deleted meanwhile. Fetching takes a while: when the fund was edited meanwhile, numbers worked
    out from the old row must not overwrite the new one, so nothing is stored (the next refresh prices the edit)."""
    fresh = db.get_mutual_fund_by_id(fund["id"], fund["user_id"])
    if not fresh or any(fresh.get(key) != fund.get(key) for key in REFRESH_INPUT_FIELDS):
        return fresh
    updates = {}
    if nav_info:
        units = fresh.get("units") or 0
        updates = {"current_nav": nav_info["nav"], "scheme_code": nav_info.get("scheme_code")}
        if units > 0:
            updates["current_value"] = round(units * nav_info["nav"], 2)
    updates.update(pricing or {})  # a SIP's pricing values its units too, at the history's latest NAV
    return db.update_mutual_fund(fund["id"], fund["user_id"], updates) if updates else fresh

@app.get("/api/mutual-funds", response_model=List[MutualFund])
async def get_mutual_funds(user_id: str = Depends(get_user_id), refresh_nav: bool = False):
    """Get all mutual funds for current user. Set refresh_nav=true to fetch latest NAV."""
    funds = db.get_mutual_funds_by_user(user_id)
    on = valuation.today()

    if refresh_nav and funds:
        missed = []  # funds whose NAV neither the latest-NAV lookup nor a SIP's NAV history could refresh
        sips_missed = []  # funds whose NAV was refreshed but whose SIP couldn't be priced
        refreshed = []
        for fund in funds:
            nav_info = await nav_service.fetch_nav_by_fund_name(fund["fund_name"])
            if nav_info and not _nav_fits(fund.get("units", 0), nav_info["nav"]):
                refreshed.append(fund)  # too large to store: leave this fund unchanged
                continue
            # A SIP is priced from the NAV history, so a failed latest-NAV lookup doesn't stop it
            pricing = await _sip_refresh_pricing(fund, nav_info, on, warn=False)
            stored = _store_refresh(fund, nav_info, pricing)
            if stored is None:
                continue  # deleted while its NAVs were being fetched
            refreshed.append(stored)
            if not nav_info and not pricing:
                missed.append(fund["fund_name"])
            elif valuation.sip_active(fund) and not pricing:
                sips_missed.append(fund["fund_name"])
        funds = refreshed
        # One message per kind, naming a few funds each; a fund the NAV message names isn't named again for its SIP
        _warn_funds_not_refreshed(missed)
        _warn_sips_not_priced(sips_missed)

    return [valuation.fund_view(fund, on) for fund in funds]

@app.post("/api/mutual-funds", response_model=MutualFund, status_code=status.HTTP_201_CREATED)
async def create_mutual_fund(fund_data: MutualFundCreate, user_id: str = Depends(get_user_id)):
    """Create a new mutual fund"""
    fund_dict = fund_data.model_dump()
    fund_dict.update(_sip_defaults(fund_dict))
    _check_sip_dates(fund_dict)  # a defaulted start can fall after the end date that was given
    fund_dict = await _process_mutual_fund_data(fund_dict)
    _reject_oversized_fund(fund_dict)
    # A new fund has no earlier pricing to clear: it stores pricing only when it has some, as a backup restore does
    fund_dict.update({key: value for key, value in (await _sip_changes(fund_dict)).items() if value is not None})
    return valuation.fund_view(db.create_mutual_fund(user_id, fund_dict), valuation.today())

@app.get("/api/mutual-funds/{fund_id}", response_model=MutualFund)
async def get_mutual_fund(fund_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific mutual fund"""
    fund = db.get_mutual_fund_by_id(fund_id, user_id)
    if not fund:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    return valuation.fund_view(fund, valuation.today())

@app.put("/api/mutual-funds/{fund_id}", response_model=MutualFund)
async def update_mutual_fund(fund_id: str, update_data: MutualFundUpdate, user_id: str = Depends(get_user_id)):
    """Update a mutual fund"""
    existing = db.get_mutual_fund_by_id(fund_id, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    sent = update_data.model_dump(exclude_unset=True)
    merged = {**existing, **sent}
    merged.update(_sip_defaults(merged))
    _check_sip_dates(merged)
    folded = {}
    if _sip_rescheduled(existing, merged, sent):
        # The new amount, frequency or day applies from today: what the SIP bought so far joins the holding, as of
        # today, so replaying those installments with the new schedule can neither invent nor lose money
        folded = await _sip_folded(existing, valuation.today())
        if folded is None:
            raise HTTPException(status_code=409, detail="Couldn't fetch NAVs to apply the SIP change from today; "
                                                        "try again when NAVs are available")
        merged.update(folded)
    # If fund_name is being updated or current_nav is not set, try to fetch NAV
    merged = await _process_mutual_fund_data(merged)
    _reject_oversized_fund(merged)
    if any(merged.get(key) != existing.get(key) for key in SIP_PRICING_FIELDS):
        changes = await _sip_changes(merged)
        if (not folded and "current_value" not in changes and existing.get("sip_units") is not None
                and not sent.get("current_value")):
            # The stored value counted units the old pricing bought and the new one doesn't: value the holdings alone
            merged["current_value"] = None
            merged = await _process_mutual_fund_data(merged)
            _reject_oversized_fund(merged)
        merged.update(changes)
    fund = db.update_mutual_fund(fund_id, user_id, merged)
    if not fund:  # deleted while the NAVs were being fetched
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    return valuation.fund_view(fund, valuation.today())

@app.delete("/api/mutual-funds/{fund_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mutual_fund(fund_id: str, user_id: str = Depends(get_user_id)):
    """Delete a mutual fund"""
    if not db.delete_mutual_fund(fund_id, user_id):
        raise HTTPException(status_code=404, detail="Mutual fund not found")

@app.get("/api/mutual-funds-summary")
async def get_mutual_funds_summary(user_id: str = Depends(get_user_id)):
    """Get mutual fund summary"""
    on = valuation.today()
    funds = db.get_mutual_funds_by_user(user_id)
    views = [valuation.fund_view(fund, on) for fund in funds]
    total_invested = sum(view["total_invested"] for view in views)
    total_current = sum(view.get("current_value") or 0 for view in views)
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
    if nav_info and not _nav_fits(fund.get("units", 0), nav_info["nav"]):
        return {"status": "error", "message": "The fetched NAV would make the fund's value too large to store"}
    # A SIP is priced from the NAV history, so a failed latest-NAV lookup doesn't stop it
    on = valuation.today()
    pricing = await _sip_refresh_pricing(fund, nav_info, on)
    fund = _store_refresh(fund, nav_info, pricing)
    if not fund:  # deleted while the NAVs were being fetched
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    if nav_info:
        return {"status": "success", "nav": nav_info["nav"], "date": nav_info["date"],
                "fund": valuation.fund_view(fund, on)}
    if pricing:  # the lookup failed, but the history priced the SIP: its latest NAV is the fund's
        return {"status": "success", "nav": pricing["current_nav"], "date": None,
                "fund": valuation.fund_view(fund, on)}
    user_warnings.warn(f"Couldn't fetch the latest NAV for {fund['fund_name']} from mfapi.in; "
                       "its value uses the last fetched NAV.")
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
        missed = []
        for equity in equities:
            price_info = stock_service.fetch_stock_price(equity["symbol"], equity["market"])
            if price_info and price_info.get("current_price"):
                db.update_equity_price(equity["id"], user_id, price_info["current_price"])
            else:
                missed.append(equity["symbol"])
        _warn_stock_prices(missed)
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
        _warn_stock_price(equity_data.symbol)
    
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
    else:
        _warn_stock_price(equity["symbol"])
    
    return equity

@app.get("/api/equities-summary")
async def get_equities_summary(user_id: str = Depends(get_user_id)):
    """Get equities summary in INR (US-market holdings converted at the live rate)"""
    equities = db.get_equities_by_user(user_id)
    usd_to_inr = await _usd_rate_if_needed(equities)

    def in_inr(equity: dict, amount: float) -> float:
        return amount * usd_to_inr if equity.get("market") in USD_MARKETS else amount

    total_invested = sum(in_inr(e, e["invested_amount"]) for e in equities)
    total_current = sum(in_inr(e, e["current_value"]) for e in equities)
    total_gain = total_current - total_invested
    return {
        "total_invested": total_invested,
        "total_current_value": total_current,
        "total_gain": total_gain,
        "gain_percent": (total_gain / total_invested * 100) if total_invested >= 0.01 else 0,
        "holding_count": len(equities)
    }

@app.get("/api/stock-price/{market}/{symbol}")
async def get_stock_price(market: str, symbol: str):
    """Get live stock price for a symbol"""
    price_info = stock_service.fetch_stock_price(symbol, market)
    if not price_info:
        # A lookup, not a holding: nothing's value falls back. The symbol comes from the path, so it is cut short.
        user_warnings.warn(f"Couldn't fetch the price of {symbol[:20]} right now.")
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

async def _seed_demo_history(user_id: str, on) -> None:
    """Six synthetic month-start snapshots (oldest first) built from the demo user's own totals, so the first
    real visit shows a small change. Each month back, assets are 1% lower and liabilities 1% higher (loans
    amortize); every breakdown map scales with its total, so the asset classes keep the live mix.
    The rate is the cached one: starting up never waits on the network."""
    totals = await _portfolio_totals(user_id, on, usd_to_inr=exchange_service.get_cached_rate())
    breakdown = _snapshot_breakdown(totals)
    this_month = date(on.year, on.month, 1)
    for months_back in range(6, 0, -1):
        asset_factor, liability_factor = 0.99 ** months_back, 1.01 ** months_back
        factors = {"assets_by_category": asset_factor, "assets_by_class": asset_factor,
                   "liabilities_by_category": liability_factor}
        db.create_snapshot(
            user_id,
            round(totals["total_assets"] * asset_factor, 2),
            round(totals["total_liabilities"] * liability_factor, 2),
            breakdown={
                key: {name: round(value * factors[key], 2) for name, value in values.items()}
                for key, values in breakdown.items()
            },
            timestamp=f"{valuation.add_months(this_month, -months_back).isoformat()}T00:00:00",
        )

# Startup event to create demo data
@app.on_event("startup")
async def startup_event():
    """Create demo user and sample data on startup (only if CREATE_DEMO_DATA=true)"""
    if not settings.CREATE_DEMO_DATA:
        return

    from auth import get_password_hash

    on = valuation.today()
    iso = lambda d: d.isoformat()

    # Check if demo user exists
    username = settings.DEMO_USERNAME
    demo_user = db.get_user_by_username(username)
    new_demo_user = not demo_user
    if new_demo_user:
        # Create demo user; the password is DEMO_PASSWORD if set, otherwise generated and logged once
        password = settings.DEMO_PASSWORD
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12)
        demo_user = db.create_user(username, f"{username}@example.com", get_password_hash(password))
        if generated:
            logger.warning("Created demo user %r with a generated password: %s (set DEMO_PASSWORD to choose one)",
                           username, password)

        user_id = demo_user["id"]
        
        # Add sample assets - all categories
        sample_assets = [
            {"name": "Emergency Fund", "category": "cash", "value": 300000, "notes": "HDFC Savings account"},
            {"name": "Cash at Home", "category": "cash", "value": 50000, "notes": "Petty cash and emergency"},
            {"name": "Direct Equity Portfolio", "category": "investments", "value": 450000, "notes": "Stocks in Zerodha - TCS, Infosys, HDFC Bank"},
            {"name": "PPF Account", "category": "ppf", "value": 850000, "notes": "SBI PPF - 10 years maturity", "interest_rate": 7.1, "monthly_contribution": 12500, "valuation_date": iso(valuation.add_months(on, -6))},
            {"name": "Primary Residence", "category": "real_estate", "value": 8500000, "notes": "3BHK Apartment in Bangalore"},
            {"name": "Agricultural Land", "category": "real_estate", "value": 2500000, "notes": "2 acres in native village"},
            {"name": "Honda City", "category": "vehicles", "value": 1200000, "notes": "2022 Model - ZX CVT", "annual_change_rate": -15, "valuation_date": iso(valuation.add_months(on, -12))},
            {"name": "Royal Enfield Classic 350", "category": "vehicles", "value": 180000, "notes": "2021 Model"},
            {"name": "EPF Balance", "category": "epf", "value": 1200000, "notes": "Employee Provident Fund", "interest_rate": 8.25, "monthly_contribution": 3600, "valuation_date": iso(valuation.add_months(on, -6))},
            {"name": "NPS Account", "category": "nps", "value": 350000, "notes": "National Pension Scheme",
             "monthly_contribution": 6000, "yearly_contribution": 50000, "yearly_contribution_month": 3,
             "valuation_date": iso(valuation.add_months(on, -6)),
             "nps_schemes": [
                 {"scheme_code": "SM002027", "scheme_name": "NPS TRUST A/C - UTI PENSION FUND SCHEME E - TIER I DIRECT",
                  "allocation_pct": 75, "units": None},
                 {"scheme_code": "SM002028", "scheme_name": "NPS TRUST A/C - UTI PENSION FUND SCHEME C - TIER I DIRECT",
                  "allocation_pct": 15, "units": None},
                 {"scheme_code": "SM002029", "scheme_name": "NPS TRUST A/C - UTI PENSION FUND SCHEME G - TIER I DIRECT",
                  "allocation_pct": 10, "units": None},
             ]},
            {"name": "Bitcoin Holdings", "category": "crypto", "value": 150000, "notes": "0.05 BTC on WazirX"},
            {"name": "Ethereum Holdings", "category": "crypto", "value": 75000, "notes": "0.5 ETH"},
            {"name": "Gold Jewelry", "category": "gold", "value": 500000, "notes": "Family gold - 50 grams", "quantity": 50, "unit_price": 10000},
            {"name": "MacBook Pro", "category": "other", "value": 180000, "notes": "M2 Pro - Work laptop"},
        ]
        for asset in sample_assets:
            db.create_asset(user_id, asset)
        
        # Add sample liabilities - all categories
        sample_liabilities = [
            {"name": "Home Loan - SBI", "category": "mortgage", "amount": 5000000, "interest_rate": 8.5, "notes": "15 years tenure, EMI ₹52,000", "emi": 52000, "balance_date": iso(valuation.add_months(on, -6))},
            {"name": "Car Loan - HDFC", "category": "car_loan", "amount": 600000, "interest_rate": 9.0, "notes": "5 years tenure, EMI ₹12,500", "emi": 12500, "balance_date": iso(valuation.add_months(on, -6))},
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
            {"bank_name": "Axis Bank", "account_number": "918020012345678", "account_type": "fd", "balance": 500000, "branch": "HSR Layout", "ifsc_code": "UTIB0001234", "interest_rate": 7.1, "start_date": iso(on - timedelta(days=200)), "maturity_date": iso(on + timedelta(days=20))},
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
            {"fund_name": "UTI Nifty Index Fund", "amc": "UTI Mutual Fund", "category": "index", "invested_amount": 80000, "current_value": 92000, "units": 650.00, "nav": 141.54, "folio_number": "32165498/78",
             "sip_amount": 5000, "sip_frequency": "monthly", "sip_day": 5,
             "sip_start_date": iso(valuation.add_months(on, -6)), "holdings_date": iso(valuation.add_months(on, -6))},
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

    if new_demo_user:
        await _seed_demo_history(user_id, on)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
