"""Showrooming rescue (#7) — capture the in-store shopper into the CRM, then follow up so the sale closes with you."""

import pandas as pd
import streamlit as st

import cs_lib

cs_lib.page_title("Showrooming rescue",
                  "For shops losing try-on customers to online: capture the in-store shopper in seconds, "
                  "then follow up so the sale closes with you — not Amazon.")
cs_lib.problem_note("They try it on in your shop, then buy it cheaper on their phone. Capturing them here "
                    "keeps the sale yours — and every shopper you capture lands in your <b>Customer CRM</b>.")

# ---------------------------------------------------------------------------
# Live metrics from the CRM (real, not illustrative)
# ---------------------------------------------------------------------------
open_fu = cs_lib.crm_open_followups()
all_contacts = cs_lib.crm_all()
captured = sum(1 for c in all_contacts if c.get("followups"))
recovered = sum(1 for c in all_contacts for f in c.get("followups", []) if f.get("status") == "Recovered")

m = st.columns(3)
m[0].metric("Shoppers captured", captured)
m[1].metric("Open follow-ups", len(open_fu))
m[2].metric("Sales recovered", recovered)

# ---------------------------------------------------------------------------
# Capture a shopper -> creates/updates a CRM contact + schedules a follow-up
# ---------------------------------------------------------------------------
st.markdown("##### Capture a shopper")
with st.form("capture", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("Rider name")
    disc = c2.selectbox("Discipline", ["", "Dressage", "Show jumping", "Eventing", "Hacking", "Western"])
    horse = c3.text_input("Horse / size notes", placeholder="16.2hh · breeches 28 · tall boot 39")
    c4, c5, c6 = st.columns(3)
    tried = c4.text_input("Item they tried on")
    email = c5.text_input("Email")
    channel = c6.selectbox("Follow-up by", ["Email", "SMS", "Call"])
    if st.form_submit_button("Save & schedule follow-up", type="primary") and (name or email):
        cid = cs_lib.crm_upsert({"name": name, "email": email, "discipline": disc,
                                 "horse": horse, "source": "in-store"})
        if tried:
            cs_lib.crm_add_followup(cid, tried, channel)
        st.success("Captured {} — follow-up scheduled. They're now in your CRM.".format(name or email))

# ---------------------------------------------------------------------------
# Follow-up queue (real) — mark recovered right here
# ---------------------------------------------------------------------------
st.markdown("##### Follow-up queue")
if not open_fu:
    st.info("No open follow-ups. Capture a shopper above and they'll appear here.")
else:
    for f in open_fu:
        c = f["contact"]
        cols = st.columns([3, 2, 2, 1])
        cols[0].write("**{}**".format(c.get("name", "")))
        cols[1].write(f.get("item", ""))
        cols[2].write("{} · _{}_".format(f.get("channel", ""), f.get("status", "")))
        if cols[3].button("✅ Won", key="sr_won_{}_{}".format(c["id"], f["idx"])):
            cs_lib.crm_set_followup_status(c["id"], f["idx"], "Recovered")
            st.rerun()

st.page_link("views/p_crm.py", label="→  Open the full Customer CRM", icon="👥")

cs_lib.how_it_works([
    "Staff capture the in-store shopper in seconds — rider, horse, discipline, sizes.",
    "It's saved to your Customer CRM and a personal follow-up is scheduled (the exact item, their fit).",
    "If they didn't buy in-store, the follow-up closes the sale with you instead of online.",
    "Every captured shopper also enriches your customer and demand data.",
])
cs_lib.pricing_note("Retailers pay per recovered sale — you only pay when it works.")
