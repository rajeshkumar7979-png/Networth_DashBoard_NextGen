# IMPLEMENT_PROGRESS.md — post-audit confirmed-fix run (Networth_DashBoard_NextGen)

**Mode:** autonomous implement run covering the 9 confirmed items. Read-only
forensic audit (previous phase) closed all gates green; this phase makes **only**
objectively-confirmed fixes Illustr. Rules honored throughout:
AGENTS.md §1/§3/§4/§10 (preserve provenance, no invented financial data, no
scope creep), preserve the 7 modified other-feature files + untracked
`INVESTMENT_OS_SPEC.md` (never reset/stash/discard/revert), no commit/push unless
a fix is actually warranted, never weaken/remove tests.

## ETA (booked at start)
- Phase A  re-verify 9 items against source (targeted, no broad re-audit):      6 min
- Phase B  implement any confirmed gap:                                        10 min
- Phase C  gates: pytest / pytest -m smoke / ruff / git diff --check:           6 min
- Phase D  live Selenium: 8 routes × desktop+mobile, nav/context, console/net:  6 min
- Phase E  financial reconciliation + cross-page session contract:              4 min
- Phase F  commit (only if changes) + push + verify + final report:             4 min
**Total ETA = 36 min**, start 0:00.

## Continuous tracker
| at | % | elapsed | remaining | ETA | note |
|----|----|---------|-----------|-----|------|
| 0:00 | 0 | 0:00 | 36 | +0:36 | booked |
| |  |  |  |  | after each phase |

## Phase log (append-only; final row = completion)
- A.0  Targeted source + live re-check per item (below).
