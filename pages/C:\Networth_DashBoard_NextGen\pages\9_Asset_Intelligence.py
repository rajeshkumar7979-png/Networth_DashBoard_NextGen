# ============================================================
# NORTHLINE — ASSET INTELLIGENCE WING
# Isolated intelligence adapter.
#
# IMPORTANT:
#   This file is intentionally self-contained.
#   It does NOT modify existing dashboard modules.
#
#   It reuses healthy existing sources when available and
#   degrades gracefully when a source is unavailable.
#
# Save as:
#   pages/9_Asset_Intelligence.py
# ============================================================

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st


# ------------------------------------------------------------
# SAFE IMPORT LAYER
# ------------------------------------------------------------

def _optional_import(module_name: str):
    try:
        return __import__(module_name, fromlist=["*"])
    except Exception:
        return None


_roster_mod = _optional_import("lib.roster")
_portfolio_mod = _optional_import("lib.portfolio")
_tape_mod = _optional_import("lib.company_tape")
_exposure_mod = _optional_import("lib.intelligence.exposure")
_live_mod = _optional_import("lib.intelligence.live")
_news_mod = _optional_import("lib.news")
_ai_mod = _optional_import("lib.intelligence.ai")
_config_mod = _optional_import("lib.intelligence.ai.config")


# ------------------------------------------------------------
# BASIC UTILITIES
# ------------------------------------------------------------

def _finite(value):
    try:
        if value is None:
            return None
        n = float(value)
        if not math.isfinite(n):
            return None
        return n
    except Exception:
        return None


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _num(row, *keys):
    if row is None:
        return None

    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            continue

        value = _finite(value)
        if value is not None:
            return value

    return None


def _first(row, *keys):
    if row is None:
        return ""

    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            continue

        value = _text(value)
        if value:
            return value

    return ""


def _pct(value):
    n = _finite(value)
    return None if n is None else f"{n:.1f}%"


def _money(value):
    n = _finite(value)
    if n is None:
        return "n/a"
    return f"₹{n:,.0f}"


def _flag(label, text, tone, evidence=None):
    return {
        "label": label,
        "text": text,
        "tone": tone,
        "evidence": evidence or [],
    }


# ------------------------------------------------------------
# DATA LOADING
# ------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def _load_books():
    """
    Prefer existing portfolio loader.
    Never fail the entire page if the workbook/source is unavailable.
    """
    if _portfolio_mod is None:
        return {}

    try:
        books = _portfolio_mod.load_excel()
        if isinstance(books, tuple) and len(books) >= 3:
            return {
                "fd": books[0],
                "mf": books[1],
                "stocks": books[2],
                "gold": pd.DataFrame(),
            }
    except Exception:
        pass

    return {}


def _clean_book(df, current_col="Current Value"):
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    out = df.copy()

    if current_col in out.columns:
        out = out[out[current_col].notna()].copy()

    return out.reset_index(drop=True)


def _build_roster(books):
    """
    Reuse the canonical roster builder if possible.
    Otherwise create a minimal local roster.
    """
    if _roster_mod is not None:
        try:
            return _roster_mod.build_roster(
                mf_valid=_clean_book(books.get("mf"), "Current Value"),
                stocks_valid=_clean_book(books.get("stocks"), "Current Value"),
                gold_valid=_clean_book(books.get("gold"), "Current Value"),
                fd_valid=_clean_book(books.get("fd"), "Current Value (INR)"),
            )
        except Exception:
            pass

    rows = []

    mappings = [
        ("MF", "mf", "Current Value"),
        ("Stocks", "stocks", "Current Value"),
        ("Gold", "gold", "Current Value"),
        ("FD", "fd", "Current Value (INR)"),
    ]

    for kind, key, value_col in mappings:
        df = _clean_book(books.get(key), value_col)

        for idx, raw in df.iterrows():
            row = raw.to_dict()

            name = _first(
                row,
                "Fund Name",
                "Company Name",
                "Symbol",
                "Product",
                "Account Number",
            )

            current = _num(row, value_col, "Current Value")
            invested = _num(
                row,
                "Invested",
                "Principal (INR, at deposit FX)",
            )

            if current is None:
                continue

            pnl = current - (invested or 0)

            rows.append(
                {
                    "Key": f"{kind}:{idx}:{name}",
                    "Name": name or kind,
                    "Kind": kind,
                    "Class": kind,
                    "Member": _first(row, "Owner", "Holder Name"),
                    "Current Value": current,
                    "Invested": invested or 0,
                    "P&L": pnl,
                    "Return %": (
                        pnl / invested * 100
                        if invested and invested != 0
                        else None
                    ),
                }
            )

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# SOURCE ROW MATCHING
# ------------------------------------------------------------

def _source_row_for_roster(books, selected):
    kind = _text(selected.get("Kind"))

    mapping = {
        "MF": "mf",
        "Stocks": "stocks",
        "Gold": "gold",
        "FD": "fd",
    }

    book_name = mapping.get(kind)
    if not book_name:
        return {}

    df = books.get(book_name)

    if df is None or df.empty:
        return {}

    name = _text(selected.get("Name"))
    key = _text(selected.get("Key"))

    # Exact identifier first.
    candidate_cols = []

    if kind == "MF":
        candidate_cols = ["Fund Name", "ISIN", "Scheme Code"]
    elif kind == "Stocks":
        candidate_cols = ["Symbol", "ISIN", "Company Name"]
    elif kind == "Gold":
        candidate_cols = ["Symbol", "ISIN"]
    else:
        candidate_cols = ["Account Number", "Product"]

    for col in candidate_cols:
        if col not in df.columns:
            continue

        values = df[col].astype(str).str.strip()

        for token in (name, key):
            if not token:
                continue

            mask = values.str.upper().eq(token.upper())

            if mask.any():
                return df.loc[mask].iloc[0].to_dict()

    # Conservative fallback: name token containment.
    if name:
        upper_name = name.upper()

        for idx, raw in df.iterrows():
            text = " | ".join(
                _text(v).upper()
                for v in raw.to_dict().values()
                if _text(v)
            )

            if upper_name and upper_name in text:
                return raw.to_dict()

    return {}


# ------------------------------------------------------------
# PORTFOLIO CONTEXT
# ------------------------------------------------------------

def _portfolio_context(roster, selected):
    if roster is None or roster.empty:
        return {}

    total_assets = float(
        pd.to_numeric(
            roster["Current Value"],
            errors="coerce",
        ).fillna(0).sum()
    )

    current = _finite(selected.get("Current Value")) or 0
    weight = current / total_assets * 100 if total_assets else None

    same_kind = roster[
        roster["Kind"].astype(str).eq(
            _text(selected.get("Kind"))
        )
    ].copy()

    kind_total = float(
        pd.to_numeric(
            same_kind["Current Value"],
            errors="coerce",
        ).fillna(0).sum()
    )

    kind_weight = current / kind_total * 100 if kind_total else None

    return {
        "total_assets": total_assets,
        "asset_weight_pct": weight,
        "asset_class_total": kind_total,
        "asset_class_weight_pct": kind_weight,
        "class_rank": (
            int(
                same_kind["Current Value"]
                .astype(float)
                .rank(method="min", ascending=False)
                .loc[
                    same_kind.index[
                        same_kind["Key"].astype(str)
                        .eq(_text(selected.get("Key")))
                    ]
                ]
                .iloc[0]
            )
            if not same_kind.empty
            and (
                same_kind["Key"].astype(str)
                .eq(_text(selected.get("Key")))
                .any()
            )
            else None
        ),
    }


# ------------------------------------------------------------
# STOCK INTELLIGENCE
# ------------------------------------------------------------

def _stock_intelligence(raw, selected):
    facts = []
    green = []
    red = []
    watch = []
    gaps = []

    symbol = _first(raw, "Symbol")

    if not symbol:
        symbol = _text(selected.get("Name"))

    exchange = _first(raw, "Exchange") or "NSE"

    if _tape_mod is not None and symbol:
        try:
            ticker = _tape_mod.yahoo_ticker(symbol, exchange)

            with st.spinner("Reading available stock intelligence…"):
                tape = _tape_mod.fetch_yahoo_equity(
                    symbol,
                    exchange,
                )

            if tape:
                fundamentals = tape.get("fundamentals") or {}
                technicals = tape.get("technicals") or {}

                for source in (fundamentals, technicals):
                    for item in source.get("rows", []) or []:
                        label = _text(item.get("label"))
                        value = item.get("value")

                        if label:
                            facts.append(
                                {
                                    "Parameter": label,
                                    "Value": value,
                                    "Source": source.get(
                                        "source",
                                        "Yahoo Finance",
                                    ),
                                }
                            )

                # -------------------------
                # Fundamental flags
                # -------------------------

                metrics = {
                    _text(x.get("label")).lower(): x.get("value")
                    for x in (
                        fundamentals.get("rows", [])
                        or []
                    )
                }

                pe = _finite(metrics.get("trailing p/e"))
                fpe = _finite(metrics.get("forward p/e"))
                margin = _finite(metrics.get("profit margin"))
                roe = _finite(metrics.get("roe"))
                debt = _finite(metrics.get("debt / equity"))
                beta = _finite(metrics.get("beta"))

                if margin is not None:
                    if margin < 0:
                        red.append(
                            _flag(
                                "Profitability",
                                "Reported profit margin is negative.",
                                "red",
                            )
                        )
                    elif margin >= 10:
                        green.append(
                            _flag(
                                "Profitability",
                                f"Reported profit margin is {margin:.1f}%.",
                                "green",
                            )
                        )

                if roe is not None:
                    if roe < 0:
                        red.append(
                            _flag(
                                "ROE",
                                "Reported ROE is negative.",
                                "red",
                            )
                        )
                    elif roe >= 10:
                        green.append(
                            _flag(
                                "ROE",
                                f"Reported ROE is {roe:.1f}%.",
                                "green",
                            )
                        )

                if debt is not None:
                    if debt >= 200:
                        red.append(
                            _flag(
                                "Leverage",
                                f"Debt/equity is elevated at {debt:.1f}.",
                                "red",
                            )
                        )
                    elif debt < 100:
                        green.append(
                            _flag(
                                "Leverage",
                                f"Debt/equity is below 100 ({debt:.1f}).",
                                "green",
                            )
                        )

                if pe is not None:
                    if pe >= 80:
                        red.append(
                            _flag(
                                "Valuation",
                                f"Trailing P/E is {pe:.1f}; valuation deserves scrutiny.",
                                "red",
                            )
                        )
                    elif pe < 0:
                        watch.append(
                            _flag(
                                "Valuation",
                                "Trailing P/E is negative; conventional P/E interpretation is not meaningful.",
                                "watch",
                            )
                        )

                if fpe is not None and pe is not None:
                    if fpe < pe:
                        green.append(
                            _flag(
                                "Forward valuation",
                                "Forward P/E is below trailing P/E.",
                                "green",
                            )
                        )
                    elif fpe > pe * 1.25:
                        watch.append(
                            _flag(
                                "Forward valuation",
                                "Forward P/E is materially above trailing P/E.",
                                "watch",
                            )
                        )

                if beta is not None and beta >= 1.5:
                    watch.append(
                        _flag(
                            "Volatility",
                            f"Beta is {beta:.1f}; price sensitivity may be elevated.",
                            "watch",
                        )
                    )

                # -------------------------
                # Technical flags
                # -------------------------

                tech_metrics = {
                    _text(x.get("label")).lower(): x.get("value")
                    for x in (
                        technicals.get("rows", [])
                        or []
                    )
                }

                rsi = _finite(tech_metrics.get("rsi-14"))
                vs_sma50 = _finite(
                    tech_metrics.get("vs sma 50")
                )
                range_pos = _finite(
                    tech_metrics.get("in 52-week range")
                )

                if vs_sma50 is not None:
                    if vs_sma50 >= 0:
                        green.append(
                            _flag(
                                "Price trend",
                                f"Price is {vs_sma50:.1f}% above SMA 50.",
                                "green",
                            )
                        )
                    else:
                        watch.append(
                            _flag(
                                "Price trend",
                                f"Price is {abs(vs_sma50):.1f}% below SMA 50.",
                                "watch",
                            )
                        )

                if rsi is not None:
                    if rsi >= 70:
                        watch.append(
                            _flag(
                                "Momentum",
                                f"RSI-14 is {rsi:.1f}, indicating an extended reading.",
                                "watch",
                            )
                        )
                    elif rsi <= 30:
                        watch.append(
                            _flag(
                                "Momentum",
                                f"RSI-14 is {rsi:.1f}, indicating a weak/oversold reading.",
                                "watch",
                            )
                        )

                if range_pos is not None:
                    if range_pos >= 90:
                        watch.append(
                            _flag(
                                "52-week position",
                                f"Price is around {range_pos:.0f}% of its 52-week range.",
                                "watch",
                            )
                        )
                    elif range_pos <= 10:
                        watch.append(
                            _flag(
                                "52-week position",
                                f"Price is around {range_pos:.0f}% of its 52-week range.",
                                "watch",
                            )
                        )

                if not metrics:
                    gaps.append(
                        "Yahoo fundamental tape unavailable."
                    )

                if not tech_metrics:
                    gaps.append(
                        "Yahoo technical history unavailable."
                    )

                facts.append(
                    {
                        "Parameter": "Yahoo ticker",
                        "Value": ticker,
                        "Source": "Yahoo Finance",
                    }
                )

        except Exception as exc:
            gaps.append(
                f"Stock intelligence source unavailable: {type(exc).__name__}"
            )
    else:
        gaps.append("Stock intelligence module unavailable.")

    return {
        "facts": facts,
        "green": green,
        "red": red,
        "watch": watch,
        "gaps": gaps,
    }


# ------------------------------------------------------------
# MUTUAL FUND INTELLIGENCE
# ------------------------------------------------------------

def _mf_intelligence(raw, selected):
    facts = []
    green = []
    red = []
    watch = []
    gaps = []

    # -------------------------
    # Direct verified fund facts
    # -------------------------

    fields = [
        ("Category", "Category"),
        ("Fund house", "AMC"),
        ("Scheme", "Fund Name"),
        ("ISIN", "ISIN"),
        ("1Y return", "1Y %"),
        ("3Y return", "3Y %"),
        ("5Y return", "5Y %"),
        ("1Y vs Nifty50", "vs Nifty50 1Y"),
        ("3Y vs Nifty50", "vs Nifty50 3Y"),
        ("5Y vs Nifty50", "vs Nifty50 5Y"),
        ("Expense ratio", "Expense Ratio"),
        ("AUM", "AUM"),
        ("Risk", "Risk"),
        ("Manager", "Fund Manager"),
    ]

    for label, col in fields:
        value = raw.get(col)

        if value is None:
            continue

        if _text(value):
            facts.append(
                {
                    "Parameter": label,
                    "Value": value,
                    "Source": "Portfolio workbook",
                }
            )

    # -------------------------
    # Performance flags
    # -------------------------

    r1 = _num(raw, "1Y %")
    r3 = _num(raw, "3Y %")
    r5 = _num(raw, "5Y %")

    v1 = _num(raw, "vs Nifty50 1Y")
    v3 = _num(raw, "vs Nifty50 3Y")
    v5 = _num(raw, "vs Nifty50 5Y")

    for period, value in (
        ("1Y", r1),
        ("3Y", r3),
        ("5Y", r5),
    ):
        if value is None:
            gaps.append(f"{period} return unavailable.")

    for period, value in (
        ("1Y", v1),
        ("3Y", v3),
        ("5Y", v5),
    ):
        if value is None:
            continue

        if value > 0:
            green.append(
                _flag(
                    f"{period} benchmark",
                    f"Fund is {value:.1f} percentage points above Nifty50.",
                    "green",
                )
            )
        elif value < -5:
            red.append(
                _flag(
                    f"{period} benchmark",
                    f"Fund is {abs(value):.1f} percentage points below Nifty50.",
                    "red",
                )
            )
        else:
            watch.append(
                _flag(
                    f"{period} benchmark",
                    f"Fund is {value:.1f} percentage points versus Nifty50.",
                    "watch",
                )
            )

    # -------------------------
    # MF holdings look-through
    # -------------------------

    isin = _first(raw, "ISIN")
    scheme_code = _first(
        raw,
        "Scheme Code",
        "SchemeCode",
        "AMFI Code",
    )

    holdings = []

    if _exposure_mod is not None:
        try:
            cache = _exposure_mod.load_holdings_cache()

            candidate_keys = [
                scheme_code,
                str(scheme_code).split(".")[0],
                isin,
            ]

            for key in candidate_keys:
                if key and key in cache:
                    holdings = cache[key]
                    break

        except Exception:
            holdings = []

    if holdings:
        try:
            normalized, _derived = (
                _exposure_mod._normalize_holdings(holdings)
            )

            normalized = sorted(
                normalized,
                key=lambda x: _finite(x.get("weight")) or 0,
                reverse=True,
            )

            top5 = normalized[:5]

            for item in top5:
                facts.append(
                    {
                        "Parameter": "Top holding",
                        "Value": (
                            f"{item.get('name')} "
                            f"({_finite(item.get('weight')):.1f}%)"
                            if _finite(item.get("weight")) is not None
                            else item.get("name")
                        ),
                        "Source": "MF holdings disclosure cache",
                    }
                )

            top5_weight = sum(
                _finite(x.get("weight")) or 0
                for x in top5
            )

            if top5_weight >= 45:
                red.append(
                    _flag(
                        "Concentration",
                        f"Top five disclosed holdings represent approximately {top5_weight:.1f}% of the fund.",
                        "red",
                    )
                )
            elif top5_weight >= 30:
                watch.append(
                    _flag(
                        "Concentration",
                        f"Top five disclosed holdings represent approximately {top5_weight:.1f}% of the fund.",
                        "watch",
                    )
                )
            else:
                green.append(
                    _flag(
                        "Concentration",
                        f"Top five disclosed holdings represent approximately {top5_weight:.1f}% of the fund.",
                        "green",
                    )
                )

        except Exception:
            gaps.append(
                "MF holdings disclosure exists but could not be normalized."
            )
    else:
        gaps.append(
            "No usable MF holdings disclosure was available for this scheme."
        )

    # -------------------------
    # Category / quality
    # -------------------------

    category = _first(raw, "Category")

    if category:
        facts.append(
            {
                "Parameter": "Category",
                "Value": category,
                "Source": "Portfolio workbook",
            }
        )
    else:
        gaps.append("Fund category unavailable.")

    return {
        "facts": facts,
        "green": green,
        "red": red,
        "watch": watch,
        "gaps": gaps,
    }


# ------------------------------------------------------------
# NEWS / EXTERNAL EVIDENCE
# ------------------------------------------------------------

def _external_evidence(selected, raw):
    rows = []

    try:
        if _live_mod is not None:
            cohort = _live_mod.load_live_cohort()

            if cohort is not None:
                developments = _live_mod.development_rows(
                    cohort
                )

                name = _text(selected.get("Name"))
                symbol = _first(raw, "Symbol")
                isin = _first(raw, "ISIN")

                terms = [
                    x.upper()
                    for x in (
                        name,
                        symbol,
                        isin,
                    )
                    if x
                ]

                for item in developments or []:
                    title = _text(
                        item.get("title")
                        or item.get("headline")
                    )

                    haystack = title.upper()

                    if any(
                        term in haystack
                        for term in terms
                        if len(term) >= 3
                    ):
                        rows.append(
                            {
                                "Headline": title,
                                "Source": _text(
                                    item.get("source")
                                    or item.get("publisher")
                                ),
                                "Date": _text(
                                    item.get("published")
                                    or item.get("date")
                                ),
                            }
                        )

    except Exception:
        pass

    return rows[:8]


# ------------------------------------------------------------
# AI SYNTHESIS — OPTIONAL
# ------------------------------------------------------------

def _ai_synthesis(pack):
    """
    Use the existing AI provider only if available.
    This is deliberately isolated from the existing portfolio AI pipeline.
    """
    if _ai_mod is None or _config_mod is None:
        return None

    try:
        cfg = _config_mod.load_ai_config()

        if not _config_mod.provider_is_configured(cfg):
            return None

        client_mod = _optional_import(
            "lib.intelligence.ai.client"
        )

        schema_mod = _optional_import(
            "lib.intelligence.ai.schema"
        )

        if client_mod is None or schema_mod is None:
            return None

        client = client_mod.build_client(cfg)

        question = """
You are the Northline Asset Intelligence Analyst.

Interpret ONLY the verified intelligence pack supplied below.

Do not repeat basic register facts unless they explain a risk or strength.
Do not invent missing metrics.
Do not create PE, ROE, CAGR, XIRR, tax, FX or other values.
Do not give buy/sell/order instructions.

Return concise investor intelligence with exactly:

OVERALL
GREEN FLAGS
RED FLAGS
WATCH ITEMS
KEY EVIDENCE
WHAT COULD INVALIDATE THIS VIEW
DATA GAPS

The purpose is to explain what an investor should pay attention to,
not to repeat how many shares/units are owned or the purchase price.
"""

        pack_text = repr(pack)

        request = client_mod.AIRequest(
            messages=(
                {
                    "role": "system",
                    "content": question,
                },
                {
                    "role": "user",
                    "content": pack_text,
                },
            ),
            json_schema=getattr(
                schema_mod,
                "OUTPUT_SCHEMA",
                None,
            ),
            max_tokens=min(
                int(getattr(cfg, "max_tokens", 1200)),
                1600,
            ),
            temperature=0.0,
        )

        response = client.complete(
            request,
            api_key=getattr(cfg, "api_key", None),
        )

        return _text(
            getattr(response, "text", None)
            or getattr(response, "content", None)
        )

    except Exception:
        return None


# ------------------------------------------------------------
# DISPLAY
# ------------------------------------------------------------

def _render_flags(title, items, tone):
    if not items:
        return

    if tone == "green":
        icon = "🟢"
    elif tone == "red":
        icon = "🔴"
    else:
        icon = "🟠"

    st.markdown(f"### {icon} {title}")

    for item in items:
        st.markdown(
            f"**{item['label']}**  \n"
            f"{item['text']}"
        )


def _render_facts(facts):
    if not facts:
        return

    df = pd.DataFrame(facts)

    if not df.empty:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------
# PAGE
# ------------------------------------------------------------

st.set_page_config(
    page_title="Northline · Asset Intelligence",
    page_icon="◈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .intel-title {
        font-size: 2.4rem;
        font-weight: 600;
        letter-spacing: -0.03em;
        margin-bottom: 0.1rem;
    }

    .intel-sub {
        color: #8c96a5;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }

    .intel-note {
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 10px;
        padding: 12px 15px;
        color: #9aa3af;
        font-size: .85rem;
        margin-bottom: 18px;
    }

    .intel-green {
        border-left: 4px solid #28a66f;
        padding-left: 12px;
    }

    .intel-red {
        border-left: 4px solid #d65c5c;
        padding-left: 12px;
    }

    .intel-watch {
        border-left: 4px solid #c99a3b;
        padding-left: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="intel-title">Asset Intelligence</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="intel-sub">'
    "Investor intelligence · evidence first · instrument specific"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="intel-note">'
    "This is an analytical layer over the existing Northline books. "
    "It does not rewrite portfolio data, infer transaction history, "
    "or create missing financial metrics."
    "</div>",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# LOAD
# ------------------------------------------------------------

books = _load_books()
roster = _build_roster(books)

if roster is None or roster.empty:
    st.warning(
        "No usable portfolio instruments were found."
    )
    st.stop()


# ------------------------------------------------------------
# SELECTOR
# ------------------------------------------------------------

selector_rows = []

for _, row in roster.iterrows():
    selector_rows.append(
        {
            "key": _text(row.get("Key")),
            "label": (
                f"{_text(row.get('Kind'))} · "
                f"{_text(row.get('Name'))} · "
                f"{_text(row.get('Member'))}"
            ),
        }
    )

labels = [
    x["label"]
    for x in selector_rows
]

selected_label = st.selectbox(
    "Select asset",
    labels,
)

selected_key = selector_rows[
    labels.index(selected_label)
]["key"]

selected = roster[
    roster["Key"].astype(str).eq(selected_key)
]

if selected.empty:
    st.stop()

selected_row = selected.iloc[0].to_dict()
raw = _source_row_for_roster(
    books,
    selected_row,
)


# ------------------------------------------------------------
# TOP CONTEXT
# ------------------------------------------------------------

portfolio = _portfolio_context(
    roster,
    selected_row,
)

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Asset",
    _text(selected_row.get("Name"))[:35],
)

c2.metric(
    "Class",
    _text(selected_row.get("Kind")),
)

c3.metric(
    "Portfolio weight",
    _pct(portfolio.get("asset_weight_pct"))
    or "n/a",
)

c4.metric(
    "Class weight",
    _pct(portfolio.get("class_weight_pct"))
    or _pct(portfolio.get("asset_class_weight_pct"))
    or "n/a",
)


# ------------------------------------------------------------
# BUILD INTELLIGENCE
# ------------------------------------------------------------

kind = _text(selected_row.get("Kind"))

if kind == "Stocks":
    intelligence = _stock_intelligence(
        raw,
        selected_row,
    )

elif kind == "MF":
    intelligence = _mf_intelligence(
        raw,
        selected_row,
    )

else:
    intelligence = {
        "facts": [],
        "green": [],
        "red": [],
        "watch": [],
        "gaps": [
            f"{kind} intelligence module is not implemented in this wing yet."
        ],
    }


# Portfolio concentration
weight = portfolio.get("asset_weight_pct")

if weight is not None:
    if weight >= 15:
        intelligence["red"].append(
            _flag(
                "Portfolio concentration",
                f"This instrument represents approximately {weight:.1f}% of total assets.",
                "red",
            )
        )
    elif weight >= 10:
        intelligence["watch"].append(
            _flag(
                "Portfolio concentration",
                f"This instrument represents approximately {weight:.1f}% of total assets.",
                "watch",
            )
        )
    else:
        intelligence["green"].append(
            _flag(
                "Portfolio concentration",
                f"This instrument represents approximately {weight:.1f}% of total assets.",
                "green",
            )
        )


# External evidence
external = _external_evidence(
    selected_row,
    raw,
)

if external:
    intelligence["facts"].extend(
        {
            "Parameter": "External development",
            "Value": x.get("Headline"),
            "Source": x.get("Source") or "Live research cache",
        }
        for x in external
    )


# ------------------------------------------------------------
# MAIN OUTPUT
# ------------------------------------------------------------

st.divider()

left, right = st.columns([1.15, 1])

with left:
    _render_flags(
        "GREEN FLAGS",
        intelligence["green"],
        "green",
    )

with right:
    _render_flags(
        "RED FLAGS",
        intelligence["red"],
        "red",
    )

_render_flags(
    "WATCH ITEMS",
    intelligence["watch"],
    "watch",
)


# ------------------------------------------------------------
# EXTERNAL DEVELOPMENTS
# ------------------------------------------------------------

if external:
    st.markdown("### External developments")

    st.dataframe(
        pd.DataFrame(external),
        use_container_width=True,
        hide_index=True,
    )


# ------------------------------------------------------------
# VERIFIED PARAMETERS
# ------------------------------------------------------------

with st.expander(
    "Verified parameters used by the intelligence engine",
    expanded=False,
):
    _render_facts(
        intelligence["facts"]
    )


# ------------------------------------------------------------
# DATA GAPS
# ------------------------------------------------------------

if intelligence["gaps"]:
    st.markdown("### Data gaps")

    for gap in intelligence["gaps"]:
        st.markdown(
            f"• {gap}"
        )


# ------------------------------------------------------------
# AI INTERPRETATION
# ------------------------------------------------------------

st.divider()

st.markdown("### Investor interpretation")

st.caption(
    "The deterministic layer above is the source of truth. "
    "AI is optional and interprets only the verified intelligence pack."
)

pack = {
    "asset": {
        "name": _text(selected_row.get("Name")),
        "kind": kind,
        "class": _text(selected_row.get("Class")),
    },
    "portfolio_context": {
        "portfolio_weight_pct":
            portfolio.get("asset_weight_pct"),
        "class_weight_pct":
            portfolio.get("asset_class_weight_pct"),
    },
    "verified_parameters": intelligence["facts"],
    "green_flags": [
        x["text"]
        for x in intelligence["green"]
    ],
    "red_flags": [
        x["text"]
        for x in intelligence["red"]
    ],
    "watch_items": [
        x["text"]
        for x in intelligence["watch"]
    ],
    "data_gaps": intelligence["gaps"],
    "external_evidence": external,
}

if st.button(
    "Run investor intelligence",
    type="primary",
):
    with st.spinner(
        "Synthesising verified asset intelligence…"
    ):
        ai_text = _ai_synthesis(pack)

    if ai_text:
        st.markdown(ai_text)
    else:
        st.info(
            "AI provider is unavailable or not configured. "
            "The deterministic GREEN / RED / WATCH analysis above "
            "remains available."
        )


# ------------------------------------------------------------
# FOOTER
# ------------------------------------------------------------

st.divider()

st.caption(
    "Northline Asset Intelligence · "
    f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
    "Evidence-driven · No transaction reconstruction · "
    "No buy/sell instructions"
)
