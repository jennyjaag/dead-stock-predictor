"""Demand radar — which categories/brands are rising or fading in the network (DEMO preview)."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Demand radar",
                  "Which categories and brands are heating up or cooling across the network — "
                  "so you (or your brand) can get ahead of demand.",
                  demo=True)

mock = pd.DataFrame({
    "Category": ["Air vests", "Show coats", "Fly rugs", "Tailcoats", "Sun shirts"],
    "Trend vs last year": [0.34, 0.12, 0.28, -0.22, 0.41],
}).set_index("Category")
st.bar_chart(mock, color="#0F6E56", height=320)
st.caption("Positive = demand rising vs last year; negative = fading.")
st.info("⚠️ Demo only. The live radar reads the aggregated network sell-through to surface early trends by region.")
