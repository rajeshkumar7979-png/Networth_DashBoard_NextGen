"""Command Center loader.

Prefers local lib/cc_parts/body_all.b64 or body_XX.b64 parts when complete
and clean; otherwise loads the known-good full body from GitHub and applies
cash patches. Rejects any payload containing null bytes.
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


def _clean(code: str | None) -> str | None:
    if not code:
        return None
    if any(ord(c) == 0 for c in code):
        return None
    if "total_networth" not in code or len(code) < 50_000:
        return None
    return code


def _load_local_body() -> str | None:
    parts_dir = Path(__file__).resolve().parents[1] / "lib" / "cc_parts"
    single = parts_dir / "body_all.b64"
    numbered = sorted(parts_dir.glob("body_[0-9]*.b64"))
    try:
        if single.exists() and single.stat().st_size >= 5_000:
            b64 = single.read_text(encoding="utf-8", errors="strict").strip()
        elif numbered:
            b64 = "".join(
                p.read_text(encoding="utf-8", errors="strict").strip() for p in numbered
            )
        else:
            return None
        if "PLACEHOLDER" in b64 or len(b64) < 5_000:
            return None
        raw = base64.b64decode(b64, validate=False)
        code = gzip.decompress(raw).decode("utf-8")
        return _clean(code)
    except Exception:
        return None


def _load_github_body() -> str:
    with urllib.request.urlopen(_GOOD, timeout=60) as resp:
        data = resp.read()
    if b"\x00" in data:
        data = data.replace(b"\x00", b"")
    return data.decode("utf-8", errors="strict")


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

    if "gold_pct = (total_gold / total_networth * 100)" in code and "cash_pct =" not in code:
        code = code.replace(
            "gold_pct = (total_gold / total_networth * 100) if total_networth else 0",
            "gold_pct = (total_gold / total_networth * 100) if total_networth else 0\n"
            "cash_pct = (total_cash / total_networth * 100) if total_networth else 0",
            1,
        )
    if '("Gold", gold_pct)),' in code and '("Cash", cash_pct)' not in code:
        code = code.replace(
            '("Gold", gold_pct)),',
            '("Gold", gold_pct), ("Cash", cash_pct)),',
            1,
        )
    if '{"label": "Gold", "value": total_gold},' in code and '{"label": "Cash"' not in code:
        code = code.replace(
            '{"label": "Gold", "value": total_gold},\n], total=total_networth)',
            '{"label": "Gold", "value": total_gold},\n'
            '    {"label": "Cash", "value": float(total_cash) if "total_cash" in dir() else 0},\n'
            '], total=total_networth)',
            1,
        )
    if 'MF + Stocks + Gold + FD"' in code and 'FD + Cash"' not in code:
        code = code.replace(
            '"Portfolio total = MF + Stocks + Gold + FD", abs((total_mf + total_stocks + total_gold + total_fd) - total_networth) < 1, "by construction"',
            '"Portfolio total = MF + Stocks + Gold + FD + Cash", abs((total_mf + total_stocks + total_gold + total_fd + float(total_cash if "total_cash" in dir() else 0)) - total_networth) < 1, "by construction"',
            1,
        )
    return code


try:
    _code = _load_local_body()
    if _code is None:
        _code = _apply_cash_patches(_load_github_body())
    elif "total_cash" not in _code:
        _code = _apply_cash_patches(_code)
    _code = _clean(_code)
    if _code is None:
        raise RuntimeError("Command Center body invalid (null bytes or too small)")
    exec(compile(_code, "Command_Center_loaded.py", "exec"), globals())
except Exception as _exc:
    st.error("Command Center failed to load.")
    st.exception(_exc)
    st.info(
        "Reboot the app. Loader will fall back to the pinned GitHub body if "
        "local lib/cc_parts payload is corrupt."
    )
