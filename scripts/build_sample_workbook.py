#!/usr/bin/env python3
"""Build data/Networth_Raw_Data.xlsx from the public sample CSVs (no personal names)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample_book"
OUT = ROOT / "data" / "Networth_Raw_Data.xlsx"


def main() -> int:
    fd = pd.read_csv(SAMPLE / "fd.csv")
    mf = pd.read_csv(SAMPLE / "mf.csv")
    stocks = pd.read_csv(SAMPLE / "stocks.csv")
    for frame, col in ((fd, "Holder Name"), (mf, "Owner"), (stocks, "Owner")):
        if col in frame.columns:
            bad = frame[col].astype(str).str.contains(
                r"khandelwal|sharma|kavita|rajesh", case=False, na=False
            )
            if bad.any():
                raise SystemExit(f"Refusing to publish personal-looking names in {col}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        fd.to_excel(writer, sheet_name="FD", index=False)
        mf.to_excel(writer, sheet_name="MF", index=False)
        stocks.to_excel(writer, sheet_name="Stocks", index=False)
    print(f"Wrote {OUT} from {SAMPLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
