import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from collections import defaultdict
import json
import time
from lib.mf_health import analyze_fund, get_holdings_for_funds
from lib.mf_holdings import HOLDINGS_META_CACHE
from lib.deploy_meta import mf_period_status
from lib.theme import inject_css, PLOTLY_LAYOUT
from lib.formatters import format_inr_compact
from lib.overlap import (
    CONCENTRATION_THRESHOLD_PCT,
    DIRECT_REGULAR_NOTE,
    LOOKTHROUGH_METHOD,
    OVERLAP_METHOD,
    concentration_flags,
    direct_regular_pairs,
    family_look_through,
    pairwise_matrix,
    pairwise_overlap_pct,
)
from lib.returns import (
    LUMP_SUM_ANN_LABEL,
    MULTI_CASHFLOW_XIRR_GAP,
    SIMPLE_ROI_LABEL,
    TRAILING_CAGR_LABEL,
)
from lib.ui import (
    page_header_html,
    section_header_html,
    pill,
    kpi_cards,
    empty_state,
    caption,
    banner,
    footnote,
    nav_shell,
)

inject_css()

nav_shell("funds")
st.markdown(page_header_html(
    "Northline · Family desk",
    "Quality, overlap, concentration",
    "The mutual-fund book, portfolio-first. Every pillar traces to a disclosed or observed number; "
    "cost stays un-scored (no free expense-ratio source).",
    meta=[
        "PORTFOLIO-FIRST",
        "DISCLOSED NUMBERS ONLY",
        "COST UNSCORED",
    ],
), unsafe_allow_html=True)

mf_list = st.session_state.get("mf_holdings_for_health", [])
if not mf_list:
    st.markdown(empty_state(
        "Nothing to analyze yet",
        "Open the Command Center once so your funds and scheme codes are loaded here.",
        hint="Command Center → Intelligence → Refresh holdings",
    ), unsafe_allow_html=True)
    st.stop()

st.info(
    "Funds page body is being restored. Open Command Center for net worth; "
    "reboot Cloud after the full restore commit lands."
)
_period = mf_period_status()
if _period.get("ok"):
    st.caption(_period.get("headline") or "")
    st.caption(
        f"SAME_PERIOD {_period.get('same_period', 0)} · "
        f"new/changed {_period.get('new_period', 0)} · "
        f"errors {_period.get('errors', 0)} · unresolved {_period.get('unresolved', 0)}"
    )
else:
    st.caption(_period.get("reason") or "Holdings meta unavailable")
