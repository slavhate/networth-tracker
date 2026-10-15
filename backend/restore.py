"""Parse and validate a backup file for restore. Nothing here touches storage."""
import json
import math
from typing import Any, Dict, Type

from pydantic import BaseModel, ValidationError

from models import (
    AssetRestore, LiabilityRestore, BankAccountRestore, InsuranceRestore,
    MutualFundRestore, EquityRestore, SnapshotRestore, GoalRestore,
)

MAX_BACKUP_BYTES = 10 * 1024 * 1024
SIP_PRICING_KEYS = ("sip_units", "sip_invested", "sip_priced_through")

# Backup sections holding a list of items, and the model each item must satisfy
LIST_SECTIONS: Dict[str, Type[BaseModel]] = {
    "assets": AssetRestore,
    "liabilities": LiabilityRestore,
    "bank_accounts": BankAccountRestore,
    "insurances": InsuranceRestore,
    "mutual_funds": MutualFundRestore,
    "equities": EquityRestore,
    "snapshots": SnapshotRestore,
}


class RestoreError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text} is too large")
    return value


def _reject_constant(name: str):
    raise ValueError(f"{name} is not valid JSON")


def _clean(model: Type[BaseModel], item: Any, where: str) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise RestoreError(400, f"{where}: must be an object")
    try:
        cleaned = model.model_validate(item).model_dump(mode="json")
    except ValidationError as e:
        first = e.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        raise RestoreError(400, f"{where}.{field}: {first['msg']}" if field else f"{where}: {first['msg']}")
    return cleaned


def parse_backup(raw: bytes) -> Dict[str, Any]:
    """Return every LIST_SECTIONS key (list of clean dicts) plus "goal" (clean dict or None).

    Raises RestoreError on the first problem, so the caller can reject the file before writing anything.
    """
    if len(raw) > MAX_BACKUP_BYTES:
        raise RestoreError(413, "Backup file too large (max 10MB)")
    try:
        backup = json.loads(raw.decode("utf-8-sig"), parse_float=_finite_float, parse_constant=_reject_constant)
    # covers UnicodeDecodeError, json.JSONDecodeError and JSON nested too deeply to parse
    except (ValueError, RecursionError):
        raise RestoreError(400, "Invalid JSON file")
    if not isinstance(backup, dict):
        raise RestoreError(400, "Backup must be a JSON object")
    if not any(key in backup for key in (*LIST_SECTIONS, "goal")):
        raise RestoreError(400, "This file doesn't look like a Net Worth Tracker backup")

    cleaned: Dict[str, Any] = {}
    for section, model in LIST_SECTIONS.items():
        items = backup.get(section, [])
        if not isinstance(items, list):
            raise RestoreError(400, f"{section} must be a list")
        cleaned[section] = [_clean(model, item, f"{section}[{i}]") for i, item in enumerate(items)]

    for i, account in enumerate(cleaned["bank_accounts"]):
        start, maturity = account.get("start_date"), account.get("maturity_date")
        if start and maturity and maturity < start:  # normalized ISO dates compare as dates
            raise RestoreError(400, f"bank_accounts[{i}]: Maturity date must be after the start date")

    for asset in cleaned["assets"]:
        # Only NPS pricing sets nps_priced_through, so an asset that was never priced omits it, as a new asset does
        if asset.get("nps_priced_through") is None:
            asset.pop("nps_priced_through", None)

    for fund in cleaned["mutual_funds"]:
        # Only SIP pricing sets these, so a fund that was never priced omits them, as a new fund does
        for key in SIP_PRICING_KEYS:
            if fund.get(key) is None:
                fund.pop(key, None)

    goal = backup.get("goal")
    cleaned["goal"] = None if goal is None else _clean(GoalRestore, goal, "goal")
    return cleaned
