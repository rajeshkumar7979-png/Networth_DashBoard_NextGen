import streamlit as st
from lib.theme import inject_css

st.set_page_config(
    page_title="NORTHLINE · Family desk",
    page_icon="▚",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

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
        ],
        "PLANNING": [
            st.Page("pages/2_Deep_Health.py", title="Decision Desk", url_path="decisions"),
        ],
    },
    # The navigation widget itself is hidden: lib/ui/nav.py renders the brand
    # rail (desktop st.sidebar + mobile bottom bar) with state-preserving
    # st.page_link elements. url_paths above feed those page links.
    position="hidden",
)
pg.run()