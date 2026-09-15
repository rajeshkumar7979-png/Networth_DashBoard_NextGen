# AGENTS.md — Networth Dashboard (NextGen)

## Permanent engineering operating contract

This is the standing engineering contract for **all** future implementation work in this repository. Apply it **automatically** on every task — do not wait to be reminded, and do not require re-explanation. Only an explicit, task-level instruction from the user overrides a rule here.

### 1. Understand before changing

- Inspect the relevant existing architecture first. Reuse modules in `lib/`, the established `st.session_state` cross-page flow, the frozen test baseline, and the intelligence model — do not reimplement capabilities that already exist.
- Search the repository before creating a new abstraction or a new file. If a function, classifier, formatter, cache, or adapter already covers the need, extend it.
- Re-read `INVESTMENT_OS_SPEC.md` (the audited v1.1 spec) before adding features: every feature has a Data-Availability Class (1–5) that defines what data exists vs. what must not be invented.
- Understand existing financial semantics before modifying anything. Identify dependencies and downstream consumers — pages import `lib/*`, intelligence imports `lib/*`, tests pin behavior. A change to `lib/` must be re-verified through its consumers.
- Never assume a missing capability means it must be rebuilt. Verify whether it already exists in another layer (page vs `lib` vs script vs committed cache) first.

### 2. Design before implementing

- Think through the smallest correct architecture that satisfies the requested behavior — no speculative generality.
- Prefer simple, deterministic, pure, testable components over clever or stateful ones.
- Preserve provider neutrality where it exists (e.g. `lib/intelligence/sources/` is a provider-neutral gateway; pages depend on adapters, never on raw URLs).
- Explicitly distinguish what is currently implemented from what is future architecture. Do not implement roadmap items that are not the requested task.
- State your assumptions explicitly and reject any assumption the repository/spec does not support — especially any that would invent data.

### 3. Financial correctness is a hard constraint

- Existing financial calculations are the source of truth unless the task explicitly changes them. Deterministic tests pin the current numbers (`tests/frozen_baseline.py`, `tests/test_drivers.py`, `tests/test_fcnr_attribution.py`, `tests/test_fd_valuation.py`, `tests/test_ledger.py`, `tests/test_register.py`, `tests/test_golden_totals.py`).
- Never silently redefine financial terminology. Examples already frozen: `Net Worth = Total Assets − Liabilities` is computed **only** by `lib/ledger.net_worth()`; per-class `invested_basis_change` is the **"Invested-Basis Change"** and is never called a "flow", "deposit", "withdrawal", "SIP", "redemption", or transaction.
- Never invent transaction history, cash flows, SIPs, returns, valuations, holdings, tax consequences, corporate actions, or exposures. Missing data stays missing and renders as "no data" / "insufficient evidence".
- Distinguish facts, calculated facts, signals, AI interpretations, and recommendations (the `FactKind` taxonomy in `lib/intelligence/model.py`). External data is an observed `FACT`; our deterministic math is a `CALCULATED FACT`; never label either as AI.
- Never convert unknown/missing values into zero merely to make calculations or UI look complete.
- Preserve precision where financially material (e.g. full-precision FD attribution with a labeled rounding residual, not silent rounding).
- Preserve provenance for external data: source identity, retrieval/publication timestamps, and the valuation method used.

### 4. Implement completely

- Implement the requested behavior including realistic failure modes, not just the happy path.
- Handle — wherever relevant — malformed data, missing data, duplicate data, stale data, provider failures, timeouts, missing credentials, corrupted caches, identifier collisions, empty datasets, and schema changes.
- Failures must degrade safely (live → disk cache → stale-degraded → explicit "no data"); a failure must never silently alter or corrupt portfolio information.
- Do not leave obvious TODOs, dead code, or knowingly incomplete behavior unless the task explicitly asks for a scaffold.

### 5. Self-review before reporting completion

- After implementing, independently review your own work as if reviewing another engineer's pull request. Ask:
  - What could be wrong? What assumptions did I make?
  - What edge cases did I miss?
  - Can existing behavior regress? Can data provenance become misleading?
  - Can identifiers collide? Can stale/missing data be misrepresented?
  - Can a failure path corrupt or alter financial results?
  - Did I accidentally expand scope, duplicate existing logic, or add unnecessary dependencies?
  - Did I create security/privacy issues (secrets, logging, account-number redaction)?
  - Does the implementation actually satisfy the architectural intent?
- If you find defects, **fix them yourself** before reporting completion. Do not stop at "tests pass" when code inspection reveals a problem.

### 6. Test the implementation

- Add focused tests for new behavior and regression tests for any important bug you discover. Test happy paths **and** meaningful failure paths.
- Run the complete existing suite, not only the new tests: `pytest` (the default suite is network-free; `pytest -m smoke` is the optional network/multipage AppTest).
- Run lint and static checks: `ruff check .`. Run formatting/diff checks: `git diff --check`.
- Where relevant, compare important financial outputs against the established baseline (`FROZEN_TOTALS` / `FROZEN_BOOKS`) instead of trusting a one-off run.

### 7. Regression safety

- Before declaring completion, verify: unrelated existing functionality is unchanged; existing session-state keys and cross-page flow still work; existing financial metrics are unchanged where they should be; no unintended files, caches, data files, or configuration changed.
- Inspect `git status` and `git diff`. Check for accidental secrets, debug code, temporary files, generated artifacts, or unnecessary dependencies.

### 8. Data / external-provider safety

- Use authoritative sources where available; preserve source identity and provenance.
- Record retrieval/publication timestamps appropriately and distinguish cached/stale data from freshly retrieved data.
- Never claim an external source says something it does not.
- Never infer identity using fuzzy matching where exact identity is required (see `lib/intelligence/sources/mapping.py` — exact match only).
- A provider failure must never become a financial fact: failure degrades to unavailable/stale, never to a successful record with made-up values.
- Credentials must never leak into source records, logs, cache keys, cache files, UI, or error messages. Keys come from the environment/secrets, never from source code.
- Network calls happen only where explicitly intended (e.g. opening the Command Center must not trigger gateway provider calls; the gateway fetches only when its `fetch_*` functions are invoked).

### 9. AI safety (for when AI is eventually introduced)

- Python/deterministic systems remain the source of truth for financial facts.
- AI may interpret verified facts but must never invent them; AI-generated claims must retain evidence/provenance.
- Insufficient evidence results in expressed uncertainty, never fabrication.
- Recommendations remain decision support, never automatic trading.
- Clearly distinguish fact, calculation, signal, interpretation, and recommendation in any output.

### 10. Scope discipline

- Implement the requested phase completely. Do not silently implement unrelated roadmap items.
- Do not introduce databases, automation, new APIs, AI providers, infrastructure, or dependencies merely because they may be useful later.
- Do proactively fix defects that are directly caused by the implementation or necessary for correctness.
- If a requested design conflicts with existing financial semantics, stop and resolve the conflict rather than silently implementing something unsafe.

### 11. Efficiency

- Do not repeatedly ask the user to perform engineering checks you can perform yourself.
- Do not stop merely because the first implementation works, and do not create artificial review cycles.
- Complete implementation + self-review + testing + correction as one engineering task whenever possible.
- Ask the user only when a genuine product/architecture/business decision cannot be determined safely from the repository or the specification.

### 12. Reporting

When finished, report: what was implemented; important design decisions; files changed; tests/checks performed; defects discovered and fixed during self-review; remaining limitations; whether the implementation is ready for commit. Never claim "complete" merely because the requested code was written.

## Project-specific rules (inviolable)

- The original `Networth_DashBoard` repository is **never** modified. All work happens in this repository: `Networth_DashBoard_NextGen`.
- `INVESTMENT_OS_SPEC.md` is a working specification and must remain **untracked** unless explicitly instructed otherwise. Do not modify it unless asked.
- Existing data caches and sample/demo data (`data/Networth_Raw_Data.xlsx`, `data/amfi_scheme_universe.json`, `data/mf_holdings_cache.json`, `data/mf_holdings_meta.json`, `data/amfi_nav_cache.json`, `data/history.csv`) must not be modified unless explicitly requested. `data/intel_gateway_cache/` is gitignored runtime data that the gateway may write.
- Preserve the existing dashboard. Prefer extending existing functionality over rebuilding it.
- No automatic trading. No invented financial history. No unsupported financial conclusions.
- The committed workbook is fabricated sample data (obfuscated names like "Mrs. KAVITA KHANDELWAL", account numbers like `ABC123`/); do not treat it as private, and never use sample-data assumptions as a substitute for protecting real data if it is later replaced.

## What this is

Streamlit multi-page app for a family net-worth dashboard (NRI-focused). Dark institutional theme.

**Product plan:** `INVESTMENT_OS_SPEC.md` (root) is the audited v1.1 spec for the Family Investment Intelligence OS transformation. Each feature there is tagged with a Data-Availability Class (1–5). Re-read it before adding features; it defines what data exists vs. what must not be invented.

## Run locally

```bash
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py
```

Python 3.11 (matches CI `setup-python@v6`). No build step.

## Test & lint

```bash
pip install -r requirements-dev.txt   # adds pytest + ruff
pytest        # deterministic regression suite (no network); smoke excluded by default
pytest -m smoke   # optional network/multipage Streamlit AppTest (flaky offline)
ruff check .  # lint, minimal E/F scope (see ruff.toml)
git diff --check   # whitespace/conflict-marker gate before reporting done
```

CI (`.github/workflows/ci.yml`) installs **both** `requirements.txt` and `requirements-dev.txt`, then runs `ruff check .` and `pytest` on every push/PR. The default pytest suite never hits the network; the `smoke`-marked AppTest does. The operating contract (§6–§7) requires the **full** suite + lint + diff-check to pass before completion is reported.

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
| `pages/1_Command_Center.py` | **Main page (~2000 lines).** All portfolio logic, valuation, scoring, charts; imports and delegates financial compute to `lib/*`. |
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
| `lib/drivers.py` | **P&L drivers + snapshot delta** (Phase 1B, pure module): `class_pnl_from_register`, `decompose_current`, `snapshot_delta`, `fd_return_components`, `fd_rounding_bound`, `class_slug`, `DRIVER_KEYS`, `DRIVER_LABELS`, `NOT_A_CASHFLOW_LABEL`. Decomposes current-run P&L into six drivers (Equity market, Liquid NAV, Gold price, FCNR interest, FCNR FX-on-principal, INR FD interest) plus a labeled rounding residual bounded by `1.5*n_fd + 1`. |
| `lib/snapshot.py` | **Enriched ledger snapshots** (Phase 1B, pure module): `build_snapshot_row`, `clean`, `load_history`, `upsert_snapshot`, `merge_uploaded`, `SCHEMA`, `BASE_COLS`. Historical rows are append-only/immutable; today's row is upserted (same-date replace). Base columns keep historical names; enriched columns are additive on top. Legacy 6-col rows stay legacy and are never back-filled. Reads/writes history by column name, never positionally. |
| `lib/mf_holdings.py` | MF holdings ingestion (fund-disclosures → mfdata.in fallback). |
| `lib/mf_health.py` | MF health analysis. |
| `lib/news.py` | Portfolio news aggregation. |
| `lib/theme.py` | CSS injection (`inject_css`). |
| `lib/intelligence/` | **Portfolio intelligence foundation** (committed): shared domain model (`model.py` — `FactKind`/`SourceClass`/`SourceType`, `make_fact`, `make_evidence`, `slugify`), `evidence.py` (evidence bag + provenance), `exposure.py` (look-through exposure facts + `Coverage`), `signals.py` (deterministic signal rules), `provider.py` (deterministic/reasoner provider protocol + `validate_claims`), `portfolio_brain.py` (`build_briefing`). Pages consume it read-only; the Command Center renders a briefing expander. |
| `lib/intelligence/sources/` | **Intelligence Data Gateway v1** (provider-neutral): `record.py` (`SourceRecord`/`SourceResult`), `errors.py`, `httpio.py` (network seam), `cache.py` (TTL JSON cache under `data/intel_gateway_cache/`, gitignored), `fred.py`/`sec.py`/`mf.py`, `mapping.py` (exact-match portfolio relevance). Live fetch is on-demand only; `gateway_status()` reads caches with no network. |
| `scripts/update_holdings_cache.py` | CLI script run by GitHub Actions daily. Refreshes `data/mf_holdings_cache.json`. |

## Cross-page data flow

Pages communicate via `st.session_state`. Command Center writes keys like `matured_fd_amount`, `mf_holdings_for_health`, `cc_equity_pct`, `cc_intel_briefing`, `cc_intel_gateway_status`. Deep Health and MF Health read them. There is no shared database — everything is session-scoped and recomputed on each page load.

## External data sources (called at runtime)

- **AMFI NAVAll.txt** — NAV by ISIN. Cached to `data/amfi_nav_cache.json` on disk as fallback.
- **Groww** — live stock/SGB prices (NSE CASH endpoint).
- **Yahoo Finance** — market indices, COMEX gold/silver, FX, historical NAVs.
- **Frankfurter** — USD/INR live and historical rates.
- **goldprice.dev** — INR gold spot.
- **fund-disclosures / mfdata.in** — MF portfolio holdings (used by holdings refresh script).
- **Google News RSS** — news feed.
- **FRED** and **SEC EDGAR** — via the Intelligence Data Gateway (`lib/intelligence/sources/`): explicit on-demand `fetch_*` functions only, TTL-cached to `data/intel_gateway_cache/`. `FRED_API_KEY` (Streamlit secret `st.secrets["fred"]["FRED_API_KEY"]`, else env; runtime-gated so scripts/tests never read the secrets file) and `SEC_USER_AGENT` (env, optional) are the only credentials.

All have TTL-based Streamlit caching. Network failures degrade gracefully to disk/previous cache. Per §8, opening a page must not trigger hidden gateway network calls.

## Gold routing logic

Gold instruments (SGB tickers `SGB*-GB`, gold ETFs, gold FoFs) are routed **out** of the Stocks and MF tables into a unified Gold book. `is_gold_symbol()` and `is_gold_fund()` in `lib/gold.py` control this (Command Center imports and delegates). If you add a new gold instrument, update those functions — and add a case to `tests/test_gold_routing.py`.

## NRI-specific valuation

FCNR (USD) deposits use historical FX from deposit date for cost basis, not today's rate. See `compute_fd_current_native()` and `compute_fcnr_attribution()` in `lib/valuation.py`. The identity `interest_at_current_fx + fx_on_principal == current_value_inr - cost_basis_inr` must reconcile within ₹1 (pinned by `tests/test_fcnr_attribution.py`).

## Phase 1B — P&L drivers + snapshot delta (vocabulary rules)

The workbook has **no cash-flow/transaction ledger** (SPEC R-403 retired). The per-class `invested_basis_change = class_invested_now - class_invested_prev` is **never** called a "flow", "deposit", "withdrawal", "SIP", "redemption", or transaction — it is the **"Invested-Basis Change"** and every output carries `NOT_A_CASHFLOW_LABEL = "NOT a cash-flow measurement; transaction history unavailable."` Stop immediately if any code/UI/label/doc calls it a "flow". Delta decomposition identity (in `lib/drivers.snapshot_delta`):

- `invested_basis_change_c = class_invested_now - class_invested_prev` (exact)
- `market_valuation_change_c = (class_current_now - class_invested_now) - (class_current_prev - class_invested_prev)`
- `delta_current_c = invested_basis_change_c + market_valuation_change_c` (exact)
- `delta_pnl = Σ market_valuation_change_c` (exact)

Current-run P&L decomposes into six valuation drivers (`decompose_current`) plus a labeled rounding residual bounded by `fd_rounding_bound(n)=1.5*n_fd+1` (worst case ~23 for 23 FDs, not `<1`). Command Center's FD loop accumulates full-precision pre-round attribution (`fd_attrib`) keyed by `Product` (FCNR vs INR FD); the page's three driver reconciliation entries use that bound. Historical snapshots are persisted via `lib/snapshot.build_snapshot_row/upsert_snapshot` into `data/history.csv` (gitignored) with enriched columns (`schema`, `class_current_*`, `class_invested_*`, `member_current_*`, `member_invested_*`, `fcnr_interest_total`, `fcnr_fx_principal_total`, `inr_fd_interest_total`, …). Persistence semantics: historical rows are append-only/immutable; today's row is upserted (same-date replace), and older dates are never rewritten. A legacy pre-Phase 1B prior row cannot decompose; the delta block flags it as unattributed instead of mixing in transactions. Pinned by `tests/test_drivers.py` and `tests/test_snapshot.py`.

## Phase 1A golden baseline (tests/frozen_baseline.py)

`tests/frozen_baseline.py` freezes the actual Command Center totals and the four validated books (`mf`/`stocks`/`gold`/`fd`, register-relevant columns) from a live capture run on the committed sample workbook (TODAY `2026-09-08`, USD_INR `94.49`). `tests/test_register.py` rebuilds the register from these frozen books and asserts class/member/register totals reconcile to `FROZEN_TOTALS` and `FROZEN_MEMBER_CURRENT/INVESTED` within ₹1 — i.e. the register (canonical view) equals the Command Center (page view) by construction; it also pins FD key uniqueness (all workbook FDs are `acct:`-backed) and the `NonUniqueKeyError` collision STOP. `tests/test_page_smoke.py` additionally asserts on every live run that the rendered Reconciliation block contains no `✗ FAIL` (register vs page reconciliation gate). `FROZEN_BOOKS` also backs Phase 1B's `CLASS_PNL_GOLDEN` (5 class P&L values) and `FROZEN_FD_DRIVERS` (full-precision FCNR/INR FD components, `n_fd=23`) used by `tests/test_drivers.py`; these were captured from the same baseline and need no live run to reproduce. If a future SPEC-approved Phase 1+ change alters valuation, recapture the baseline (run the Command Center once with a dump harness) rather than editing the frozen numbers by hand.

## Intelligence foundation & data gateway vocabulary

The intelligence layers add a provenance vocabulary (§3, §8, §9) layered on top of — never replacing — the financial compute:

- **Facts** (`Fact` in `lib/intelligence/model.py`) carry kind (`FACT` / `CALCULATED FACT` / `SIGNAL` / `AI INTERPRETATION` / `RECOMMENDATION`), source class (A authoritative … D experimental), and source type (calculated / observed / official-filing / news / ai-inferred).
- **Evidence** (`Evidence`/`Provenance`) attaches provenance to every external claim. `INSUFFICIENT_EVIDENCE` is the explicit "no data" fallback — never a fabricated value.
- **Signals** (`lib/intelligence/signals.py`) are deterministic rules over facts+evidence (e.g. FCNR concentration ≥ 35% → warn). They are facts with a level, not advice.
- **Gateway records** (`lib/intelligence/sources/`) normalize external data (FRED observations, SEC filings/company-facts summary, AMFI NAV, fund holdings) into observed `SourceRecord`s that convert to `Evidence` unchanged. Exact-identifier entity mapping only (`mapping.py`); a provider failure is an `unavailable` result, never evidence.

## Research & Synthesis v1 (evidence-based research brief)

`lib/intelligence/research.py` answers the research questions on top of the same facts/evidence/signals the briefing already uses, deterministically and **network-free**:

- `build_research_brief(...)` -> `ResearchBrief` with `changes` (P&L drivers + Invested-Basis Change + market/valuation change + labeled residual), `external` (ranked developments: mapped-to-portfolio first, then news/macro, by a deterministic `score_evidence` quality score), `risks` (elevated signals), `research_needs` (decision-support questions where evidence is thin — never orders), `gaps` (explicit "insufficient evidence" items), a `synthesis` (`ResearchSynthesizer`, deterministic rule-based), and `research-*` conclusions.
- **Every conclusion carries an `invalidation` condition and a `strength` label** (`strong`/`moderate`/`weak`/`insufficient`). No AI provider is connected; a future AI plugs in behind the existing `provider.py` registry and its claims are still downgraded by `validate_claims` when a cited fact id is absent.
- **Reuse rules**: the brief consumes the existing register/drivers/snapshot delta (`lib/drivers.py`, `delta_from_history` over `data/history.csv`), the existing `EvidenceBag`, `evaluate_signals`, `build_portfolio_index`/`assess_relevance` (exact-match only) and cache-read-only gateway loaders (`load_mf_nav_evidence(only_isins=...)`, `load_mf_holdings_evidence`, `gateway_cached_evidence`). Opening the Command Center never triggers gateway network calls.
- **Vocabulary frozen (tests pin it)**: the invested difference between snapshots is the **"Invested-Basis Change"**, `cashflow_measurement=False`, labeled with `NOT_A_CASHFLOW_LABEL`, and `tests/test_intel_research.py` asserts no "deposit/withdrawal/SIP/redemption/XIRR/buy/sell" wording leaks into any change row or conclusion. The research layer is decision-support only — it never contains orders or trade actions.
- Command Center computes the brief after the intelligence expander and stores it in `st.session_state["cc_research_brief"]`; render is read-only.

## AI Research Provider v1 (opt-in provider-neutral AI interpretation)

`lib/intelligence/ai/` adds an **opt-in AI interpretation layer** on top of — never replacing — the deterministic research layer. The AI restates and interprets verified facts/evidence; it must **never compute or invent** portfolio values, P&L, NAV, prices, holdings, exposure, transactions, cash flows, XIRR, SIP history, tax conclusions, corporate actions, or valuation metrics (they are supplied as deterministic context or restated verbatim). Every claim that survives is still downgraded by the existing `provider.validate_claims`.

- **Entry point:** `run_ai_research(*, brief, config=None, client=None, facts=(), evidence=(), question=None, now=None) -> AIOutcome`. IMPORTANT: this is **never called during page load** — only the Command Center's `Run AI research` button invokes it, and the page computes a data fingerprint (`cc_ai_outcome_for`) so a stale outcome from an older brief is dropped.
- **Provider abstraction:** an `AIProviderClient` Protocol + `register_ai_provider/get_ai_client/build_client` registry. Default transport is Groq (`llama-3.3-70b-versatile`, OpenAI-compatible `/chat/completions`; `openai/gpt-oss-120b` selectable via `AI_MODEL`) with `json_schema` Structured Outputs attempted first and a single 400-degrade retry to `json_object`. Groq supports `json_schema` (strict) only on a few models (gpt-oss variants, qwen3.8-27b); llama-3.3-70b-versatile rejects it with a 400, so the default model always runs the `json_object` path; the prompt spells out every field's exact type so parsing still recovers the schema. The local parser (`parse.py`) recovers the two scalar string fields a drifting model most often mangles (`overall_assessment`, `uncertainty` — object/list/bool/null → bounded plain text with a labeled downgrade) instead of failing the whole answer; genuinely broken shapes still classify `malformed`. The raw model response is logged at DEBUG (bounded 1500-char excerpt, redacted, never shown in the UI) before validation. A provider 404/'model discontinued' rejection raises a clear `AI model {model} is no longer supported. Please update AI_MODEL in your secrets file.` error (see `lib/intelligence/ai/client.py` — no degrade retry is wasted on a discontinued model).
- **Cascade (graceful degradation):** on a retriable network error (timeout/connection refused) with **no explicit `client=` override**, `run_ai_research` falls back Groq → **Ollama local** (`ollama_local`, `http://localhost:11434/v1`, `llama3.1:8b`, keyless, 120 s timeout) → "AI unavailable". The Command Center's AI expander header shows the active provider (Groq / Ollama local / Unavailable / Not configured).
- **Config (Streamlit secrets override env; no hard-coded secrets):** the primary source for `AI_API_KEY` is Streamlit's native secrets (`st.secrets["ai"]["AI_API_KEY"]`, held in the git-ignored `.streamlit/secrets.toml`); everything falls back to the environment keys `AI_API_KEY`, `AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_MAX_TOKENS`, `AI_TEMPERATURE`, `AI_STRUCTURED_OUTPUT`, `AI_MAX_EVIDENCE_CATALOG` (default 20). `ollama_local` is a **keyless** provider — `provider_is_configured()` marks it configured without any key. Secrets are read only when Streamlit's runtime exists (`st.runtime.exists()`), so tests/scripts never touch them. `ai_config_status()` reports configuration **without ever exposing the key**; `redact()` is the single scrub choke point for error strings.
- **Privacy (what is sent):** the prompt carries only deterministic totals/change summaries, deterministic risks/research needs, gaps, a bounded evidence catalog of **curated scalar snippets** (`_SNIPPET_KEYS` allow-list), the allowed evidence-id list, and the research question. Raw positions, holdings dumps, account numbers, holder names, cache payloads and credentials are **never** sent. Tests assert no raw payload leaks into any context.
- **Grounding & validation pipeline:** evidence grounding (every cited id must come from the allow-list, and `fact`-kind findings must cite ≥1 evidence id) → `inherit_fact_ids` (map findings to the deterministic conclusion fact ids via shared evidence ids) → findings → `Interpretation`/`Claim` → existing `validate_claims` (unsupported fact ids downgrade). Downgrades are surfaced in the UI as ⚠ / "downgraded:" notes, never silently dropped.
- **Failure handling (`AIOutcome` statuses):** `ok | not_configured | insufficient_evidence | failed | malformed`; every non-`ok` records `fallback_used=True` and the deterministic `ResearchBrief` synthesis is shown unchanged (provider failures never become financial facts; keys are scrubbed from reasons).
- Output schema (in `lib/intelligence/ai/schema.py`): `overall_assessment`, `confidence` (0..1, clamped), `uncertainty`, `key_findings|risks|opportunities|research_needs` (items with `text`, `evidence_ids`, `kind: fact|interpretation`, per-section cap 8), `invalidation_conditions`, `limitations`. Vocabulary rule from Research & Synthesis still applies — no extra-flows wording, no orders.
- Pinned by `tests/test_ai_provider.py` (fully offline/mocked — no real key, no network). Live endpoint testing is manual/optional only.

## Portfolio-Aware Live Research & News Evidence v1 (cached cohort, explicit refresh only)

`lib/intelligence/live/` adds a **portfolio-aware live research cohort** that keeps ordinary page loads network-free and makes live retrieval strictly on-demand. Deriving the plan and reading the cache happen on every page load; **only the Command Center's `Refresh research evidence` button calls `run_live_research()`**, which hits the network. A provider failure degrades to stale/unavailable, never to a fabricated record, and `scrub_error()` is the single credential-redaction choke point.

- **Entry points:** `build_live_plan(stock_symbols=, fund_names=, gold_symbols=, has_usd_book=, equity_pct=, asset_class_weights=, now=)` (planner: weight-prioritized query derivation — top-5 stock/fund holdings ranked by portfolio value, a sovereign-gold query only when an SGB is held, per-ETF symbol queries except `SGB*`, asset-class contextual queries ("USD INR forecast RBI policy" when a USD/FCNR book exists, "gold price INR forecast" when gold is held, "Nifty 50 valuation PE ratio" when equity >30%) capped at 6 by portfolio weight via `MAX_PORTFOLIO_QUERIES`; FRED USD/INR target `DEXINUS` **only** when a USD book is present; fixed NRI/tax + macro sets are added on top and never crowded out), `load_live_cohort(...)` (network-free cache read, used on page load), `run_live_research(...)` (the ONLY network entry point; explicit button), `live_status(...)` (cache-scan, flags corrupt/stale entries), `development_rows(cohort, index, now)` (UI rows; `affected_for`/`assess_relevance` use **exact identifier matching only** via `sources/mapping.py`).
- **Query hygiene & zero-record fallback:** every derived query passes `sanitize_query()` (planner) — underscores and punctuation that suppress Google News recall ("GOLD_GOLDFEED"/"HDFC_MID_CAP") collapse to spaces; fund queries become "AMC + category" ("HDFC mid cap fund") instead of the full scheme name; the exact identifier is still carried for mapping. When a planned query returns zero records, `run_live_research` retries once with `simplify_query()` (gold/silver → "gold price India", else the first three words) and joins the fallback bucket into the cohort; zero-record misses are logged at INFO for debugging (the simplified form at DEBUG) and never become failures.
- **Providers (final):** **Google News RSS** via feedparser (no API key; `news.py` normalizes to `SourceRecord`s with a `content_id` sha1 digest of the normalized title for dedupe) to `data/live_research_cache/` (gitignored, `gnews-cache-<category>-<query>.json`, TTL 30 min, NEWS per-query cap 8 / cohort cap 40). **FRED `DEXINUS`** (only when FCNR/USD present) writes to the normal gateway cache. **Gateway cache scan** merges any existing FRED/SEC records. No GDELT/Alpha Vantage/SEC-discovery (documented limitation).
- **Evidence model:** gnews records are converted unchanged into `SourceRecord`s → `Evidence` with `FACT` kind, `NEWS` source-type, source class C; they are **OBSERVED FACT evidence, never auto-converted into verified portfolio facts**. Cohort news replaces the generic `ev:news:` feed items in the ResearchBrief base evidence AND is passed as `gateway_evidence` so deterministic `classify_external`/`score_evidence` can rank portfolio-mapped stories first (mapped +fresh → higher).
- **Network separation:** the Intelligence Data Gateway seam (`sources/httpio._http_get`) is the single transport; `load_live_cohort`/`live_status`/page load never call it. `run_live_research` never raises, and its per-provider failures are recorded with scrubbed reasons. A stale/failed refresh degrades the expander with per-query failure rows (credentials scrubbed).
- **Session keys:** `cc_live_result`, `cc_live_refreshed_at`. The AI provider (already opt-in) consumes the augmented brief with the news snippet keys still `()` — never a raw payload.
- **Vocabulary/scope:** research layer remains decision-support only — no orders; the "Invested-Basis Change" wording rules apply unchanged. Pinned by `tests/test_live_research.py` (hermetic, no network, no real key, no committed caches).

## Known resolved bug

`pages/1_Command_Center.py` previously had a `notess` typo (should be `notes`) that would NameError on the simple-interest FD fallback path with a long-tenor warning. Phase 0 extracted valuation into `lib/valuation.py` and fixed the typo there; the fixed path is pinned by `tests/test_fd_valuation.py::test_simple_interest_fallback_formula`.

## GitHub Actions

`.github/workflows/update-holdings.yml` runs daily at 04:30 UTC (manual dispatch also available). Refreshes MF holdings cache and commits back to the repo. Uses `actions/checkout@v5`, Python 3.11, and `actions/setup-python@v6`.
