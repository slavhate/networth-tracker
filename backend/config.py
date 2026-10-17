from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import secrets
import logging

logger = logging.getLogger(__name__)

def _default_secret_key() -> str:
    key = secrets.token_hex(32)
    logger.warning(
        "SECRET_KEY not set — using auto-generated key. "
        "Tokens will not survive restarts. "
        "Set SECRET_KEY env var for persistent sessions. "
        "Each process gets its own key, so run a single worker unless SECRET_KEY is set."
    )
    return key

MIN_SECRET_KEY_LENGTH = 32

class Settings(BaseSettings):
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    MFA_TOKEN_EXPIRE_MINUTES: int = 5  # 2FA login challenge lifetime
    DATA_FILE: str = os.path.join(os.path.dirname(__file__), "..", "data", "data.json")
    CREATE_DEMO_DATA: bool = False
    ALLOW_REGISTRATION: bool = True  # false: only existing users can log in (POST /api/auth/register returns 403)
    # Comma-separated addresses or networks of reverse proxies whose X-Real-IP / X-Forwarded-For name the client
    # (for the login limiter). The default is the range Docker allocates bridge networks from, where the bundled
    # docker-compose nginx sits; an address outside the list is counted as itself, whatever headers it sends.
    TRUSTED_PROXIES: str = "172.16.0.0/12"
    DEMO_USERNAME: str = "demo"
    DEMO_PASSWORD: str = ""  # empty = a random password is generated when the demo user is created
    NPS_NAV_API_URL: str = "https://npsnav.in/api"  # NPS scheme list and NAV history (npsnav.in, or a mirror)
    METAL_PRICE_API_URL: str = "https://api.gold-api.com/price"  # gold (XAU) and silver (XAG) spot, USD per troy ounce
    # India's customs duty on gold and silver, % added to the international spot price (GST is not: market rates are
    # quoted before GST)
    METAL_IMPORT_DUTY_PCT: float = 6.0

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()

def check_secret_key(s: Settings) -> None:
    """Fill in a random key when none is set; warn when the one set is too short."""
    if not s.SECRET_KEY:
        s.SECRET_KEY = _default_secret_key()
    elif len(s.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
        # A short key can be guessed offline from any token, which then lets anyone sign in as any user
        logger.warning(
            "SECRET_KEY is only %d characters long; use at least %d random characters "
            "(generate one with: openssl rand -hex 32).",
            len(s.SECRET_KEY), MIN_SECRET_KEY_LENGTH,
        )

check_secret_key(settings)
