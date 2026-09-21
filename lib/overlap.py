# -------------------------------------------------
# Look-through overlap. Pure. No network. No Streamlit.
#
# Pairwise overlap is the Morningstar-style sum of min(weight_a, weight_b)
# over common equity holdings (percent of each fund's disclosed book).
# Family look-through multiplies those weights by the family's rupees in
# each fund. Nothing here is an order: numbers and exposure only.
# -------------------------------------------------
from __future__ import annotations

import re
from collections import defaultdict

CONCENTRATION_THRESHOLD_PCT = 5.0  # of the MF book, not of total assets
OVERLAP_METHOD = (
    "Pairwise overlap = Σ min(w_fundA, w_fundB) over common equity ISINs "
    "(or cleaned names when ISIN is missing). Weights are the fund's "
    "disclosed portfolio weights, not the family's rupee mix."
)
LOOKTHROUGH_METHOD = (
    "Family exposure to a stock = Σ (fund current value × disclosed weight). "
    "Funds with no disclosure are excluded from the numerator and kept in "
    "the MF-book denominator as unique (zero overlapped rupees)."
)
DIRECT_REGULAR_NOTE = (
    "Direct and Regular of the same scheme in the same family book is a "
    "cost fact (Regular carries a distributor load). Not an order to merge."
)


def _finite(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def holding_key(isin=None, name=None):
    """Exact identity: ISIN wins. Name is a compact fallback, never fuzzy."""
    code = str(isin or "").strip().upper()
    if code and code not in {"-", "NA", "N/A", "NONE", "NAN"}:
        return "ISIN:" + code
    compact = re.sub(r"[^A-Z0-9]", "", str(name or "").upper())
    return "NAME:" + compact if compact else None


def pairwise_overlap_pct(weights_a, weights_b):
    """Sum of min(w_a, w_b) over keys present in both. None if either is empty."""
    if not weights_a or not weights_b:
        return None
    common = set(weights_a) & set(weights_b)
    if not common:
        return 0.0
    total = 0.0
    for key in common:
        a = _finite(weights_a.get(key))
        b = _finite(weights_b.get(key))
        if a is None or b is None:
            continue
        total += min(a, b)
    return float(total)


def pairwise_matrix(fund_weights):
    """Ordered list of (fund_a, fund_b, overlap_pct) for a < b.

    fund_weights: dict[fund_name, dict[holding_key, weight_pct]]
    Funds with no disclosed weights are omitted, not zero-filled.
    """
    names = [n for n, w in fund_weights.items() if w]
    names.sort()
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pct = pairwise_overlap_pct(fund_weights[a], fund_weights[b])
            if pct is None:
                continue
            rows.append((a, b, pct))
    return rows


def family_look_through(stock_exposure, total_mf_value):
    """Roll disclosed equity up to family rupees.

    stock_exposure: key -> iterable of (fund_name, weight_pct, fund_value, display_name)
    Returns a list of dicts sorted by exposure descending. Empty when the
    book or the disclosures are missing — never a row of zeros.
    """
    total = _finite(total_mf_value)
    if not stock_exposure or total is None or total <= 0:
        return []
    rows = []
    for key, apps in stock_exposure.items():
        if not apps:
            continue
        funds = sorted({str(a[0]) for a in apps if a and a[0]})
        exposure = 0.0
        display = None
        best_w = -1.0
        for app in apps:
            if not app or len(app) < 3:
                continue
            weight, fund_value = app[1], app[2]
            name = app[3] if len(app) > 3 else None
            w = _finite(weight)
            fv = _finite(fund_value)
            if w is None or fv is None or w <= 0 or fv <= 0:
                continue
            exposure += fv * (w / 100.0)
            if w > best_w and name:
                best_w = w
                display = name
        if exposure <= 0:
            continue
        rows.append({
            "key": key,
            "name": display or key,
            "n_funds": len(funds),
            "funds": tuple(funds),
            "exposure_inr": exposure,
            "pct_of_mf": exposure / total * 100.0,
        })
    rows.sort(key=lambda r: (-r["exposure_inr"], r["name"]))
    return rows


def concentration_flags(look_through_rows, threshold_pct=CONCENTRATION_THRESHOLD_PCT):
    """Rows whose family MF-book weight exceeds the threshold. Fact, not advice."""
    cut = _finite(threshold_pct)
    if cut is None:
        cut = CONCENTRATION_THRESHOLD_PCT
    return [r for r in look_through_rows if (r.get("pct_of_mf") or 0) >= cut]


def scheme_stem(name):
    """Strip Direct/Regular/Growth/Plan/Option so two share-classes can match."""
    s = str(name or "")
    s = re.sub(r"[-–]\s*(Direct|Regular).*", "", s, flags=re.I)
    s = re.sub(r"\b(Direct|Regular|Growth|Plan|Option)\b", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" -").lower()


def _share_class(name):
    low = str(name or "").lower()
    if re.search(r"\bregular\b", low):
        return "regular"
    if re.search(r"\bdirect\b", low):
        return "direct"
    return None


def direct_regular_pairs(fund_names):
    """(stem, direct_names, regular_names) where the family holds both classes."""
    groups = defaultdict(lambda: {"direct": [], "regular": []})
    seen = set()
    for raw in fund_names or []:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        klass = _share_class(name)
        if klass is None:
            continue
        groups[scheme_stem(name)][klass].append(name)
    pairs = []
    for stem, bucket in sorted(groups.items()):
        if bucket["direct"] and bucket["regular"]:
            pairs.append((stem, tuple(bucket["direct"]), tuple(bucket["regular"])))
    return pairs
