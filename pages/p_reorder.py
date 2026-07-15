"""Reorder engine — right quantity + timing so winners don't run out or pile up."""

import streamlit as st

import cs_lib

cs_lib.require_data()
cs_lib.page_title("Reorder engine",
                  "The right quantity and timing to restock your winners — so they never run out, "
                  "and you never over-buy into next season's dead stock.",
                  demo=(st.session_state.get("kind") == "demo"))
cs_lib.render_buyplan(cs_lib.get_r(), reorder_only=True)
