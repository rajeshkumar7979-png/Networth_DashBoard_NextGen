import streamlit as st
from lib.theme import inject_css

st.set_page_config(
    page_title="Portfolio Intelligence Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()

pg = st.navigation(
    {
        "PORTFOLIO": [
            st.Page("pages/1_Command_Center.py", title="Command Center", icon="📊", default=True),
        ],
        "DECISION": [
            st.Page("pages/2_Deep_Health.py", title="Decision Desk", icon="🧭"),
            st.Page("pages/3_Asset_Detail.py", title="Asset Dossier", icon="🧾"),
        ],
        "INTELLIGENCE": [
            st.Page("pages/4_News.py", title="Intel & News", icon="📰"),
            st.Page("pages/5_MF_Health.py", title="MF Health", icon="🏥"),
        ],
    }
)
pg.run()
