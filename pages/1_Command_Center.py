"""Command Center — local assembled body (no network bootstrap)."""
from __future__ import annotations

import base64
import gzip
from pathlib import Path

import streamlit as st

_parts_dir = Path(__file__).resolve().parents[1] / "lib" / "cc_parts"
_parts = sorted(_parts_dir.glob("body_*.b64"))
if len(_parts) < 1:
    st.error("Command Center body missing (lib/cc_parts/body_*.b64).")
    st.stop()

try:
    _b64 = "".join(p.read_text(encoding="utf-8").strip() for p in _parts)
    _code = gzip.decompress(base64.b64decode(_b64)).decode("utf-8")
except Exception as exc:
    st.error("Command Center body failed to decompress.")
    st.exception(exc)
    st.stop()

exec(compile(_code, "Command_Center_body.py", "exec"), globals())
