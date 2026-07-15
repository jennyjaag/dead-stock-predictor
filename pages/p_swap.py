"""Swap network — move already-stuck stock to a shop that wants it (DEMO preview)."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Swap network",
                  "Move already-stuck stock to another shop that wants it — instead of discounting to zero.",
                  demo=True)

st.write("Once shops share sell-through data, ClearShelf can **match your dead stock to shops with demand for it** "
         "— a swap or trade beats a fire-sale. Here's how it will look:")

mock = pd.DataFrame([
    {"Your dead stock": "Tweed Show Jacket 16", "Qty": 6, "Wanted by": "Willow Farm Tack (region 2)", "Suggested swap": "Fly Rugs ×4"},
    {"Your dead stock": "Neon Pink Saddle Pad", "Qty": 20, "Wanted by": "Sunnyside Equestrian (region 1)", "Suggested swap": "Cash offer $180"},
    {"Your dead stock": "Kimblewick Bit 6in", "Qty": 16, "Wanted by": "Oakwood Saddlery (region 3)", "Suggested swap": "Loose-ring snaffles ×8"},
])
st.dataframe(mock, hide_index=True, use_container_width=True)
st.info("⚠️ Demo only. The live network matches your slow movers to shops with real demand, using the shared "
        "(anonymised) sell-through data — no fire-sale needed.")
