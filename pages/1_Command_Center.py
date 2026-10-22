"""Command Center loader.

1) Prefer local lib/cc_parts/part*.b64 (gzip+base64) if complete.
2) Else fetch last known-good page from GitHub raw and apply cash patches.
3) Surface any failure instead of a blank page.
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


def _load_local_parts() -> str | None:
    parts_dir = Path(__file__).resolve().parents[1] / "lib" / "cc_parts"
    parts = sorted(parts_dir.glob("part*.b64"))
    if len(parts) < 4:
        return None
    chunks: list[str] = []
    try:
        for p in parts:
            raw = gzip.decompress(base64.b64decode(p.read_text(encoding="utf-8").strip()))
            chunks.append(raw.decode("utf-8"))
    except Exception:
        return None
    code = "".join(chunks)
    if "total_networth" not in code or len(code) < 50000:
        return None
    return code


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
        "total_cash = cash_total(cash_valid)\n"
        "total_networth = total_mf + total_stocks + total_gold + total_fd + total_cash"
    )
    if old in code:
        code = code.replace(old, new, 1)

    if "+ total_fd_invested)" in code and "total_cash" not in code[code.find("total_invested"):code.find("total_pnl") + 1]:
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

    # Visible cash block after totals
    if "#### Cash in Hand" not in code and "total_pnl = total_networth - total_invested" in code:
        code = code.replace(
            "total_pnl = total_networth - total_invested",
            "total_pnl = total_networth - total_invested\n\n"
            "if \"cash_valid\" in dir() and cash_valid is not None and not getattr(cash_valid, \"empty\", True):\n"
            "    st.markdown(\"#### Cash in Hand\")\n"
            "    st.caption(\n"
            "        f\"{len(cash_valid)} savings accounts · "
            "{format_inr_compact(float(total_cash))} included in total assets\"\n"
            "    )\n"
            "    st.dataframe(cash_valid, use_container_width=True, hide_index=True)\n",
            1,
        )

    # Allocation sleeve
    if '("Gold", gold_pct)),' in code and '("Cash",' not in code:
        code = code.replace(
            '("Gold", gold_pct)),',
            '("Gold", gold_pct), ("Cash", float(total_cash if "total_cash" in dir() else 0) * 100.0 / float(total_networth or 1))),',
            1,
        )

    return code


try:
    _code = _load_local_parts()
    if not _code:
        _code = _apply_cash_patches(_load_github_body())
    else:
        # local body already cash-patched when built
        if "total_cash" not in _code:
            _code = _apply_cash_patches(_code)
    exec(compile(_code, "Command_Center_loaded.py", "exec"), globals())
except Exception as _exc:
    st.error("Command Center failed to load.")
    st.exception(_exc)
    st.info(
        "Try Streamlit reboot. If this persists, open Desk → re-upload workbook → Command again."
    )
