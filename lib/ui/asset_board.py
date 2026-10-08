"""Stock board for Asset Intelligence. Renders only fields on the tape or book row."""
from __future__ import annotations

import pandas as pd


def _num(value):
    try:
        n = float(value)
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
        return f"{n:,.2f}"
    if kind == "pct":
        return f"{n:.2f}%"
    if kind == "inr":
        return f"₹{n:,.0f}"
    return f"{n:,.2f}"


def _card(label, value, note=""):
    note_html = f'<div class="ab-note">{note}</div>' if note else ""
    return (
        '<div class="ab-card"><div class="ab-k">' + label + '</div>'
        '<div class="ab-v">' + value + '</div>' + note_html + '</div>'
    )


def render_stock_board(st, pack, tape, rec):
    tape = tape or {}
    rec = rec or {}
    last = _row(tape, "Last price")
    prev = _row(tape, "Previous close")
    change = _row(tape, "Day change")
    pe = _row(tape, "Trailing P/E")
    pe_sector = _row(tape, "Trailing P/E sector")
    pb = _row(tape, "Price / Book")
    pb_sector = _row(tape, "Price / Book sector")
    premium = None
    if _num(pe) and _num(pe_sector):
        premium = _num(pe) / _num(pe_sector)
    pe_note = f"{premium:.1f}x sector" if premium else ""
    css = """
    <style>
    .ab-head { display:flex; justify-content:space-between; gap:1rem; align-items:flex-end; }
    .ab-title { font-size:1.6rem; font-weight:650; letter-spacing:-0.03em; }
    .ab-sub { color:#9aa3ad; font-size:0.82rem; margin-top:0.2rem; }
    .ab-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:0.6rem; margin:0.8rem 0; }
    .ab-card { border:1px solid #2a3140; border-radius:10px; padding:0.7rem 0.8rem; background:#12161c; }
    .ab-k { color:#8b95a1; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em; }
    .ab-v { font-size:1.15rem; margin-top:0.25rem; }
    .ab-note { color:#d7b15e; font-size:0.75rem; margin-top:0.2rem; }
    .ab-flags { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:0.6rem; }
    .ab-flag { border-radius:10px; padding:0.7rem 0.8rem; min-height:7rem; }
    .ab-g { background:#10261a; } .ab-r { background:#2a1416; }
    .ab-w { background:#2a2412; } .ab-d { background:#141c2a; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    st.markdown(
        '<div class="ab-head"><div><div class="ab-title">'
        + f"{pack.symbol or pack.name} · {pack.member or ''}"
        + '</div><div class="ab-sub">'
        + f"{tape.get('source') or 'Tape'} · {tape.get('retrieved_at') or 'loaded'}"
        + '</div></div></div>',
        unsafe_allow_html=True,
    )
    cards = "".join([
        _card("Last price", _fmt(last, "px"), _fmt(change, "pct") if change is not None else ""),
        _card("Day open", _fmt(_row(tape, "Day open"), "px")),
        _card("Day high", _fmt(_row(tape, "Day high"), "px")),
        _card("Day low", _fmt(_row(tape, "Day low"), "px")),
        _card("Previous close", _fmt(prev, "px")),
        _card("Trailing P/E", _fmt(pe), pe_note),
        _card("Sector P/E", _fmt(pe_sector)),
        _card("Price / Book", _fmt(pb), "sector " + _fmt(pb_sector) if pb_sector is not None else ""),
    ])
    st.markdown('<div class="ab-grid">' + cards + '</div>', unsafe_allow_html=True)

    overview, valuation, technicals, ownership, news, impact, ai = st.tabs([
        "Overview", "Valuation", "Technicals", "Ownership", "News", "Portfolio", "AI",
    ])
    with overview:
        flags = (
            '<div class="ab-flags">'
            + _flag_box("Green", pack.green, "ab-g")
            + _flag_box("Red", pack.red, "ab-r")
            + _flag_box("Watch", pack.watch, "ab-w")
            + _flag_box("Gaps", pack.gaps, "ab-d")
            + '</div>'
        )
        st.markdown(flags, unsafe_allow_html=True)
        history = tape.get("history") or []
        if history:
            st.line_chart(pd.DataFrame({"Close": history}))
        if tape.get("statements"):
            st.dataframe(pd.DataFrame(tape["statements"]), hide_index=True, use_container_width=True)
    with valuation:
        st.markdown(
            '<div class="ab-grid">'
            + _card("Trailing P/E", _fmt(pe), pe_note)
            + _card("Sector P/E", _fmt(pe_sector))
            + _card("ROE", _fmt(_row(tape, "ROE"), "pct"))
            + _card("ROCE", _fmt(_row(tape, "ROCE"), "pct"))
            + _card("ROA", _fmt(_row(tape, "ROA"), "pct"))
            + _card("EV / EBITDA", _fmt(_row(tape, "EV / EBITDA")))
            + '</div>',
            unsafe_allow_html=True,
        )
        if tape.get("statements"):
            st.dataframe(pd.DataFrame(tape["statements"]), hide_index=True, use_container_width=True)
    with technicals:
        st.markdown(
            '<div class="ab-grid">'
            + _card("SMA 20", _fmt(_row(tape, "SMA 20"), "px"))
            + _card("SMA 50", _fmt(_row(tape, "SMA 50"), "px"))
            + _card("SMA 200", _fmt(_row(tape, "SMA 200"), "px"))
            + _card("RSI-14", _fmt(_row(tape, "RSI-14")))
            + _card("52-week high", _fmt(_row(tape, "52-week high"), "px"))
            + _card("52-week low", _fmt(_row(tape, "52-week low"), "px"))
            + '</div>',
            unsafe_allow_html=True,
        )
        if history:
            st.line_chart(pd.DataFrame({"Close": history}))
    with ownership:
        left, right = st.columns(2)
        with left:
            if tape.get("shareholding"):
                st.dataframe(pd.DataFrame(tape["shareholding"]), hide_index=True, use_container_width=True)
        with right:
            if tape.get("actions"):
                st.dataframe(pd.DataFrame(tape["actions"]), hide_index=True, use_container_width=True)
            else:
                st.caption("No corporate action returned for this ISIN.")
    with news:
        if tape.get("news"):
            st.dataframe(pd.DataFrame(tape["news"]), hide_index=True, use_container_width=True)
        else:
            st.caption("No instrument news in the last 7 days.")
    with impact:
        current = rec.get("Current Value")
        invested = rec.get("Invested")
        pnl = rec.get("P&L")
        st.markdown(
            '<div class="ab-grid">'
            + _card("Family weight", _fmt(next((p.get("Value") for p in pack.parameters if p.get("Parameter") == "Weight of family assets"), None), "pct"))
            + _card("Current value", _fmt(current, "inr"))
            + _card("Invested", _fmt(invested, "inr"))
            + _card("P&L", _fmt(pnl, "inr"))
            + '</div>',
            unsafe_allow_html=True,
        )
        st.caption("Book figures. Not an Upstox holdings pull.")
    return ai


def _flag_box(title, flags, cls):
    lines = "".join(f"<div>· {f.label}: {f.text}</div>" for f in (flags or [])[:4]) or "<div>None on this tape.</div>"
    return f'<div class="ab-flag {cls}"><div class="ab-k">{title} · {len(flags or [])}</div>{lines}</div>'
