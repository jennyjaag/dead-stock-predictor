"""Trade-show buy AI — what to buy, in what depth, before the show (the buy-plan)."""

import streamlit as st

import cs_lib

cs_lib.require_data()
cs_lib.page_title("Trade-show buy AI",
                  "What to buy, and in what depth, before the show — so dead stock never starts. "
                  "The cause of dead stock, solved upstream.",
                  demo=(st.session_state.get("kind") == "demo"))
cs_lib.require_pro(
    "Trade-show buy AI", "Included in ClearShelf Pro — ~$79/mo",
    ["A ready-to-order buy list with the exact quantity per line, sized to ~4 months of cover",
     "Demand momentum by category — buy ahead of what's heating up, ease off what's cooling",
     "A 'stop buying' list that kills dead stock before the order goes in",
     "Projected sell-through value so you can justify the spend"])
cs_lib.render_buyplan(cs_lib.get_r())
