"""Sell-through intelligence for brands (#6) — where the real money is. DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Sell-through intelligence (for brands)",
                  "The flip side of the retailer tools: brands pay to see what actually sold in stores — "
                  "by region, versus competitors — built entirely on the data the retailer tools collect.",
                  demo=True)
cs_lib.problem_note("A brand goes <b>blind the moment product leaves the dock.</b> They know what they shipped "
                    "in, never what sold through. This is where the real money is.")

m = st.columns(4)
m[0].metric("Doors reporting", "212")
m[1].metric("Your sell-through", "68%")
m[2].metric("Category average", "57%", "+11 pts vs field", delta_color="normal")
m[3].metric("Regions covered", "6")

st.markdown("##### Your sell-through by region")
region = pd.DataFrame({"Region": ["North", "South", "East", "West", "Central", "Coast"],
                       "Units sold (12mo)": [420, 310, 180, 260, 340, 150]}).set_index("Region")
st.bar_chart(region, color="#0F6E56", height=300)

st.markdown("##### You vs the category (sell-through %)")
vs = pd.DataFrame({"Brand": ["You", "Competitor A", "Competitor B", "Competitor C"],
                   "Sell-through %": [0.68, 0.61, 0.55, 0.49]})
st.dataframe(vs, hide_index=True, use_container_width=True)

cs_lib.how_it_works([
    "Aggregates real store-level sell-through from the connected retailer network.",
    "Slices it by region, discipline and time — and benchmarks you against the category.",
    "Shows which doors are moving your product and which are sitting on it.",
    "Strict privacy: only aggregated signal is shown — no individual shop's raw numbers.",
])
cs_lib.pricing_note("Brands pay $$$ — the highest-value tier. Funded by the data the retailer tools (#1–#4) "
                    "collect, which is why the retailer side is priced for adoption, not revenue.")
st.info("⚠️ Demo preview — figures are illustrative and would come from the live network.")
