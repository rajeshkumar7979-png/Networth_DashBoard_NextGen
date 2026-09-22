# Temporary bootstrap while full dossier page is restored from e1840d9 + tape-table patch.
# Streamlit will load this instead of an empty file (which crashes the multipage app).
import streamlit as st

st.set_page_config(page_title="Holdings · restoring", layout="wide")
st.warning(
    "Holdings dossier is being restored after an empty deploy. "
    "Open Command / Funds for live books. Full dossier returns in the next commit."
)
st.caption("If you still see this after a few minutes, hard-refresh the app.")
