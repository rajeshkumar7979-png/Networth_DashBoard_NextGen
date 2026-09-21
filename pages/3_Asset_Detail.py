# ==================================================
# HOLDINGS — every line, one book.
#
# Sleeve-based view of the four validated books the Command Center publishes
# (mf / stocks / gold / fd): an Overview plus one tab per sleeve, a member
# filter, an exact-identifier search, and a single-instrument dossier. This
# page re-presents the Command Center's numbers and never re-values.
# ==================================================
import streamlit as st
import pandas as pd

from lib.theme import inject_css
from lib.register import canonical_instrument_key
from lib.roster import build_roster, member_filter_options
from lib.formatters import format_inr, format_identity_value
from lib.returns import (
    LUMP_SUM_ANN_LABEL,
    MULTI_CASHFLOW_XIRR_GAP,
    SIMPLE_ROI_LABEL,
    TRAILING_CAGR_LABEL,
    holding_period_days,
    lump_sum_annualized_pct,
    simple_roi_pct,
)
from lib.intelligence.exposure import load_holdings_cache, _normalize_holdings
from lib.intelligence import ai as intel_ai
from lib.intelligence.ai.config import load_ai_config, provider_is_configured
from lib.ui import (
    caption,
    data_sheet,
    empty_state,
    kpi_cards,
    nav_shell,
    page_header_html,
    pill,
    section_header_html,
    tone_for,
)
from lib.instrument_names import extract_isin, looks_like_isin
from lib.intelligence.live import development_rows

inject_css()

nav_shell("holdings")
st.markdown(page_header_html(
    "Northline · Family desk",
    "Every line, one book",
    "The four sleeves the Command Center routes from the workbook, with a dossier for any single instrument.",
), unsafe_allow_html=True)

BOOK_KIND = {"MF": "mf", "Stocks": "stocks", "Gold": "gold", "FD": "fd"}


def _num(value):
    try:
        v = float(value)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _fmt_inr(value):
    n = _num(value)
    return format_inr(n) if n is not None else "—"


def _fmt_pct(value):
    n = _num(value)
    return f"{n:.2f}%" if n is not None else "—"


def _money_view(frame):
    """Pre-format rupees as Indian-grouped text. Streamlit NumberColumn ₹%d
    cannot Indian-group, which produced ₹2767314 on the FD sleeve."""
    out = frame.copy()
    out["Booked"] = out["Current Value"].map(_fmt_inr)
    out["Invested ₹"] = out["Invested"].map(_fmt_inr)
    out["P&L ₹"] = out["P&L"].map(_fmt_inr)
    out["Return"] = out["Return %"].map(_fmt_pct)
    return out


def _raw_records_for(books, kind, key):
    """Original book row(s) behind a canonical key — only shown, never derived."""
    book = (books or {}).get(BOOK_KIND.get(kind))
    if book is None or book.empty:
        return []
    out = []
    for _, row in book.iterrows():
        rec = row.to_dict()
        if canonical_instrument_key(kind, rec) == key:
            out.append(rec)
    return out


def _scheme_code_for(rec):
    isin = str((rec or {}).get("ISIN") or "").strip()
    name = str((rec or {}).get("Fund Name") or "").strip()
    for row in st.session_state.get("mf_holdings_for_health") or []:
        row_isin = str(row.get("ISIN") or "").strip()
        row_name = str(row.get("Fund Name") or "").strip()
        code = row.get("Scheme Code")
        if not code:
            continue
        if isin and row_isin == isin:
            return code
        if name and row_name == name:
            return code
    return None


def _as_of_date():
    assets = st.session_state.get("cc_assets") or {}
    stamp = assets.get("as_of")
    if stamp:
        ts = pd.to_datetime(stamp, errors="coerce")
        if pd.notna(ts):
            return ts
    return None


def _family_funds_holding(isin):
    """Schemes in this family's MF book that disclose this equity ISIN."""
    code = str(isin or "").strip().upper()
    if not code:
        return []
    cache = load_holdings_cache()
    out = []
    seen = set()
    for holding in st.session_state.get("mf_holdings_for_health") or []:
        scheme = holding.get("Scheme Code")
        if scheme is None:
            continue
        try:
            raw = cache.get(str(int(scheme))) or cache.get(str(scheme)) or []
        except (TypeError, ValueError):
            raw = cache.get(str(scheme)) or []
        cleaned, _ = _normalize_holdings(raw if isinstance(raw, list) else [])
        hit = next(
            (x for x in cleaned if str(x.get("isin") or "").strip().upper() == code),
            None,
        )
        if not hit:
            continue
        fund = str(holding.get("Fund Name") or scheme)
        key = (fund, str(holding.get("Owner") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "Fund": fund,
            "Owner": holding.get("Owner") or "",
            "Weight %": hit.get("weight"),
        })
    return out



books = st.session_state.get("cc_books")
assets = st.session_state.get("cc_assets")
cohort = st.session_state.get("cc_live_cohort")
source_txt = "Command Center session data"

roster = None
if isinstance(books, dict):
    try:
        roster = build_roster(
            mf_valid=books.get("mf"),
            stocks_valid=books.get("stocks"),
            gold_valid=books.get("gold"),
            fd_valid=books.get("fd"),
        )
    except Exception:
        roster = None

if roster is None or len(roster) == 0:
    st.markdown(empty_state(
        "No holdings to drill into",
        "Open the Command Center first — it publishes the validated books this page reads.",
    ), unsafe_allow_html=True)
    st.stop()

_total_assets = _num((assets.get("total_assets")) if isinstance(assets, dict) else None)
if _total_assets is None:
    st.markdown(caption(
        "Contribution % of assets is unavailable until Command Center publishes total assets. "
        "This page will not invent a second total from the roster."),
        unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# OVERVIEW + SLEEVE TABS
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Books", "four sleeves"), unsafe_allow_html=True)
st.markdown(caption(f"Source: {source_txt}"), unsafe_allow_html=True)

_members = member_filter_options(roster)
_owners = st.multiselect("Member filter", _members, default=_members,
                         help="Everything below is scoped to the selected family member(s).")
_show = roster[roster["Member"].isin(_owners)] if _owners else roster

tabs = st.tabs(["Overview", "Mutual funds", "Stocks", "Gold", "FDs"])

with tabs[0]:
    class_totals = {}
    for _cls in roster["Class"].unique():
        _sub = _show[_show["Class"] == _cls]
        class_totals[_cls] = float(pd.to_numeric(_sub["Current Value"], errors="coerce").sum() or 0)
    if class_totals:
        _cards = [{"label": _c, "value": format_inr(_v), "sub": "current value (INR)",
                   "tone": "accent"} for _c, _v in class_totals.items()]
        st.markdown(kpi_cards(_cards, cols=4), unsafe_allow_html=True)
        st.markdown(caption("Class labels follow the Command Center routing rules "
                            "(gold is routed out of stocks/MF; FCNR ≠ INR FD); no-data classes "
                            "don't appear because they have no workbook source."), unsafe_allow_html=True)
    _ov = _show[["Name", "Member", "Kind", "Class", "Current Value", "Invested", "P&L", "Return %"]].sort_values(
        "Current Value", ascending=False)
    _ov_view = _money_view(_ov)
    st.dataframe(
        _ov_view[["Name", "Member", "Kind", "Class", "Booked", "Invested ₹", "P&L ₹", "Return"]],
        hide_index=True, use_container_width=True,
        column_config={
            "Name": st.column_config.TextColumn("Instrument", width="medium"),
            "Member": st.column_config.TextColumn("Member", width="medium"),
            "Kind": st.column_config.TextColumn("Sleeve", width="small"),
            "Class": st.column_config.TextColumn("Class", width="small"),
            "Booked": st.column_config.TextColumn("Booked (INR)", width="small"),
            "Invested ₹": st.column_config.TextColumn("Invested (INR)", width="small"),
            "P&L ₹": st.column_config.TextColumn("P&L", width="small"),
            "Return": st.column_config.TextColumn("Return %", width="small"),
        },
    )
    st.markdown(caption(
        "Return % = (current − invested) / invested from the single purchase record. "
        "Not annualized, not XIRR. FD ROI % p.a. in the dossier is the contractual rate."),
        unsafe_allow_html=True)

_map = {"Mutual funds": "MF", "Stocks": "Stocks", "Gold": "Gold", "FDs": "FD"}


def _fmt_pct_cell(v):
    n = _num(v)
    return f"{n:.1f}%" if n is not None else "—"


def _render_sleeve(kind):
    sub = _show[_show["Kind"] == kind]
    if sub.empty:
        st.markdown(caption("Nothing in this sleeve for the selected member(s)."),
                    unsafe_allow_html=True)
        return
    df = sub.copy()
    if kind == "FD":
        def _fmt_mat(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "—"
            s = str(v).strip()
            if not s or s.lower() in {"nan", "nat", "none", "—"}:
                return "—"
            ts = pd.to_datetime(s, errors="coerce")
            return ts.strftime("%d %b %Y") if pd.notna(ts) else s
        df["Maturity"] = df["Maturity"].map(_fmt_mat) if "Maturity" in df.columns else "—"
        products, accounts, ccys, rois, days = [], [], [], [], []
        prin_n, prin_i, val_n, interest, fx, days_num = [], [], [], [], [], []
        for _, r in df.iterrows():
            recs = _raw_records_for(books, "FD", str(r["Key"]))
            rec = recs[0] if recs else {}
            product = str(rec.get("Product") or r.get("Class") or "FD")
            if product.upper() == "FCNR":
                product = "FCNR (USD)"
            products.append(product)
            accounts.append(str(rec.get("Account Number") or ""))
            ccys.append(str(rec.get("Currency") or ""))
            _roi = _num(rec.get("ROI %"))
            rois.append(f"{_roi:.2f}%" if _roi is not None else "—")
            _d = _num(rec.get("Days to Maturity"))
            days.append(str(int(_d)) if _d is not None else "—")
            days_num.append(_d)
            _cur = str(rec.get("Currency") or "").strip().upper()
            prin_n.append(format_identity_value(
                "Principal (native)", rec.get("Principal (Native)"),
                currency=_cur or None))
            prin_i.append(_fmt_inr(rec.get("Principal (INR, at deposit FX)")))
            val_n.append(format_identity_value(
                "Value (native)", rec.get("Current Value (Native)"),
                currency=_cur or None))
            interest.append(_fmt_inr(rec.get("Interest Return (INR)")))
            fx.append(_fmt_inr(rec.get("FX Gain/Loss (INR)")))
        df["Product"] = products
        df["Account"] = accounts
        df["Ccy"] = ccys
        df["Principal"] = prin_n
        df["Principal INR"] = prin_i
        df["ROI"] = rois
        df["Days left"] = days
        df["Value (native)"] = val_n
        df["Interest"] = interest
        df["FX P&L"] = fx
        df["_days"] = days_num
        view = _money_view(df).sort_values("_days", ascending=True, na_position="last")
        st.dataframe(
            view[["Product", "Account", "Member", "Ccy", "Principal", "Principal INR",
                  "ROI", "Days left", "Value (native)", "Booked", "Interest", "FX P&L",
                  "Maturity"]],
            hide_index=True, use_container_width=True,
            column_config={
                "Product": st.column_config.TextColumn("Product", width="small"),
                "Account": st.column_config.TextColumn("Account", width="small"),
                "Member": st.column_config.TextColumn("Member", width="medium"),
                "Ccy": st.column_config.TextColumn("Ccy", width="small"),
                "Principal": st.column_config.TextColumn("Principal", width="small"),
                "Principal INR": st.column_config.TextColumn("Principal INR", width="small"),
                "ROI": st.column_config.TextColumn("ROI %", width="small"),
                "Days left": st.column_config.TextColumn("Days left", width="small"),
                "Value (native)": st.column_config.TextColumn("Value (native)", width="small"),
                "Booked": st.column_config.TextColumn("Value (INR)", width="small"),
                "Interest": st.column_config.TextColumn("Interest", width="small"),
                "FX P&L": st.column_config.TextColumn("FX P&L", width="small"),
                "Maturity": st.column_config.TextColumn("Matures", width="small"),
            },
        )
        st.markdown(caption(
            "NRI view: USD rows are FCNR (interest + FX vs deposit-date rate). INR rows are "
            "domestic FDs. Native currency and INR sit side by side — a FCNR is never shown "
            "as an INR deposit. Sorted by days to maturity. Return % on other sleeves is "
            "(current − invested) / invested from the single purchase record — not annualized, "
            "not XIRR. ROI % p.a. here is the contractual rate."),
            unsafe_allow_html=True)
        return
    if kind == "MF":
        y1, y3, y5, n1, n3, n5, cats, ann = [], [], [], [], [], [], [], []
        for _, r in df.iterrows():
            recs = _raw_records_for(books, "MF", str(r["Key"]))
            rec = recs[0] if recs else {}
            y1.append(_fmt_pct_cell(rec.get("1Y %")))
            y3.append(_fmt_pct_cell(rec.get("3Y %")))
            y5.append(_fmt_pct_cell(rec.get("5Y %")))
            n1.append(_fmt_pct_cell(rec.get("vs Nifty50 1Y")))
            n3.append(_fmt_pct_cell(rec.get("vs Nifty50 3Y")))
            n5.append(_fmt_pct_cell(rec.get("vs Nifty50 5Y")))
            cats.append(str(rec.get("Category") or r.get("Class") or "—"))
            ann.append(_fmt_pct_cell(rec.get("Ann. Return %")))
        df["Category"] = cats
        df["1Y"] = y1
        df["3Y"] = y3
        df["5Y"] = y5
        df["vs Nifty 1Y"] = n1
        df["vs Nifty 3Y"] = n3
        df["vs Nifty 5Y"] = n5
        df["Ann. %"] = ann
        view = _money_view(df).sort_values("Current Value", ascending=False)
        st.dataframe(
            view[["Name", "Member", "Category", "Booked", "P&L ₹", "Return", "Ann. %",
                  "1Y", "3Y", "5Y", "vs Nifty 1Y", "vs Nifty 3Y", "vs Nifty 5Y"]],
            hide_index=True, use_container_width=True,
            column_config={
                "Name": st.column_config.TextColumn("Fund", width="medium"),
                "Member": st.column_config.TextColumn("Member", width="small"),
                "Category": st.column_config.TextColumn("Category", width="small"),
                "Booked": st.column_config.TextColumn("Current (INR)", width="small"),
                "P&L ₹": st.column_config.TextColumn("P&L", width="small"),
                "Return": st.column_config.TextColumn("Return %", width="small"),
                "Ann. %": st.column_config.TextColumn("Lump-sum ann. %", width="small"),
                "1Y": st.column_config.TextColumn("1Y", width="small"),
                "3Y": st.column_config.TextColumn("3Y", width="small"),
                "5Y": st.column_config.TextColumn("5Y", width="small"),
                "vs Nifty 1Y": st.column_config.TextColumn("vs Nifty50 1Y", width="small"),
                "vs Nifty 3Y": st.column_config.TextColumn("vs Nifty50 3Y", width="small"),
                "vs Nifty 5Y": st.column_config.TextColumn("vs Nifty50 5Y", width="small"),
            },
        )
        st.markdown(caption(
            "1Y / 3Y / 5Y and vs Nifty50 are trailing CAGR from the latest NAV "
            "(years × 365.25) — a broad equity bar, not each fund's official benchmark. "
            "Mid/small/flexi/contra can look better or worse vs Nifty50 for the wrong reason. "
            "'—' means insufficient history or a debt-like category. Roster Return % is "
            "(current − invested) / invested from the single purchase record — not annualized, "
            "not a multi-cashflow XIRR. Lump-sum ann. % annualizes that one buy; it equals XIRR "
            "only if there was no SIP/sell/dividend."),
            unsafe_allow_html=True)
        return
    if kind == "Stocks":
        qty, avg, px, bought = [], [], [], []
        for _, r in df.iterrows():
            recs = _raw_records_for(books, "Stocks", str(r["Key"]))
            rec = recs[0] if recs else {}
            q = _num(rec.get("Quantity"))
            qty.append(f"{q:.0f}" if q is not None else "—")
            a = _num(rec.get("Avg Buy Price"))
            avg.append(f"{a:.2f}" if a is not None else "—")
            p = _num(rec.get("Current Price"))
            px.append(f"{p:.2f}" if p is not None else "—")
            pdt = rec.get("Purchase Date")
            bought.append(str(pdt)[:10] if pdt is not None and str(pdt) not in {"", "NaT", "nan", "None"} else "—")
        df["Qty"] = qty
        df["Avg buy"] = avg
        df["Price"] = px
        df["Bought"] = bought
        view = _money_view(df).sort_values("Current Value", ascending=False)
        st.dataframe(
            view[["Name", "Member", "Qty", "Avg buy", "Price", "Booked", "Invested ₹", "P&L ₹", "Return", "Bought"]],
            hide_index=True, use_container_width=True,
            column_config={
                "Name": st.column_config.TextColumn("Instrument", width="medium"),
                "Member": st.column_config.TextColumn("Member", width="small"),
                "Qty": st.column_config.TextColumn("Qty", width="small"),
                "Avg buy": st.column_config.TextColumn("Avg buy", width="small"),
                "Price": st.column_config.TextColumn("Price", width="small"),
                "Booked": st.column_config.TextColumn("Booked (INR)", width="small"),
                "Invested ₹": st.column_config.TextColumn("Invested (INR)", width="small"),
                "P&L ₹": st.column_config.TextColumn("P&L", width="small"),
                "Return": st.column_config.TextColumn("Return %", width="small"),
                "Bought": st.column_config.TextColumn("Purchase", width="small"),
            },
        )
        st.markdown(caption(
            "Return % = (current − invested) / invested from the single purchase record. "
            "Not annualized, not a multi-cashflow XIRR. Open the dossier for lump-sum "
            "annualized when Purchase Date is on the book."),
            unsafe_allow_html=True)
        return
    view = _money_view(df).sort_values("Current Value", ascending=False)
    st.dataframe(
        view[["Name", "Member", "Booked", "Invested ₹", "P&L ₹", "Return"]],
        hide_index=True, use_container_width=True,
        column_config={
            "Name": st.column_config.TextColumn("Instrument", width="medium"),
            "Member": st.column_config.TextColumn("Member", width="medium"),
            "Booked": st.column_config.TextColumn("Booked (INR)", width="small"),
            "Invested ₹": st.column_config.TextColumn("Invested (INR)", width="small"),
            "P&L ₹": st.column_config.TextColumn("P&L", width="small"),
            "Return": st.column_config.TextColumn("Return %", width="small"),
        },
    )
    st.markdown(caption(
        "Return % = (current − invested) / invested from the single purchase record. "
        "Not annualized, not XIRR."),
        unsafe_allow_html=True)


for _tab_name, _tab in zip(("Mutual funds", "Stocks", "Gold", "FDs"), tabs[1:]):
    with _tab:
        _render_sleeve(_map[_tab_name])

st.markdown("---")


# ---------------------------------------------------------------------------
# DOSSIER — one instrument at a time
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Dossier", "one instrument, whole record"), unsafe_allow_html=True)

_options = list(dict.fromkeys(roster["Key"].tolist()))
if len(_options) > 60:
    _options = sorted(_options, key=lambda k: str(roster[roster["Key"] == k].iloc[0]["Name"]))
_default = 0
_q_symbol = (st.query_params.get("symbol") or "").strip()
if _q_symbol:
    _hits = roster.index[roster["Key"].astype(str).eq(_q_symbol)
                         | roster["Name"].astype(str).eq(_q_symbol)].tolist()
    if _hits:
        _default = _hits[0]
def _dossier_label(k):
    hit = roster[roster["Key"] == k]
    if hit.empty:
        return str(k)
    r = hit.iloc[0]
    name = str(r["Name"] or "").strip()
    member = str(r["Member"] or "").strip()
    kind = str(r["Kind"] or "")
    bits = [b for b in (name, member, kind) if b]
    if kind == "FD":
        mat = str(r.get("Maturity") or "").strip()
        if mat and mat.lower() not in {"nan", "nat", "none", "—"}:
            ts = pd.to_datetime(mat, errors="coerce")
            bits.append(ts.strftime("%d %b %Y") if pd.notna(ts) else mat[:10])
    return " · ".join(bits) if bits else str(k)


choice = st.selectbox(
    "Instrument",
    _options,
    index=_default,
    key="holdings_dossier_instrument",
    format_func=_dossier_label,
)

_positions = roster[roster["Key"] == choice]
if len(_positions) > 1:
    st.markdown(caption(
        f"{len(_positions)} positions share this instrument key (different owners) — "
        "shown separately, never merged."), unsafe_allow_html=True)

for _idx, (__, row) in enumerate(_positions.iterrows()):
    if len(_positions) > 1:
        st.markdown(section_header_html(f"{row['Name']} · position {_idx + 1} of "
                                        f"{len(_positions)}", "position"), unsafe_allow_html=True)
    else:
        st.markdown(section_header_html(f"{row['Name']}", "dossier"), unsafe_allow_html=True)

    cur = _num(row["Current Value"])
    inv = _num(row["Invested"])
    pnl = _num(row["P&L"])
    ret = _num(row.get("Return %"))
    contrib = (cur / _total_assets * 100.0) if (cur is not None and _total_assets) else None

    st.markdown(
        '<div class="t-meta-row">'
        + pill(str(row["Kind"]), "info")
        + pill(str(row["Class"]), "neutral")
        + pill(str(row["Member"]) if len(str(row["Member"])) > 0 else "member n/a", "neutral")
        + (pill(f"{contrib:.1f}% of family assets", "positive") if contrib is not None else "")
        + '</div>',
        unsafe_allow_html=True,
    )
    if contrib is not None:
        st.markdown(caption(
            "Contribution % is this line ÷ family total assets (all members, all sleeves), "
            "not this member's book."),
            unsafe_allow_html=True)

    st.markdown(kpi_cards([
        {"label": "Current Value (INR)", "value": format_inr(cur) if cur is not None else "n/a",
         "tone": "accent", "sub": "register value" if cur is not None else "not valued here"},
        {"label": "Invested Basis", "value": format_inr(inv) if inv is not None else "n/a",
         "sub": "book cost"},
        {"label": "P&L", "value": format_inr(pnl) if pnl is not None else "n/a",
         "tone": tone_for(pnl) if pnl is not None else "neutral",
         "sub": f"{ret:.2f}%" if ret is not None else "no return basis"},
    ]), unsafe_allow_html=True)

    # Identity — from the book rows the Command Center published
    recs = _raw_records_for(books, str(row["Kind"]), str(row["Key"]))
    rec = recs[0] if recs else {}
    if str(row["Kind"]) == "FD" and str(rec.get("Currency") or "").strip().upper() == "USD":
        _int = _num(rec.get("Interest Return (INR)"))
        _fx = _num(rec.get("FX Gain/Loss (INR)"))
        _native = _num(rec.get("Principal (Native)"))
        _prin_inr = _num(rec.get("Principal (INR, at deposit FX)"))
        _rates = st.session_state.get("cc_rates") or {}
        _today_fx = _num(_rates.get("usd_inr"))
        _dep_fx = (_prin_inr / _native) if (_prin_inr is not None and _native) else None
        _fx_sub = "n/a"
        if _dep_fx is not None and _today_fx is not None:
            _fx_sub = f"deposit {_dep_fx:.2f} → today {_today_fx:.2f}"
        elif _today_fx is not None:
            _fx_sub = f"today {_today_fx:.2f}"
        st.markdown(section_header_html("FCNR return · two parts", "USD book marked to INR"),
                    unsafe_allow_html=True)
        st.markdown(kpi_cards([
            {"label": "Interest at today's FX",
             "value": format_inr(_int) if _int is not None else "n/a",
             "sub": "Accrued USD × this run's USD/INR",
             "tone": tone_for(_int) if _int is not None else "neutral"},
            {"label": "FX on principal",
             "value": format_inr(_fx) if _fx is not None else "n/a",
             "sub": "Principal × (today − deposit-date FX)",
             "tone": tone_for(_fx) if _fx is not None else "neutral"},
            {"label": "Native principal",
             "value": format_identity_value("Principal (native)", _native, currency="USD")
                      if _native is not None else "n/a",
             "sub": _fx_sub},
        ]), unsafe_allow_html=True)
        st.markdown(caption(
            "FCNR is a USD deposit book. Native principal and maturity proceeds stay in USD. "
            "INR is this run's mark. Interest + FX on principal = FCNR P&L within ₹1. "
            "Figures are the Command Center book columns, not a second valuation."),
            unsafe_allow_html=True)

    # Returns — three different numbers, three different questions. Never mixed.
    _as_of = _as_of_date()
    _pdate = rec.get("Purchase Date") or rec.get("Deposit Date")
    _days = holding_period_days(_pdate, _as_of)
    _roi = simple_roi_pct(cur, inv)
    _ann = _num(rec.get("Ann. Return %"))
    if _ann is None:
        _ann = lump_sum_annualized_pct(cur, inv, _days)
    _ret_cards = [
        {"label": "Simple ROI",
         "value": f"{_roi:.2f}%" if _roi is not None else "n/a",
         "sub": "current vs book cost",
         "tone": tone_for(_roi) if _roi is not None else "neutral"},
        {"label": "Lump-sum annualized",
         "value": f"{_ann:.2f}%" if _ann is not None else "n/a",
         "sub": (f"{_days} days held" if _days is not None else "needs purchase date + ≥30 days"),
         "tone": tone_for(_ann) if _ann is not None else "neutral"},
    ]
    if str(row["Kind"]) == "MF":
        _y1, _y3, _y5 = _num(rec.get("1Y %")), _num(rec.get("3Y %")), _num(rec.get("5Y %"))
        _ret_cards.append({
            "label": "Scheme 1Y / 3Y / 5Y",
            "value": " · ".join(
                f"{v:.1f}%" if v is not None else "—" for v in (_y1, _y3, _y5)
            ),
            "sub": "trailing CAGR of the NAV, not your cash-flow return",
        })
    st.markdown(section_header_html("How this line is doing", "three different returns"),
                unsafe_allow_html=True)
    st.markdown(kpi_cards(_ret_cards, cols=3), unsafe_allow_html=True)
    st.markdown(caption(SIMPLE_ROI_LABEL), unsafe_allow_html=True)
    st.markdown(caption(LUMP_SUM_ANN_LABEL), unsafe_allow_html=True)
    if str(row["Kind"]) == "MF":
        st.markdown(caption(TRAILING_CAGR_LABEL), unsafe_allow_html=True)
        _n1, _n3, _n5 = _num(rec.get("vs Nifty50 1Y")), _num(rec.get("vs Nifty50 3Y")), _num(rec.get("vs Nifty50 5Y"))
        if any(v is not None for v in (_n1, _n3, _n5)):
            st.markdown(caption(
                "Nifty50 trailing CAGR this run: "
                + " · ".join(
                    f"{lbl} {v:.1f}%" if v is not None else f"{lbl} —"
                    for lbl, v in (("1Y", _n1), ("3Y", _n3), ("5Y", _n5))
                )
                + " — a broad equity bar, not this fund's official benchmark."
            ), unsafe_allow_html=True)
    st.markdown(caption(MULTI_CASHFLOW_XIRR_GAP), unsafe_allow_html=True)

    identity = []
    if recs:
        rec = recs[0]
        kind = str(row["Kind"])
        if kind == "MF":
            fields = [("Fund Name", "Fund Name"), ("ISIN", "ISIN"),
                      ("Category", "Category"), ("Owner", "Owner"),
                      ("Units", "Units"), ("Current NAV", "Current NAV"),
                      ("Purchase Date", "Purchase Date")]
        elif kind == "Stocks":
            fields = [("Company Name", "Company"), ("Symbol", "Symbol"),
                      ("ISIN", "ISIN"),
                      ("Exchange", "Exchange"), ("Owner", "Owner"),
                      ("Quantity", "Quantity"), ("Avg Buy Price", "Avg buy"),
                      ("Current Price", "Last price"),
                      ("Purchase Date", "Purchase Date")]
        elif kind == "Gold":
            fields = [("Symbol", "Symbol"), ("Owner", "Owner"),
                      ("Quantity", "Quantity"), ("Current Price", "Last price"),
                      ("Purchase Date", "Purchase Date")]
        else:
            fields = [("Account Number", "Account Number"), ("Holder Name", "Holder"),
                      ("Product", "Product"), ("Currency", "Currency"),
                      ("ROI %", "ROI % p.a."), ("ROI % p.a.", "ROI % p.a."),
                      ("Maturity Date", "Maturity Date"),
                      ("Principal (Native)", "Principal (native)"),
                      ("Principal Amount", "Principal (native)"),
                      ("Current Value (INR)", "Booked value (INR)"),
                      ("Maturity Amount (Native)", "Maturity proceeds (native)")]
        seen_labels = set()
        for col, label in fields:
            if label in seen_labels:
                continue
            value = rec.get(col)
            if value is None or (isinstance(value, float) and value != value):
                continue
            if label == "Company" and looks_like_isin(value):
                recovered = extract_isin(value)
                if "ISIN" not in seen_labels and recovered:
                    seen_labels.add("ISIN")
                    identity.append({"Field": "ISIN", "Value": recovered})
                continue
            if not str(value).strip() or str(value).strip().lower() in {"nan", "none"}:
                continue
            seen_labels.add(label)
            native = label.lower().endswith("(native)")
            cur = rec.get("Currency") if native else None
            identity.append({"Field": label, "Value": format_identity_value(label, value, currency=cur)})
    identity.append({"Field": "Register key", "Value": str(row["Key"])})
    identity.append({"Field": "Asset class", "Value": str(row["Class"])})
    if identity:
        st.markdown(section_header_html("Identity", "record"), unsafe_allow_html=True)
        st.markdown(data_sheet(
            [{"label": r["Field"], "value": r["Value"]} for r in identity]),
            unsafe_allow_html=True)

    if str(row["Kind"]) == "MF":
        st.markdown(section_header_html("Look-through · this fund", "statutory disclosure cache"),
                    unsafe_allow_html=True)
        _code = _scheme_code_for(rec)
        _cache = load_holdings_cache()
        _raw = []
        if _code is not None:
            try:
                _raw = _cache.get(str(int(_code))) or _cache.get(str(_code)) or []
            except (TypeError, ValueError):
                _raw = _cache.get(str(_code)) or []
        _cleaned, _derived = _normalize_holdings(_raw if isinstance(_raw, list) else [])
        _top = sorted(_cleaned, key=lambda c: -(c.get("weight") or 0))[:10]
        if _top:
            _family_codes = []
            for _h in st.session_state.get("mf_holdings_for_health") or []:
                _sc = _h.get("Scheme Code")
                if _sc is not None:
                    _family_codes.append(_sc)
            _rows = []
            for _h in _top:
                _isin = str(_h.get("isin") or "").strip().upper()
                _also = 0
                if _isin:
                    for _oc in _family_codes:
                        if _code is not None and str(_oc) == str(_code):
                            continue
                        try:
                            _oraw = _cache.get(str(int(_oc))) or _cache.get(str(_oc)) or []
                        except (TypeError, ValueError):
                            _oraw = _cache.get(str(_oc)) or []
                        _oclean, _ = _normalize_holdings(_oraw if isinstance(_oraw, list) else [])
                        if any(str(x.get("isin") or "").strip().upper() == _isin for x in _oclean):
                            _also += 1
                _rows.append({
                    "Name": _h.get("name") or "—",
                    "Weight %": f"{_h['weight']:.2f}%" if _h.get("weight") is not None else "—",
                    "Also in": f"{_also} other family fund(s)" if _also else "this fund only",
                })
            st.dataframe(pd.DataFrame(_rows), hide_index=True, use_container_width=True)
            st.markdown(caption(
                "Weights are the fund's disclosed portfolio, not your rupee mix. "
                + ("Some weights derived from market value (disclosure had no weight_pct). "
                   if _derived else "")
                + "Also-in counts other schemes in this family's book that disclose the same ISIN."
            ), unsafe_allow_html=True)
        else:
            st.markdown(caption(
                "No disclosed holdings in the committed cache for this scheme. "
                "Look-through is no data, not zero. Refresh holdings from Funds if the cache is stale."),
                unsafe_allow_html=True)

    st.markdown(section_header_html("Health · this line in the book", "what the register actually knows"),
                unsafe_allow_html=True)
    _kind = str(row["Kind"])
    _last = _num(rec.get("Current Price"))
    _avg = _num(rec.get("Avg Buy Price"))
    _mark_vs_buy = None
    if _last is not None and _avg and _avg > 0:
        _mark_vs_buy = (_last / _avg - 1.0) * 100.0
    _health_cards = [
        {"label": "Simple ROI",
         "value": f"{_roi:.2f}%" if _roi is not None else "n/a",
         "sub": "current vs book cost",
         "tone": tone_for(_roi) if _roi is not None else "neutral"},
        {"label": "Lump-sum annualized",
         "value": f"{_ann:.2f}%" if _ann is not None else "n/a",
         "sub": f"{_days} days held" if _days is not None else "needs purchase date",
         "tone": tone_for(_ann) if _ann is not None else "neutral"},
        {"label": "Of family assets",
         "value": f"{contrib:.2f}%" if contrib is not None else "n/a",
         "sub": "this line ÷ total assets"},
    ]
    if _mark_vs_buy is not None:
        _health_cards.append({
            "label": "Mark vs avg buy",
            "value": f"{_mark_vs_buy:+.1f}%",
            "sub": "last price vs workbook avg buy — not a signal",
            "tone": tone_for(_mark_vs_buy),
        })
    if _kind == "MF":
        _y3 = _num(rec.get("3Y %"))
        _n3 = _num(rec.get("vs Nifty50 3Y"))
        _health_cards.append({
            "label": "Scheme 3Y vs Nifty50",
            "value": (
                f"{_y3:.1f}% vs {_n3:.1f}%" if _y3 is not None and _n3 is not None
                else (f"{_y3:.1f}%" if _y3 is not None else "n/a")
            ),
            "sub": "trailing NAV CAGR, not your XIRR",
        })
    st.markdown(kpi_cards(_health_cards, cols=4), unsafe_allow_html=True)

    if _kind == "Stocks":
        _isin = extract_isin(rec.get("ISIN"), rec.get("Company Name"), row.get("Key"))
        _also = _family_funds_holding(_isin) if _isin else []
        st.markdown(section_header_html("Also inside family funds", "look-through, same ISIN"),
                    unsafe_allow_html=True)
        if _also:
            _also_rows = []
            for item in _also:
                w = item.get("Weight %")
                _also_rows.append({
                    "Fund": item["Fund"],
                    "Member": item.get("Owner") or "",
                    "Weight in that fund": f"{w:.2f}%" if isinstance(w, (int, float)) else "—",
                })
            st.dataframe(pd.DataFrame(_also_rows), hide_index=True, use_container_width=True)
            st.markdown(caption(
                f"{len(_also)} scheme(s) in this family's MF book disclose {_isin or 'this ISIN'}. "
                "Weight is the fund's statutory portfolio, not your rupee mix. Direct holding above is extra."),
                unsafe_allow_html=True)
        else:
            st.markdown(caption(
                "No family fund in the committed holdings cache discloses this ISIN. "
                "That is 'not in the look-through', not 'zero overlap'."),
                unsafe_allow_html=True)

        st.markdown(section_header_html("Fundamentals · technicals", "what this desk does not have"),
                    unsafe_allow_html=True)
        st.markdown(caption(
            "PE, book value, earnings, shareholding, RSI, moving averages and candle patterns "
            "are not in the workbook and there is no NSE/BSE fundamentals or charting feed on this desk. "
            "SEC EDGAR covers US filers only. Missing stays missing — never a guessed PE or a buy/sell from candles. "
            "Health above is this line in YOUR book (cost, mark, days held, family weight, fund overlap)."),
            unsafe_allow_html=True)
    elif _kind == "MF":
        st.markdown(caption(
            "Scheme 1Y/3Y/5Y and Nifty bars come from the Command Center NAV path. "
            "Portfolio overlap, pairwise heatmap and the illustrative health index live on Funds — "
            "they are book-level, not re-scored here. This dossier does not fetch a new NAV series."),
            unsafe_allow_html=True)
    else:
        st.markdown(caption(
            "No PE / RSI overlay is computed for gold or deposits. FCNR health is the two-part "
            "return above; INR FD health is contractual ROI and days to maturity."),
            unsafe_allow_html=True)

    st.markdown(section_header_html("Not recorded for this position", "no-data"),
                unsafe_allow_html=True)
    st.markdown(empty_state(
        "NRI / tax treatment is not modelled",
        "No tax ledger, FEMA classification, or treaty treatment exists in the workbook. "
        "This is not tax advice. Missing stays missing — never filled with zero.",
    ), unsafe_allow_html=True)
    st.markdown(
        "<div class='t-card'><ul class='t-list'>"
        "<li>True multi-cashflow XIRR — SIPs, sells and dividends are not stored; lump-sum annualized is the one-buy number above</li>"
        "<li>Rolling CAGR series — NAV path is not kept on this page</li>"
        "<li>Dividends / corporate actions — no payout or tax ledger exists</li>"
        "<li>Tax treatment — not modelled for any asset</li>"
        "<li>Cash flows — the workbook records positions, not deposits/withdrawals</li>"
        "</ul></div>",
        unsafe_allow_html=True,
    )

    related = []
    if cohort is not None:
        try:
            terms = {str(t).upper() for t in (row.get("Match Terms") or [])}
            for dev in development_rows(cohort, None, None):
                affected = {
                    a.strip().upper()
                    for a in str(dev.get("Affected") or "").split(",")
                    if a.strip() and a.strip() != "—"
                }
                if terms and (terms & affected):
                    related.append(dev)
        except Exception:
            pass
    st.markdown(section_header_html("Related external developments", "evidence"),
                unsafe_allow_html=True)
    if related:
        rel_cols = ["Development", "Source", "Published", "Category", "Link"]
        st.dataframe(pd.DataFrame(related[:6]),
                     hide_index=True, use_container_width=True,
                     column_config={"Link": st.column_config.LinkColumn("Link")})
    else:
        st.markdown(caption(
            "No external developments mapped to this exact identifier "
            "(refresh research evidence in the Command Center to build the cohort)."),
            unsafe_allow_html=True)

    st.markdown(section_header_html("AI interpretation", "opt-in · never on load"),
                unsafe_allow_html=True)
    st.markdown(caption(
        "AI restates verified facts from the Command Center research brief. "
        "It never computes a rupee, never invents XIRR, PE or a trade, and never runs when this page opens."
    ), unsafe_allow_html=True)
    _ai_key = f"holdings_ai_{row['Key']}_{_idx}"
    try:
        _ai_cfg = load_ai_config()
        _ai_ready = provider_is_configured(_ai_cfg)
    except Exception:
        _ai_ready = False
    if not _ai_ready:
        st.markdown(caption(
            "No AI provider is configured (local Ollama or an API key in secrets). "
            "The numbers above stay the source of truth."
        ), unsafe_allow_html=True)
    _run_ai = st.button(
        "Interpret this instrument (opt-in AI)",
        key=_ai_key,
        help="Calls the existing research provider with the Command Center brief. Never on page load.",
    )
    if _run_ai:
        _brief = st.session_state.get("cc_research_brief")
        _briefing = st.session_state.get("cc_intel_briefing")
        if _brief is None:
            st.warning("Open Command Center once so the research brief exists. AI will not invent one.")
        else:
            _q = (
                f"Given only the verified family research brief, what does the evidence say "
                f"about the instrument classified as {row['Kind']} / {row['Class']} named "
                f"{str(row['Name'])[:80]}"
                f" (symbol {str(rec.get('Symbol') or row.get('Key') or '')[:24]}, "
                f"ISIN {extract_isin(rec.get('ISIN'), rec.get('Company Name')) or 'n/a'})"
                f"? Restate verified numbers. Do not invent PE, RSI, "
                f"XIRR, tax or a buy/sell. Say where evidence is thin."
            )
            with st.spinner("AI is reading the verified brief…"):
                _out = intel_ai.run_ai_research(
                    brief=_brief,
                    facts=getattr(_briefing, "facts", ()) or (),
                    evidence=getattr(_briefing, "evidence", ()) or (),
                    question=_q,
                )
            st.session_state[_ai_key + "_out"] = _out
    _stored = st.session_state.get(_ai_key + "_out")
    if _stored is not None:
        _status = getattr(_stored, "status", "")
        if _status == "ok" and getattr(_stored, "assessment", None) is not None:
            _ass = _stored.assessment
            st.markdown(caption(str(getattr(_ass, "overall_assessment", "") or "")),
                        unsafe_allow_html=True)
            if getattr(_ass, "uncertainty", None):
                st.markdown(caption("Uncertainty: " + str(_ass.uncertainty)),
                            unsafe_allow_html=True)
            for _f in (getattr(_ass, "findings", None) or [])[:5]:
                st.markdown(caption("· " + str(getattr(_f, "text", _f))),
                            unsafe_allow_html=True)
            st.markdown(caption(
                "Decision-support only. Not an order. Numbers on this page were not rewritten."
            ), unsafe_allow_html=True)
        else:
            _label = getattr(_stored, "status_label", None) or _status or "unavailable"
            _reason = str(getattr(_stored, "reason", "") or "").strip()
            _line = f"AI did not produce a grounded reading — {_label}."
            if _reason:
                _line += f" {_reason}"
            if _status == "not_configured":
                _line += " Configure a local Ollama endpoint or an API key in secrets. The numbers above stay the source of truth."
            elif _status == "insufficient_evidence":
                _line += " Open Command Center so the research brief has evidence; AI will not invent it."
            else:
                _line += " The deterministic dossier above is unchanged."
            st.markdown(caption(_line), unsafe_allow_html=True)

st.markdown("---")
st.markdown(
    '<div class="t-footnote">Figures come from the Command Center register — this page '
    're-presents them and never re-values. Valuation basis: AMFI NAVs / exchange closes / '
    'USD-INR at the last Command Center run.</div>',
    unsafe_allow_html=True,
)