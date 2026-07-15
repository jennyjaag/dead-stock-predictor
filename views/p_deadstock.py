"""Dead-stock report — what's stuck right now."""

import streamlit as st

import cs_lib

cs_lib.require_data()
cs_lib.page_title("Dead-stock report",
                  "What's stuck right now — ranked by risk, with the cash you'd free by acting.",
                  demo=(st.session_state.get("kind") == "demo"))
cs_lib.render_deadstock(cs_lib.get_r())
