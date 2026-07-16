"""Settings — shop details, currency, filters/thresholds, and buying assumptions."""

import streamlit as st

import cs_lib

cs_lib.page_title("Settings", "Your shop details and the assumptions the tools use. Changes apply as you go.")

st.subheader("Shop")
st.text_input("Shop name", key="shop_name")
st.selectbox("Currency", ["$", "£", "€"], key="currency")

st.divider()
st.subheader("Plan")
st.toggle("EquiSphere Pro (unlocks the Trade-show buy AI)", key="pro_plan")
st.caption("Demo: toggling this simulates the paid Pro plan. Real billing comes later.")

st.divider()
st.subheader("Dead-stock view")
st.caption("Risk, cash, category, brand, action and search filters now live **on the Dead-stock report "
           "itself** (under 🔎 Filter the report).")
st.checkbox("Break down by size / colour (per variant)", key="variant_view",
            help="Needs the two-CSV upload; the master file is product-level.")

st.divider()
st.subheader("Dead-stock accuracy — stop crying wolf")
st.number_input("Grace period for new stock (weeks)", min_value=0, max_value=52, step=1, key="grace_weeks",
                help="A product in stock for fewer than this many weeks hasn't had a fair chance to sell, "
                     "so it's held back as 'too new to judge' — never counted as dead stock. Default 8.")
seasonal_input = st.text_input(
    "Seasonal product types to hold back (comma-separated)",
    value=", ".join(st.session_state.get("seasonal_types", [])),
    help="e.g. Rugs, Fly Control — out-of-season slowness in these types won't be flagged as dead.")
st.session_state["seasonal_types"] = [s.strip() for s in seasonal_input.split(",") if s.strip()]

st.divider()
st.subheader("Buying assumptions — reorder & buy AI")
st.number_input("Supplier lead time (weeks)", min_value=0, max_value=52, step=1, key="lead_time_weeks",
                help="How far ahead to place orders. Shown on the Reorder engine.")

st.caption("Shop name, currency, filters and grace period apply the next time you load data "
           "(re-connect / re-upload). Product **age** for the grace period comes from Shopify (live connect "
           "or the master file); the two-CSV export doesn't include product dates.")

if cs_lib.has_data():
    st.page_link("views/home.py", label="← Back to Home", icon="🏠")
