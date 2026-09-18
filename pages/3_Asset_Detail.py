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
from lib.formatters import format_inr, format_identity_value
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
        products, accounts = [], []
        for _, r in df.iterrows():
            recs = _raw_records_for(books, "FD", str(r["Key"]))
            rec = recs[0] if recs else {}
            product = str(rec.get("Product") or r.get("Class") or "FD")
            if product.upper() == "FCNR":
                product = "FCNR (USD)"
            products.append(product)
            accounts.append(str(rec.get("Account Number") or ""))
        df["Product"] = products
        df["Account"] = accounts
        view = _money_view(df).sort_values("Current Value", ascending=False)
        st.dataframe(
            view[["Product", "Account", "Member", "Maturity",
                  "Booked", "Invested ₹", "P&L ₹", "Return"]],
            hide_index=True, use_container_width=True,
            column_config={
                "Product": st.column_config.TextColumn("Product", width="small"),
                "Account": st.column_config.TextColumn("Account", width="small"),
                "Member": st.column_config.TextColumn("Member", width="medium"),
                "Maturity": st.column_config.TextColumn("Maturity", width="small"),
                "Booked": st.column_config.TextColumn("Booked (INR)", width="small"),
                "Invested ₹": st.column_config.TextColumn("Invested (INR)", width="small"),
                "P&L ₹": st.column_config.TextColumn("P&L", width="small"),
                "Return": st.column_config.TextColumn("Return %", width="small"),
            },
        )
        st.markdown(caption(
            "Booked = Current Value (INR). Return % is (booked − invested) / invested "
            "from the single purchase record — not annualized, not XIRR. "
            "ROI % p.a. in the dossier is the contractual rate."),
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
choice = st.selectbox(
    "Instrument",
    _options,
    index=_default,
    key="holdings_dossier_instrument",
    format_func=lambda k: (
        (lambda n, kind: f"{n} · {kind}" if n else f"{kind} · {k}")(
            str(roster[roster["Key"] == k].iloc[0]["Name"] or "").strip(),
            str(roster[roster["Key"] == k].iloc[0]["Kind"]),
        )
    ),
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

    st.markdown(section_header_html("Not recorded for this position", "no-data"),
                unsafe_allow_html=True)
    st.markdown(empty_state(
        "NRI / tax treatment is not modelled",
        "No tax ledger, FEMA classification, or treaty treatment exists in the workbook. "
        "This is not tax advice. Missing stays missing — never filled with zero.",
    ), unsafe_allow_html=True)
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