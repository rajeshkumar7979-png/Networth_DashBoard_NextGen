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
from lib.roster import build_roster, instrument_summary, member_filter_options
from lib.formatters import format_inr
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
    _total_assets = _num(pd.to_numeric(roster["Current Value"], errors="coerce").sum())


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
    st.dataframe(
        _show[["Name", "Member", "Kind", "Class", "Current Value", "Invested", "P&L", "Return %"]]
        .sort_values("Current Value", ascending=False),
        hide_index=True, use_container_width=True,
        column_config={
            "Name": st.column_config.TextColumn("Instrument", width="medium"),
            "Member": st.column_config.TextColumn("Member", width="small"),
            "Kind": st.column_config.TextColumn("Sleeve", width="small"),
            "Class": st.column_config.TextColumn("Class", width="small"),
            "Current Value": st.column_config.NumberColumn("Current (INR)", format="₹%d"),
            "Invested": st.column_config.NumberColumn("Invested (INR)", format="₹%d"),
            "P&L": st.column_config.NumberColumn("P&L", format="₹%d"),
            "Return %": st.column_config.NumberColumn("Return %", format="%.2f%%"),
        },
    )

_map = {"Mutual funds": "MF", "Stocks": "Stocks", "Gold": "Gold", "FDs": "FD"}


def _render_sleeve(kind):
    sub = _show[_show["Kind"] == kind]
    if sub.empty:
        st.markdown(caption("Nothing in this sleeve for the selected member(s)."),
                    unsafe_allow_html=True)
        return
    cols = ["Name", "Member", "Current Value", "Invested", "P&L", "Return %"]
    if kind == "FD":
        cols = ["Name", "Member", "Maturity", "Current Value", "Invested", "P&L", "Return %"]
    df = sub.copy()
    if kind == "FD":
        df["Maturity"] = "—"
    st.dataframe(df[cols].sort_values("Current Value", ascending=False),
                 hide_index=True, use_container_width=True,
                 column_config={
                     "Name": st.column_config.TextColumn("Instrument", width="medium"),
                     "Member": st.column_config.TextColumn("Member", width="small"),
                     "Maturity": st.column_config.TextColumn("Maturity", width="small"),
                     "Current Value": st.column_config.NumberColumn("Current (INR)", format="₹%d"),
                     "Invested": st.column_config.NumberColumn("Invested (INR)", format="₹%d"),
                     "P&L": st.column_config.NumberColumn("P&L", format="₹%d"),
                     "Return %": st.column_config.NumberColumn("Return %", format="%.2f%%"),
                 })


for _tab_name, _tab in zip(("Mutual funds", "Stocks", "Gold", "FDs"), tabs[1:]):
    with _tab:
        _render_sleeve(_map[_tab_name])

st.markdown("---")


# ---------------------------------------------------------------------------
# DOSSIER — one instrument at a time
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Dossier", "one instrument, whole record"), unsafe_allow_html=True)

_options = roster["Key"].tolist()
if len(_options) > 60:
    _options = sorted(_options, key=lambda k: str(roster[roster["Key"] == k].iloc[0]["Name"]))
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
        + (pill(f"{contrib:.1f}% of assets", "positive") if contrib is not None else "")
        + '</div>',
        unsafe_allow_html=True,
    )

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
    if identity:
        st.markdown(section_header_html("Identity", "record"), unsafe_allow_html=True)
        st.markdown(data_sheet(
            [{"label": r["Field"], "value": r["Value"]} for r in identity]),
            unsafe_allow_html=True)

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

st.markdown("---")
st.markdown(
    '<div class="t-footnote">Figures come from the Command Center register — this page '
    're-presents them and never re-values. Valuation basis: AMFI NAVs / exchange closes / '
    'USD-INR at the last Command Center run.</div>',
    unsafe_allow_html=True,
)