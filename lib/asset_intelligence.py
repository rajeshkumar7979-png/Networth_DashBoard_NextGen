# -------------------------------------------------
# Asset Intelligence Pack — deterministic, session-only.
#
# Builds an instrument-scoped intelligence pack from Command Center session
# state + optional opt-in Yahoo tape already fetched elsewhere.
# No Excel load. No network. Missing stays missing.
# -------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from lib.company_tape import metric_tone
from lib.instrument_names import extract_isin
from lib.intelligence.exposure import load_holdings_cache, _normalize_holdings
from lib.intelligence.instrument_brief import build_instrument_brief
from lib.intelligence.sources.mapping import PortfolioIndex

CONC_WATCH_PCT = 8.0
CONC_ELEVATED_PCT = 15.0
TOP_HOLDING_WATCH = 10.0


def _finite(value):
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def _text(value) -> str:
    return str(value or "").strip()


def _row_metric(rows, label: str):
    want = label.strip().lower()
    for row in rows or []:
        if str(row.get("label") or "").strip().lower() == want:
            return row.get("value")
    return None


@dataclass
class IntelligenceFlag:
    tone: str
    label: str
    text: str
    source: str


@dataclass
class AssetIntelligencePack:
    kind: str
    name: str
    member: str
    key: str
    isin: str
    symbol: str
    parameters: list[dict] = field(default_factory=list)
    green: list[IntelligenceFlag] = field(default_factory=list)
    red: list[IntelligenceFlag] = field(default_factory=list)
    watch: list[IntelligenceFlag] = field(default_factory=list)
    gaps: list[IntelligenceFlag] = field(default_factory=list)
    developments: list[dict] = field(default_factory=list)
    lookthrough: list[dict] = field(default_factory=list)
    family_overlap: list[dict] = field(default_factory=list)
    freshness: list[str] = field(default_factory=list)
    brief: Any = None
    tape_ok: bool = False

    def flags_by_tone(self, tone: str) -> list[IntelligenceFlag]:
        return [f for f in (*self.green, *self.red, *self.watch, *self.gaps) if f.tone == tone]


def _add(bucket: list, tone: str, label: str, text: str, source: str):
    bucket.append(IntelligenceFlag(tone=tone, label=label, text=text, source=source))


def _tape_rows(tape: Optional[dict]) -> list[dict]:
    if not tape or not tape.get("ok"):
        return []
    rows = []
    for section in ("fundamentals", "technicals"):
        rows.extend((tape.get(section) or {}).get("rows") or [])
    return rows


def _concentration(current, total_assets) -> Optional[float]:
    cur = _finite(current)
    tot = _finite(total_assets)
    if cur is None or tot is None or tot <= 0:
        return None
    return cur / tot * 100.0


def _instrument_index(kind: str, isin: str, symbol: str, name: str,
                      scheme_code=None) -> PortfolioIndex:
    isins = {isin.upper()} if isin else set()
    symbols = {symbol.upper()} if symbol else set()
    names = {name.upper()} if name and kind == "MF" else set()
    codes = set()
    if scheme_code is not None:
        text = str(scheme_code).strip().lstrip("0") or "0"
        codes.add(text)
        codes.add(str(scheme_code).strip())
    return PortfolioIndex(
        isins=frozenset(isins),
        symbols=frozenset(symbols),
        scheme_codes=frozenset(codes),
        fund_names=frozenset(names),
        instrument_keys=frozenset(),
    )


def _scheme_code(rec: dict, session_holdings) -> Optional[str]:
    isin = _text(rec.get("ISIN"))
    name = _text(rec.get("Fund Name"))
    for row in session_holdings or []:
        code = row.get("Scheme Code")
        if not code:
            continue
        if isin and _text(row.get("ISIN")) == isin:
            return code
        if name and _text(row.get("Fund Name")) == name:
            return code
    return rec.get("Scheme Code")


def _mf_lookthrough(scheme_code) -> tuple[list[dict], Optional[str]]:
    if scheme_code is None:
        return [], None
    cache = load_holdings_cache()
    try:
        raw = cache.get(str(int(scheme_code))) or cache.get(str(scheme_code)) or []
    except (TypeError, ValueError):
        raw = cache.get(str(scheme_code)) or []
    cleaned, _ = _normalize_holdings(raw if isinstance(raw, list) else [])
    as_of = None
    for item in cleaned:
        as_of = item.get("as_of") or item.get("as_of_date") or as_of
    top = sorted(cleaned, key=lambda c: -(_finite(c.get("weight")) or 0))[:10]
    rows = []
    for item in top:
        rows.append({
            "Name": item.get("name") or "—",
            "ISIN": item.get("isin") or "",
            "Weight %": _finite(item.get("weight")),
            "Sector": item.get("sector") or item.get("industry") or "",
        })
    return rows, as_of


def _family_overlap(isin: str, session_holdings) -> list[dict]:
    code = _text(isin).upper()
    if not code:
        return []
    cache = load_holdings_cache()
    out = []
    seen = set()
    for holding in session_holdings or []:
        scheme = holding.get("Scheme Code")
        if scheme is None:
            continue
        try:
            raw = cache.get(str(int(scheme))) or cache.get(str(scheme)) or []
        except (TypeError, ValueError):
            raw = cache.get(str(scheme)) or []
        cleaned, _ = _normalize_holdings(raw if isinstance(raw, list) else [])
        hit = next(
            (x for x in cleaned if _text(x.get("isin")).upper() == code),
            None,
        )
        if not hit:
            continue
        fund = _text(holding.get("Fund Name") or scheme)
        key = (fund, _text(holding.get("Owner")))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "Fund": fund,
            "Owner": holding.get("Owner") or "",
            "Weight %": _finite(hit.get("weight")),
        })
    return out


def _mapped_developments(cohort, index: PortfolioIndex) -> list[dict]:
    if cohort is None:
        return []
    rows = []
    try:
        from lib.intelligence.live import development_rows
        for row in development_rows(cohort, index, None):
            if row.get("Relevance") == "mapped":n                rows.append(row)
    except Exception:
        return []
    return rows


def _flag_tape(rows, green, red, watch, gaps):
    present = {str(r.get("label") or "").strip().lower() for r in rows}
    wanted = [
        "Sector", "Industry", "Market cap", "Trailing P/E", "Forward P/E",
        "Price / Book", "Trailing EPS", "Profit margin", "ROE",
        "Debt / Equity", "Beta", "Dividend yield",
        "SMA 20", "SMA 50", "SMA 200", "RSI-14", "In 52-week range",
    ]
    for label in wanted:
        if label.lower() not in present:
            _add(gaps, "gap", label, f"{label} is not on the observed tape this session.", "yahoo-tape")
    for row in rows:
        label = _text(row.get("label"))
        value = row.get("value")
        tone = metric_tone(label, value)
        if tone == "ok":
            _add(green, "green", label, f"{label} is inside the conservative observed band.", "yahoo-tape")
        elif tone == "watch":
            _add(watch, "watch", label, f"{label} is on the watch band of the observed tape.", "yahoo-tape")
        elif tone == "elevated":
            _add(red, "red", label, f"{label} is on the elevated band of the observed tape.", "yahoo-tape")


def _flag_concentration(weight_pct, green, red, watch, gaps):
    if weight_pct is None:
        _add(gaps, "gap", "Concentration",
             "Family asset total was not published this session — weight is unknown.",
             "command-center")
        return
    text = f"This line is {weight_pct:.1f}% of published family assets."
    if weight_pct >= CONC_ELEVATED_PCT:
        _add(red, "red", "Concentration", text + " Elevated single-name weight.", "register")
    elif weight_pct >= CONC_WATCH_PCT:
        _add(watch, "watch", "Concentration", text + " Watch single-name weight.", "register")
    else:
        _add(green, "green", "Concentration", text + " Below the 8% watch band.", "register")


def _flag_mf_perf(rec, green, red, watch, gaps):
    y1 = _finite(rec.get("1Y %"))
    vs1 = _finite(rec.get("vs Nifty50 1Y"))
    if y1 is None:
        _add(gaps, "gap", "1Y %", "Scheme 1Y is not on the Command Center row.", "command-center")
    elif y1 < 0:
        _add(watch, "watch", "1Y %", f"Scheme 1Y is {y1:.1f}% (trailing, not XIRR).", "command-center")
    else:
        _add(green, "green", "1Y %", f"Scheme 1Y is {y1:.1f}% (trailing, not XIRR).", "command-center")
    if vs1 is None:
        _add(gaps, "gap", "vs Nifty 1Y", "Benchmark comparison is missing on this row.", "command-center")
    elif vs1 < 0:
        _add(watch, "watch", "vs Nifty 1Y", f"Trailing 1Y vs Nifty50 is {vs1:.1f} pp.", "command-center")
    else:
        _add(green, "green", "vs Nifty 1Y", f"Trailing 1Y vs Nifty50 is {vs1:+.1f} pp.", "command-center")


def build_asset_pack(
        *,
        row: dict,
        rec: Optional[dict] = None,
        books=None,
        assets=None,
        research_brief=None,
        live_cohort=None,
        tape: Optional[dict] = None,
        session_holdings=None,
) -> AssetIntelligencePack:
    rec = rec or {}
    kind = _text(row.get("Kind"))
    name = _text(row.get("Name") or rec.get("Fund Name") or rec.get("Company Name"))
    member = _text(row.get("Member"))
    key = _text(row.get("Key"))
    isin = extract_isin(rec.get("ISIN"), rec.get("Company Name"), row.get("Key"), name)
    symbol = _text(rec.get("Symbol") or (row.get("Key") if kind == "Stocks" else ""))
    current = rec.get("Current Value") if rec.get("Current Value") is not None else row.get("Current Value")
    invested = rec.get("Invested") if rec.get("Invested") is not None else row.get("Invested")
    total_assets = None
    if isinstance(assets, dict):
        total_assets = assets.get("total_assets")
    weight = _concentration(current, total_assets)

    green, red, watch, gaps = [], [], [], []
    parameters = []
    freshness = []
    if isinstance(assets, dict) and assets.get("as_of"):
        freshness.append(f"Command Center as-of {assets.get('as_of')}")

    lookthrough: list[dict] = []
    family_overlap: list[dict] = []
    scheme_code = _scheme_code(rec, session_holdings) if kind == "MF" else None
    holdings_as_of = None

    if kind == "Stocks":
        tape_rows = _tape_rows(tape)
        tape_ok = bool(tape and tape.get("ok") and tape_rows)
        if tape_ok:
            freshness.append(f"Yahoo tape {tape.get('retrieved_at') or 'loaded'}")
            for item in tape_rows:
                parameters.append({
                    "Parameter": item.get("label"),
                    "Value": item.get("value"),
                    "Unit": item.get("sub") or "",
                    "Source": "Yahoo Finance (opt-in tape)",
                })
            _flag_tape(tape_rows, green, red, watch, gaps)
        else:
            tape_ok = False
            _add(gaps, "gap", "Company tape",
                 "Yahoo tape is not loaded this session — PE/RSI/SMA stay missing.",
                 "yahoo-tape")
        family_overlap = _family_overlap(isin, session_holdings)
        if family_overlap:
            _add(watch, "watch", "MF overlap",
                 f"{len(family_overlap)} family fund-row(s) also disclose this ISIN.",
                 "mf-holdings-cache")
        else:
            _add(gaps, "gap", "MF overlap",
                 "No family fund in the committed holdings cache discloses this ISIN.",
                 "mf-holdings-cache")
    elif kind == "MF":
        tape_ok = False
        for label, keyn in (
            ("Category", "Category"),
            ("AMC", "AMC"),
            ("Fund House", "Fund House"),
            ("1Y %", "1Y %"),
            ("3Y %", "3Y %"),
            ("5Y %", "5Y %"),
            ("vs Nifty50 1Y", "vs Nifty50 1Y"),
            ("vs Nifty50 3Y", "vs Nifty50 3Y"),
            ("vs Nifty50 5Y", "vs Nifty50 5Y"),
        ):
            val = rec.get(keyn) or row.get(keyn)
            if val not in (None, "", "—"):
                parameters.append({
                    "Parameter": label,
                    "Value": val,
                    "Unit": "",
                    "Source": "Command Center row",
                })
        if not rec.get("Category") and not row.get("Class"):
            _add(gaps, "gap", "Category", "Fund category is not on this row.", "command-center")
        else:
            parameters.append({
                "Parameter": "Class",
                "Value": rec.get("Category") or row.get("Class"),
                "Unit": "",
                "Source": "Command Center row",
            })
        _flag_mf_perf(rec, green, red, watch, gaps)
        lookthrough, holdings_as_of = _mf_lookthrough(scheme_code)
        if holdings_as_of:
            freshness.append(f"Holdings disclosure {holdings_as_of}")
        if lookthrough:
            top_w = _finite(lookthrough[0].get("Weight %"))
            if top_w is not None and top_w >= TOP_HOLDING_WATCH:
                _add(watch, "watch", "Top holding",
                     f"Largest disclosed name is {lookthrough[0].get('Name')} at {top_w:.1f}%.",
                     "mf-holdings-cache")
            else:
                _add(green, "green", "Look-through",
                     f"{len(lookthrough)} disclosed names available in the holdings cache.",
                     "mf-holdings-cache")
            sectors = [r.get("Sector") for r in lookthrough if r.get("Sector")]
            if not sectors:
                _add(gaps, "gap", "Sector exposure",
                     "Holdings cache rows carry no sector field this run.",
                     "mf-holdings-cache")
        else:
            _add(gaps, "gap", "Look-through",
                 "No disclosed holdings in the committed cache for this scheme.",
                 "mf-holdings-cache")
        shared = 0
        for item in lookthrough[:5]:
            overlap = _family_overlap(item.get("ISIN"), session_holdings)
            shared += max(0, len(overlap) - 1)
        if shared:
            _add(watch, "watch", "Family-fund overlap",
                 f"Top disclosed names also appear in {shared} other family fund-row(s).",
                 "mf-holdings-cache")
    else:
        tape_ok = False
        _add(gaps, "gap", "Issuer tape",
             f"{kind or 'This sleeve'} has no company-tape overlay in Asset Intelligence.",
             "register")

    _flag_concentration(weight, green, red, watch, gaps)
    if weight is not None:
        parameters.append({
            "Parameter": "Weight of family assets",
            "Value": round(weight, 2),
            "Unit": "%",
            "Source": "Command Center totals",
        })

    inst_index = _instrument_index(kind, isin, symbol, name, scheme_code)
    developments = _mapped_developments(live_cohort, inst_index)
    if developments:
        freshness.append(f"{len(developments)} mapped external development(s)")
        _add(watch, "watch", "Mapped evidence",
             f"{len(developments)} cohort item(s) exact-match this instrument.",
             "live-cohort")
    else:
        _add(gaps, "gap", "Mapped evidence",
             "No portfolio-mapped external development exact-matches this instrument this session.",
             "live-cohort")

    brief = build_instrument_brief(
        parent=research_brief,
        kind=kind,
        name=name,
        member=member,
        isin=isin,
        symbol=symbol,
        current_value=current,
        invested=invested,
        pnl=rec.get("P&L") or row.get("P&L"),
        simple_roi=rec.get("Return %") or row.get("Return %"),
        lump_sum_ann=rec.get("Ann. Return %"),
        y1=rec.get("1Y %"),
        y3=rec.get("3Y %"),
        y5=rec.get("5Y %"),
        vs_n1=rec.get("vs Nifty50 1Y"),
        vs_n3=rec.get("vs Nifty50 3Y"),
        vs_n5=rec.get("vs Nifty50 5Y"),
        lookthrough=lookthrough or family_overlap,
        tape=tape if tape_ok else None,
    )

    return AssetIntelligencePack(
        kind=kind,
        name=name,
        member=member,
        key=key,
        isin=isin,
        symbol=symbol,
        parameters=parameters,
        green=green,
        red=red,
        watch=watch,
        gaps=gaps,
        developments=developments,
        lookthrough=lookthrough,
        family_overlap=family_overlap,
        freshness=freshness,
        brief=brief,
        tape_ok=tape_ok,
    )


AI_QUESTION = (
    "You are interpreting an Asset Intelligence Pack, not a holdings summary. "
    "Use ONLY the catalog and deterministic flags already in this brief. "
    "Structure the reading as: overall investor view; green flags; red flags; "
    "watch items; key evidence; what could change / invalidate this view; data gaps. "
    "Do not restate quantity, average buy price, invested amount or current value "
    "unless they are needed to explain concentration or trailing performance. "
    "Do not invent PE, RSI, XIRR, SIP history, tax, or buy/sell instructions. "
    "Decision-support only."
)


def pack_prompt_extras(pack: AssetIntelligencePack) -> str:
    lines = [AI_QUESTION, "", "Deterministic flags already computed (do not invent new ones):"]
    for group, title in (
        (pack.green, "GREEN"),
        (pack.red, "RED"),
        (pack.watch, "WATCH"),
        (pack.gaps, "GAPS"),
    ):
        if not group:
            continue
        lines.append(title + ":")
        for flag in group:
            lines.append(f"- [{flag.source}] {flag.label}: {flag.text}")
    if pack.freshness:
        lines.append("Freshness: " + " · ".join(pack.freshness))
    return "\n".join(lines)
