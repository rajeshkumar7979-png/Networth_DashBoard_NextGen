# INVESTMENT_OS_SPEC.md

## Family Investment Intelligence OS — Product & Engineering Specification

**Version:** 1.1 (audited against repository, AGENTS.md, and sample workbook — nothing implemented yet)
**Target platform:** Streamlit (free Community Cloud), Python 3.11, dark institutional UI
**Positioning:** Move the app from a *net-worth readout* to a **decision-grade Family Investment Intelligence OS** — a private, NRI-aware system that lets the family see through its portfolios, manage the full lifecycle of money (buy → hold → mature → reinvest/tax), and surface *why* something matters, not just the number.

This document is the single source of truth for the transformation. Each section states a **requirement (R-nnn)**, the **problem** it solves, a **proposed design**, and **acceptance criteria**. Every valuable feature is tagged with a **Data Availability Class** (see §0) so we never build on data we don't have or invent figures to paper over gaps.

> **Audit note (v1.0 → v1.1).** A critical review against the actual repo and workbook found the v1.0 draft over-claimed in several places: it treated the *sample* workbook as real/private data, assumed liabilities that don't exist, proposed reconstructing fake SIP transactions, made arbitrary overlap/tax/SGB recommendations, pre-locked history into Google Sheets, overstated free-tier guarantees, and mis-linked a few cross-references. All corrected below. The ambitious vision is preserved, but every claim is now scoped to what the available data can actually support. **No missing financial data is invented.**

---

## 0. Data Availability Classification (apply to every feature)

Every feature below is tagged with one of five classes. This is the load-bearing decision rule for planning:

| Class | Meaning | Example in this project |
|---|---|---|
| **1. VERIFIED AVAILABLE NOW** | Works today in the committed codebase with the sample workbook; feature exists and runs | Net worth readout, FCNR attribution, gold routing, news, holdings-cache refresh script |
| **2. CAN BE CALCULATED FROM CURRENT DATA** | The data to compute it already exists (workbook **or** committed caches/APIs), but the UI/feature is not yet built | Look-through & overlap from `mf_holdings_cache.json`; XIRR for lump-sum positions |
| **3. REQUIRES NEW USER DATA** | Not derivable from anything present; the user must supply new input | Liabilities ledger, transaction/SIP-by-SIP history, SGB series purchase/redemption dates |
| **4. REQUIRES EXTERNAL DATA** | Depends on a third-party API/RSS at runtime (or a not-yet-held external feed) and is inherently best-effort | Live prices/NAV, FX, corporate-action calendar, holdings enrichment |
| **5. OPTIONAL/FUTURE** | Visionary, not required for v1; depends on new data, paid-grade sources, or new infrastructure | Full AI analyst, per-goal scenario engine, multi-user auth |

**Rule:** A feature tagged 3 or 4 must show a clear "not available / needs data" state and never fabricate a number. A tag is not a pass to invent data.

---

## 1. Family net worth (core ledger)

### 1.1 Problem
The current app computes net worth as `MF + Stocks + Gold + FD` from three static sheets. It has no liability side, no cross-member consolidation that is *visible* beyond the existing per-owner tables, and no "today's number vs. explainable drivers."

### 1.2 Requirements

- **R-101 — Family asset register. [Class 1/2]** A normalized register keyed by (Owner, Asset Class, Instrument, Account/ISIN/Symbol). The plumbing largely exists (the workbook sheets + gold routing); formalize it so all downstream features consume one register, not the raw sheets. *Data:* fully supported by the workbook.
- **R-102 — Assets minus liabilities = net worth. [Class 3]** Introduce an explicit **Liabilities** ledger: home/car/personal loans, credit-card balances, outstanding tax, lien amounts. **The sample workbook has NO liabilities sheet.** Net worth = total assets − total liabilities only once the user supplies liabilities. Until then, net worth = total assets (unchanged from today), with a "no liabilities recorded" notice rather than a fabricated zero.
- **R-103 — Asset class taxonomy. [Class 1/2]** Canonical classes: Equity, Debt/Debt-MF, Liquid, FCNR (USD), INR FD, Gold, Retirement (PPF/EPF/NPS — new data), Real Estate (new data), Savings/Cash (new data), Liabilities (new data). Instruments already in the workbook map automatically; the unused classes render as "no data" until supplied.
- **R-104 — Member-level and family-level reporting. [Class 1/2]** The workbook already carries distinct Owner/Holder values across all three sheets, so member and family views are computable today. All concentrations computed at the *family* level (same fund across members = one exposure) — already the intent in Command Center; make it consistent everywhere.
- **R-105 — Drivers of change. [Class 2]** Net-worth delta vs. previous snapshot decomposed into: fresh inflows, market movement, FX movement (FCNR), revaluation/method changes. Deterministic decomposition is computable from the workbook + FX history; classify each driver by provenance, and where a driver cannot be attributed exactly, say so (do not force percentages to sum to 100 by fudging).
- **R-106 — Snapshot immutability. [Class 5 infrastructure]** Each logged snapshot must be immutable once written; corrections write a new snapshot. This guards history integrity but depends on the durable-history decision (see §15).

---

## 2. Portfolio look-through

### 2.1 Problem
An equity MF holding is a black box: the app tracks NAV vs. Nifty but not what the fund actually holds. The funds' real risk and overlap live under the wrapper. `mf_holdings_cache.json`, `mf_holdings_meta.json`, and `amfi_scheme_universe.json` are already committed and populated (20 funds in cache, per-holding sector/market-cap/credit-rating, AMFI universe of 14k+ schemes), but the holdings-refresh script only exercises the cache — no look-through UI exists.

### 2.2 Requirements

- **R-201 — Holdings cache as an asset. [Class 1/2]** Treat the three committed data files as a first-class store. A `PortfolioLookThrough` service aggregates them per family. The cache is **external data already present in the repo**; the feature is the aggregation + UI, not new acquisition.
- **R-202 — Underlying-granularity exposure. [Class 2]** Compute the family's *underlying* equity exposure (per company/ISIN + sector) by weighting each fund's holdings by the family's ₹ in that fund. Produces underlying top holdings, sector allocation, and underlying concentration. *Limits:* per-fund `as_of` dates vary; only weight-checked holdings (PASS/WARN) are safe to aggregate. Instruments whose holdings are not in cache aggregate only to their own fund value with a caveat — never prorated to a guessed underlying.
- **R-203 — Unified gold routing. [Class 1]** `is_gold_symbol()` / `is_gold_fund()` already route SGB and gold funds out of Stocks and MF into a single Gold book. Formalize as one canonical family gold exposure. *Verified in workbook:* `SGBSEP31II-GB`, `SGBMR29XII-GB`, `GOLDBEES` are present and correctly routed today.
- **R-204 — Stale/quality-aware lookup. [Class 2]** Every look-through figure carries the source's `as_of` and `weight_check` (PASS/WARN/NOT_AVAILABLE). If holdings are stale (>90 days) or weight-check fails, show it and degrade aggregation with a visible caveat. Meta file already stores this per fund.
- **R-205 — Index-relative look-through. [Class 4/5]** Compare underlying-holding weights vs. a reference index (Nifty 50 / Nifty 500) for active bets. Requires index constituent data (external, best-effort); optional for v1.

---

## 3. Mutual fund intelligence & overlap

### 3.1 Problem
Category-level allocation (existing `infer_category`) is a proxy and is labeled as such in the UI. Real overlap needs security-level holdings — which are now in the cache. "Do I own too much of one stock through several funds?" is answerable from current data.

### 3.2 Requirements

- **R-301 — Pairwise fund overlap matrix. [Class 2]** Overlap between fund pairs computed from common holdings' weight (e.g. a weighted Jaccard-like measure) across the family's funds in cache. **Present the numbers and the exposure only.** Any "consolidate/sell" wording must be neutral ("X and Y share ~N% of holdings — review whether both are needed"), **not** an arbitrary "merge if >60%" rule. Rationale appended as a data-quality fact, not investment advice.
- **R-302 — Single-issue concentration. [Class 2]** Roll family MF holdings up to the *effective single-stock weight*; flag when one underlying company exceeds a threshold (e.g. >5% of the family equity book). Threshold is a configurable, explainable parameter — flagging is fact, not a recommendation.
- **R-303 — Category hygiene audit. [Class 2]** Reconcile inferred category vs. AMFI official category for the funds in the universe/cache; flag mismatches. Computable from `amfi_scheme_universe.json`.
- **R-304 — Holdings-vs-benchmark drift. [Class 4/5]** Style drift vs. a benchmark requires benchmark constituent data (external). Optional for v1; clearly labeled.
- **R-305 — Best-in-class dedup. [Class 2]** Group direct-vs-regular plans of the same scheme; flag holding both (fee leakage signal). Computable from fund names/ISIN in the workbook.
- **R-306 — Per-fund health. [Class 2/4]** Extend `lib/mf_health.py` to consume the look-through: credit-rating mix (debt funds), market-cap mix (equity), concentration — all present in the cache. Price performance is separate and already computed.

---

## 4. XIRR / transactions

### 4.1 Problem
The workbook is **not** transaction-grade. MF rows carry a single lump `Invested Amount`, `Purchase Date`, `Units`, `Purchase NAV` (no SIP-by-SIP history). Stocks carry `Quantity`, `Avg Buy Price`, `Invested Amount`. There is no redeem/sell, dividend, or intra-position cashflow stream. The current `Return %` = `(current − invested)/invested` is only correct for a single lump sum (which these data approximately are).

### 4.2 Requirements — with strict honesty about what is and isn't reconstructable

- **R-401 — Transaction data model. [Class 3]** A canonical `transactions` table (owner, class, instrument_key, side, date, units, price, amount, currency). **The workbook does not contain sell/dividend events.** Populate from user-supplied transaction exports; seed it from the workbook's lump buys only where verified. No invented intermediate cashflows.
- **R-402 — XIRR per holding / class / member / family. [Class 2/3]**
  - **Lump-sum positions (all current holdings):** XIRR is computable from a single buy + current value — equivalent to what the workbook supports, and implementable now as a correctness improvement over `(current−invested)/invested`.
  - **True XIRR (multi-cashflow, SIPs, sells, dividends):** **requires new user transaction data** (R-401). Until supplied, show "needs transaction history" and keep the lump-sum return with its stated definition.
- **R-403 — SIP reconstruction. [REJECTED — remove.]** The v1.0 draft proposed deriving SIP transaction dates from NAV history. This **invents transaction history** and is explicitly out of scope under the "never invent missing financial data" rule. Users must supply real SIP statements. (Retired as an anti-pattern note: any reconstruction would fabricate cashflows and corrupt XIRR.)
- **R-404 — Time-weighted return (TWR). [Class 4]** TWR from NAV/price history is computable (free mfapi/Yahoo). Present alongside XIRR. TWR is `as_of`-sensitive and degrades if history is short.
- **R-405 — Dividend & corporate-action capture. [Class 4]** Capture dividends/splits/bonuses from free price/history feeds to keep returns and unit counts consistent. External and best-effort; never back-fill a corporate action into a historical figure without a provenance event (§14).

---

## 5. FD / FCNR valuation

### 5.1 Problem
Current FD valuation (`compute_fd_current_native`) prefers Maturity-Amount interpolation, then Available Balance, then a simple-interest fallback. **Known bug in AGENTS.md:** the simple-interest fallback uses `notess` (should be `notes`) → NameError on the long-tenor path. The workbook's FD sheet has real columns incl. `Lien Amount` (3 non-zero today) which current valuation ignores. Valuation method is collapsed into one number per FD with no consolidated runway.

### 5.2 Requirements

- **R-501 — Deterministic, audited valuation. [Class 1]** Keep the three-method priority; make each FD's valuation auditable (method, inputs, notes). For FCNR, the identity `interest_at_current_fx + fx_on_principal == current_value_inr − cost_basis_inr` must reconcile within ₹1. **R-501a — Fix the `notess` bug** (First correction in Phase 0). *Verified:* 14 USD FDs exist, so this path is live.
- **R-502 — FCNR attribution is first-class. [Class 1]** Present interest (at current FX) and FX-on-principal (vs. deposit-date FX) as separate, always-reconciled components per FCNR and family. Already implemented and correct in Command Center; formalize into a reusable service so Asset 360 & others share it.
- **R-503 — FD maturity runway. [Class 2]** Time-ordered runway of all deposits (date, holder, amount at maturity, currency, reinvest-vs-deploy decision state). Fully computable from the workbook. **Integrates with the Deep Health decision desk (R-802)** — corrected cross-ref (was R-701, which is in the risk section).
- **R-504 — Interest recomputation freshness. [Class 2]** State whether current value uses bank Maturity Amount (static) or interpolation/simple interest (time-evolving); never mix a static value with a time extrapolation unlabeled. **Also surface `Lien Amount`** (present in workbook, currently unused) as a separate, visibly-excluded liquidity figure rather than silently ignoring it.
- **R-505 — Value-method change detection on re-runs. [Class 1/2]** If a method changes between runs (e.g. Maturity Amount → simple interest), record it as a provenance event (ties to R-1405) so historical comparability isn't silently assumed.

---

## 6. Gold

### 6.1 Problem
Gold is already unified into a Gold book. *Notably, AGENTS.md states:* "SGB maturity/interest are not invented — source file does not carry them." The workbook carries only the `-GB` ticker strings; there is no SGB series purchase/redemption/issue data. So SGB-specific economics cannot be computed from current data.

### 6.2 Requirements

- **R-601 — Gold sub-classify. [Class 1]** Split the Gold book into SGB (by `-GB` ticker), gold ETFs (e.g. GOLDBEES), and gold FoFs (via `is_gold_fund`). Classification is deterministic from current data; each subclass shows its own expense/holding characteristics only where known.
- **R-602 — SGB decision support. [Class 3/4 (mostly 3)]** Coupon schedule (2.5% p.a., semi-annual) and tax-advantaged-holding facts are **external, time-sensitive claims that must be verified against an authoritative current source before display** — do not hardcode them in 2026 text. **The workbook does not carry SGB series purchase/redemption dates**, so a maturity-aware recommendation is **not computable today**. Build the feature to accept SGB series metadata as user/external data (Class 3/4); until present, show the SGB's value, cost basis, and coupon *if* derivable — and a clear "series/redemption data not provided" state. No fabricated series facts. AGENTS.md's stance (don't invent SGB maturity/interest) is preserved and reinforced.
- **R-603 — Gold allocation discipline. [Class 2]** Gold % of net worth vs. a configurable target band; flag over/under. Computable now. The band is a user-set parameter, presented as fact, not advice.

---

## 7. Risk analytics

### 7.1 Problem
The health score is a fixed-weight composite of Allocation/Concentration/Liquidity/Diversification/Performance. It is instructive but not a risk model: no volatility, drawdown, beta, stress test, correlation, or per-member risk budget.

### 7.2 Requirements

- **R-701 — Risk metrics from history. [Class 4]** From NAV/price history (free mfapi/Yahoo): per-holding and portfolio volatility (annualized), max drawdown, beta vs. Nifty, Sharpe/Sortino. External and best-effort; honors the leaving-data-grade-explicit rule. *Note:* R-701 lives here (risk); it is **not** the Deep Health decision desk (that is R-802) — a v1.0 cross-ref from R-503 pointed here wrongly and is fixed.
- **R-702 — Correlation & concentration risk. [Class 2/4]** Effective-holdings overlap (§3) feeds a correlation-aware concentration measure, replacing the "top-5 %" proxy where holdings data supports it. Mix of present cache data and external correlation time-series.
- **R-703 — Stress scenarios. [Class 2]** Deterministic shocks (−15%/−30% Nifty, INR +10% vs USD, gold −10%) applied to the *current portfolio* from present valuations. Computable now; results are a mechanical sensitivity, labeled as such (not a forecast).
- **R-704 — Liquidity stress. [Class 2/3]** True-liquid runway (liquid MF + FDs ≤90d + savings) vs. near-term obligations (loans/tax — liabilities, Class 3). Without supplied liabilities the obligation side is absent and the app must say so.
- **R-705 — Explainable score. [Class 1/2]** Keep the score but attribute every point to a factor + instrument with a rationale string. The factor weights/definitions are already in Command Center; formalize as a pure, testable function.

---

## 8. Allocation & Deep Health

### 8.1 Problem
`pages/2_Deep_Health.py` is a lightweight decision desk for a single "amount available" prefilled from maturing FDs. It lacks target-allocation awareness, full maturing-money context, and NRI/tax nuance.

### 8.2 Requirements

- **R-801 — Target allocation engine. [Class 2]** User-configurable target weights with tolerance bands; present actual-vs-target with ₹ and % gaps and a rebalancing delta. Computable from current data + config.
- **R-802 — Maturing-money decision desk (v2). [Class 2/3]** Aggregate actionable money (maturing FDs from the R-503 runway; maturing SGB only when series data exists — Class 3; surplus) into one decision queue: amount, horizon need, tax implication, proposed direction. **This is the Deep Health surface** the R-503 runway integrates with. Advisory text stays clearly caveated.
- **R-803 — NRI decision context. [Class 2/4]** Repatriation flags and tax context shown as advisory notes drawn from the **NRI-tax news layer (R-1103)**, with "not tax advice". **Corrected cross-ref:** was R-1301 (the data-adapter section); the NRI-tax content actually lives in the news section (§11, R-1103).
- **R-804 — Goal-based scenarios. [Class 5]** Per-goal (education/retirement) scenarios are optional/future; require user goal inputs and are beyond v1.

---

## 9. Asset 360

### 9.1 Problem
`pages/3_Asset_Detail.py` is a thin drill-down. There's no single instrument dossier tying valuation, returns, holdings, news, risk, tax, and maturity into one view.

### 9.2 Requirements

- **R-901 — Instrument dossier. [Class 2/4]** For any selected holding: valuation & method, XIRR/TWR (within the §4 honesty limits), holdings look-through (funds, §2), risk metrics (§7), news pulse (§11), maturity context (§5), and provenance/quality tags. Rendered only for what each instrument has data for; absent pieces show "no data".
- **R-902 — Deep links. [Class 1/2]** Table rows deep-link to the dossier. Feature work (does not require new data).
- **R-903 — Per-instrument timeline. [Class 2/4]** Purchase info (workbook) + NAV/price chart (external history) + dividend/corporate-action events (external, best-effort) + valuation-method transitions (provenance). Mix of classes; render each part only when supported.

---

## 10. Corporate actions & results calendar

### 10.1 Problem
No results/earnings or corporate-action calendaring for direct stocks, and no NAV-event awareness for funds.

### 10.2 Requirements

- **R-1001 — Results calendar. [Class 4/5]** Pull upcoming earnings/results dates for held direct stocks from free feeds (NSE/BSE announcements pages when accessible, or aggregator RSS). External, best-effort, frequently rate-limited; **explicitly a Class 4 wish**, not guaranteed. No single free source is reliable enough to promise coverage — state it.
- **R-1002 — Corporate actions. [Class 4]** Capture dividends/bonus/splits/rights from free price/history APIs so returns and unit counts stay correct (feeds R-405). Best-effort; always via provenance event.
- **R-1003 — Emission-free fallback. [Class 4]** If a source is unavailable, show "no data this run" with provenance note; never guess. This preserves correctness even when the external feed is flaky.

---

## 11. Portfolio-specific news intelligence

### 11.1 Problem
`lib/news.py` already has strong, real patterns: per-category staleness windows, curated sentiment keyword lists, NRI-tax reserved slots, homonym-ticker handling, deferred-date sorting. It is keyword matching on Google News RSS with no exposure weighting or per-holding "why this matters."

### 11.2 Requirements

- **R-1101 — Exposure-weighted news. [Class 2/4]** Rank news by the family's ₹ at risk in the affected holding (exposure weight is computable; news itself is external). Implementable now over existing news output.
- **R-1102 — Relevancy scoring. [Class 2/4]** Score each item on: exposure weight, holding-match confidence, recency (per category), source, sentiment → one relevance rank, with the scoring exposed so it's auditable (no black-box).
- **R-1103 — NRI/tax/macro guarantees. [Class 1]** Preserve the existing reservation mechanics (min NRI-tax and macro slots) and per-category staleness windows — these already work and are the differentiator. **This is the NRI-tax layer referenced by R-803.**
- **R-1104 — Per-dossier news. [Class 2/4]** Each Asset 360 dossier (R-901) gets an instrument-specific news strip using the same scoring. Consistent family/dossier views.
- **R-1105 — Actionable flags. [Class 2/4]** Material-exposure + negative-relevance surge (drop/probe/fraud keywords) → OS attention tile, not just a news card.

---

## 12. AI investment analyst

### 12.1 Problem
Families want a plain-language "talk to your portfolio." The app recomputes full state each load with provenance — a good substrate for an analyst grounded in *real* numbers, not generic commentary.

### 12.2 Requirements

- **R-1201 — Grounded analyst. [Class 5 (optional/future)]** An `Analyst` interface consuming the session's computed state and answering natural-language questions, citing figure + provenance. **This depends on the whole §0-§2 framing and is genuinely future** — it is not implementable on free tier without an external LLM call and careful grounding; defer.
- **R-1202 — Guardrails. [Class 5]** Refuse to fabricate numbers, refuse personalized tax/investment advice beyond caveated guidance, refuse answers about absent data. Every answer ends with a data-quality caveat where inference occurred.
- **R-1203 — Deterministic facts first. [Class 5]** Factual questions resolve via deterministic compute described in the answer; the LLM phrases, never computes.
- **R-1204 — Context pack. [Class 5]** A single versioned context builder (numbers + provenance + caveats) reused by every analyst call.
- **R-1205 — Privacy posture. [Class 5]** No portfolio data leaves unless the user opts in; the model call is optional/switchable; logs are local and de-identified. **Explicitly: the sample workbook contains fabricated names/account numbers (ABC123…), so don't confuse it with real private data in any privacy or security framing.**

---

## 13. Free financial data / API sources

### 13.1 Problem
Free sources are integrated ad hoc. A consolidated, replaceable data-access layer is needed so one upstream change doesn't break five pages.

### 13.2 Source catalogue (free/public) — with honest reliability notes

| Domain | Source | Reliability / class |
|---|---|---|
| Mutual fund NAV | AMFI NAVAll.txt | Free, daily update; disk-cached fallback on failure. Class 4 |
| MF NAV history | mfapi.in | Free, per-scheme full history. Class 4 |
| MF scheme universe | AMFI NAVAll → `amfi_scheme_universe.json` | Already committed (14k+ schemes). Class 1 (cached) |
| MF holdings | fund-disclosures API → mfdata.in fallback | `mf_holdings_cache.json` committed (20 funds). Class 1 (cached) |
| Direct stocks / SGB | Groww NSE CASH LTP (primary), Yahoo `.NS` (fallback) | Free, live intraday + close. Class 4 |
| Market indices & metals | Yahoo Finance | Free, delayed. Class 4 |
| FX (live + historical) | Frankfurter | Free. Class 4 |
| Gold ₹ (spot) | goldprice.dev | Free, no key. Class 4 |
| News | Google News RSS | Free, best-effort; feeds are unauthenticated RSS. Class 4 |
| Corporate actions / results | Free scrapers/feeds (NSE/BSE/aggregators) | **No reliable guaranteed free source; rate-limited.** Class 4/5 |

### 13.3 Requirements

- **R-1301 — Adapter layer. [Class 1/4 infra]** `lib/data_sources/` with one adapter per source, uniform interface (fetch, parse, cache, TTL, provenance). Pages depend on adapters, never raw URLs. Each fetch records `{source, url, fetched_at, as_of, ttl, cached}`. **Note: R-1301 is the data-adapter layer, not the NRI-tax news section (that's R-1103) — do not confuse the two.**
- **R-1302 — Unified cache. [Class 1/4 infra]** A single TTL + disk-cache manager (merging today's per-function caches) with a cache/live/offline indicator. Systematic, and correct-by-construction away from silent zeros.
- **R-1303 — Graceful degradation matrix. [Class 4 infra]** Per-source fallback chain (live → disk cache → degraded → explicit "no data") plus the severity/flag shown at each step. **Free APIs and GitHub Actions are best-effort**; no matrix step may invent a number.

---

## 14. Data provenance & quality

### 14.1 Problem
Numbers flow from a hand-maintained **sample** workbook plus live APIs plus cached holdings. Integrity issues and reconciliation are already logged in-UI, but provenance isn't attached to individual figures and quality isn't a persistent journal.

### 14.2 Requirements

- **R-1401 — Figure-level provenance. [Class 2]** Every displayed figure traceable to source + as-of + method, shown as "Why this number?". Deterministic plumbing over existing data.
- **R-1402 — Quality journal. [Class 2/5]** An append-only `data_quality.jsonl` of issues (severity, message, figure, method, timestamp), driving flags, reconciliation, and analyst caveats. Note: on free ephemeral storage, persistence is Class 5 unless tied to the durable-history decision (§15).
- **R-1403 — Reconciliation suite. [Class 1]** Keep and expand the existing pass/fail reconciliation tests (owner sums, allocation 100%, gold non-leak, FCNR identity). Already implemented in Command Center; formalize and share with pytest (R-1805).
- **R-1404 — Workbook lint. [Class 1/2]** On load validate columns, types, duplicates (existing FD dedup logic), and cross-sheet sanity. Sample workbook columns are already known and good; add structured lint output.
- **R-1405 — Method-change detection. [Class 2]** If a valuation method changes between runs, record it as a provenance event (feeds R-505, R-903).

---

## 15. Historical tracking

### 15.1 Problem
History is a single local `history.csv` (net_worth, equity_pct, fd_pct, pnl, health_score). `lib/history.py` already contains an explicit comment: *"Still uses local file — ephemeral on Streamlit Cloud. Swap body later for Google Sheet / Supabase without changing callers."* So the abstraction *exists*; the backend is undecided.

### 15.2 Requirements

- **R-1501 — Durable history backend — decide, don't pre-lock. [Class 2 infra / 5 persistence]** Implement the already-anticipated swap behind the existing `HistoryStore`-style abstraction (do not couple callers to a backend). **Google Sheets is one candidate, not a decision.** On free Streamlit Cloud, alternatives include: Google Sheets (needs OAuth/service-account + secrets), Supabase (free tier, needs account), or a committed-JSON via GitHub Actions (leverages the existing workflow that already commits to the repo). **Evaluate each against free-tier constraints before choosing; keep the interface backend-agnostic.** Persistence on the ephemeral app filesystem is the actual problem; pick the backend that survives restarts and is cheapest to operate for one family.
- **R-1502 — Richer snapshot schema. [Class 2/5]** Extend snapshots beyond 6 columns (net-worth by class, per-member, XIRR summary, risk metrics, allocation actual-vs-target, active flags). Keep backward-compatible column names for existing downloads. Heartily scoped: the metrics exist (Class 2); persistence of the richer schema is Class 5.
- **R-1503 — Outlier & gap handling. [Class 2]** Detect and mark anomalous snapshots (sudden >X% swings with no driver); allow explicit user annotation. Computable; annotation is Class 3.
- **R-1504 — Restore/audit. [Class 1/5]** Import prior exports (the existing merge logic already does this) and render an audit view of when/from-what snapshots were written. Import works now; durable audit view is Class 5 persistence.

---

## 16. Automation

### 16.1 Problem
The only automation is the existing GitHub Action (`update-holdings.yml`) refreshing MF holdings daily. Everything else recomputes per page load and hits live APIs at request time.

### 16.2 Requirements

- **R-1601 — Scheduled snapshot pipeline. [Class 4/5 infra — honest limits]** A scheduled job that ingests the workbook, computes OS state, and writes a durable snapshot. **GitHub Actions free tier: scheduled workflows can be paused after ~60 days of repo inactivity, and the runner cannot run the Streamlit app's session logic directly.** A scheduled *script* (like the existing holdings refresh) that computes and commits snapshots is feasible; a full "independent of anyone opening the dashboard" claim is only partially achievable and needs the backend decision (§15). Scope honestly; mark the guaranteed-delivery limits.
- **R-1602 — Cache warming. [Class 4/5]** Pre-warm AMFI universe, MF NAV history, holdings cache, and FX history on schedule so first load is fast and offline-tolerant. Feasible as a script job; best-effort (external APIs).
- **R-1603 — Pipeline stages. [Class 2 infra]** Formalize `ingest → clean → compute → persist → publish`, each idempotent and retryable, with a run log.
- **R-1604 — Notification on anomalies. [Class 5]** When the quality journal emits CRITICAL, or an attention tile fires, optionally notify (email via free tier / GitHub issue). Future; depends on persistence + external mail service.

---

## 17. Responsive institutional UI

### 17.1 Problem
The existing theme (`lib/theme.py`, dark palette, custom CSS in Command Center) already provides an institutional feel, but styling is partly ad hoc and there's no component system or fully coherent mobile strategy.

### 17.2 Requirements

- **R-1701 — Component library. [Class 1/2]** Reusable `lib/ui/` components (metric card, KPI strip, attention tile, provenance tooltip, quality badge, chart wrappers) sharing one dark design system. Refactor work over existing functionality.
- **R-1702 — Responsive first. [Class 1/2]** Extend the existing mobile media-query work into a coherent breakpoint strategy; tables collapse to cards; the auto-refresh toggle stays but is polite.
- **R-1703 — Institutional density + explanation. [Class 1/2]** Dense tables with inline "why this matters"/caveats; every chart has a definition and source caption.
- **R-1704 — Navigation & focus. [Class 1/2]** Keep the 5-page nav; add new surfaces (Look-through, Overlap, XIRR, Risk, Asset 360, Calendar) via focused sub-navigation without bloating any single page.
- **R-1705 — Accessibility. [Class 1/2]** Contrast (already met), keyboard navigation, non-color sentiment indicators (icons + text).

---

## 18. Testing

### 18.1 Problem
No test suite, no lint config (AGENTS.md). For financial accuracy this is the highest-risk gap.

### 18.2 Requirements

- **R-1801 — Test framework. [Class 1 infra]** Adopt `pytest`; add config. Unit, integration, and a small end-to-end smoke over the **sample** workbook as a fixture.
- **R-1802 — Pure-compute unit tests. [Class 1/2 infra]** Extract math into pure functions (FCNR attribution, FD valuation, gold routing, XIRR, overlap, look-through, risk, health score) and test:
  - FCNR identity within ₹1 (R-502).
  - XIRR on lump-sum + user-supplied cashflow fixtures.
  - FD valuation across all three methods incl. simple-interest/long-tenor **and the `notess` bug**.
  - Gold routing / dedup / non-leak invariants.
  - Sentiment + relevancy scoring on fixture headlines.
- **R-1803 — Regression fixtures. [Class 1/2 infra]** Version the sample workbook + a `mf_holdings_cache` snapshot; capture golden totals and assert thereafter so refactors can't silently change numbers. **Explicitly fixtures, not live personal data** — the repo's workbook is fabricated sample data.
- **R-1804 — Adapter tests with mocks. [Class 1/4 infra]** Record sample payloads; no network in CI; live network only in an opt-in integration suite.
- **R-1805 — Reconciliation parity. [Class 1/2]** The visible reconciliation suite (R-1403) and pytest run the same underlying checks (one implementation, two surfaces).
- **R-1806 — Lint. [Class 1 infra]** Add `ruff` (or `flake8`+`black`), minimal config, run in CI. First pass fixes `notess` and any other real defects found.

---

## 19. Performance

### 19.1 Problem
The main page recomputes everything and pulls live APIs per request (TTL-cached). On free Streamlit Cloud this can be slow and hit memory limits.

### 19.2 Requirements

- **R-1901 — Cache discipline. [Class 1/4 infra]** Via the unified manager (R-1302); never fetch synchronously in a render-critical path if a cached value exists.
- **R-1902 — Compute de-dup. [Class 1/2]** Compute the OS state once per session and share across pages via `st.session_state` (the existing cross-page pattern); not per page.
- **R-1903 — Lazy/warm load. [Class 4/5]** Warm caches via pipeline (R-1602); lazily compute expensive look-through/risk on first view rather than blocking headline metrics.
- **R-1904 — DataFrame hygiene. [Class 1/2]** Cheap display transforms; reuse styled tables; cap chart points; avoid repeated `to_csv`/`concat` in hot paths.
- **R-1905 — Budgets. [Class 5]** Rough target: headline metrics <1.5s after warm cache, dossier <2s, full page <6s cold on free tier. Optional "perf trace" toggle.

---

## 20. Security

### 20.1 Problem
The workbook and caches contain financial data. **Important audit correction:** the committed `Networth_Raw_Data.xlsx` in the source repo is **fabricated sample data** (names like "Mrs. KAVITA KHANDELWAL", account numbers "ABC123…"), not a real family. When the user supplies a real workbook, it will contain real data — that is when access control matters. Security framing should assume a future real workbook, but not treat the sample as live secrets.

### 20.2 Requirements

- **R-2001 — Access control on Streamlit Cloud. [Class 3/5 infra]** Add an app-wide auth gate (session password via `st.secrets`, or OAuth if free tier allows) so a real deployment isn't public by default. Session-locked after inactivity. Optional/future given the app is currently sample-data driven.
- **R-2002 — Secrets handling. [Class 1/5 infra]** Move credentials/tokens (history backend, optional analyst key) into Streamlit secrets; never hardcode; `.streamlit/secrets.toml` git-ignored.
- **R-2003 — No secret logging. [Class 1/5]** Ensure workflows use `GITHUB_TOKEN` only; redact account numbers in any export/log view; quality journal excludes sensitive fields.
- **R-2004 — Export redaction. [Class 2]** CSV/export features redact account numbers by default; full detail behind auth. Feasible (the FD sheet's Account Number is present and can be redacted).
- **R-2005 — Dependency hygiene. [Class 1]** Pin/spot-check `requirements.txt`; keep Python 3.11 consistent with the workflow (`setup-python@v6`, 3.11).
- **R-2006 — External-call safety. [Class 1/4]** HTTPS-only, time-boxed (existing timeouts), never send portfolio data to third parties without user opt-in (R-1205).

---

## 21. Free Streamlit deployment

### 21.1 Problem
Free Streamlit Community Cloud: ephemeral filesystem, no persistent DB, limited memory, constrained scheduled tasks. Everything must work within those limits.

### 21.2 Requirements

- **R-2101 — Ephemeral-filesystem tolerance. [Class 5]** Everything that must survive restarts lives in a durable backend (chosen in R-1501) or is reproducible; filesystem is cache/scratch, never source of truth. **Honest scope:** on free tier this is achievable but limited; deliver incrementally (start with history durability + quality journal, not full persistence).
- **R-2102 — Config-driven deployment. [Class 1/5]** `.streamlit/config.toml` + `.streamlit/secrets.toml` (git-ignored) drive auth, theme, settings; document one-time Cloud setup in a RUNBOOK.
- **R-2103 — CI parity + honest limits. [Class 1/4 infra]** `.github/workflows` runs lint + unit tests (R-1806/R-1802), the existing holdings-refresh action, and — with the §16 caveats — the scheduled snapshot pipeline (R-1601). Local `streamlit run app.py` and CI must agree (same `requirements.txt`, same Python 3.11). **Mitigate free-tier limits** (workflow pause on inactivity, no DNS on the app itself) with a documented fallback (e.g. keep history commit job within the existing workflow).
- **R-2104 — Scale limits. [Class 1]** Optimize for a small family (tens of holdings, ~26 MF + 36 stocks + 33 FD rows today). Document that the free tier is sized for this, not for scale.

---

## 22. Phasing & release

### 22.1 Suggested sequencing (each phase shippable; tags from §0)

- **Phase 0 — Foundation [Class 1]:** Fix `notess` bug; pytest + ruff; extract pure compute from Command Center into `lib/`; unified cache + provenance manager; **decide** (not lock) durable-history backend; workbook-lint.
- **Phase 1 — Ledger [Class 1/2]:** Asset register + member/family reporting + net-worth decomposition + optional liabilities (Class 3) as an explicit "needs data" input surface.
- **Phase 2 — Returns [Class 2 + Class 3 for multi-cashflow]:** lump-sum XIRR correctness now (R-402 lump path); true XIRR once real transaction data is supplied (R-401). No SIP reconstruction (R-403 retired).
- **Phase 3 — Look-through & overlap [Class 2]:** holdings-driven exposure, sector/underlying allocation, pairwise overlap — from committed cache.
- **Phase 4 — Risk & scenarios [Class 2/4]:** volatility/drawdown/beta/Sharpe, stress tests, explainable score.
- **Phase 5 — OS surfaces [Class 2/4]:** Asset 360 dossiers, maturity/decision runway, results/action calendar (best-effort), exposure-weighted news.
- **Phase 6 — AI analyst [Class 5]:** grounded analyst + context pack + guardrails — optional/future.
- **Phase 7 — Automation & hardening [Class 4/5 + Class 1]:** scheduled snapshot pipeline (honest limits), notifications, security gate, performance budgets, mobile polish, durable persistence decision shipped.

### 22.2 Definition of done
Each requirement ships with: (1) unit tests covering the math, (2) provenance + quality tags on the figures, (3) reconciliation checks passing, (4) updated RUNBOOK/deployment notes, and (5) no regression on the existing visible reconciliation suite. **Each feature must also disclose its Data Availability Class and show a correct "no data" state where its data is absent. Nothing ships that can silently produce a wrong number.**

---

## 23. Non-goals (v1)

- No real brokerage/bank API integration (stays manual-workbook + free data).
- No multi-currency beyond USD/INR, no derivatives/options.
- No paid data subscriptions.
- No SIP-transaction reconstruction from NAV history (invents data — expressly forbidden).
- No multi-user access beyond a family-level auth gate.
- No mobile-native app (responsive web only).
- No fabricated SGB/liability/tax/series figures (AGENTS.md's do-not-invent rule preserved).
