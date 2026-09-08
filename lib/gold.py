# -------------------------------------------------
# Gold routing + MF category inference.
# Extracted verbatim from pages/1_Command_Center.py (Phase 0).
# No calculation changes in this phase.
# -------------------------------------------------
import re

CATEGORY_RULES = [
    ("Overnight", r"overnight"),
    ("Liquid", r"\bliquid\b"),
    ("Money Market", r"money\s*market"),
    ("Ultra Short", r"ultra\s*short"),
    ("Low Duration", r"low\s*duration"),
    ("Short Duration", r"short\s*(duration|term)\b"),
    ("Corporate Bond", r"corporate\s*bond"),
    ("Banking PSU", r"banking\s*(?:&|and)?\s*psu|psu\s*debt"),
    ("Gilt", r"\bgilt\b|g-?sec"),
    ("Arbitrage", r"arbitrage"),
    ("Conservative Hybrid", r"conservative\s*hybrid|hybrid\s*conservative"),
    ("Aggressive Hybrid", r"aggressive\s*hybrid|hybrid\s*aggressive|balanced\s*advantage|dynamic\s*asset"),
    ("Hybrid", r"\bhybrid\b|\bbalanced\b"),
    ("Small Cap", r"small\s*cap"),
    ("Mid Cap", r"mid\s*cap"),
    ("Large Cap", r"large\s*cap|blue\s*chip|bluechip"),
    ("Large & Mid", r"large\s*(?:&|and)\s*mid"),
    ("Flexi Cap", r"flexi\s*cap|multi\s*cap|focused"),
    ("ELSS", r"\belss\b|tax\s*saver|equity\s*linked"),
    ("Index", r"\bindex\b|next\s*50|nifty\s*50\b|sensex\b|etf\b"),
    ("International", r"international|global|us\s*equity|nasdaq|overseas|world\s*fund"),
    ("Contra/Value", r"\bcontra\b|value\s*discovery|\bvalue\b"),
    ("Dividend Yield", r"dividend\s*yield"),
    ("Sectoral/Thematic", r"infra|defence|pharma|healthcare|banking|financial|consumption|digital|technology|manufacturing|energy|commodity|reform|bharat\s*22|business\s*cycle|special\s*situations|thematic|sector"),
]

DEBT_LIKE = {
    "Overnight", "Liquid", "Money Market", "Ultra Short", "Low Duration",
    "Short Duration", "Corporate Bond", "Banking PSU", "Gilt", "Arbitrage",
}

SGB_TICKER_PATTERN = re.compile(r"^SGB.*-GB$", re.IGNORECASE)
GOLD_ETF_TICKERS = {"GOLDBEES", "GOLDSHARE", "GOLDCASE", "AXISGOLD", "QGOLDHALF", "BSLGOLDETF", "IVZINGOLD"}
GOLD_FUND_NAME_RE = re.compile(
    r"gold\s*(etf|fof|fund\s*of\s*fund|fund\s*of\s*funds)|\bgold\b.*\b(etf|fof)\b",
    re.IGNORECASE,
)


def is_gold_symbol(symbol: str) -> bool:
    s = (symbol or "").strip().upper()
    if not s:
        return False
    if SGB_TICKER_PATTERN.match(s):
        return True
    if s in GOLD_ETF_TICKERS or s.endswith("GOLD") or ("GOLD" in s and s.endswith("ETF")):
        return True
    return False


def is_gold_fund(fund_name: str) -> bool:
    return bool(GOLD_FUND_NAME_RE.search(fund_name or ""))


def infer_category(fund_name: str, amfi_name=None) -> str:
    if is_gold_fund(fund_name) or (amfi_name and is_gold_fund(amfi_name)):
        return "Gold"
    candidates = []
    if amfi_name and str(amfi_name).strip():
        candidates.append(str(amfi_name).strip())
    if fund_name and str(fund_name).strip():
        candidates.append(str(fund_name).strip())
    blob = " | ".join(candidates).lower()
    if not blob.strip():
        return "Other Equity"
    for label, pattern in CATEGORY_RULES:
        if re.search(pattern, blob, flags=re.IGNORECASE):
            return label
    if re.search(r"debt|income|bond|gilt|duration|money\s*market", blob, flags=re.IGNORECASE):
        return "Other Debt"
    return "Other Equity"