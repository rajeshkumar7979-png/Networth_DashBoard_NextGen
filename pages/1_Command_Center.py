"""Command Center — assembled from lib/cc_parts (avoids large single-file push limits)."""
from pathlib import Path

_parts = sorted((Path(__file__).resolve().parents[1] / "lib" / "cc_parts").glob("part*.txt"))
if not _parts:
    import streamlit as st
    st.error("Command Center body missing (lib/cc_parts). Redeploy from GitHub.")
    st.stop()
_code = "".join(p.read_text(encoding="utf-8") for p in _parts)
exec(compile(_code, "Command_Center_assembled.py", "exec"), globals())
