"""Sell-through intelligence — what actually sold, where (DEMO preview, brand-side tool)."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Sell-through intelligence",
                  "For brands: what actually sold through to riders, in which doors and regions — "
                  "not just what shipped from the dock.",
                  demo=True)

st.write("This is the **brand-side** tool. Once enough shops share data, a brand sees real store-level "
         "sell-through for its lines. Preview:")

mock = pd.DataFrame({
    "Region": ["North", "South", "East", "West"],
    "Units sold (12mo)": [420, 310, 180, 260],
    "Sell-through %": [0.78, 0.64, 0.41, 0.71],
}).set_index("Region")
st.bar_chart(mock[["Units sold (12mo)"]], color="#0F6E56", height=300)
st.dataframe(mock, use_container_width=True)
st.info("⚠️ Demo only. In the live product this is powered by the aggregated, anonymised network — "
        "individual shops' raw numbers are never exposed.")
