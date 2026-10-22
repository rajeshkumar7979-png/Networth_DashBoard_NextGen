"""Command Center loader.

Prefers local lib/cc_parts/body_*.b64 when complete; otherwise loads the
last known-good body from GitHub and applies cash patches (totals +
allocation sleeve). No top-of-page cash dump.
"""
from __future__ import annotations

import base64
import gzip
import urllib.request
from pathlib import Path

import streamlit as st

_GOOD = (
    "https://raw.githubusercontent.com/rajeshkumar7979-png/"
    "Networth_DashBoard_NextGen/1f6c2807f6d76a746043c2d923486b26500123b9/"
    "pages/1_Command_Center.py"
)


def _load_local_body() -> str | None:
    parts_dir = Path(__file__).resolve().parents[1] / "lib" / "cc_parts"
    single = parts_dir / "body_all.b64"
    parts = [single] if single.exists() else sorted(parts_dir.glob("body_*.b64"))
    if not parts:
        return None
    try:
        b64 = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
        if "PLACEHOLDER" in b64 or len(b64) < 1000:
            return None
        code = gzip.decompress(base64.b64decode(b64)).decode("utf-8")
        if "total_networth" not in code or len(code) < 50000:
            return None
        return code
    except Exception:
        return None


def _load_github_body() -> str:
    with urllib.request.urlopen(_GOOD, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _apply_cash_patches(code: str) -> str:
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
        "total_cash = float(cash_total(cash_valid) or 0)\n"
        "total_networth = total_mf + total_stocks + total_gold + total_fd + total_cash"
    )
    if old in code:
        code = code.replace(old, new, 1)

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
            "_bm = st.session_state.get(\"book_mode\") or \"\"\n"
            "if st.session_state.get(\"cc_uploaded_bytes\") or _bm == \"upload\":\n"
            "    st.caption(\n"
            "        \"Book mode: UPLOADED workbook\"\n"
            "        + (f\" ({st.session_state.get('cc_uploaded_name')})\" if st.session_state.get(\"cc_uploaded_name\") else \"\")\n"
            "        + \". Not the public sample.\"\n"
            "    )\n"
            "elif str(_bm).startswith(\"private\"):\n"
            "    st.caption(\n"
            "        \"Book mode: PRIVATE durable book\"\n"
            "        + (f\" · {st.session_state.get('book_path_display')}\" if st.session_state.get(\"book_path_display\") else \"\")\n"
            "        + \". Survives reboot when secrets/env are set.\"\n"
            "    )",
            1,
        )

    if "cash_pct = _pct" not in code:
        code = code.replace(
            "gold_pct = _pct(total_gold)\n",
            "gold_pct = _pct(total_gold)\ncash_pct = _pct(float(total_cash) if \"total_cash\" in dir() else 0.0)\n",
            1,
        )
    if "+ cash_pct" not in code:
        code = code.replace(
            "alloc_sum = equity_pct + liquid_mf_pct + inr_fd_pct + fcnr_pct + gold_pct",
            "alloc_sum = equity_pct + liquid_mf_pct + inr_fd_pct + fcnr_pct + gold_pct + cash_pct",
            1,
        )
    if '("Gold", gold_pct)),' in code and '("Cash", cash_pct)' not in code:
        code = code.replace(
            '("Gold", gold_pct)),',
            '("Gold", gold_pct), ("Cash", cash_pct)),',
            1,
        )
    if 'st.session_state["cc_gold_pct"] = float(gold_pct)' in code and "cc_cash_pct" not in code:
        code = code.replace(
            'st.session_state["cc_gold_pct"] = float(gold_pct)',
            'st.session_state["cc_gold_pct"] = float(gold_pct)\n'
            'st.session_state["cc_cash_pct"] = float(cash_pct if \"cash_pct\" in dir() else 0)\n'
            'st.session_state["cc_total_cash"] = float(total_cash if \"total_cash\" in dir() else 0)',
            1,
        )
    return code


try:
    _code = _load_local_body()
    if _code is None:
        _code = _apply_cash_patches(_load_github_body())
    elif "total_cash" not in _code:
        _code = _apply_cash_patches(_code)
    exec(compile(_code, "Command_Center_loaded.py", "exec"), globals())
except Exception as _exc:
    st.error("Command Center failed to load.")
    st.exception(_exc)
    st.info("Reboot the app, then Desk → re-upload workbook → open Command again.")
