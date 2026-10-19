# Public sample book

This folder is the **only** portfolio book intended for the public repository.

- Holder names are synthetic: Member A / B / C / D
- Account numbers are `SAMPLE-###`
- Fund ISINs and market identifiers are public scheme codes, not personal data
- Amounts are demo figures for app testing

## Real family book (private)

Do **not** commit a real book to this repository.

Put the private workbook path in Streamlit secrets:

```toml
[book]
path = "/path/or/mount/to/private_Networth_Raw_Data.xlsx"
```

Or set environment variable `NORTHLINE_BOOK_PATH`.

The app resolves: private path from secrets/env → `data/Networth_Raw_Data.xlsx` (sample).
