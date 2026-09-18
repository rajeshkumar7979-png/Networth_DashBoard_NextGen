# AUDIT_REPORT.md — Networth_DashBoard_NextGen forensic audit

**Scope:** read-only forensic audit — full source inspection, live-route probing
(all 8 routes × both live instances), Selenium DOM/console/mobile pass, network-on-
load check, financial vocabulary + provenance scan, duplication scan, test + lint
gates. **No code, test, config, or data changes.** Nothing committed or pushed.
Working tree preserved byte-for-byte from turn start.

**Audited at:** HEAD `b893b05` (`Complete AI provider stack: provider abstraction,
llama-3.3 default, clean discontinued-model 404s`), `data/` clean, two live
instances both serving this repo (`:8501` pid 11720, `:8512` pid 44424 — both
`streamlit run app.py`, both `_stcore/health = ok`).

---

## 1. Findings Summary

| Severity | Count | Notes |
|---|---|---|
| **P0** | 0 | No blocking defects. |
| **P1** | 0 | No financial-correctness, provenance, or page-nav gaps. |
| **P2** | 1 | Non-committed working tree (feature-in-progress files + `INVESTMENT_OS_SPEC.md` untracked) — see §9. Not an app defect; intentional per AGENTS.md. |
| **P3** | 1 | Two `smoke`-marked tests are network/AppTest-gated and deselected in the default suite by design; pass on explicit `-m smoke`. |

---

## 2. Route & Runtime Matrix (live, read-only)

Both instances (`127.0.0.1:8501` and `127.0.0.1:8512`) serve the **same** committed
app. All 8 routes + root + health return **HTTP 200** on both:

| Route | 8501 | 8512 | Route | 8501 | 8512 |
|---|---|---|---|---|---|
| `/` (Command Center) | 200 | 200 | `/intelligence` | 200 | 200 |
| `/holdings` | 200 | 200 | `/pulse` | 200 | 200 |
| `/funds` | 200 | 200 | `/outlook` | 200 | 200 |
| `.../decisions` | 200 | 200 | `/desk` | 200 | 200 |
| `/_stcore/health` | ok | ok | — | — | — |

Legend: `/holdings` = `url_path="holdings"` (page 3), `/funds` = `url_path="funds"`
(page 5), `/intelligence` = page 6, `/pulse` = page 4, `/outlook` = page 7,
`/decisions` = page 2, `/desk` = page 8; filename aliases (`/1_Command_Center`,
`/2_Deep_Health`, `/3_Asset_Detail`, `/4_News`, `/5_MF_Health`, `/6_Intelligence`,
`/7_Outlook`, `/8_Desk`) all 200 too.

**Selenium (Chrome headless):** every route loaded on desktop (1440×900) and mobile
(390×844); page titles render; body text present on all. The only console noise on
desktop was Streamlit's own `_stcore/health` + `_stcore/host-config` 404s (internal
Streamlit sub-resources, not app code; app renders fine). **No app-level console
errors, no st.exception widgets, no route 404s.** Mobile viewport served the same
app with no blocking errors.

---

## 3. Network-on-Load Check

- Opening any page makes **no** gateway/network data calls. Intelligence Gateway
  fetches only on explicit on-demand entry points (Run AI research button,
  `refresh research evidence`); page load reads caches/session state only.
- Confirmed via source scan: no `requests`/`urllib`/`httpio`/`openai` call at page
  import or render top-level; gateway calls live behind `functools`-cached,
  button-gated `_run_*` handlers in the Command Center.
- No secrets in source: keys read from `st.secrets`/env at runtime only
  (`provider_is_configured`, runtime-gated). No API key literal anywhere in the
  repo.

---

## 4. Financial Vocabulary & Provenance Scan

Every "FORBIDDEN vocabulary" hit from the scan is a **permitted/required** occurrence:

- `NOT a cash-flow measurement; transaction history unavailable.` —
  the mandated `NOT_A_CASHFLOW_LABEL` (AGENTS.md / INVESTMENT_OS_SPEC) applied to
  invested-basis change. Correct.
- `Principal (INR, at deposit FX)` — actual workbook column name (FD/FCNR sheet).
- `"maturity date … before deposit date"` / `"simple interest from deposit date"` —
  FD integrity warnings / valuation fallback prose, driven by workbook IDs.
  **No** page labels invested-basis change as deposit/withdrawal/SIP/redemption/
  XIRR/cash flow. Zero invented transaction history.
- Conclusions carry provenance: only facts/evidence as inputs; findings cite
  evidence ids; missing → `INSUFFICIENT_EVIDENCE`, never fabricated.
- No "recompute" of canonical financial calculations in pages — Command Center
  imports and delegates to `lib/ledger.net_worth()`, `lib/valuation`,
  `lib/{gold,scoring,drivers}`. The 3 page-level `net_worth=`/`class_*=` lines are
  snapshot-row pass-throughs of lib-computed values inside `_build_history_row()`
  (line 1191–1210), not redefinition.

---

## 5. Duplication & Data Provenance

- No duplicated module: single canonical implementations in `lib/`
  (`valuation.py`, `gold.py`, `scoring.py`, `drivers.py`, `ledger.py`,
  `snapshot.py`, `register.py`, `intelligence/`). Pages import and delegate.
- Data provenance: workbook (`data/Networth_Raw_Data.xlsx`) is the sole source;
  caches (`history.csv`, NAV/holdings caches) are derived. `data/` remains clean
  (no churn from tests — `git status` shows no data modifications after full run).
- `INVESTMENT_OS_SPEC.md` is untracked and left untouched (never modified or
  committed, in accordance with AGENTS.md).

---

## 6. Test, Lint, Hygiene Gates

| Gate | Result |
|---|---|
| `pytest` (default, network-free) | **480 passed, 2 deselected** (smoke) |
| `pytest -m smoke` | **2 passed** (AppTest multipage) |
| `ruff check .` | clean (0 errors) |
| `git diff --check` | clean |
| `git status --short` | unchanged from turn start: 7 modified other-feature files + `?? INVESTMENT_OS_SPEC.md`; **`data/` clean** |

| Test | Result |
|---|---|
| `tests/frozen_baseline.py` | FROZEN_TOTALS / FROZEN_BOOKS intact, register↔Command-Center reconcile within ₹1 |
| `tests/test_drivers.py` | 23-FD rounding bound, P&L decomposition identity, invested-basis rule |
| `tests/test_fcnr_attribution.py` | FCNR/INR FD attribution identity ⇒ within ₹1 |
| `tests/test_fd_valuation.py` | simple-interest fallback formula pinned |
| `tests/test_ledger.py` | net worth semantics pinned |
| `tests/test_live_research.py` / `test_macro_cascade.py` | live + macro cascade evidence grounding, hermetic |
| `tests/test_register.py` | non-unique key collision STOP    |
| `tests/test_page_smoke.py` | multipage navigation smoke |
| `tests/test_intel_research.py` / `test_intel_signals.py` | vocabulary + cash-flow-label prohibitions asserted |

---

## 7. Session-State / Cross-Page Contract

Pages communicate via `st.session_state` keys written by Command Center and read by
consumer pages (e.g. `mf_holdings_for_health`, `cc_equity_pct`, `cc_intel_briefing`,
`cc_live_*`, portfolio register). Selenium DOM pass confirms Command Center renders
the full register/nav on first load; consumer pages render data when reached in
`st.Page` multipage flow)Skip to the desk page directly.

---

## 8. Findings Detail

### P2-1 — Uncommitted working tree (informational, not a defect)
7 other-feature source files are modified vs HEAD (`lib/intelligence/live/*`,
`lib/intelligence/sources/macro_cascade.py`, `pages/1_Command_Center.py`,
`tests/test_live_research.py`, `tests/test_macro_cascade.py`), all carry tests that
pass, and `INVESTMENT_OS_SPEC.md` is untracked. This matches the standing AGENTS.md
workflow (spec untracked; no commit of working-tree feature). **No action required.**

### P3-1 — Smoke suite network-gated
Two tests are `@pytest.mark.smoke` (network-backed AppTest) and deselected in the
default offline suite by design (`addopts = -m "not smoke"`). Run explicitly:
`pytest -m smoke` → 2 passed. Documented limitation, not a defect.

---

## 9. Conclusion

The application is **healthy across all 8 routes on both live instances**:
- All routes return 200; health ok; no st.exception widgets; no app-level console
  errors; mobile renders.
- No page-load network calls; gateway strictly on-demand; no secrets in source.
- Financial vocabulary compliant — invested-basis change never labeled as a cash
  flow/SIP/withdrawal/redemption/deposit; no invented transaction history.
- All 8 committed page files present and served; no missing routes.
- pytest (480/2), ruff, diff-check, data-hygiene all green.

**Verdict: NO P0/P1 findings. No code, test, config, or data was modified.
Working tree preserved. Ready to continue (no commit/push made — per audit brief).**
