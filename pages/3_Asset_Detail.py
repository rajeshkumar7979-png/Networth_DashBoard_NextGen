import streamlit as st
import pandas as pd

from lib.theme import inject_css
from lib.portfolio import load_excel
from lib.register import canonical_instrument_key, assign_asset_class
from lib.roster import build_roster
from lib.formatters import format_inr
from lib.ui import (
    page_header_html,
    section_header_html,
    kpi_cards,
    pill,
    tone_for,
    caption,
    footnote,
    empty_state,
)
from lib.intelligence.live import development_rows

inject_css()

st.markdown(page_header_html(
    "Instrument dossier",
    "Asset Detail",
    "One holding, one view · identity, value, basis and the evidence around it — "
    "this page re-presents the Command Center's numbers, never re-values",
), unsafe_allow_html=True)
st.page_link("pages/1_Command_Center.py", label="Command Center", icon="📊")

BOOK_KIND = {"MF": "mf", "Stocks": "stocks", "Gold": "gold", "FD": "fd"}


def _num(value):
    try:
        v = float(value)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _raw_records_for(books, kind, key):
    """Original book row(s) behind a canonical key — the page only *shows* what
    the books already contain; nothing is derived or invented here."""
    book = (books or {}).get(BOOK_KIND.get(kind))
    if book is None or book.empty:
        return []
    out = []
    for _, row in book.iterrows():
        rec = row.to_dict()
        if canonical_instrument_key(kind, rec) == key:
            out.append(rec)
    return out


def _fallback_roster():
    """Degraded path (no session data): workbook rows only — identity without
    invented valuation. A gold row keeps its workbook kind; the class label
    still reflects Command Center routing rules."""
    try:
        fd, mf, stocks = load_excel()
    except Exception:
        return pd.DataFrame()
    rows = []
    for df, kind, name_col, member_col in (
        (mf, "MF", "Fund Name", "Owner"),
        (stocks, "Stocks", "Company Name", "Owner"),
        (fd, "FD", "Account Number", "Holder Name"),
    ):
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            rec = r.to_dict()
            key = canonical_instrument_key(kind, rec)
            if not key:
                continue
            nm = rec.get(name_col) or (rec.get("ISIN") if kind == "MF" else
                                       (rec.get("Symbol") if kind == "Stocks" else ""))
            rows.append({
                "Key": key,
                "Name": str(nm).strip() or key,
                "Kind": kind,
                "Class": assign_asset_class(kind, rec),
                "Member": str(rec.get(member_col) or "").strip(),
                "Current Value": None,
                "Invested": None,
                "P&L": None,
                "Return %": None,
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


books = st.session_state.get("cc_books")
assets = st.session_state.get("cc_assets")
cohort = st.session_state.get("cc_live_cohort")
source_txt = "Command Center session data"

roster = None
if isinstance(books, dict):
    try:
        roster = build_roster(**books)
    except Exception:
        roster = None
if roster is None or len(roster) == 0:
    roster = _fallback_roster()
    if not roster.empty:
        source_txt = "workbook rows only — open Command Center for live valuation"

if roster.empty:
    st.markdown(empty_state(
        "No holdings to drill into",
        "Open the Command Center first — it publishes the validated books this page reads.",
    ), unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------------------
# SELECTOR
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Find the instrument", "selector"),
            unsafe_allow_html=True)
st.markdown(caption(f"Source: {source_txt}"), unsafe_allow_html=True)

_options = roster["Key"].tolist()
_default = 0
_q_symbol = (st.query_params.get("symbol") or "").strip()
if _q_symbol:
    _hits = roster.index[roster["Key"].astype(str).eq(_q_symbol)
                         | roster["Name"].astype(str).eq(_q_symbol)].tolist()
    if _hits:
        _default = _hits[0]
choice = st.selectbox(
    "Instrument",
    _options,
    index=_default,
    format_func=lambda k: f"{roster[roster['Key'] == k].iloc[0]['Name']} · "
                          f"{roster[roster['Key'] == k].iloc[0]['Kind']}",
)

_total_assets = _num((assets.get("total_assets")) if isinstance(assets, dict) else None)
if _total_assets is None:
    _tot_sum = roster["Current Value"].sum()
    _total_assets = _num(_tot_sum)

_positions = roster[roster["Key"] == choice]
if len(_positions) > 1:
    st.markdown(caption(
        f"{len(_positions)} positions share this instrument key (different owners) — "
        "shown separately, never merged."), unsafe_allow_html=True)

for _idx, (__, row) in enumerate(_positions.iterrows()):
    st.markdown("---")
    if len(_positions) > 1:
        st.markdown(
            section_header_html(f"{row['Name']} · position {_idx + 1} of "
                                f"{len(_positions)}", "position"),
            unsafe_allow_html=True)
    else:
        st.markdown(section_header_html(f"{row['Name']}", "dossier"),
                    unsafe_allow_html=True)

    cur = _num(row["Current Value"])
    inv = _num(row["Invested"])
    pnl = _num(row["P&L"])
    ret = _num(row.get("Return %"))
    contrib = (cur / _total_assets * 100.0) if (cur is not None and _total_assets) else None

    chip_row = (
        '<div class="t-meta-row">'
        + pill(str(row["Kind"]), "info")
        + pill(str(row["Class"]), "neutral")
        + pill(str(row["Member"]) if len(row["Member"]) > 0 else "member n/a", "neutral")
        + (pill(f"{contrib:.1f}% of assets", "positive") if contrib is not None else "")
        + '</div>'
    )
    st.markdown(chip_row, unsafe_allow_html=True)

    st.markdown(kpi_cards([
        {"label": "Current Value (INR)", "value": format_inr(cur) if cur is not None else "n/a",
         "tone": "accent", "sub": "register value" if cur is not None else "not valued here"},
        {"label": "Invested Basis", "value": format_inr(inv) if inv is not None else "n/a",
         "sub": "book cost"},
        {"label": "P&L", "value": format_inr(pnl) if pnl is not None else "n/a",
         "tone": tone_for(pnl) if pnl is not None else "neutral",
         "sub": f"{ret:.2f}%" if ret is not None else "no return basis"},
    ]), unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # IDENTITY — from the book rows the Command Center published
    # ------------------------------------------------------------------
    recs = _raw_records_for(books, str(row["Kind"]), str(row["Key"]))
    identity = []
    if recs:
        rec = recs[0]
        kind = str(row["Kind"])
        if kind == "MF":
            fields = [("Fund Name", "Fund Name"), ("ISIN", "ISIN"),
                      ("Category", "Category"), ("Owner", "Owner")]
        elif kind == "Stocks":
            fields = [("Company Name", "Company"), ("Symbol", "Symbol"),
                      ("Exchange", "Exchange"), ("Owner", "Owner")]
        elif kind == "Gold":
            fields = [("Symbol", "Symbol"), ("Owner", "Owner")]
        else:
            fields = [("Account Number", "Account Number"), ("Holder Name", "Holder"),
                      ("Product", "Product"), ("Currency", "Currency"),
                      ("ROI % p.a.", "ROI % p.a."), ("Maturity Date", "Maturity Date"),
                      ("Principal Amount", "Principal (native)")]
        for col, label in fields:
            value = rec.get(col)
            if value is not None and not (isinstance(value, float) and value != value):
                identity.append({"Field": label, "Value": str(value)})
    identity.append({"Field": "Register key", "Value": str(row["Key"])})
    identity.append({"Field": "Asset class", "Value": str(row["Class"])})
    if len(identity):
        st.markdown(section_header_html("Identity", "record"), unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(identity)[["Field", "Value"]],
            hide_index=True, width="stretch",
        )

    # ------------------------------------------------------------------
    # WHAT IS NOT RECORDED — explicit, never guessed
    # ------------------------------------------------------------------
    st.markdown(section_header_html("Not recorded for this position", "no-data"),
                unsafe_allow_html=True)
    st.markdown(
        "<div class='t-card'><ul class='t-list'>"
        "<li>XIRR / return history — transaction dates beyond the purchase record are not stored</li>"
        "<li>Dividends / corporate actions — no payout or tax ledger exists</li>"
        "<li>Tax treatment — not modelled for any asset</li>"
        "<li>Cash flows — the workbook records positions, not deposits/withdrawals</li>"
        "</ul></div>",
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # EXTERNAL DEVELOPMENTS MAPPED TO THIS EXACT IDENTIFIER
    # ------------------------------------------------------------------
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
                     hide_index=True, width="stretch",
                     column_config={"Link": st.column_config.LinkColumn("Link")})
    else:
        st.markdown(caption(
            "No external developments mapped to this exact identifier "
            "(refresh research evidence in the Command Center to build the cohort)."),
            unsafe_allow_html=True)

st.markdown("---")
st.markdown(footnote(
    "Figures come from the Command Center's register — this page re-presents them and never "
    "re-values. Valuation basis: AMFI NAVs / exchange closes / USD-INR at the last Command "
    "Center run."), unsafe_allow_html=True)