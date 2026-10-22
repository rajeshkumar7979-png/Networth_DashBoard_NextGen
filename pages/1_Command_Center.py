"""Command Center loader.

Bootstraps the full Command Center body from the last known-good GitHub
revision, then applies cash (savings) into totals / allocation only —
no early dumped table (cash detail lives on Desk with the other books).
"""
from __future__ import annotations

import urllib.request

import streamlit as st

_GOOD = (
    "https://raw.githubusercontent.com/rajeshkumar7979-png/"
    "Networth_DashBoard_NextGen/1f6c2807f6d76a746043c2d923486b26500123b9/"
    "pages/1_Command_Center.py"
)


def _load_github_body() -> str:
    with urllib.request.urlopen(_GOOD, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _apply_cash_patches(code: str) -> str:
    """Wire Cash in Hand into math and allocation — never dump a top table."""
    if "from lib.cash_book import" not in code:
        code = code.replace(
            "from lib.portfolio import load_excel as load_data\n",
            "from lib.portfolio import load_excel as load_data\n"
            "from lib.cash_book import build_cash_book, cash_total\n",
            1,
        )

    old = (
        'total_fd = fd_valid["Current Value (INR)"].sum() if not fd_valid.empty else 0\n'
        "total_networth = total_mf + total_stocks + total_gold + total_fd"
    )
    new = (
        'total_fd = fd_valid["Current Value (INR)"].sum() if not fd_valid.empty else 0\n'
        'cash_valid = build_cash_book(st.session_state.get("cc_cash_raw"))\n'
        "total_cash = cash_total(cash_valid)\n"
        "total_networth = total_mf + total_stocks + total_gold + total_fd + total_cash"
    )
    if old in code:
        code = code.replace(old, new, 1)

    # Invested basis includes cash face value
    inv_start = code.find("total_invested = ((")
    inv_end = code.find("total_pnl", inv_start)
    if inv_start > 0 and inv_end > inv_start and "total_cash" not in code[inv_start:inv_end]:
        code = code.replace(
            "+ total_fd_invested)",
            "+ total_fd_invested\n                  + float(total_cash if \"total_cash\" in dir() else 0))",
            1,
        )

    old_books = (
        'st.session_state["cc_books"] = {\n'
        '        "mf": mf_valid if "mf_valid" in dir() else None,\n'
        '        "stocks": stocks_valid if "stocks_valid" in dir() else None,\n'
        '        "gold": gold_valid if "gold_valid" in dir() else None,\n'
        '        "fd": fd_valid if "fd_valid" in dir() else None,\n'
        "    }"
    )
    new_books = (
        'st.session_state["cc_books"] = {\n'
        '        "mf": mf_valid if "mf_valid" in dir() else None,\n'
        '        "stocks": stocks_valid if "stocks_valid" in dir() else None,\n'
        '        "gold": gold_valid if "gold_valid" in dir() else None,\n'
        '        "fd": fd_valid if "fd_valid" in dir() else None,\n'
        '        "cash": cash_valid if "cash_valid" in dir() else None,\n'
        "    }"
    )
    if old_books in code:
        code = code.replace(old_books, new_books, 1)

    if "UPLOADED workbook" not in code:
        code = code.replace(
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

    # Allocation sleeve only (no top-of-page table)
    if '("Gold", gold_pct)),' in code and '("Cash"' not in code:
        code = code.replace(
            '("Gold", gold_pct)),',
            '("Gold", gold_pct), ("Cash", (float(total_cash) * 100.0 / float(total_networth or 1.0)) if "total_cash" in dir() else 0.0)),',
            1,
        )

    return code


try:
    _code = _apply_cash_patches(_load_github_body())
    exec(compile(_code, "Command_Center_loaded.py", "exec"), globals())
except Exception as _exc:
    st.error("Command Center failed to load.")
    st.exception(_exc)
    st.info("Reboot the app, then Desk → re-upload workbook → open Command again.")
