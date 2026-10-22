"""Command Center — decompress lib/cc_parts/*.b64.gz and execute."""
from __future__ import annotations

import base64
import gzip
from pathlib import Path

_parts_dir = Path(__file__).resolve().parents[1] / "lib" / "cc_parts"
_parts = sorted(_parts_dir.glob("part*.b64"))
if not _parts:
    import streamlit as st

    st.error("Command Center body missing (lib/cc_parts). Redeploy from GitHub.")
    st.stop()

_chunks = []
for _p in _parts:
    _b64 = _p.read_text(encoding="utf-8").strip()
    _chunks.append(gzip.decompress(base64.b64decode(_b64)).decode("utf-8"))
_code = "".join(_chunks)
exec(compile(_code, "Command_Center_assembled.py", "exec"), globals())
