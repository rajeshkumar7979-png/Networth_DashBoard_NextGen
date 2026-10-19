# Northline / Networth Dashboard NextGen

Family desk for **read-only** portfolio monitoring. No trading execution.

Live app: https://northline-family-desk.streamlit.app/

## What is production-ready today

| Capability | Status |
|------------|--------|
| Daily MF holdings refresh (GitHub Actions) | Yes — archives each `as_of` period under `data/mf_snapshots/` |
| AMFI NAV (8-field + legacy 6-field) | Yes |
| Durable history `data/portfolio_history.csv` | Yes — MF mark + stocks invested + FD + totals |
| Public sample book only | Yes — `Member A/B/C/D`, no real family names on HEAD |
| Private book path | Secrets/env — see below |
| Upstox tape | Opt-in; reports **complete / partial / empty** |
| MF period-over-period diff | Ready when a **new** `as_of` appears; currently all schemes are `2026-09-30` / `SAME_PERIOD` |

## Secrets (Streamlit Cloud)

```toml
[upstox]
ACCESS_TOKEN = "your_analytics_token"
# or ANALYTICS_TOKEN = "..."

# Optional AI (cloud cannot reach localhost Ollama)
[ai]
# provider settings as used by lib/intelligence/ai/config.py

# Optional private workbook — path must exist *inside* the Cloud runtime.
# A Windows laptop path will NOT work on Streamlit Cloud.
[book]
path = "/mount/private_Networth_Raw_Data.xlsx"
```

Env alternative: `UPSTOX_ACCESS_TOKEN`, `NORTHLINE_BOOK_PATH`.

## Portfolio history (how you know change over time)

File: `data/portfolio_history.csv` (committed by the daily job).

- **MF** = workbook units × AMFI NAV  
- **Stocks** = invested basis until a live mark is wired into the job  
- **FD** = available balance or principal  
- **total_assets_inr** / **total_invested_inr** = sum of the above  

Older rows before the NAV fix may show `mf_current_inr = 0`; trust rows after the 8-field parser fix.

## MF holdings change detection

1. Daily job fetches scheme holdings and writes `data/mf_snapshots/{scheme}/{as_of}.json`.  
2. If `as_of` is unchanged → `comparison_status = SAME_PERIOD` (not a false “no change forever”).  
3. When AMC publishes a **new** period → prior file is kept; meta gets added/exited/changed counts.  

**Current HEAD evidence:** all schemes still report `as_of = 2026-09-30` and `SAME_PERIOD`. October disclosures have not appeared yet; the pipeline is waiting, not broken.

## Deploy SHA check (do this after every Cloud refresh)

1. Open the app → note any footer / about SHA if present, or  
2. GitHub → latest commit on `main`  
3. Streamlit Cloud → **Manage app → Logs / reboot** after that SHA is deployed  
4. Confirm `data/portfolio_history.csv` on GitHub has today’s row after the Actions job  

Cloud is **not** gated on green CI by itself — always verify the deployed commit hash matches `main` HEAD after reboot.

## Local / CI

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
python scripts/build_sample_workbook.py
python scripts/update_holdings_cache.py   # needs network for AMFI + holdings CDN
```

## Hard rules

- Do not commit a real family workbook.  
- Do not invent NAVs, filings, or AI verdicts without evidence.  
- Upstox **partial** load is not a full verified board — UI and AI must respect `completeness`.  
