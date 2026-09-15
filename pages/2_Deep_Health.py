import streamlit as st
import pandas as pd

from lib.theme import inject_css
from lib.ui import page_header_html, section_header_html, banner, footnote, nav_shell, pill

inject_css()

nav_shell("decisions")
st.markdown(page_header_html(
    "Northline · Family desk",
    "Decision Desk",
    "Test a move before you make it — a deterministic sandbox for maturing money "
    "and allocation choices. Not investment advice.",
    meta=[
        "DECISION SANDBOX",
        "DETERMINISTIC ONLY",
        "NOT INVESTMENT ADVICE",
    ],
), unsafe_allow_html=True)

default_amount = float(st.session_state.get("matured_fd_amount", 0) or 0)
if default_amount > 0:
    st.markdown(banner(
        f"<b>Decision on the desk</b> · Command Center flagged a matured amount of "
        f"₹{default_amount:,.0f}. This section works out where it could sit.",
        "warn"), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 01 · MONEY THAT NEEDS A DECISION
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Money to move", "01"),
            unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    decision_amount = st.number_input(
        "Amount available (₹)",
        min_value=0,
        value=int(default_amount) if default_amount > 0 else 0,
        step=50000,
        help="Auto-filled if Command Center detected a matured FD.",
    )
with col2:
    days_to_need = st.selectbox(
        "When do you need this money?",
        ["0–3 months", "3–12 months", "1–3 years", "3+ years / not sure"],
    )

# ---------------------------------------------------------------------------
# 02 · INITIAL DIRECTION
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Time horizon", "02"), unsafe_allow_html=True)

_sugg = {
    "0–3 months": (
        "Prefer Liquid / short FD",
        "warn",
        [
            "Keep in Liquid Mutual Fund or short-term FD",
            "Do not put this money into equity right now",
        ],
    ),
    "3–12 months": (
        "Prefer short FD + some Liquid",
        "warn",
        [
            "Majority in FD maturing near your need date",
            "Small portion can stay in Liquid fund",
        ],
    ),
    "1–3 years": (
        "Can consider a mix",
        "info",
        [
            "Part in FD / debt",
            "Part can go to equity or hybrid only if you can tolerate ups and downs",
        ],
    ),
    "3+ years / not sure": (
        "Longer horizon — equity can be considered",
        "info",
        [
            "Only if this money is truly not needed for 3+ years",
            "Match with your overall equity target",
        ],
    ),
}

if decision_amount <= 0:
    st.markdown("<div class='t-empty'><b>Enter an amount above</b> to see a direction.</div>",
                unsafe_allow_html=True)
else:
    _s_title, _s_tone, _s_bullets = _sugg[days_to_need]
    _bul = "".join(f"<li>{b}</li>" for b in _s_bullets)
    st.markdown(banner(
        f"<b>{_s_title}</b><ul class='t-list' style='margin:8px 0 0 0; padding-left:18px'>"
        f"{_bul}</ul>",
        _s_tone), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 03 · ASSUMPTIONS — current weights (prefer Command Center numbers)
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Current allocation & net worth", "03"),
            unsafe_allow_html=True)

# Read from Command Center when it has run; otherwise start from NEUTRAL zero
# rather than fabricating a portfolio. These weights/net-worth are user inputs
# (the sandbox's own assumptions), never figures the app computed without a run.
_def_eq = float(st.session_state.get("cc_equity_pct", 0.0) or 0.0)
_def_liq = float(st.session_state.get("cc_liquid_pct", 0.0) or 0.0)
_def_inr = float(st.session_state.get("cc_inr_fd_pct", 0.0) or 0.0)
_def_fcnr = float(st.session_state.get("cc_fcnr_pct", 0.0) or 0.0)
_def_gold = float(st.session_state.get("cc_gold_pct", 0.0) or 0.0)
_def_nw = float(st.session_state.get("cc_net_worth", 0.0) or 0.0)

st.caption("Enter your current approximate weights. They are pre-filled from the "
           "Command Center only when it has already run (no fabricated portfolio here — "
           "without a run start from zero). Gold is kept constant across scenarios.")

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    curr_equity = st.number_input("Equity %", 0.0, 100.0, float(round(_def_eq, 1)), 0.5)
with c2:
    curr_liquid = st.number_input("Liquid MF %", 0.0, 100.0, float(round(_def_liq, 1)), 0.5)
with c3:
    curr_inr_fd = st.number_input("INR FD %", 0.0, 100.0, float(round(_def_inr, 1)), 0.5)
with c4:
    curr_fcnr = st.number_input("FCNR %", 0.0, 100.0, float(round(_def_fcnr, 1)), 0.5)
with c5:
    curr_gold = st.number_input("Gold %", 0.0, 100.0, float(round(_def_gold, 1)), 0.5)

total_nw = st.number_input("Current Net Worth (₹)", min_value=0.0,
                           value=float(round(_def_nw, 0)), step=100000.0)

mode = st.radio(
    "What is this amount?",
    [
        "Already inside net worth (reallocation) — e.g. matured FD still counted in NW",
        "New money outside net worth (injection)",
    ],
    index=0,
    help="Matured FDs detected by Command Center are usually still inside NW until you redeploy them.",
)
is_reallocation = mode.startswith("Already inside")

source_bucket = "INR FD"
if is_reallocation:
    source_bucket = st.selectbox(
        "Money is currently sitting in",
        ["INR FD", "Liquid MF", "FCNR", "Equity"],
        index=0,
        help="Reallocation subtracts the amount from this bucket, then adds it to the target.",
    )

weight_sum = curr_equity + curr_liquid + curr_inr_fd + curr_fcnr + curr_gold
if abs(weight_sum - 100.0) > 1.5:
    st.warning(
        f"Your weights sum to {weight_sum:.1f}% (expected ~100%). "
        "Scenarios still run, but % may be off if inputs are incomplete."
    )


def _rupee(pct: float) -> float:
    return pct / 100.0 * total_nw


def _apply_move(eq, liq, inr, fcnr, gold, amount, target: str, source: str | None):
    """
    Move `amount` into `target`.
    If source is set (reallocation), subtract from source first; NW unchanged.
    If source is None (new money), only add; NW grows by amount.
    Targets/sources: Equity | Liquid MF | INR FD | FCNR | Gold
    """
    buckets = {
        "Equity": eq,
        "Liquid MF": liq,
        "INR FD": inr,
        "FCNR": fcnr,
        "Gold": gold,
    }
    if source:
        available = buckets[source]
        take = min(amount, available)
        buckets[source] = available - take
        put = take
        new_nw = total_nw  # reallocation
    else:
        put = amount
        new_nw = total_nw + amount  # injection

    buckets[target] = buckets[target] + put

    def pct(x):
        return round(x / new_nw * 100.0, 1) if new_nw > 0 else 0.0

    return {
        "Equity %": pct(buckets["Equity"]),
        "Liquid %": pct(buckets["Liquid MF"]),
        "INR FD %": pct(buckets["INR FD"]),
        "FCNR %": pct(buckets["FCNR"]),
        "Gold %": pct(buckets["Gold"]),
        "New NW (₹)": int(round(new_nw, 0)),
    }


# ---------------------------------------------------------------------------
# 04 · SCENARIOS — impact of each choice on the allocation
# ---------------------------------------------------------------------------
st.markdown(section_header_html("Scenarios · impact on allocation", "04"),
            unsafe_allow_html=True)

if decision_amount > 0 and total_nw > 0:
    eq0, liq0, inr0, fcnr0, gold0 = (
        _rupee(curr_equity),
        _rupee(curr_liquid),
        _rupee(curr_inr_fd),
        _rupee(curr_fcnr),
        _rupee(curr_gold),
    )

    if is_reallocation:
        st.caption(
            f"Reallocation of ₹{decision_amount:,.0f} out of {source_bucket} "
            f"(net worth stays ≈ ₹{total_nw:,.0f})."
        )
        src = source_bucket
    else:
        st.caption(
            f"Injection of ₹{decision_amount:,.0f} of new money "
            f"(net worth rises from ₹{total_nw:,.0f})."
        )
        src = None

    targets = [
        ("All → INR FD", "INR FD"),
        ("All → Liquid MF", "Liquid MF"),
        ("All → Equity", "Equity"),
        ("All → FCNR", "FCNR"),
        ("50% FD + 50% Liquid", None),  # special
    ]

    scenarios = []
    for label, target in targets:
        if target is None:
            # 50/50 FD + Liquid
            half = decision_amount / 2.0
            if is_reallocation:
                available = {
                    "Equity": eq0,
                    "Liquid MF": liq0,
                    "INR FD": inr0,
                    "FCNR": fcnr0,
                    "Gold": gold0,
                }[source_bucket]
                take = min(decision_amount, available)
                buckets = {
                    "Equity": eq0,
                    "Liquid MF": liq0,
                    "INR FD": inr0,
                    "FCNR": fcnr0,
                    "Gold": gold0,
                }
                buckets[source_bucket] = available - take
                buckets["INR FD"] = buckets["INR FD"] + take / 2.0
                buckets["Liquid MF"] = buckets["Liquid MF"] + take / 2.0
                new_nw = total_nw
            else:
                buckets = {
                    "Equity": eq0,
                    "Liquid MF": liq0 + half,
                    "INR FD": inr0 + half,
                    "FCNR": fcnr0,
                    "Gold": gold0,
                }
                new_nw = total_nw + decision_amount

            def pct(x, nw=new_nw):
                return round(x / nw * 100.0, 1) if nw > 0 else 0.0

            row = {
                "Scenario": label,
                "Equity %": pct(buckets["Equity"]),
                "Liquid %": pct(buckets["Liquid MF"]),
                "INR FD %": pct(buckets["INR FD"]),
                "FCNR %": pct(buckets["FCNR"]),
                "Gold %": pct(buckets["Gold"]),
                "New NW (₹)": int(round(new_nw, 0)),
            }
        else:
            row = {"Scenario": label}
            row.update(_apply_move(eq0, liq0, inr0, fcnr0, gold0, decision_amount, target, src))
        scenarios.append(row)

    # Baseline row for comparison
    baseline = {
        "Scenario": "Current (no change)",
        "Equity %": round(curr_equity, 1),
        "Liquid %": round(curr_liquid, 1),
        "INR FD %": round(curr_inr_fd, 1),
        "FCNR %": round(curr_fcnr, 1),
        "Gold %": round(curr_gold, 1),
        "New NW (₹)": int(round(total_nw, 0)),
    }
    out = pd.DataFrame([baseline] + scenarios)

    st.caption("Each row is the same decision, routed differently. Weights after the move.")
    st.dataframe(out, use_container_width=True, hide_index=True)

    _wt_cols = ["Equity %", "Liquid %", "INR FD %", "FCNR %", "Gold %"]
    st.bar_chart(out.set_index("Scenario")[_wt_cols], height=320)

    for r in scenarios:
        s = r["Equity %"] + r["Liquid %"] + r["INR FD %"] + r["FCNR %"] + r["Gold %"]
        if abs(s - 100.0) > 2.0:
            st.caption(f"Note: “{r['Scenario']}” weights sum to {s:.1f}% (rounding or capped source).")
            break
else:
    st.markdown("<div class='t-empty'><b>Enter an amount and net worth above</b> "
                "to see the impact of each scenario.</div>", unsafe_allow_html=True)

st.markdown("---")
st.markdown(section_header_html("Caveats", "05"), unsafe_allow_html=True)
st.markdown(
    '<div class="t-meta-row">'
    + pill("deterministic, not investment advice", "stale")
    + pill("reallocation keeps net worth flat", "info")
    + pill("weights are your inputs", "neutral")
    + '</div>',
    unsafe_allow_html=True,
)
st.markdown(
    footnote("This is only a decision helper. Final choice depends on your cash needs, "
             "risk comfort and tax situation."),
    unsafe_allow_html=True,
)