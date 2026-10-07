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
# Desktop: inset the main column by the rail and hide the mobile bar, so a
# maximised window does not push tabs off the right edge.
st.markdown(
    """
<style>
@media (min-width: 992px) {
  [data-testid="stSidebar"] {
    position: fixed; top: 0; left: 0; height: 100vh;
    width: 15.5rem !important; z-index: 100;
  }
  [data-testid="stAppViewContainer"] > .main,
  [data-testid="stMain"] {
    margin-left: 15.5rem !important;
    width: calc(100vw - 15.5rem) !important;
    max-width: calc(100vw - 15.5rem) !important;
  }
  .st-key-nb_mobile_bar { display: none !important; }
  .stTabs [data-baseweb="tab-list"] { width: 100% !important; overflow-x: auto !important; }
}
</style>
""",
    unsafe_allow_html=True,
)
# One publisher for every page. Command Center still overwrites these keys
# with its live valuation when that page runs.
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
