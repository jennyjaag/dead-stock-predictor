"""MAP / direct-undercut monitor (#5) — brands selling direct below your price. DEMO preview."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("MAP / direct-undercut monitor",
                  "AI crawls every marketplace and brand site for the SKUs you carry, and flags when the "
                  "brand is selling direct below the price they expect you to hold.",
                  demo=True)
cs_lib.problem_note("Aims straight at the <b>14% of retailers who say “brands are undercutting us.”</b> "
                    "You can't defend a price you don't know is being broken.")

# use real brands/products if loaded
if cs_lib.has_data():
    top = [x for x in cs_lib.get_r().get("at_risk", []) if x.get("vendor")][:5]
    seed = [(x["title"], x["vendor"]) for x in top] or [("Horse Pilot AirVest", "Horse Pilot")]
else:
    seed = [("Horse Pilot AirVest", "Horse Pilot"), ("Parlanti Denver Boots", "Parlanti"),
            ("Equiline Breeches", "Equiline")]

import_prices = [(825, 742, "discountequestrian.com", "⚠️ Below MAP"),
                 (1190, 1190, "Oakwood Saddlery", "✅ OK"),
                 (395, 355, "brand.com (direct)", "⚠️ Brand undercut"),
                 (299, 260, "marketplace listing", "⚠️ Below MAP"),
                 (149, 149, "your shop", "✅ OK")]
rows = [{"Product": t, "Brand": b, "Your price": cs_lib.money(p[0]),
         "Seen at": cs_lib.money(p[1]), "Seller": p[2], "Status": p[3]}
        for (t, b), p in zip(seed, import_prices)]
breaches = sum(1 for r in rows if "⚠️" in r["Status"])

m = st.columns(3)
m[0].metric("SKUs monitored", "1,240")
m[1].metric("Price breaches found", breaches)
m[2].metric("Marketplaces crawled", "8")
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

cs_lib.how_it_works([
    "AI crawls marketplaces + brand DTC sites for the exact SKUs you stock.",
    "Compares live prices against MAP / the wholesale-implied retail you should be holding.",
    "Flags breaches — a competitor below MAP, or the brand itself undercutting you direct.",
    "Gives you the receipts to push back on the brand, or match/deprioritise that line.",
])
cs_lib.pricing_note("Both sides pay — retailers for defense, brands for policing their own channel. "
                    "Retailer wedge + brand upsell in one crawl.")
st.info("⚠️ Demo preview — prices shown are illustrative.")
