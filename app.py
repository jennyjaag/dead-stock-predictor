"""
EquiSphere — dead-stock intelligence for independent tack shops.

Entry point: sets the theme, shared state and the grouped sidebar navigation.
Each tool lives in its own file under views/ ; all the analysis is unchanged
(shopify_join / master_load / buy_plan_view), just organised into pages.

Launch:  python3 -m streamlit run app.py
(First time only:  pip3 install -r requirements.txt )
"""

import streamlit as st

import cs_lib

st.set_page_config(page_title="EquiSphere", page_icon="🐴", layout="wide")

cs_lib.init_state()
cs_lib.inject_css()
cs_lib.require_login()      # gate the app behind a login when logins are configured
cs_lib.sidebar_brand()

# Grouped navigation: each dict key is a collapsible section header in the sidebar.
pages = {
    " ": [
        st.Page("views/home.py", title="Home", icon="🏠", default=True),
        st.Page("views/messages.py", title="Messages", icon="💬"),
    ],
    "Dead stock": [
        st.Page("views/p_deadstock.py", title="Dead-stock report", icon="📉"),
        st.Page("views/p_buyai.py", title="Trade-show buy AI", icon="🛒"),
        st.Page("views/p_reorder.py", title="Reorder engine", icon="🔁"),
        st.Page("views/p_swap.py", title="Swap network", icon="🔄"),
    ],
    "Retail tools": [
        st.Page("views/p_showrooming.py", title="Showrooming rescue", icon="🛍️"),
        st.Page("views/p_pos.py", title="POS / inventory reconciler", icon="🔧"),
        st.Page("views/p_fit.py", title="Sizing / fit advisor", icon="📏"),
    ],
    "Brands": [
        st.Page("views/p_sellthrough.py", title="Sell-through intelligence", icon="📊"),
        st.Page("views/p_map.py", title="MAP / undercut monitor", icon="🛡️"),
        st.Page("views/p_radar.py", title="Demand radar", icon="📡"),
    ],
    "Settings": [
        st.Page("views/settings.py", title="Settings", icon="⚙️"),
    ],
}

st.navigation(pages).run()
