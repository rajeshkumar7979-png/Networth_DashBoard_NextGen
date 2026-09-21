import pytest

from lib.gold import infer_category

# Exact per-fund mapping captured from the committed sample workbook using the
# same infer_category implementation (verified earlier). Kept as a golden to
# catch any drift in classification rules.
EXPECTED_WORKBOOK_CATEGORIES = {
    "Axis Large Cap Fund Direct Growth": "Large Cap",
    "DSP Large Cap Fund Growth": "Large Cap",
    "DSP NIFTY NEXT 50 INDEX FUND - DIRECT PLAN": "Index",
    "EDELWEISS MID CAP FUND - DIRECT PLAN": "Mid Cap",
    "HDFC Gold ETF Fund of Fund": "Gold",
    "HDFC LIQUID FUND - DIRECT PLAN": "Liquid",
    "HDFC Large Cap Fund Growth - Regular": "Large Cap",
    "HDFC MID CAP FUND - DIRECT PLAN - GROWTH OPTION": "Mid Cap",
    "ICICI PRUDENTIAL INFRASTRUCTURE FUND - DIRECT PLAN": "Sectoral/Thematic",
    "ICICI Prudential BHARAT 22 FOF Direct Growth": "Sectoral/Thematic",
    "ICICI Prudential Gold ETF FoF Growth": "Gold",
    "ICICI Prudential Value Discovery Fund Direct Growth": "Contra/Value",
    "INVESCO INDIA SMALL CAP FUND - DIRECT GROWTH": "Small Cap",
    "ITI SMALL CAP FUND - DIRECT PLAN": "Small Cap",
    "Kotak Hybrid Equity Fund Growth": "Hybrid",
    "Kotak Infrastructure & Economic Reform Fund Direct Growth": "Sectoral/Thematic",
    "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN": "Flexi Cap",
    "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN GROWTH": "Flexi Cap",
    "PARAG PARIKH LIQUID FUND-DIRECT PLAN-GROWTH": "Liquid",
    "Quant Small Cap Fund Direct Plan Growth": "Small Cap",
    "SBI Contra Direct Plan Growth": "Contra/Value",
    "UTI NIFTY NEXT 50 INDEX FUND - DIRECT GROWTH PLAN": "Index",
}


def test_workbook_category_mapping(mf_df):
    names = sorted(str(n).strip() for n in mf_df["Fund Name"].astype(str).unique())
    assert names == sorted(EXPECTED_WORKBOOK_CATEGORIES)
    for name in names:
        assert infer_category(name) == EXPECTED_WORKBOOK_CATEGORIES[name]


def test_every_category_inferable_is_not_other():
    for name, cat in EXPECTED_WORKBOOK_CATEGORIES.items():
        assert cat not in ("Gold",) or name.startswith(("HDFC Gold", "ICICI Prudential Gold"))
        assert cat != "Other Equity" and cat != "Other Debt"


@pytest.mark.parametrize("name,category", [
    ("HDFC Liquid Fund", "Liquid"),
    ("Nippon India Gilt Fund - Direct", "Gilt"),
    ("SBI Magnum Overnight Fund", "Overnight"),
    ("Axis Ultra Short Term Fund", "Ultra Short"),
    ("HDFC Gold ETF Fund of Fund", "Gold"),
    ("ICICI Prudential Corporate Bond Fund", "Corporate Bond"),
    ("UTI Nifty 50 Index Fund - Direct", "Index"),
    ("Parag Parikh Tax Saver ELSS", "ELSS"),
    ("Kotak Infrastructure & Economic Reform Fund", "Sectoral/Thematic"),
    ("Quant Small Cap Fund", "Small Cap"),
    ("Axis Bluechip Fund", "Large Cap"),
])
def test_rule_based_categories(name, category):
    assert infer_category(name) == category


def test_amfi_name_has_priority_over_fund_display_name():
    assert infer_category("HDFC Liquid Fund", amfi_name="HDFC Gold Fund (FoF)") == "Gold"
    assert infer_category("Nippon India Growth Fund", amfi_name="SBI Bluechip Fund") == "Large Cap"


def test_empty_names_fall_to_other_equity():
    assert infer_category("", None) == "Other Equity"
    assert infer_category(None, None) == "Other Equity"


def test_unmatched_debt_keywords_collapse_to_other_debt():
    assert infer_category("XYZ Income Fund") == "Other Debt"
    assert infer_category("ABC Dynamic Bond") == "Other Debt"