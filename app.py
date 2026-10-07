import streamlit as st
from lib.theme import inject_css
from lib.book_session import ensure_published_book

st.set_page_config(
    page_title="NORTHLINE · Family desk",
    page_icon="▚",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
# Do not take the sidebar out of flow and do not hide the mobile bar.
# A collapsed rail plus a hidden bar is what left the page with no tabs.
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
