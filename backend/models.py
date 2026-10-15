from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from typing import Annotated, Dict, Literal, Optional, List
from datetime import date, datetime
from enum import Enum

# Upper bounds on user-entered numbers: far above any real holding, low enough that products and sums
# of stored values can never overflow a float.
MAX_AMOUNT = 1e15      # any rupee (or dollar) amount
MAX_QUANTITY = 1e9     # shares
MAX_UNITS = 1e12       # mutual fund units, grams, shares


class InputModel(BaseModel):
    """Base for every model that accepts user input: rejects NaN and ±Infinity in any float field."""
    model_config = ConfigDict(allow_inf_nan=False)


def _iso_date(value: str) -> str:
    # PydanticCustomError, unlike ValueError, reports its message as is, without a "Value error, " prefix
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise PydanticCustomError("invalid_date", "Invalid date")
    if not 1900 <= parsed.year <= 2200:
        raise PydanticCustomError("invalid_date", "Invalid date")
    return parsed.isoformat()


# A calendar date stored as "YYYY-MM-DD"
IsoDate = Annotated[str, AfterValidator(_iso_date)]

NPS_SCHEME_CODE = r"^SM[0-9]{6}$"  # the CRA's code for an NPS scheme; \d would also match other scripts' digits


class NpsSchemeInput(InputModel):
    """One NPS investment option: the scheme, the share of new contributions it gets and, optionally, the units
    held on the balance date (from the statement)."""
    scheme_code: str = Field(..., pattern=NPS_SCHEME_CODE)
    scheme_name: str = Field(..., min_length=1, max_length=150)
    allocation_pct: float = Field(..., ge=0, le=100)
    units: Optional[float] = Field(None, gt=0, le=MAX_UNITS)


class NpsSchemeStored(NpsSchemeInput):
    """A scheme as stored: the input plus what pricing worked out (absent while the asset is unpriced)."""
    nav: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)
    nav_date: Optional[IsoDate] = None
    base_units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)
    contribution_units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)


class NpsSchemeView(NpsSchemeStored):
    """A scheme as the API returns it: units held today and their value, when priced."""
    current_units: Optional[float] = None
    current_value: Optional[float] = None


class NpsSchemeOption(BaseModel):
    """An NPS scheme the form can pick from, with its latest NAV."""
    scheme_code: str
    scheme_name: str
    pfm_name: Optional[str] = None
    nav: Optional[float] = None
    nav_date: Optional[str] = None


def _check_nps_schemes(schemes: List[NpsSchemeInput]) -> List[NpsSchemeInput]:
    codes = [s.scheme_code for s in schemes]
    if len(set(codes)) != len(codes):
        raise PydanticCustomError("nps_schemes", "Each scheme can be added once")
    # float noise: three shares of 33.33 leave a gap of 0.010000000000005 to 100, just over 0.01, so round first
    if round(abs(sum(s.allocation_pct for s in schemes) - 100), 6) > 0.01:
        raise PydanticCustomError("nps_schemes", "Allocations must add up to 100%")
    with_units = sum(1 for s in schemes if s.units is not None)
    if 0 < with_units < len(schemes):
        raise PydanticCustomError("nps_schemes", "Enter units for every scheme or for none")
    return schemes


NpsSchemes = Annotated[List[NpsSchemeInput], Field(min_length=1, max_length=10), AfterValidator(_check_nps_schemes)]
StoredNpsSchemes = Annotated[List[NpsSchemeStored], Field(min_length=1, max_length=10),
                             AfterValidator(_check_nps_schemes)]


class AssetCategory(str, Enum):
    CASH = "cash"
    INVESTMENTS = "investments"
    REAL_ESTATE = "real_estate"
    VEHICLES = "vehicles"
    RETIREMENT = "retirement"
    CRYPTO = "crypto"
    EPF = "epf"
    PPF = "ppf"
    NPS = "nps"
    GOLD = "gold"
    SGB = "sgb"          # Sovereign Gold Bonds
    BONDS = "bonds"
    ESOP_RSU = "esop_rsu"
    OTHER = "other"

class LiabilityCategory(str, Enum):
    MORTGAGE = "mortgage"
    CAR_LOAN = "car_loan"
    STUDENT_LOAN = "student_loan"
    CREDIT_CARD = "credit_card"
    PERSONAL_LOAN = "personal_loan"
    OTHER = "other"

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

class User(BaseModel):
    id: str
    username: str
    email: str
    created_at: str

class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: str
    mfa_required: bool = False
    mfa_token: Optional[str] = None

class TokenData(BaseModel):
    username: Optional[str] = None

class MfaLoginRequest(BaseModel):
    mfa_token: str
    code: str = Field(..., max_length=64)

class TwoFactorEnable(BaseModel):
    password: str
    code: str = Field(..., max_length=64)

class TwoFactorDisable(BaseModel):
    password: str
    code: str = Field(..., max_length=64)

class TwoFactorStatus(BaseModel):
    enabled: bool
    backup_codes_remaining: int

class TwoFactorSetup(BaseModel):
    secret: str
    otpauth_uri: str

class TwoFactorBackupCodes(BaseModel):
    backup_codes: List[str]

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    code: Optional[str] = Field(None, max_length=64)

class AssetBase(InputModel):
    name: str = Field(..., min_length=1, max_length=100)
    value: float = Field(..., ge=0, le=MAX_AMOUNT)
    category: AssetCategory
    description: Optional[str] = None
    annual_change_rate: Optional[float] = Field(None, ge=-99, le=100)  # % per year; negative depreciates
    valuation_date: Optional[IsoDate] = None  # the date `value` was accurate
    monthly_contribution: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # EPF/PPF
    interest_rate: Optional[float] = Field(None, ge=0, le=100)  # EPF/PPF, % per year
    quantity: Optional[float] = Field(None, gt=0, le=MAX_UNITS)  # grams or units
    unit_price: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # price per gram or unit
    yearly_contribution: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # NPS: the subscriber's own, per year
    yearly_contribution_month: Optional[int] = Field(None, ge=1, le=12)  # NPS: month it's paid (March if unset)
    nps_schemes: Optional[NpsSchemes] = None  # NPS investment options

class Asset(AssetBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str
    current_value: float = 0
    nps_schemes: Optional[List[NpsSchemeView]] = None
    nps_priced_through: Optional[str] = None  # contributions up to this date are converted to units

class AssetCreate(AssetBase):
    pass

class AssetRestore(AssetCreate):
    """An asset as stored in a backup file: the create fields plus what NPS pricing worked out"""
    nps_schemes: Optional[StoredNpsSchemes] = None
    nps_priced_through: Optional[IsoDate] = None

class AssetUpdate(InputModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    category: Optional[AssetCategory] = None
    description: Optional[str] = None
    annual_change_rate: Optional[float] = Field(None, ge=-99, le=100)  # % per year; negative depreciates
    valuation_date: Optional[IsoDate] = None  # the date `value` was accurate
    monthly_contribution: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # EPF/PPF
    interest_rate: Optional[float] = Field(None, ge=0, le=100)  # EPF/PPF, % per year
    quantity: Optional[float] = Field(None, gt=0, le=MAX_UNITS)  # grams or units
    unit_price: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # price per gram or unit
    yearly_contribution: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # NPS: the subscriber's own, per year
    yearly_contribution_month: Optional[int] = Field(None, ge=1, le=12)  # NPS: month it's paid (March if unset)
    nps_schemes: Optional[NpsSchemes] = None  # NPS investment options

class LiabilityBase(InputModel):
    name: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., ge=0, le=MAX_AMOUNT)
    category: LiabilityCategory
    interest_rate: Optional[float] = Field(None, ge=0, le=100)
    description: Optional[str] = None
    emi: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)
    balance_date: Optional[IsoDate] = None  # the date `amount` was the balance; EMIs fall on its anniversaries
    tenure_months: Optional[int] = Field(None, ge=1, le=600)  # input helper: EMI is derived from it when not given

class Liability(LiabilityBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str
    outstanding: float = 0
    amortized: bool = False
    months_remaining: Optional[int] = None
    payoff_date: Optional[str] = None
    interest_remaining: Optional[float] = None
    next_emi_interest: Optional[float] = None
    next_emi_principal: Optional[float] = None
    emi_too_low: bool = False
    last_emi_date: Optional[str] = None  # the latest EMI anniversary on or before today: where edits re-anchor

class LiabilityCreate(LiabilityBase):
    pass

class LiabilityUpdate(InputModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    amount: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    category: Optional[LiabilityCategory] = None
    interest_rate: Optional[float] = Field(None, ge=0, le=100)
    description: Optional[str] = None
    emi: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)
    balance_date: Optional[IsoDate] = None  # the date `amount` was the balance; EMIs fall on its anniversaries
    tenure_months: Optional[int] = Field(None, ge=1, le=600)  # input helper: EMI is derived from it when not given

class NetWorthSnapshot(BaseModel):
    id: str
    user_id: str
    total_assets: float
    total_liabilities: float
    net_worth: float
    timestamp: str
    # Breakdowns exist on newer snapshots only
    assets_by_category: Optional[dict] = None
    liabilities_by_category: Optional[dict] = None
    assets_by_class: Optional[dict] = None

class SnapshotRestore(InputModel):
    """A snapshot as stored in a backup file"""
    # Totals of valid holdings can pass 1e18 (1e9 shares at 1e15 each), so the cap is loose; InputModel rejects NaN/inf
    total_assets: float = Field(..., ge=0, le=1e300)
    total_liabilities: float = Field(..., ge=0, le=1e300)
    timestamp: str
    assets_by_category: Optional[Dict[str, Annotated[float, Field(ge=0, le=1e300)]]] = None
    liabilities_by_category: Optional[Dict[str, Annotated[float, Field(ge=0, le=1e300)]]] = None
    assets_by_class: Optional[Dict[str, Annotated[float, Field(ge=0, le=1e300)]]] = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_iso(cls, value: str) -> str:
        datetime.fromisoformat(value)  # raises ValueError for anything that isn't an ISO date-time
        return value

class DashboardMetrics(BaseModel):
    total_assets: float
    total_liabilities: float
    net_worth: float
    debt_to_asset_ratio: float
    assets_by_category: dict
    liabilities_by_category: dict
    net_worth_history: List[NetWorthSnapshot]
    asset_count: int
    liability_count: int
    maturities: List[dict] = []
    assets_by_class: dict = {}
    snapshot_frequency: str = "monthly"
    next_snapshot_on: Optional[str] = None  # the first day the next automatic snapshot is due


SnapshotFrequency = Literal["weekly", "fortnightly", "monthly", "quarterly"]


class SnapshotSettings(InputModel):
    frequency: SnapshotFrequency


class SnapshotSettingsView(BaseModel):
    frequency: str
    next_snapshot_on: str

# Bank Account Models
class AccountType(str, Enum):
    SAVINGS = "savings"
    CURRENT = "current"
    SALARY = "salary"
    FD = "fd"
    RD = "rd"

class BankAccountBase(InputModel):
    bank_name: str = Field(..., min_length=1, max_length=100)
    account_number: str = Field(..., min_length=4, max_length=20)
    account_type: AccountType
    balance: float = Field(..., ge=0, le=MAX_AMOUNT)
    branch: Optional[str] = None
    ifsc_code: Optional[str] = None
    interest_rate: Optional[float] = Field(None, ge=0, le=100)  # FD/RD only, % per year
    start_date: Optional[IsoDate] = None
    maturity_date: Optional[IsoDate] = None
    monthly_deposit: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)  # RD installment

class BankAccount(BankAccountBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str
    current_value: float = 0
    maturity_value: Optional[float] = None
    matured: bool = False
    days_to_maturity: Optional[int] = None

class BankAccountCreate(BankAccountBase):
    pass

class BankAccountUpdate(InputModel):
    bank_name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_number: Optional[str] = Field(None, min_length=4, max_length=20)
    account_type: Optional[AccountType] = None
    balance: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    branch: Optional[str] = None
    ifsc_code: Optional[str] = None
    interest_rate: Optional[float] = Field(None, ge=0, le=100)  # FD/RD only, % per year
    start_date: Optional[IsoDate] = None
    maturity_date: Optional[IsoDate] = None
    monthly_deposit: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)  # RD installment

# Insurance Models
class InsuranceType(str, Enum):
    LIFE = "life"
    HEALTH = "health"
    TERM = "term"
    VEHICLE = "vehicle"
    HOME = "home"
    OTHER = "other"

class InsuranceBase(InputModel):
    policy_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=100)
    policy_number: Optional[str] = None
    insurance_type: InsuranceType
    sum_assured: float = Field(..., ge=0, le=MAX_AMOUNT)
    premium: float = Field(..., ge=0, le=MAX_AMOUNT)
    premium_frequency: str = "yearly"  # monthly, quarterly, yearly
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    nominee: Optional[str] = None
    notes: Optional[str] = None

class Insurance(InsuranceBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class InsuranceCreate(InsuranceBase):
    pass

class InsuranceUpdate(InputModel):
    policy_name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider: Optional[str] = Field(None, min_length=1, max_length=100)
    policy_number: Optional[str] = None
    insurance_type: Optional[InsuranceType] = None
    sum_assured: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    premium: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    premium_frequency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    nominee: Optional[str] = None
    notes: Optional[str] = None
    nominee: Optional[str] = None

# Mutual Fund Models
class MutualFundCategory(str, Enum):
    EQUITY = "equity"
    DEBT = "debt"
    HYBRID = "hybrid"
    ELSS = "elss"
    INDEX = "index"
    LIQUID = "liquid"
    OTHER = "other"

SipFrequency = Literal["weekly", "monthly", "quarterly"]


def _check_sip_dates(start: Optional[str], end: Optional[str]) -> None:
    if start and end and end < start:
        raise PydanticCustomError("sip_dates", "SIP end date must be on or after its start date")


class MutualFundBase(InputModel):
    fund_name: str = Field(..., min_length=1, max_length=150)
    amc: str = Field(..., min_length=1, max_length=100)  # Asset Management Company
    category: MutualFundCategory
    folio_number: Optional[str] = None
    units: float = Field(default=0, ge=0, le=MAX_UNITS)
    avg_nav: float = Field(default=0, ge=0, le=MAX_AMOUNT)  # Average Net Asset Value (purchase NAV)
    current_nav: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # Current NAV (fetched from API)
    invested_amount: float = Field(..., ge=0, le=MAX_AMOUNT)
    current_value: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # Optional - calculated from units * current_nav
    sip_amount: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # SIP amount if applicable
    sip_frequency: Optional[SipFrequency] = None  # monthly when a SIP is set without one
    sip_day: Optional[int] = Field(None, ge=1, le=31)  # monthly/quarterly: the day each installment lands
    sip_start_date: Optional[IsoDate] = None  # the first installment
    sip_end_date: Optional[IsoDate] = None  # no installment after this
    holdings_date: Optional[IsoDate] = None  # when `units` and `invested_amount` were accurate
    scheme_code: Optional[str] = None  # AMFI scheme code for NAV fetching

    @model_validator(mode="after")
    def sip_dates_in_order(self):
        _check_sip_dates(self.sip_start_date, self.sip_end_date)
        return self

class MutualFund(MutualFundBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str
    # The view's numbers are computed, never stored, so unlike the input fields they have no upper bound:
    # installments pile up without limit, and the response must not fail on a number the input cap would refuse
    current_value: Optional[float] = Field(None, ge=0)
    sip_units: Optional[float] = None  # units the SIP installments bought, up to sip_priced_through
    sip_invested: Optional[float] = None
    sip_priced_through: Optional[str] = None
    total_units: Optional[float] = Field(None, ge=0)  # units + SIP units
    total_invested: Optional[float] = Field(None, ge=0)  # invested amount + SIP installments

class MutualFundCreate(MutualFundBase):
    pass

class MutualFundRestore(MutualFundCreate):
    """A mutual fund as stored in a backup file: the create fields plus what SIP pricing worked out"""
    sip_units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)
    sip_invested: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    sip_priced_through: Optional[IsoDate] = None

class MutualFundUpdate(InputModel):
    fund_name: Optional[str] = Field(None, min_length=1, max_length=150)
    amc: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[MutualFundCategory] = None
    folio_number: Optional[str] = None
    units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)
    avg_nav: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    current_nav: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    invested_amount: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    current_value: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    sip_amount: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    sip_frequency: Optional[SipFrequency] = None
    sip_day: Optional[int] = Field(None, ge=1, le=31)
    sip_start_date: Optional[IsoDate] = None
    sip_end_date: Optional[IsoDate] = None
    holdings_date: Optional[IsoDate] = None
    scheme_code: Optional[str] = None

    @model_validator(mode="after")
    def sip_dates_in_order(self):
        _check_sip_dates(self.sip_start_date, self.sip_end_date)
        return self

# Equity/Stock Models
class StockMarket(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"

# US listings are priced in USD and converted to INR wherever values are totalled
USD_MARKETS = frozenset({StockMarket.NASDAQ.value, StockMarket.NYSE.value})

class EquityBase(InputModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    company_name: Optional[str] = None
    market: StockMarket
    quantity: int = Field(..., ge=1, le=MAX_QUANTITY)
    avg_buy_price: float = Field(..., ge=0, le=MAX_AMOUNT)
    current_price: Optional[float] = Field(None, le=MAX_AMOUNT)
    notes: Optional[str] = None

class Equity(EquityBase):
    id: str
    user_id: str
    invested_amount: float
    current_value: float
    gain_loss: float
    gain_loss_percent: float
    created_at: str
    updated_at: str

class EquityCreate(InputModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    company_name: Optional[str] = None
    market: StockMarket
    quantity: int = Field(..., ge=1, le=MAX_QUANTITY)
    avg_buy_price: float = Field(..., ge=0, le=MAX_AMOUNT)
    notes: Optional[str] = None

class EquityUpdate(InputModel):
    symbol: Optional[str] = Field(None, min_length=1, max_length=20)
    company_name: Optional[str] = None
    market: Optional[StockMarket] = None
    quantity: Optional[int] = Field(None, ge=1, le=MAX_QUANTITY)
    avg_buy_price: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    current_price: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    notes: Optional[str] = None

class EquityRestore(EquityCreate):
    """An equity as stored in a backup file: the create fields plus the last known price"""
    current_price: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)

# Goal Models
class GoalBase(InputModel):
    target_amount: float = Field(..., ge=0, le=MAX_AMOUNT)
    name: Optional[str] = "Net Worth Goal"

class Goal(GoalBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class GoalCreate(GoalBase):
    pass

class GoalUpdate(InputModel):
    target_amount: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    name: Optional[str] = None


