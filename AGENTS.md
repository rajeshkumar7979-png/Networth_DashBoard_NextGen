# AGENTS.md — Networth Dashboard (NextGen)

## What this is

Streamlit multi-page app for a family net-worth dashboard (NRI-focused). Dark institutional theme.

**Product plan:** `INVESTMENT_OS_SPEC.md` (root) is the audited v1.1 spec for the Family Investment Intelligence OS transformation. Each feature there is tagged with a Data-Availability Class (1–5). Re-read it before adding features; it defines what data exists vs. what must not be invented.

## Run locally

```bash
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py
```

Python 3.11. No build step.

## Test & lint

```bash
pip install -r requirements-dev.txt   # adds pytest + ruff
pytest        # deterministic regression suite (no network); smoke excluded by default
pytest -m smoke   # optional network/multipage Streamlit AppTest (flaky offline)
ruff check .  # lint, minimal E/F scope (see ruff.toml)
```

CI (`.github/workflows/ci.yml`) installs **both** `requirements.txt` and `requirements-dev.txt`, then runs `ruff check .` and `pytest` on every push/PR. The default pytest suite never hits the network; the `smoke`-marked AppTest does.

Extraction rule: the pure financial compute (FD valuation, FCNR attribution, gold routing, category inference, health scoring) lives in `lib/valuation.py`, `lib/gold.py`, `lib/scoring.py`. Command Center imports and delegates to these — **do not redefine financial calculations in the page**, and do not change the math without a SPEC-approved Phase 1+ change. The deterministic tests pin the current numbers.

## Data prerequisite

The app reads `data/Networth_Raw_Data.xlsx`. The currently committed workbook is **sample/fabricated data** (obfuscated names like "Mrs. KAVITA KHANDELWAL", account numbers like `ABC123`/) pulled from the public `rajeshkumar7979-png/Networth_DashBoard` repo. It is tracked in git, NOT private, and can be committed. A real workbook may replace it for deployment — then it must be git-ignored. Without it, most pages show errors or an empty state.

Workbook shape (verified against the committed sample): 3 sheets — **FD** (33 rows; columns incl. `Account Number`, `Holder Name`, `Deposit Date`, `Maturity Date`, `Currency`, `Principal Amount`, `Lien Amount`, `Available Balance`, `Maturity Amount`, `ROI % p.a.`; 14 USD = FCNR, rest INR/blank), **MF** (26 rows; `Owner`, `Fund Name`, `ISIN`, `Purchase Date`, `Units`, `Purchase NAV`, `Invested Amount` — lump-sum per fund, no SIP/txn history), **Stocks** (36 rows; `Ticker / Symbol`, `Company Name`, `Exchange`, `Purchase Date`, `Quantity`, `Avg Buy Price`, `Invested Amount`; includes `SGBSEP31II-GB`, `SGBMR29XII-GB`, `GOLDBEES`).

There are no liabilities, savings/drawdown, PPF/EPF, property, or transaction-history sheets. Security/auth only matters once real data is used.

**Net-worth semantics (Phase 1A):** the k1 metric is labelled **"Total Assets (INR)"** (the `total_networth` variable/calculations are unchanged — only the label was renamed). `Net Worth = Total Assets − Liabilities` is computed exclusively by `lib/ledger.net_worth()`; since the workbook has no liabilities sheet, the Command Center shows a **session-only** liabilities input (`st.session_state["cc_liabilities"]`) and, at zero, the caption "Net Worth = Total Assets (no liabilities recorded)" instead of a second metric. Do not add a liabilities book or persist liabilities to session data — they are estimates by definition.

## Architecture

| Path | Role |
|---|---|
| `app.py` | Entrypoint. Calls `st.navigation` with 5 pages. |
| `pages/1_Command_Center.py` | **Main page (~2000 lines).** All portfolio logic, valuation, scoring, charts. |
| `pages/2_Deep_Health.py` | Decision desk for maturing money. Reads `st.session_state` from Command Center. |
| `pages/3_Asset_Detail.py` | Detail drill-down. |
| `pages/4_News.py` | News feed. |
| `pages/5_MF_Health.py` | Mutual-fund health scoring. Reads `st.session_state["mf_holdings_for_health"]`. |
| `lib/config.py` | Global paths, IST timezone, `ROOT`/`DATA_DIR` constants. |
| `lib/portfolio.py` | Excel loader (`load_excel`) — reads FD/MF/stocks sheets. |
| `lib/formatters.py` | INR formatting helpers. |
| `lib/valuation.py` | **FD valuation + FCNR attribution** (extracted Phase 0): `compute_fd_current_native`, `compute_fcnr_attribution`, `_safe_maturity_amount`. |
| `lib/gold.py` | **Gold routing + category inference** (extracted Phase 0): `is_gold_symbol`, `is_gold_fund`, `infer_category`, `CATEGORY_RULES`, `DEBT_LIKE`. |
| `lib/scoring.py` | **Health score factors** (extracted Phase 0): `score_allocation`, `score_concentration`, `score_liquidity_nri`, `score_diversification`, `score_performance`. |
| `lib/register.py` | **Canonical family asset register + taxonomy** (Phase 1A): `build_asset_register`, `aggregate_by_class`, `aggregate_by_member`, `family_level_sum`, `NonUniqueKeyError`. Maps the Command Center books (`mf_valid`/`stocks_valid`/`gold_valid`/`fd_valid`) to 5 data-backed classes (Equity, Liquid, FCNR (USD), INR FD, Gold) + 4 no-data classes (Retirement, Real Estate, Savings/Cash, Liabilities) that are flagged, never summed. FD instrument keys use `acct:<no>` otherwise a unique fingerprint — a collision raises `NonUniqueKeyError` and Command Center halts the register-dependent UI instead of inventing/merging keys. |
| `lib/ledger.py` | **Net-worth semantics** (Phase 1A): `net_worth(assets_total, liabilities_total=None)` only. `Net Worth = Total Assets − Liabilities`; zero/None liabilities ⇒ net worth == assets exactly (pinned by `tests/test_ledger.py`). Rejects negative/non-finite inputs. |
| `lib/mf_holdings.py` | MF holdings ingestion (fund-disclosures → mfdata.in fallback). |
| `lib/mf_health.py` | MF health analysis. |
| `lib/news.py` | Portfolio news aggregation. |
| `lib/theme.py` | CSS injection (`inject_css`). |
| `scripts/update_holdings_cache.py` | CLI script run by GitHub Actions daily. Refreshes `data/mf_holdings_cache.json`. |

## Cross-page data flow

Pages communicate via `st.session_state`. Command Center writes keys like `matured_fd_amount`, `mf_holdings_for_health`, `cc_equity_pct`, etc. Deep Health and MF Health read them. There is no shared database — everything is session-scoped and recomputed on each page load.

## External data sources (called at runtime)

- **AMFI NAVAll.txt** — NAV by ISIN. Cached to `data/amfi_nav_cache.json` on disk as fallback.
- **Groww** — live stock/SGB prices (NSE CASH endpoint).
- **Yahoo Finance** — market indices, COMEX gold/silver, FX, historical NAVs.
- **Frankfurter** — USD/INR live and historical rates.
- **goldprice.dev** — INR gold spot.
- **fund-disclosures / mfdata.in** — MF portfolio holdings (used by holdings refresh script).
- **Google News RSS** — news feed.

All have TTL-based Streamlit caching. Network failures degrade gracefully to disk/previous cache.

## Gold routing logic

Gold instruments (SGB tickers `SGB*-GB`, gold ETFs, gold FoFs) are routed **out** of the Stocks and MF tables into a unified Gold book. `is_gold_symbol()` and `is_gold_fund()` in `lib/gold.py` control this (Command Center imports and delegates). If you add a new gold instrument, update those functions — and add a case to `tests/test_gold_routing.py`.

## NRI-specific valuation

FCNR (USD) deposits use historical FX from deposit date for cost basis, not today's rate. See `compute_fd_current_native()` and `compute_fcnr_attribution()` in `lib/valuation.py`. The identity `interest_at_current_fx + fx_on_principal == current_value_inr - cost_basis_inr` must reconcile within ₹1 (pinned by `tests/test_fcnr_attribution.py`).

## Phase 1A golden baseline (tests/frozen_baseline.py)

`tests/frozen_baseline.py` freezes the actual Command Center totals and the four validated books (`mf`/`stocks`/`gold`/`fd`, register-relevant columns) from a live capture run on the committed sample workbook (TODAY `2026-09-08`, USD_INR `94.49`). `tests/test_register.py` rebuilds the register from these frozen books and asserts class/member/register totals reconcile to `FROZEN_TOTALS` and `FROZEN_MEMBER_CURRENT/INVESTED` within ₹1 — i.e. the register (canonical view) equals the Command Center (page view) by construction; it also pins FD key uniqueness (all workbook FDs are `acct:`-backed) and the `NonUniqueKeyError` collision STOP. `tests/test_page_smoke.py` additionally asserts on every live run that the rendered Reconciliation block contains no `✗ FAIL` (register vs page reconciliation gate). If a future SPEC-approved Phase 1+ change alters valuation, recapture the baseline (run the Command Center once with a dump harness) rather than editing the frozen numbers by hand.

## Known resolved bug

`pages/1_Command_Center.py` previously had a `notess` typo (should be `notes`) that would NameError on the simple-interest FD fallback path with a long-tenor warning. Phase 0 extracted valuation into `lib/valuation.py` and fixed the typo there; the fixed path is pinned by `tests/test_fd_valuation.py::test_simple_interest_fallback_formula`.

## GitHub Actions

`.github/workflows/update-holdings.yml` runs daily at 04:30 UTC (manual dispatch also available). Refreshes MF holdings cache and commits back to the repo. Uses `actions/checkout@v5`, Python 3.11, and `actions/setup-python@v6`.
