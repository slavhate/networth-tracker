from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class AssetCategory(str, Enum):
    CASH = "cash"
    INVESTMENTS = "investments"
    REAL_ESTATE = "real_estate"
    VEHICLES = "vehicles"
    RETIREMENT = "retirement"
    CRYPTO = "crypto"
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
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    value: float = Field(..., ge=0)
    category: AssetCategory
    description: Optional[str] = None

class Asset(AssetBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[float] = None
    category: Optional[AssetCategory] = None
    description: Optional[str] = None

class LiabilityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., ge=0)
    category: LiabilityCategory
    interest_rate: Optional[float] = Field(None, ge=0, le=100)
    description: Optional[str] = None

class Liability(LiabilityBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class LiabilityCreate(LiabilityBase):
    pass

class LiabilityUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[LiabilityCategory] = None
    interest_rate: Optional[float] = None
    description: Optional[str] = None

class NetWorthSnapshot(BaseModel):
    id: str
    user_id: str
    total_assets: float
    total_liabilities: float
    net_worth: float
    timestamp: str

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

# Bank Account Models
class AccountType(str, Enum):
    SAVINGS = "savings"
    CURRENT = "current"
    SALARY = "salary"
    FD = "fd"
    RD = "rd"

class BankAccountBase(BaseModel):
    bank_name: str = Field(..., min_length=1, max_length=100)
    account_number: str = Field(..., min_length=4, max_length=20)
    account_type: AccountType
    balance: float = Field(..., ge=0)
    branch: Optional[str] = None
    ifsc_code: Optional[str] = None

class BankAccount(BankAccountBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class BankAccountCreate(BankAccountBase):
    pass

class BankAccountUpdate(BaseModel):
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_type: Optional[AccountType] = None
    balance: Optional[float] = None
    branch: Optional[str] = None
    ifsc_code: Optional[str] = None

# Insurance Models
class InsuranceType(str, Enum):
    LIFE = "life"
    HEALTH = "health"
    TERM = "term"
    VEHICLE = "vehicle"
    HOME = "home"
    OTHER = "other"

class InsuranceBase(BaseModel):
    policy_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=100)
    policy_number: Optional[str] = None
    insurance_type: InsuranceType
    sum_assured: float = Field(..., ge=0)
    premium: float = Field(..., ge=0)
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

class InsuranceUpdate(BaseModel):
    policy_name: Optional[str] = None
    provider: Optional[str] = None
    policy_number: Optional[str] = None
    insurance_type: Optional[InsuranceType] = None
    sum_assured: Optional[float] = None
    premium: Optional[float] = None
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

class MutualFundBase(BaseModel):
    fund_name: str = Field(..., min_length=1, max_length=150)
    amc: str = Field(..., min_length=1, max_length=100)  # Asset Management Company
    category: MutualFundCategory
    folio_number: Optional[str] = None
    units: float = Field(default=0, ge=0)
    avg_nav: float = Field(default=0, ge=0)  # Average Net Asset Value (purchase NAV)
    current_nav: Optional[float] = None  # Current NAV (fetched from API)
    invested_amount: float = Field(..., ge=0)
    current_value: Optional[float] = None  # Optional - calculated from units * current_nav
    sip_amount: Optional[float] = None  # SIP amount if applicable
    scheme_code: Optional[str] = None  # AMFI scheme code for NAV fetching

class MutualFund(MutualFundBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class MutualFundCreate(MutualFundBase):
    pass

class MutualFundUpdate(BaseModel):
    fund_name: Optional[str] = None
    amc: Optional[str] = None
    category: Optional[MutualFundCategory] = None
    folio_number: Optional[str] = None
    units: Optional[float] = None
    avg_nav: Optional[float] = None
    current_nav: Optional[float] = None
    invested_amount: Optional[float] = None
    current_value: Optional[float] = None
    sip_amount: Optional[float] = None
    scheme_code: Optional[str] = None

# Equity/Stock Models
class StockMarket(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NASDAQ = "NASDAQ"

class EquityBase(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    company_name: Optional[str] = None
    market: StockMarket
    quantity: int = Field(..., ge=1)
    avg_buy_price: float = Field(..., ge=0)
    current_price: Optional[float] = None
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

class EquityCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    company_name: Optional[str] = None
    market: StockMarket
    quantity: int = Field(..., ge=1)
    avg_buy_price: float = Field(..., ge=0)
    notes: Optional[str] = None

class EquityUpdate(BaseModel):
    symbol: Optional[str] = None
    company_name: Optional[str] = None
    market: Optional[StockMarket] = None
    quantity: Optional[int] = None
    avg_buy_price: Optional[float] = None
    current_price: Optional[float] = None
    notes: Optional[str] = None

# Goal Models
class GoalBase(BaseModel):
    target_amount: float = Field(..., ge=0)
    name: Optional[str] = "Net Worth Goal"

class Goal(GoalBase):
    id: str
    user_id: str
    created_at: str
    updated_at: str

class GoalCreate(GoalBase):
    pass

class GoalUpdate(BaseModel):
    target_amount: Optional[float] = None
    name: Optional[str] = None


