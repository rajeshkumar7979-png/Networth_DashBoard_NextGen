import streamlit as st
from lib.theme import inject_css
from lib.book_session import ensure_published_book
from lib.deploy_meta import render_build_footer

st.set_page_config(
    page_title="NORTHLINE · Family desk",
    page_icon="▚",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
st.markdown(
    """
<style>
[data-testid="stSidebar"] {
  display: block !important;
  visibility: visible !important;
  transform: none !important;
  min-width: 16rem !important;
}
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] {
  display: none !important;
}
[data-testid="stDataFrame"] { width: 100% !important; }
.stTabs [data-baseweb="tab-list"] {
  width: 100% !important;
  overflow-x: auto !important;
}
</style>
""",
    unsafe_allow_html=True,
)
ensure_published_book()
try:
    from lib.private_book import materialize_private_book
    materialize_private_book()  # sets book_private_status even if none
except Exception:
    pass
_mode = st.session_state.get("book_mode") or "unknown"
_priv = st.session_state.get("book_private_status") or ""
if st.session_state.get("cc_uploaded_bytes") or _mode == "upload":
    st.caption(
        "Book mode: UPLOADED workbook"
        + (f" ({st.session_state.get('cc_uploaded_name')})" if st.session_state.get("cc_uploaded_name") else "")
        + " · temporary until reboot. Set secrets for permanent book."
    )
elif str(_mode).startswith("private"):
    st.caption(
        "Book mode: PRIVATE durable book"
        + (f" · {st.session_state.get('book_path_display')}" if st.session_state.get("book_path_display") else "")
        + " · survives reboot."
    )
elif _mode == "sample":
    st.warning(
        "Book mode: PUBLIC SAMPLE — cash and real holdings are missing. "
        "Upload once on Desk **or** set Streamlit secrets `[book] xlsx_b64 = \"...\"` "
        "with your real Excel (the one that has the Cash in Hand sheet). "
        + (f"Private status: {_priv}" if _priv else "Private status: not configured.")
    )
else:
    st.caption(f"Book mode: {_mode}" + (f" · {_priv}" if _priv else ""))

pg = st.navigation(
    {
        "BOOKS": [
            st.Page("pages/1_Command_Center.py", title="Command Center", url_path="command", default=True),
            st.Page("pages/7_Outlook.py", title="Outlook", url_path="outlook"),
            st.Page("pages/3_Asset_Detail.py", title="Holdings", url_path="holdings"),
            st.Page("pages/5_MF_Health.py", title="Funds", url_path="funds"),
            st.Page("pages/8_Desk.py", title="Desk", url_path="desk"),
        ],
        "INTELLIGENCE": [
            st.Page("pages/6_Intelligence.py", title="Intelligence", url_path="intelligence"),
            st.Page("pages/4_News.py", title="Pulse", url_path="pulse"),
            st.Page("pages/9_Asset_Intelligence.py",
                    title="Asset Intelligence", url_path="asset-intelligence"),
        ],
        "PLANNING": [
            st.Page("pages/2_Deep_Health.py", title="Decision Desk", url_path="decisions"),
        ],
    },
    position="hidden",
)
pg.run()
render_build_footer(st)
