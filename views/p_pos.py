"""AI POS / inventory reconciler (#8) — clean the sync mess. The data pipe. DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("AI POS / inventory reconciler",
                  "An agent that reconciles POS, e-commerce and supplier feeds and cleans the mismatches "
                  "automatically. Boring, painful — and it's your data pipe.",
                  demo=True)
cs_lib.problem_note("For the <b>8% drowning in sync problems.</b> When POS, web and supplier don't agree, "
                    "every other number is wrong. Fix this and you own the data feed.")

m = st.columns(3)
m[0].metric("Records reconciled", "4,233")
m[1].metric("Mismatches found", "37")
m[2].metric("Auto-fixed", "31", "6 need review", delta_color="off")

st.markdown("##### Mismatches detected")
mm = pd.DataFrame([
    {"SKU": "HP-AIRVEST-14", "POS": "20", "Web store": "18", "Supplier feed": "20", "Issue": "Web oversold by 2", "Action": "Auto-fixed ✅"},
    {"SKU": "PARL-DENVER-39", "POS": "0", "Web store": "3", "Supplier feed": "0", "Issue": "Web shows phantom stock", "Action": "Auto-fixed ✅"},
    {"SKU": "EQ-BREECH-28", "POS": "5", "Web store": "5", "Supplier feed": "12", "Issue": "Cost price differs", "Action": "Needs review ⚠️"},
    {"SKU": "GIFT-CARD", "POS": "-1", "Web store": "0", "Supplier feed": "—", "Issue": "Negative inventory", "Action": "Flagged ⚠️"},
])
st.dataframe(mm, hide_index=True, use_container_width=True)

if cs_lib.has_data():
    st.caption("On your real data, EquiSphere already surfaces some of these (negative stock, missing costs) "
               "in the dead-stock report's data-quality flags — the reconciler would fix them at the source.")

cs_lib.how_it_works([
    "Connects POS, e-commerce and supplier feeds and compares them continuously.",
    "Flags oversells, phantom stock, cost-price drift, negative inventory, duplicates.",
    "Auto-fixes the safe ones; queues the judgement calls for you.",
    "Result: clean numbers everywhere — and a live, trustworthy data feed for every other tool.",
])
cs_lib.pricing_note("Retailers pay monthly. Strategic wedge — dull to do, painful to lack, and it makes you "
                    "the system of record (which is where the data moat starts).")
st.info("⚠️ Demo preview — mismatches shown are illustrative.")
