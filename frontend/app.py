"""Machine Health Monitor – Streamlit entry point.   Run from project root:  streamlit run frontend\\app.py"""
import streamlit as st

st.set_page_config(page_title="Machine Health Monitor", page_icon="🛠️", layout="wide")

pages = st.navigation([
    st.Page("dashboard.py", title="Dashboard", icon="📊", default=True),
    st.Page("events_page.py", title="Recent Events", icon="🚨"),
])
pages.run()
