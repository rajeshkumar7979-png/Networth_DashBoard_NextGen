"""Investor intelligence board. Every figure comes from the tape or the book row."""
from __future__ import annotations

import html
import pandas as pd


def _num(value):
    try:
        n = float(str(value).replace("%", "").replace(",", "").replace("₹", ""))
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def _row(tape, label):
    for section in ("fundamentals", "technicals"):
        for row in ((tape or {}).get(section) or {}).get("rows") or []:
            if str(row.get("label") or "") == label:
                return row.get("value")
    return None


def _fmt(value, kind="num"):
    n = _num(value)
    if n is None:
        return "—"
    if kind == "px":
        return f"₹{n:,.2f}"
    if kind == "pct":
        return f"{n:.2f}%"
    if kind == "inr":
        return f"₹{n:,.0f}"
    return f"{n:,.2f}"


def _weight(pack):
    for item in pack.parameters or []:
        if item.get("Parameter") == "Weight of family assets":
            return item.get("Value")
    return None


def _verdict(pack, tape):
    pe = _num(_row(tape, "Trailing P/E"))
    sector = _num(_row(tape, "Trailing P/E sector"))
    premium = pe / sector if pe and sector else None
    if pack.red or (premium and premium >= 2):
        return "RED", "Elevated observed band. Not a sell."
    if pack.watch or (premium and premium >= 1.3):
        return "AMBER", "Watch band. Not an order."
    return "GREEN", "No elevated band on the loaded tape. Not a buy."


def _lines(flags):
    if not flags:
        return "<div class='ni-empty'>None on verified inputs.</div>"
    return "".join(
        "<div class='ni-li'><b>%s.</b> %s</div>" % (html.escape(f.label), html.escape(f.text))
        for f in flags[:5]
    )


def _reading(pack, tape, rec):
    tone, line = _verdict(pack, tape)
    pe = _fmt(_row(tape, "Trailing P/E"))
    sector = _fmt(_row(tape, "Trailing P/E sector"))
    weight = _fmt(_weight(pack), "pct")
    profit = next((r for r in (tape.get("statements") or []) if "profit" in str(r.get("Line") or "").lower()), None)
    bits = [
        "%s is %s of published family assets." % (pack.symbol or pack.name, weight),
        "Trailing P/E is %s against a sector %s." % (pe, sector),
    ]
    if profit:
        bits.append("Latest %s is %s %s (%s)." % (profit.get("Line"), profit.get("Latest"), profit.get("Unit") or "", profit.get("Period") or ""))
    if not tape.get("news"):
        bits.append("No instrument news was returned for the last 7 days.")
    bits.append(line)
    return tone, " ".join(bits)


def render_stock_board(st, pack, tape, rec):
    tape = tape or {}
    rec = rec or {}
    tone, reading = _reading(pack, tape, rec)
    tone_cls = {"GREEN": "ni-green", "AMBER": "ni-amber", "RED": "ni-red"}[tone]
    pe = _row(tape, "Trailing P/E")
    sector = _row(tape, "Trailing P/E sector")
    premium = ""
    if _num(pe) and _num(sector):
        premium = "%.1fx sector" % (_num(pe) / _num(sector))
    st.markdown("""
    <style>
    .ni { color:#e8edf2; }
    .ni h2 { font-size:1.45rem; margin:0; letter-spacing:-0.03em; }
    .ni-sub { color:#93a0ad; font-size:0.85rem; margin:0.2rem 0 0.8rem; }
    .ni-sec { margin:1rem 0 0.4rem; font-size:0.72rem; letter-spacing:0.08em; color:#8b95a1; }
    .ni-rule { border-top:1px solid #2c3440; margin:0.8rem 0; }
    .ni-row { display:flex; flex-wrap:wrap; gap:1.2rem; font-size:1.05rem; }
    .ni-k { color:#8b95a1; font-size:0.72rem; display:block; }
    .ni-verdict { border-radius:10px; padding:0.8rem 1rem; margin:0.4rem 0 0.8rem; }
    .ni-green { background:#10261a; } .ni-amber { background:#2a2412; } .ni-red { background:#2a1416; }
    .ni-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:0.55rem; }
    .ni-box { border-radius:10px; padding:0.7rem; min-height:6.5rem; }
    .ni-g { background:#10261a; } .ni-r { background:#2a1416; } .ni-w { background:#2a2412; } .ni-d { background:#141c2a; }
    .ni-li { margin:0.25rem 0; font-size:0.86rem; }
    .ni-empty { color:#8b95a1; font-size:0.86rem; }
    </style>
    """, unsafe_allow_html=True)
    st.markdown(
        "<div class='ni'><h2>%s — INVESTOR INTELLIGENCE</h2>"
        "<div class='ni-sub'>%s · %s · %s</div>"
        "<div class='ni-sec'>PRICE / VALUATION SNAPSHOT</div>"
        "<div class='ni-row'><div><span class='ni-k'>Last</span>%s</div>"
        "<div><span class='ni-k'>P/E</span>%s <span class='ni-k'>%s</span></div>"
        "<div><span class='ni-k'>Sector P/E</span>%s</div>"
        "<div><span class='ni-k'>P/B</span>%s <span class='ni-k'>sector %s</span></div>"
        "<div><span class='ni-k'>Portfolio</span>%s</div></div>"
        "<div class='ni-sec'>INVESTOR VERDICT</div>"
        "<div class='ni-verdict %s'><b>%s</b><div>%s</div></div>"
        "<div class='ni-sec'>GREEN · RED · WATCH · GAPS</div>"
        "<div class='ni-grid'><div class='ni-box ni-g'><b>Green</b>%s</div>"
        "<div class='ni-box ni-r'><b>Red</b>%s</div>"
        "<div class='ni-box ni-w'><b>Watch</b>%s</div>"
        "<div class='ni-box ni-d'><b>Gaps</b>%s</div></div></div>"
        % (
            html.escape(pack.symbol or pack.name or "Stock"),
            html.escape(pack.member or "—"),
            html.escape(pack.symbol or "NSE"),
            html.escape(str(tape.get("source") or "Tape")),
            _fmt(_row(tape, "Last price"), "px"),
            _fmt(pe),
            html.escape(premium),
            _fmt(sector),
            _fmt(_row(tape, "Price / Book")),
            _fmt(_row(tape, "Price / Book sector")),
            _fmt(_weight(pack), "pct"),
            tone_cls,
            tone,
            html.escape(reading),
            _lines(pack.green),
            _lines(pack.red),
            _lines(pack.watch),
            _lines(pack.gaps),
        ),
        unsafe_allow_html=True,
    )
    st.markdown("<div class='ni-sec'>VALUATION</div>", unsafe_allow_html=True)
    st.write("P/E %s vs sector %s. P/B %s vs sector %s. Forward P/E and a history of the multiple are not on this tape." % (
        _fmt(pe), _fmt(sector), _fmt(_row(tape, "Price / Book")), _fmt(_row(tape, "Price / Book sector")),
    ))
    st.markdown("<div class='ni-sec'>FINANCIAL QUALITY</div>", unsafe_allow_html=True)
    if tape.get("statements"):
        st.dataframe(pd.DataFrame(tape["statements"]), hide_index=True, use_container_width=True)
    else:
        st.caption("No statement rows returned.")
    st.write("ROE %s. ROCE %s. ROA %s. A missing ratio stays missing." % (
        _fmt(_row(tape, "ROE"), "pct"), _fmt(_row(tape, "ROCE"), "pct"), _fmt(_row(tape, "ROA"), "pct"),
    ))
    st.markdown("<div class='ni-sec'>TECHNICAL HEALTH</div>", unsafe_allow_html=True)
    st.write("SMA 20 %s · SMA 50 %s · SMA 200 %s · RSI-14 %s · 52-week %s to %s." % (
        _fmt(_row(tape, "SMA 20"), "px"), _fmt(_row(tape, "SMA 50"), "px"), _fmt(_row(tape, "SMA 200"), "px"),
        _fmt(_row(tape, "RSI-14")), _fmt(_row(tape, "52-week low"), "px"), _fmt(_row(tape, "52-week high"), "px"),
    ))
    if tape.get("history"):
        st.line_chart(pd.DataFrame({"Close": tape["history"]}))
    left, right = st.columns(2)
    with left:
        st.markdown("<div class='ni-sec'>OWNERSHIP</div>", unsafe_allow_html=True)
        if tape.get("shareholding"):
            st.dataframe(pd.DataFrame(tape["shareholding"]), hide_index=True, use_container_width=True)
    with right:
        st.markdown("<div class='ni-sec'>CORPORATE ACTIONS</div>", unsafe_allow_html=True)
        if tape.get("actions"):
            st.dataframe(pd.DataFrame(tape["actions"]), hide_index=True, use_container_width=True)
        else:
            st.caption("No corporate action returned.")
    st.markdown("<div class='ni-sec'>PORTFOLIO CONTEXT</div>", unsafe_allow_html=True)
    st.write("Weight %s · current %s · invested %s · P&L %s. Book row, not an Upstox holdings pull." % (
        _fmt(_weight(pack), "pct"), _fmt(rec.get("Current Value"), "inr"),
        _fmt(rec.get("Invested"), "inr"), _fmt(rec.get("P&L"), "inr"),
    ))
    if pack.family_overlap:
        st.dataframe(pd.DataFrame(pack.family_overlap), hide_index=True, use_container_width=True)
    else:
        st.caption("No family fund in the holdings cache discloses this ISIN.")
    st.markdown("<div class='ni-sec'>NEWS AND DEVELOPMENTS</div>", unsafe_allow_html=True)
    if tape.get("news"):
        st.dataframe(pd.DataFrame(tape["news"]), hide_index=True, use_container_width=True)
    else:
        st.caption("No instrument news in the last 7 days. Unmapped stays unmapped.")
    if pack.developments:
        st.dataframe(pd.DataFrame(pack.developments), hide_index=True, use_container_width=True)
    st.markdown("<div class='ni-sec'>AI INVESTOR READING</div>", unsafe_allow_html=True)
    st.write(reading)
    st.caption("This reading is computed from the rows above. A provider failure does not remove it.")
