# Northline / Networth Dashboard NextGen

Family desk for **read-only** portfolio monitoring. No trading execution.

Live app: https://northline-family-desk.streamlit.app/

## What is production-ready today

| Capability | Status |
|------------|--------|
| Daily MF holdings refresh (GitHub Actions) | Yes — archives each `as_of` under `data/mf_snapshots/` |
| AMFI NAV (8-field + legacy 6-field) | Yes |
| Durable history `data/portfolio_history.csv` | Yes — MF mark + Yahoo stock mark + FD (FX + ROI accrual) |
| Public sample book | Yes — `Member A/B/C/D` only on HEAD |
| Private book path | Secrets/env — **must be Cloud-reachable** (see below) |
| Upstox tape | Opt-in; **complete / partial / empty** |
| MF period-over-period diff | Ready; waiting on new AMC `as_of` (still `2026-09-30`) |
| Command Center recon | PASS on full FCNR + INR FD book (~₹2.5 Cr) |

## Secrets (Streamlit Cloud)

```toml
[upstox]
ACCESS_TOKEN = "your_analytics_token"

[ai]
# cloud cannot reach localhost Ollama — set cloud provider keys here

# Private workbook (optional)
# Streamlit Cloud **cannot** read a path on your Windows laptop.
# Options that work:
#   1. Upload the xlsx as a private GitHub release asset and download in an app
#      bootstrap (not committed to public tree), or
#   2. Host the file on a private URL / S3 and set the path after a download
#      step into /tmp or /mount in a custom container, or
#   3. Keep using the public sample book for the public app and run the real
#      book only on a private local/VPS deploy.
[book]
path = "/mount/private_Networth_Raw_Data.xlsx"
```

Env alternative: `UPSTOX_ACCESS_TOKEN`, `NORTHLINE_BOOK_PATH`.

**Do not commit a real family workbook to this public repo.**

## Portfolio history (change over time)

File: `data/portfolio_history.csv` (committed daily).

| Column | Meaning |
|--------|--------|
| `mf_current_inr` | Units × AMFI NAV |
| `stocks_current_inr` | Yahoo LTP × qty when possible, else invested |
| `fd_current_inr` | Available balance if set, else **principal × (1 + ROI × days/365)** capped at maturity amount; **USD × spot USDINR** |
| `total_assets_inr` | MF + stocks + FD (gold is inside MF/stock marks when present; CC also shows gold separately) |
| `data_quality` (UI) | `NAV_PARSE_GAP` days are audit-only, not performance |

Command Center remains the live source of truth (~₹2.5 Cr). History is the durable trend (~₹2.3–2.5 Cr depending on accrual/marks).

## MF holdings change detection (Phase 3)

1. Daily job writes `data/mf_snapshots/{scheme}/{as_of}.json`.  
2. Same `as_of` → `comparison_status = SAME_PERIOD` (not “never changes”).  
3. New period → prior file kept; meta gets added / exited / changed counts.  

**Current evidence:** all 21 schemes `as_of = 2026-09-30`, `SAME_PERIOD`. October AMC filings are not in the CDN source yet. The pipeline is waiting, not broken.

## Deploy check after every Cloud change

1. GitHub `main` HEAD SHA  
2. Streamlit Cloud → **Reboot**  
3. Command Center total should stay near **₹2.5 Cr** with FCNR ~43%  
4. Desk history latest trusted row near that ballpark  

## Local / CI

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
ruff check .
python scripts/build_sample_workbook.py
python scripts/update_holdings_cache.py
```

## Hard rules

- No real family book in the public tree.  
- No invented NAVs, filings, or AI verdicts without evidence.  
- Upstox **partial** is not a full verified board.  
- This app does not place trades.  
