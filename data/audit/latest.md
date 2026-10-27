# Northline daily self-audit — 2026-10-27T03:29:56Z

- Critical: **0**
- Warning: **3**
- Info: **9**
- Auto-fixes: **2**
- Healthy: **True**

## Issues
- `info` **BOOK_COMMITTED**: Committed-size book present (36061 bytes)
- `info` **CASH_SHEET_OK**: Cash sheet present
- `warning` **HAD_INDIAN_COMMAS**: Found and fixed 3 non-plain numeric cell(s) in FD/book
- `info` **HISTORY_LAST**: Last history row date=2026-10-21 rows=6
- `warning` **HISTORY_STALE**: History last row is 6 day(s) old (2026-10-21) — holdings job may be failing
- `info` **HISTORY_CASH_COL_ADDED**: cash_current_inr column was missing; header added
- `info` **HOLDINGS_COUNT**: Holdings cache has 21 fund key(s)
- `info` **HOLDINGS_ASOF**: Holdings as_of values: ['2026-09-30']
- `info` **AMFI_SAVED**: AMFI cache saved_at=2026-08-20 08:02
- `warning` **AMFI_STALE**: AMFI disk cache is 68 day(s) old — Cloud may still live-fetch
- `info` **WORKFLOW_BOOK_GUARD**: Holdings workflow has committed-book size guard
- `info` **GUARD_OK**: check_critical_files.py passed

## Fixes applied
- `2026-10-27T03:29:56Z` **NORMALIZE_INDIAN_COMMAS**: Normalized 3 numeric cell(s) in workbook (Indian commas / quotes)
- `2026-10-27T03:29:56Z` **HISTORY_CASH_COLUMN**: Added cash_current_inr column header to portfolio_history.csv (values filled by next holdings job)
