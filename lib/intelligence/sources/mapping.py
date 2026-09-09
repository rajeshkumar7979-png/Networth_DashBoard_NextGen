# -------------------------------------------------
# Intelligence Data Gateway — portfolio relevance mapping.
#
# Answers: "Does this external record relate to an entity or exposure in the
# user's portfolio?" using EXACT identifier matches only (normalized case) —
# no fuzzy matching, no invented mappings. Outcomes are one of
# "mapped" / "unmapped" / "insufficient".
# -------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MappingResult:
    status: str          # "mapped" | "unmapped" | "insufficient"
    matched: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class PortfolioIndex:
    isins: frozenset = frozenset()
    symbols: frozenset = frozenset()
    scheme_codes: frozenset = frozenset()
    fund_names: frozenset = frozenset()
    instrument_keys: frozenset = frozenset()

    @property
    def is_empty(self) -> bool:
        return not (self.isins or self.symbols or self.scheme_codes or self.fund_names or self.instrument_keys)


def _num_text(value) -> str:
    text = str(value).strip()
    if text.lstrip("0").isdigit():
        text = text.lstrip("0") or "0"
    return text


def build_portfolio_index(register=None, *, mf_valid=None, stocks_valid=None,
                          gold_valid=None, fd_valid=None, amfi_codes=None) -> PortfolioIndex:
    """Collect every exact identifier currently held in the portfolio books.

    register rows (canonical Key/Instrument/Source), mf ISINs + fund names,
    stock/gold symbols, FD account numbers and AMFI scheme codes are unioned.
    """
    isins: set[str] = set()
    symbols: set[str] = set()
    codes: set[str] = set()
    names: set[str] = set()
    keys: set[str] = set()

    if register is not None and not getattr(register, "empty", True):
        keys.update(str(v).strip() for v in register.get("Key", []) if str(v).strip())
        for _, row in register.iterrows():
            source = str(row.get("Source") or "").strip().upper()
            instrument = str(row.get("Instrument") or "").strip()
            if not instrument:
                continue
            if source == "MF":
                isins.add(instrument.upper())
            elif source in ("STOCKS", "GOLD"):
                symbols.add(instrument.upper())

    if mf_valid is not None and not getattr(mf_valid, "empty", True):
        for _, row in mf_valid.iterrows():
            isin = str(row.get("ISIN") or "").strip().upper()
            if isin:
                isins.add(isin)
            fname = str(row.get("Fund Name") or "").strip().upper()
            if fname:
                names.add(fname)

    if stocks_valid is not None and not getattr(stocks_valid, "empty", True):
        for _, row in stocks_valid.iterrows():
            symbol = str(row.get("Symbol") or "").strip().upper()
            if symbol:
                symbols.add(symbol)

    if gold_valid is not None and not getattr(gold_valid, "empty", True):
        for _, row in gold_valid.iterrows():
            symbol = str(row.get("Symbol") or "").strip().upper()
            if symbol:
                symbols.add(symbol)

    if fd_valid is not None and not getattr(fd_valid, "empty", True):
        for _, row in fd_valid.iterrows():
            acct = str(row.get("Account Number") or "").strip()
            if acct:
                keys.add(acct)

    if amfi_codes:
        for isin, code in amfi_codes.items():
            if isin:
                isins.add(str(isin).strip().upper())
            if code is not None:
                codes.add(_num_text(code))

    return PortfolioIndex(
        isins=frozenset(isins),
        symbols=frozenset(symbols),
        scheme_codes=frozenset(codes),
        fund_names=frozenset(names),
        instrument_keys=frozenset(keys),
    )


_IDENTIFIER_KEYS = (
    "isin", "isin_primary", "isin_secondary", "scheme_code",
    "ticker", "symbol", "cik", "instrument_key", "fund_name", "company_name",
    "trade_id",
)


def assess_relevance(record, index: PortfolioIndex) -> MappingResult:
    """Exact-match the identifiers carried by a gateway record vs the index."""
    candidates: set[str] = set()
    entity = str(getattr(record, "entity", "") or "").strip()
    if entity:
        candidates.add(entity.upper())
    payload = dict(getattr(record, "payload", {}) or {})
    for key in _IDENTIFIER_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip().upper()
        if not text:
            continue
        candidates.add(text)

    if not candidates:
        return MappingResult("insufficient", reason="record carries no identifiers")

    matched = set()
    for cand in candidates:
        if cand in index.isins or cand in index.symbols or cand in index.fund_names \
                or cand in index.instrument_keys or _num_text(cand) in index.scheme_codes:
            matched.add(cand)

    if matched:
        return MappingResult("mapped", matched=tuple(sorted(matched)))
    return MappingResult("unmapped", reason="no exact identifier match in portfolio index")