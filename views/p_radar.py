"""AI demand radar for the sport (#10) — predict what's about to move. DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("AI demand radar for the sport",
                  "Reads competition entries, discipline growth and community chatter to predict what's about "
                  "to move — before it hits shelves. The forward-looking version of the dead-stock report.",
                  demo=True)
cs_lib.problem_note("So retailers <b>stop buying last season's winner.</b> The dead-stock report tells you what's "
                    "already stuck; the radar tells you what's about to sell, so you buy ahead of it.")

m = st.columns(3)
m[0].metric("Signals tracked", "5")
m[1].metric("Rising categories", "3")
m[2].metric("Fading categories", "1")

st.markdown("##### What's heating up vs fading (vs last year)")
trend = pd.DataFrame({"Category": ["Air vests", "Sun shirts", "Fly rugs", "Show coats", "Tailcoats"],
                      "Trend vs last year": [0.34, 0.41, 0.28, 0.12, -0.22]}).set_index("Category")
st.bar_chart(trend, color="#0F6E56", height=300)
st.caption("Positive = demand rising; negative = fading.")

st.markdown("##### Signals behind the call")
sig = pd.DataFrame([
    {"Signal": "Competition entries", "Reading": "Eventing entries +18% YoY", "Points to": "Air vests, body protectors"},
    {"Signal": "Discipline growth", "Reading": "Adult dressage clinics up", "Points to": "Show coats, sun shirts"},
    {"Signal": "Community chatter", "Reading": "Heat-wave prep threads spiking", "Points to": "Fly rugs, cooling gear"},
    {"Signal": "Weather / season", "Reading": "Warm spring forecast", "Points to": "Down-weight rug buys"},
])
st.dataframe(sig, hide_index=True, use_container_width=True)

cs_lib.how_it_works([
    "Ingests competition entry data, discipline participation trends, weather and community chatter.",
    "Cross-references with what's actually selling across the network.",
    "Surfaces categories about to rise (buy ahead) and fade (ease off) — by region.",
    "Turns buying from 'what won last season' into 'what's winning next season'.",
])
cs_lib.pricing_note("Retailers and brands both pay — retailers to buy ahead, brands to plan production.")
st.info("⚠️ Demo preview — signals and trends are illustrative.")
