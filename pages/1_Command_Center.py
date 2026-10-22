"""Command Center bootstrap — load last known-good body from GitHub and apply cash patches.

This exists only because a large-file push truncated the page. Once stable, the
body can be inlined again.
"""
from __future__ import annotations

import urllib.request

_GOOD = (
    "https://raw.githubusercontent.com/rajeshkumar7979-png/"
    "Networth_DashBoard_NextGen/1f6c2807f6d76a746043c2d923486b26500123b9/"
    "pages/1_Command_Center.py"
)

with urllib.request.urlopen(_GOOD, timeout=60) as _resp:
    _code = _resp.read().decode("utf-8", errors="replace")

# Cash support (session sheet stashed by lib.portfolio.load_excel)
if "from lib.cash_book import" not in _code:
    _code = _code.replace(
        "from lib.portfolio import load_excel as load_data\n",
        "from lib.portfolio import load_excel as load_data\n"
        "from lib.cash_book import build_cash_book, cash_total\n",
        1,
    )

_old = (
    'total_fd = fd_valid["Current Value (INR)"].sum() if not fd_valid.empty else 0\n'
    "total_networth = total_mf + total_stocks + total_gold + total_fd"
)
_new = (
    'total_fd = fd_valid["Current Value (INR)"].sum() if not fd_valid.empty else 0\n'
    'cash_valid = build_cash_book(st.session_state.get("cc_cash_raw"))\n'
    "total_cash = cash_total(cash_valid)\n"
    "total_networth = total_mf + total_stocks + total_gold + total_fd + total_cash"
)
if _old in _code:
    _code = _code.replace(_old, _new, 1)

_old2 = (
    "total_invested = ((mf_valid[\"Invested\"].sum() if not mf_valid.empty else 0)\n"
    "                  + (stocks_valid[\"Invested\"].sum() if not stocks_valid.empty else 0)\n"
    "                  + (gold_valid[\"Invested\"].sum() if not gold_valid.empty else 0)\n"
    "                  + total_fd_invested)"
)
# Use simpler search for invested block
if "+ total_fd_invested)" in _code and "total_cash" not in _code.split("total_fd_invested)")[0][-80:]:
    _code = _code.replace(
        "+ total_fd_invested)",
        "+ total_fd_invested\n                  + (total_cash if \"total_cash\" in dir() else 0))",
        1,
    )

_old3 = (
    'st.session_state["cc_books"] = {\n'
    '        "mf": mf_valid if "mf_valid" in dir() else None,\n'
    '        "stocks": stocks_valid if "stocks_valid" in dir() else None,\n'
    '        "gold": gold_valid if "gold_valid" in dir() else None,\n'
    '        "fd": fd_valid if "fd_valid" in dir() else None,\n'
    "    }"
)
_new3 = (
    'st.session_state["cc_books"] = {\n'
    '        "mf": mf_valid if "mf_valid" in dir() else None,\n'
    '        "stocks": stocks_valid if "stocks_valid" in dir() else None,\n'
    '        "gold": gold_valid if "gold_valid" in dir() else None,\n'
    '        "fd": fd_valid if "fd_valid" in dir() else None,\n'
    '        "cash": cash_valid if "cash_valid" in dir() else None,\n'
    "    }"
)
if _old3 in _code:
    _code = _code.replace(_old3, _new3, 1)

if "UPLOADED workbook" not in _code:
    _code = _code.replace(
        "integrity_issues = []  # each: (severity, message)",
        "integrity_issues = []  # each: (severity, message)\n"
        "if st.session_state.get(\"book_mode\") == \"upload\" or st.session_state.get(\"cc_uploaded_bytes\"):\n"
        "    st.caption(\n"
        "        \"Book mode: UPLOADED workbook\"\n"
        "        + (f\" ({st.session_state.get('cc_uploaded_name')})\" if st.session_state.get(\"cc_uploaded_name\") else \"\")\n"
        "        + \". Not the public sample.\"\n"
        "    )",
        1,
    )

exec(compile(_code, "Command_Center_bootstrapped.py", "exec"), globals())
