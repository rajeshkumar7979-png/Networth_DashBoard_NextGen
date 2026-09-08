"""Portfolio Intelligence foundation.

Layers a provenance-based evidence model over the register/books/snapshot
machinery. Python owns all numbers (lib.intelligence.exposure); AI synthesis is
decision-support only (lib.intelligence.provider / portfolio_brain) and never
invents prices, NAVs, holdings, ownership, returns, transactions, flows,
corporate actions, macro statistics or exposure.
"""

from lib.intelligence.model import (
    Briefing,
    Claim,
    Evidence,
    Fact,
    FactKind,
    INSUFFICIENT_EVIDENCE,
    Interpretation,
    Provenance,
    Recommendation,
    Signal,
    SourceClass,
    SourceType,
)

__all__ = [
    "Briefing",
    "Claim",
    "Evidence",
    "Fact",
    "FactKind",
    "INSUFFICIENT_EVIDENCE",
    "Interpretation",
    "Provenance",
    "Recommendation",
    "Signal",
    "SourceClass",
    "SourceType",
]