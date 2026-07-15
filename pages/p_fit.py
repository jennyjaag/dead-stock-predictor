"""AI sizing / fit advisor (#9) — cut returns and wrong-buys (dead stock in disguise). DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("AI sizing / fit advisor",
                  "Boots, breeches and blankets have brutal return rates and brand-specific quirks. "
                  "An AI fit model on your site cuts returns and wrong-buys — which is dead stock in disguise.",
                  demo=True)
cs_lib.problem_note("Returns and wrong-size buys are <b>dead stock in disguise</b> — the unit comes back, "
                    "often unsellable. Getting the size right the first time protects both margin and stock.")

m = st.columns(3)
m[0].metric("Fit questions answered (30d)", "260")
m[1].metric("Return rate", "12%", "−9 pts with fit advice", delta_color="normal")
m[2].metric("Wrong-size buys avoided", "34")

st.markdown("##### Fit advisor (preview)")
c1, c2, c3 = st.columns(3)
brand = c1.selectbox("Brand", ["Pikeur", "Parlanti", "Horse Pilot", "Equiline"])
usual = c2.text_input("Your usual size", "EU 40")
height = c3.text_input("Height / build", "5'7\" · athletic")
quirk = {"Pikeur": "runs small — size up", "Parlanti": "narrow calf — check width",
         "Horse Pilot": "true to size", "Equiline": "long in the leg"}[brand]
st.success("Recommended: **{}** — note: {} ({} runs {}).".format(
    "EU 41" if "small" in quirk else usual, quirk, brand, quirk.split(" —")[0]))

st.markdown("##### Brand fit quirks the model knows")
q = pd.DataFrame([
    {"Brand": "Pikeur", "Quirk": "Runs small", "Advice": "Size up one"},
    {"Brand": "Parlanti", "Quirk": "Narrow calf", "Advice": "Check calf width first"},
    {"Brand": "Equiline", "Quirk": "Long in the leg", "Advice": "Regular ≈ others' long"},
])
st.dataframe(q, hide_index=True, use_container_width=True)

cs_lib.how_it_works([
    "A fit model learns each brand's quirks (Pikeur runs small, Parlanti narrow calf, …).",
    "On your site, the shopper answers a couple of questions and gets the right size.",
    "Fewer wrong-size orders → fewer returns → less unsellable stock coming back.",
    "Return + fit data feeds back to sharpen buying (stop over-ordering the sizes that bounce).",
])
cs_lib.pricing_note("Retailers / DTC pay per conversion — you pay when it turns a browser into a right-size buyer.")
st.info("⚠️ Demo preview — recommendations are illustrative.")
