"""
ClearShelf — dead-stock intelligence for independent tack shops.

Entry point: sets the theme, shared state and the grouped sidebar navigation.
Each tool lives in its own file under pages/ ; all the analysis is unchanged
(shopify_join / master_load / buy_plan_view), just organised into pages.

Launch:  python3 -m streamlit run app.py
(First time only:  pip3 install -r requirements.txt )
"""

import streamlit as st

import cs_lib

st.set_page_config(page_title="ClearShelf", page_icon="🐴", layout="wide")

cs_lib.init_state()
cs_lib.inject_css()
cs_lib.sidebar_brand()

# Grouped navigation: each dict key is a collapsible section header in the sidebar.
pages = {
    " ": [
        st.Page("pages/home.py", title="Home", icon="🏠", default=True),
        st.Page("pages/messages.py", title="Messages", icon="💬"),
    ],
    "Dead stock": [
        st.Page("pages/p_deadstock.py", title="Dead-stock report", icon="📉"),
        st.Page("pages/p_buyai.py", title="Trade-show buy AI", icon="🛒"),
        st.Page("pages/p_reorder.py", title="Reorder engine", icon="🔁"),
        st.Page("pages/p_swap.py", title="Swap network", icon="🔄"),
    ],
    "Retail tools": [
        st.Page("pages/p_showrooming.py", title="Showrooming rescue", icon="🛍️"),
        st.Page("pages/p_pos.py", title="POS / inventory reconciler", icon="🔧"),
        st.Page("pages/p_fit.py", title="Sizing / fit advisor", icon="📏"),
    ],
    "Brands": [
        st.Page("pages/p_sellthrough.py", title="Sell-through intelligence", icon="📊"),
        st.Page("pages/p_map.py", title="MAP / undercut monitor", icon="🛡️"),
        st.Page("pages/p_radar.py", title="Demand radar", icon="📡"),
    ],
    "Settings": [
        st.Page("pages/settings.py", title="Settings", icon="⚙️"),
    ],
}

st.navigation(pages).run()
