"""Settings — shop details, currency, filters/thresholds, and buying assumptions."""

import streamlit as st

import cs_lib

cs_lib.page_title("Settings", "Your shop details and the assumptions the tools use. Changes apply as you go.")

st.subheader("Shop")
st.text_input("Shop name", key="shop_name")
st.selectbox("Currency", ["$", "£", "€"], key="currency")

st.divider()
st.subheader("Plan")
st.toggle("ClearShelf Pro (unlocks the Trade-show buy AI)", key="pro_plan")
st.caption("Demo: toggling this simulates the paid Pro plan. Real billing comes later.")

st.divider()
st.subheader("Filters — dead-stock report")
st.caption("Raise these to shrink the report to just the items worth acting on today.")
st.slider("Only show risk ≥", 0, 100, step=5, key="min_risk")
st.number_input("Only show cash tied up ≥ ({})".format(st.session_state["currency"]),
                min_value=0, step=50, key="min_cash")
st.checkbox("Break down by size / colour (per variant)", key="variant_view",
            help="Needs the two-CSV upload; the master file is product-level.")

st.divider()
st.subheader("Buying assumptions — reorder & buy AI")
st.number_input("Supplier lead time (weeks)", min_value=0, max_value=52, step=1, key="lead_time_weeks",
                help="How far ahead to place orders. Shown on the Reorder engine.")
st.number_input("New-arrival grace period (days)", min_value=0, max_value=365, step=15, key="grace_days",
                help="A product added within this many days with no sales is 'too early to tell', not dead.")

st.caption("Shop name, currency and filters apply immediately. The grace period applies the next time you "
           "load data (Home → Load different data, then re-open your file).")

if cs_lib.has_data():
    st.page_link("pages/home.py", label="← Back to Home", icon="🏠")
