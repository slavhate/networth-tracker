"""NPS asset fields: contributions and investment options (schemes)."""
import pytest
from pydantic import ValidationError

from models import AssetCreate, AssetRestore, AssetUpdate


def scheme(code="SM900001", pct=100, units=None, name=None):
    row = {"scheme_code": code, "scheme_name": name or f"TEST PENSION FUND SCHEME E - TIER I {code}",
           "allocation_pct": pct}
    if units is not None:
        row["units"] = units
    return row


def nps(**extra):
    return {"name": "NPS", "category": "nps", "value": 100000, "valuation_date": "2026-03-31", **extra}


def messages(exc):
    return " | ".join(e["msg"] for e in exc.value.errors())


def test_contribution_fields_are_accepted():
    asset = AssetCreate(**nps(monthly_contribution=6000, yearly_contribution=50000, yearly_contribution_month=3))
    assert (asset.yearly_contribution, asset.yearly_contribution_month) == (50000, 3)


@pytest.mark.parametrize("month", [0, 13])
def test_contribution_month_is_a_calendar_month(month):
    with pytest.raises(ValidationError):
        AssetCreate(**nps(yearly_contribution=50000, yearly_contribution_month=month))


def test_schemes_are_accepted():
    asset = AssetCreate(**nps(nps_schemes=[scheme("SM900001", 75), scheme("SM900002", 25)]))
    assert [s.scheme_code for s in asset.nps_schemes] == ["SM900001", "SM900002"]


def test_allocations_may_be_rounded():
    rows = [scheme("SM900001", 33.33), scheme("SM900002", 33.33), scheme("SM900003", 33.34)]
    assert len(AssetCreate(**nps(nps_schemes=rows)).nps_schemes) == 3


def test_allocations_must_add_up_to_100():
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=[scheme("SM900001", 60), scheme("SM900002", 30)]))
    assert "Allocations must add up to 100%" in messages(exc)


def test_a_scheme_can_be_added_once():
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=[scheme("SM900001", 50), scheme("SM900001", 50)]))
    assert "Each scheme can be added once" in messages(exc)


def test_units_for_every_scheme_or_none():
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=[scheme("SM900001", 50, units=10), scheme("SM900002", 50)]))
    assert "Enter units for every scheme or for none" in messages(exc)


@pytest.mark.parametrize("code", ["SM90001", "XX900001", "sm900001", "SM9000011"])
def test_scheme_code_format(code):
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=[scheme(code)]))


def test_at_most_ten_schemes():
    rows = [scheme(f"SM90{i:04d}", 100 / 11) for i in range(11)]
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=rows))


def test_an_empty_scheme_list_is_rejected():
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=[]))


def test_input_cannot_set_priced_fields():
    row = {**scheme(), "nav": 12.5, "base_units": 5, "contribution_units": 1, "nav_date": "2026-03-31"}
    stored = AssetCreate(**nps(nps_schemes=[row], nps_priced_through="2026-03-31")).model_dump()
    assert set(stored["nps_schemes"][0]) == {"scheme_code", "scheme_name", "allocation_pct", "units"}
    assert "nps_priced_through" not in stored


def test_update_accepts_and_clears_nps_fields():
    update = AssetUpdate(nps_schemes=None, yearly_contribution=None, yearly_contribution_month=None)
    assert update.model_dump(exclude_unset=True) == {
        "nps_schemes": None, "yearly_contribution": None, "yearly_contribution_month": None}
    with pytest.raises(ValidationError):
        AssetUpdate(nps_schemes=[scheme("SM900001", 40)])


def test_restore_keeps_priced_fields():
    row = {**scheme(), "nav": 12.5, "nav_date": "2026-03-31", "base_units": 5.0, "contribution_units": 1.0}
    restored = AssetRestore(**nps(nps_schemes=[row], nps_priced_through="2026-04-01")).model_dump()
    assert restored["nps_schemes"][0]["nav"] == 12.5
    assert restored["nps_priced_through"] == "2026-04-01"


@pytest.mark.parametrize("bad", [{"nav": -1}, {"nav": 0}, {"base_units": 2e12}, {"nav_date": "2026-02-30"}])
def test_restore_bounds_priced_fields(bad):
    with pytest.raises(ValidationError):
        AssetRestore(**nps(nps_schemes=[{**scheme(), **bad}]))


def test_three_schemes_at_33_33_are_accepted():
    # 33.33 x 3 sums to 99.99: the 0.01 gap is what rounding leaves, not a missing share
    rows = [scheme("SM900001", 33.33), scheme("SM900002", 33.33), scheme("SM900003", 33.33)]
    assert len(AssetCreate(**nps(nps_schemes=rows)).nps_schemes) == 3


def test_three_schemes_at_33_3_are_rejected():
    rows = [scheme("SM900001", 33.3), scheme("SM900002", 33.3), scheme("SM900003", 33.3)]
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=rows))
    assert "Allocations must add up to 100%" in messages(exc)


def test_scheme_code_digits_are_ascii():
    # \d in a regex also matches other scripts' digits; the CRA's code uses ASCII digits only
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=[scheme("SM٠١٢٣٤٥")]))


def test_update_ignores_server_kept_fields():
    row = {**scheme(), "nav": 12.5, "nav_date": "2026-03-31", "base_units": 5, "contribution_units": 1}
    update = AssetUpdate(nps_schemes=[row], nps_priced_through="2026-03-31").model_dump(exclude_unset=True)
    assert {"scheme_code", "scheme_name", "allocation_pct"} <= set(update["nps_schemes"][0])
    assert not {"nav", "nav_date", "base_units", "contribution_units"} & set(update["nps_schemes"][0])
    assert "nps_priced_through" not in update


def test_restore_rejects_allocations_that_do_not_add_up():
    with pytest.raises(ValidationError) as exc:
        AssetRestore(**nps(nps_schemes=[scheme("SM900001", 60), scheme("SM900002", 30)]))
    assert "Allocations must add up to 100%" in messages(exc)


def test_restore_rejects_a_scheme_listed_twice():
    with pytest.raises(ValidationError) as exc:
        AssetRestore(**nps(nps_schemes=[scheme("SM900001", 50), scheme("SM900001", 50)]))
    assert "Each scheme can be added once" in messages(exc)
