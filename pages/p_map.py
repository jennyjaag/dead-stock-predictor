"""MAP / undercut monitor — who's breaking minimum advertised price (DEMO preview)."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("MAP / undercut monitor",
                  "Spot who's advertising below minimum price or undercutting the market on your lines.",
                  demo=True)

mock = pd.DataFrame([
    {"Product": "Horse Pilot AirVest", "Your MAP": "$825", "Seen at": "$742", "Seller": "discountequestrian.com", "Status": "⚠️ Below MAP"},
    {"Product": "Parlanti Denver Boots", "Your MAP": "$1,190", "Seen at": "$1,190", "Seller": "Oakwood Saddlery", "Status": "✅ OK"},
    {"Product": "Equiline Breeches", "Your MAP": "$395", "Seen at": "$355", "Seller": "tackswap (marketplace)", "Status": "⚠️ Below MAP"},
])
st.dataframe(mock, hide_index=True, use_container_width=True)
st.info("⚠️ Demo only. The live monitor tracks public listings against your MAP and flags breaches automatically.")
