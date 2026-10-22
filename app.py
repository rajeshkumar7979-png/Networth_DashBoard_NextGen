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
# Resolve durable book BEFORE the banner so reboot shows correct mode immediately.
try:
    from lib.private_book import materialize_private_book
    from lib.config import EXCEL_PATH as _EXCEL
    private, src = materialize_private_book()
    if private is not None:
        st.session_state["book_mode"] = (
            "committed" if src in ("sidecar", "committed") else f"private:{src}"
        )
        st.session_state["book_path_display"] = f"{private} ({src})"
    elif not st.session_state.get("book_mode"):
        # Fallback: full committed xlsx on disk
        try:
            if _EXCEL.exists() and _EXCEL.stat().st_size > 20000:
                st.session_state["book_mode"] = "committed"
                st.session_state["book_path_display"] = str(_EXCEL)
                st.session_state["book_private_status"] = (
                    f"committed xlsx ok · {_EXCEL.stat().st_size} bytes"
                )
        except Exception:
            pass
except Exception:
    pass
_mode = st.session_state.get("book_mode") or "unknown"
_priv = st.session_state.get("book_private_status") or ""
_path = st.session_state.get("book_path_display") or ""
if st.session_state.get("cc_uploaded_bytes") or _mode == "upload":
    st.caption(
        "Book: UPLOADED"
        + (f" ({st.session_state.get('cc_uploaded_name')})" if st.session_state.get("cc_uploaded_name") else "")
        + " · session only (lost on reboot). Prefer data/Networth_Raw_Data.xlsx in GitHub for durability."
    )
elif _mode == "committed" or str(_mode).startswith("private"):
    st.caption(
        f"Book: durable ({_mode}) · {_path}"
        + (f" · {_priv}" if _priv else "")
        + ". Survives reboot. Update via data/Networth_Raw_Data.xlsx on GitHub."
    )
else:
    st.caption(
        f"Book: fallback sample · {_path}"
        + ". Replace data/Networth_Raw_Data.xlsx on GitHub with the Cash-bearing workbook."
    )

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
