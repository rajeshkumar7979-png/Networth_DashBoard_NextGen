#!/usr/bin/env python3
"""One-shot: point mark_stocks_current at lib.mark_equity (Upstox/Yahoo LTP)."""
from pathlib import Path

p = Path("scripts/update_holdings_cache.py")
src = p.read_text(encoding="utf-8")
marker = "from lib.mark_equity import mark_stocks_current as _impl"
if marker in src:
    print("already wired")
    raise SystemExit(0)
start = src.index("def mark_stocks_current(")
end = src.index("\ndef sum_fd_current(")
wrapper = (
    "def mark_stocks_current(sheets: Dict[str, pd.DataFrame]) "
    "-> Tuple[float, float, int, str, float, float, int, int, int]:\n"
    "    from lib.mark_equity import mark_stocks_current as _impl\n"
    "    return _impl(sheets)\n\n\n"
)
src = src[:start] + wrapper + src[end:]
src = src.replace(
    'r = requests.get(url, params={"interval": "1d", "range": "5d"}, timeout=15)',
    'r = requests.get(url, params={"interval": "1d", "range": "5d"}, timeout=15, '
    'headers={"User-Agent": "Mozilla/5.0 (compatible; NorthlineFamilyDesk/1.0)"})',
)
src = src.replace(
    "Stocks prefer Yahoo LTP, else invested.",
    "Stocks prefer Upstox LTP (UPSTOX_ACCESS_TOKEN), then Yahoo LTP, else invested.",
)
src = src.replace(
    'f"Equity stocks = {stocks_mark} (yahoo {yahoo_hits}/{yahoo_attempts}). "',
    'f"Equity stocks = {stocks_mark} (live LTP {yahoo_hits}/{yahoo_attempts}). "',
)
src = src.replace(
    'f"(yahoo_hits={yahoo_hits}/{yahoo_attempts}). "',
    'f"(live_hits={yahoo_hits}/{yahoo_attempts}). "',
)
p.write_text(src, encoding="utf-8")
print("wired mark_stocks_current -> lib.mark_equity")
