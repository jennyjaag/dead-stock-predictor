"""Showrooming rescue assistant (#7) — capture the in-store shopper, close the sale. DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Showrooming rescue assistant",
                  "For shops losing try-on customers to online: an AI clienteling tool that captures the "
                  "in-store shopper, then follows up so the sale closes with you — not Amazon.",
                  demo=True)
cs_lib.problem_note("Aimed at the <b>6% losing try-on customers to online.</b> They try it on in your shop, "
                    "then buy it cheaper on their phone. This keeps the sale yours.")

m = st.columns(3)
m[0].metric("Shoppers captured (30d)", "48")
m[1].metric("Follow-ups sent", "41")
m[2].metric("Sales recovered", "17", "$4,120 recovered", delta_color="normal")

st.markdown("##### Capture a shopper (preview)")
c1, c2, c3 = st.columns(3)
c1.text_input("Rider name", "Demo — Sarah")
c2.selectbox("Discipline", ["Dressage", "Show jumping", "Eventing", "Hacking"])
c3.text_input("Horse / size notes", "16.2hh · breeches 28 · tall boot 39")
st.button("Save & schedule follow-up (demo)")

st.markdown("##### Follow-up queue")
q = pd.DataFrame([
    {"Rider": "Sarah", "Tried on": "Parlanti Denver Boots", "Status": "Follow-up due today", "Channel": "Email"},
    {"Rider": "James", "Tried on": "Horse Pilot AirVest", "Status": "Sent · opened", "Channel": "SMS"},
    {"Rider": "Priya", "Tried on": "Equiline Breeches", "Status": "Recovered ✅", "Channel": "Email"},
])
st.dataframe(q, hide_index=True, use_container_width=True)

cs_lib.how_it_works([
    "Staff capture the in-store shopper in seconds — rider, horse, discipline, sizes.",
    "The AI drafts a personal follow-up (the exact item, their fit) and schedules it.",
    "If they didn't buy in-store, the follow-up closes the sale with you instead of online.",
    "Every captured shopper also enriches your demand data.",
])
cs_lib.pricing_note("Retailers pay per recovered sale — you only pay when it works.")
st.info("⚠️ Demo preview — the form and queue are illustrative.")
