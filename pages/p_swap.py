"""Swap network (#3) — your dead stock is someone else's bestseller. DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Dead-stock swap network",
                  "Your dead stock is someone else's bestseller — different region, different discipline. "
                  "AI matches shop-to-shop and prices the swap, turning frozen cash into moving cash.",
                  demo=True)
cs_lib.problem_note("Instead of discounting dead stock to zero, <b>trade it</b> to a shop that has demand for it. "
                    "Turns frozen cash into moving cash — which makes retailers love you, and gives you their data.")

# Use the shop's REAL dead stock if data is loaded; otherwise a generic sample.
regions = ["North region", "South region", "East region", "coastal discipline hub", "dressage-heavy metro"]
swaps = ["Fly rugs ×4", "Sun shirts ×6", "cash offer", "loose-ring snaffles ×8", "cooler rugs ×3"]
if cs_lib.has_data():
    dead = [x for x in cs_lib.get_r().get("dead", []) if x.get("cash")][:8]
    rows = [{"Your dead stock": x["title"], "Qty": int(x["stock"]),
             "Cash frozen": cs_lib.money(x["cash"]),
             "Wanted by": regions[i % len(regions)],
             "Suggested swap": swaps[i % len(swaps)]} for i, x in enumerate(dead)]
    unlocked = sum(x["cash"] for x in dead)
    st.caption("Matched against your **real** dead stock below (matches are illustrative demo data).")
else:
    rows = [{"Your dead stock": "Tweed Show Jacket 16", "Qty": 6, "Cash frozen": "$330",
             "Wanted by": "North region", "Suggested swap": "Fly rugs ×4"},
            {"Your dead stock": "Neon Pink Saddle Pad", "Qty": 20, "Cash frozen": "$240",
             "Wanted by": "coastal discipline hub", "Suggested swap": "cash offer $180"}]
    unlocked = 570

m = st.columns(3)
m[0].metric("Frozen cash to unlock", cs_lib.money(unlocked) if cs_lib.has_data() else "$570")
m[1].metric("Potential swaps", len(rows))
m[2].metric("Fee per completed swap", "~3%", "you earn on each match", delta_color="off")

st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

cs_lib.how_it_works([
    "Every shop's slow movers and demand are read from the shared (anonymised) sell-through data.",
    "The AI matches your dead SKUs to shops that are **selling that exact line** elsewhere.",
    "It prices the swap — a straight trade, or a trade-plus-cash — so both sides come out ahead.",
    "You clear stock at near-full value instead of marking it down to nothing.",
])
cs_lib.pricing_note("Small fee per completed swap. It's the feature that turns frozen cash into moving cash — "
                    "retailers stay for it, and every swap deepens the data network behind everything else.")
st.info("⚠️ Demo preview — the live network activates once enough shops are connected.")
