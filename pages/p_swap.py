"""Swap network (#3) — matches YOUR dead stock to partner shops that sell it. DEMO preview.

The match is real: it reads your loaded shop's dead-stock list and looks for partner
shops whose brands/categories mean they'd actually want it. Partner shops are
simulated (there's no live network yet); the logic is what the real thing runs.
"""

import streamlit as st

import cs_lib

cs_lib.page_title("Dead-stock swap network",
                  "Your dead stock is someone else's bestseller — different state, different discipline. "
                  "ClearShelf matches shop-to-shop and prices the swap.",
                  demo=True)
cs_lib.problem_note("Instead of discounting dead stock to zero, <b>trade it</b> to a shop that sells that brand. "
                    "Turns frozen cash into moving cash — and every swap deepens the data network.")

# --- simulated partner shops (the live network doesn't exist yet) ----------
PARTNERS = [
    {"name": "Willow Farm Tack", "state": "NC", "region": "Southeast",
     "brands": ["Animo", "Equiline", "Yagya", "Catago"], "cats": ["Show Coats", "Show Shirts", "Tops & Sweaters"]},
    {"name": "Sunnyside Equestrian", "state": "CA", "region": "West",
     "brands": ["Horse Pilot", "Parlanti", "Veredus"], "cats": ["Airvest", "Boots", "Footwear"]},
    {"name": "Oakwood Saddlery", "state": "TX", "region": "South Central",
     "brands": ["Veredus", "Parlanti", "KEP", "Equiline"], "cats": ["Boots", "Footwear", "Helmets", "Bits & Bridles"]},
    {"name": "Blue Ridge Riders", "state": "VA", "region": "Mid-Atlantic",
     "brands": ["Equiline", "Pampeano", "PS of Sweden", "Criniere"], "cats": ["Breeches", "Belts", "Saddle Pads"]},
    {"name": "Harborview Horse Co.", "state": "MA", "region": "Northeast",
     "brands": ["Yagya", "Animo", "Catago", "Armateq"], "cats": ["Tops & Sweaters", "Show Shirts", "Rugs"]},
    {"name": "Prairie Performance", "state": "CO", "region": "Mountain West",
     "brands": ["Horse Pilot", "Trolle", "Equisite"], "cats": ["Show Shirts", "Show Coats", "Outerwear"]},
    {"name": "Coastal Equine", "state": "FL", "region": "Southeast",
     "brands": ["Pampeano", "LeMieux", "HKM", "StablePro"], "cats": ["Saddle Pads", "Accessories", "Rugs", "Fly Control"]},
    {"name": "Northgate Equestrian", "state": "IL", "region": "Midwest",
     "brands": ["Meadowbrook", "Oakfield", "Parforce", "Elstead"], "cats": ["Footwear", "Rider Apparel", "Feed & Treats", "Hoof Care"]},
]


def best_match(item):
    best, best_score, reason = None, 0, ""
    for p in PARTNERS:
        score, why = 0, []
        if item["vendor"] and item["vendor"] in p["brands"]:
            score += 2
            why.append("carries {}".format(item["vendor"]))
        if item["type"] in p["cats"]:
            score += 1
            why.append("sells {}".format(item["type"]))
        if score > best_score:
            best, best_score, reason = p, score, " · ".join(why)
    return best, reason


@st.dialog("Message a partner shop")
def contact(store, item):
    st.markdown("**To:** {}".format(store))
    st.text_area("Message", key="swap_msg",
                 value="Hi {} — I have {} in stock that you might be selling well. "
                       "Open to a swap or sale through ClearShelf?".format(store, item))
    if st.button("Send message", type="primary"):
        st.success("Message sent to {}. (Demo — in the live network this opens a thread "
                   "between your two shops.)".format(store))


if not cs_lib.has_data():
    st.info("Load your shop's data on **Home** and this page will match *your* dead stock "
            "to partner shops that want it.")
    st.page_link("pages/home.py", label="Go to Home", icon="🏠")
    st.stop()

r = cs_lib.get_r()
dead = [x for x in r.get("dead", []) if x.get("cash")]
matches = []
for x in dead:
    partner, reason = best_match(x)
    if not partner:
        continue
    matches.append({"item": x["title"], "brand": x["vendor"] or "—", "type": x["type"],
                    "qty": int(x["stock"]), "cash": x["cash"], "partner": partner, "reason": reason})
matches.sort(key=lambda m: m["cash"], reverse=True)
top = matches[:15]

m1, m2, m3 = st.columns(3)
m1.metric("Frozen cash you could move", cs_lib.money(sum(m["cash"] for m in top)))
m2.metric("Matched swaps", len(matches))
m3.metric("Partner shops interested", len({m["partner"]["name"] for m in top}))

st.caption("Matched **{}** of your {} dead items to partner shops that carry the brand or sell the category. "
           "Showing the top {} by cash frozen.".format(len(matches), len(dead), len(top)))

# header row
h = st.columns([3, 2.4, 2.2, 1.4])
for col, lbl in zip(h, ["Your dead stock", "Wanted by", "Suggested swap", ""]):
    col.markdown("<span style='color:#5a6b5e;font-size:11px;text-transform:uppercase;"
                 "letter-spacing:.04em'>{}</span>".format(lbl), unsafe_allow_html=True)

for i, m in enumerate(top):
    c = st.columns([3, 2.4, 2.2, 1.4])
    c[0].markdown("**{}**  \n{} · {} · {} in stock · {} frozen".format(
        m["item"], m["brand"], m["type"], m["qty"], cs_lib.money(m["cash"])))
    p = m["partner"]
    c[1].markdown("**{}**  \n{} · {}  \n<span style='color:#5a6b5e;font-size:11.5px'>{}</span>".format(
        p["name"], p["state"], p["region"], m["reason"]), unsafe_allow_html=True)
    c[2].markdown("Swap for their stock, **or cash ~{}**".format(cs_lib.money(round(m["cash"] * 0.85))))
    if c[3].button("💬 Contact", key="contact_{}".format(i)):
        contact(p["name"], m["item"])

cs_lib.how_it_works([
    "Your dead-stock list (supply) is matched against each partner shop's brands & categories (demand).",
    "Different state / discipline scores higher — no channel conflict, they sell what you can't.",
    "The AI prices a fair swap or cash offer from the network's real sell-through.",
    "Message the shop in-app, agree the trade, and ClearShelf handles labels, payment split and stock sync.",
])
cs_lib.pricing_note("Small fee per completed swap. Turns frozen cash into moving cash — the feature retailers "
                    "stay for, and every swap feeds the data network.")
st.info("⚠️ Demo preview — partner shops are simulated. The matching logic above is the real thing; "
        "it goes live once enough shops are connected.")
