"""Trade-show buy AI — what to buy, in what depth, before the show (the buy-plan)."""

import streamlit as st

import cs_lib

cs_lib.require_data()
cs_lib.page_title("Trade-show buy AI",
                  "What to buy, and in what depth, before the show — so dead stock never starts. "
                  "The cause of dead stock, solved upstream.",
                  demo=(st.session_state.get("kind") == "demo"))
cs_lib.render_buyplan(cs_lib.get_r())
