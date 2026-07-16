"""Customer CRM — your Shopify customers + clienteling (horse, discipline, sizes) and follow-ups."""

import pandas as pd
import streamlit as st

import cs_lib
import shopify_api as SA

cs_lib.page_title("Customer CRM",
                  "Every customer in one place — pulled from Shopify, enriched with the horse, discipline "
                  "and sizes you know, so every follow-up feels personal.")

# ---------------------------------------------------------------------------
# Sync from Shopify + add a walk-in manually
# ---------------------------------------------------------------------------
top = st.columns([1, 1, 2])
with top[0]:
    if SA.configured():
        if st.button("🔄  Sync customers from Shopify", type="primary", use_container_width=True):
            try:
                with st.spinner("Pulling your customers from Shopify…"):
                    custs = SA.load_customers_api()
                n = cs_lib.crm_sync_shopify(custs)
                st.success("Synced {} customers from Shopify.".format(n))
            except Exception as e:
                msg = str(e)
                if "read_customers" in msg or "access" in msg.lower() or "scope" in msg.lower():
                    st.error("Shopify blocked the customer list. Add the **read_customers** scope to your "
                             "custom app in Shopify (Settings → Apps → your app → Configuration), then sync again.")
                else:
                    st.error("Couldn't pull customers: {}".format(msg))
    else:
        st.caption("Connect Shopify on the Home page to auto-pull customers.")

with top[1]:
    with st.popover("➕  Add a walk-in", use_container_width=True):
        with st.form("add_contact", clear_on_submit=True):
            nm = st.text_input("Name")
            em = st.text_input("Email")
            ph = st.text_input("Phone")
            disc = st.selectbox("Discipline", ["", "Dressage", "Show jumping", "Eventing", "Hacking", "Western"])
            horse = st.text_input("Horse / size notes", placeholder="16.2hh · breeches 28 · tall boot 39")
            if st.form_submit_button("Save", type="primary") and (nm or em):
                cs_lib.crm_upsert({"name": nm, "email": em, "phone": ph,
                                   "discipline": disc, "horse": horse, "source": "in-store"})
                st.success("Added {}.".format(nm or em))

contacts = cs_lib.crm_all()

if not contacts:
    st.info("No customers yet. Click **Sync customers from Shopify** above, or **Add a walk-in** to start "
            "building your list.")
    st.stop()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
total_spend = sum(c.get("spent", 0) or 0 for c in contacts)
repeat = sum(1 for c in contacts if (c.get("orders", 0) or 0) >= 2)
k = st.columns(3)
k[0].metric("Customers", len(contacts))
k[1].metric("Lifetime revenue", cs_lib.money(total_spend))
k[2].metric("Repeat buyers", repeat, "{}%".format(round(100 * repeat / len(contacts))), delta_color="off")

st.divider()

# Purchase history + clear-out targeting need recent orders — pulled on demand.
orders = st.session_state.get("crm_orders")
if SA.configured():
    lc = st.columns([1, 3])
    if lc[0].button("📦  Load purchase history", use_container_width=True):
        try:
            with st.spinner("Reading recent orders…"):
                st.session_state["crm_orders"] = SA.load_orders_detailed()
            orders = st.session_state["crm_orders"]
            st.success("Loaded {} recent orders.".format(len(orders)))
        except Exception as e:
            st.error("Couldn't read orders: {}".format(e))
    lc[1].caption("Adds each customer's recent purchases and powers clear-out targeting "
                  "(last ~60 days of orders).")

# ---------------------------------------------------------------------------
# Customer list (searchable) + pick one to open
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Customers")
    q = st.text_input("🔎  Search name, email or tag", key="crm_search").strip().lower()
    rows = contacts
    if q:
        rows = [c for c in contacts if q in c.get("name", "").lower()
                or q in c.get("email", "").lower()
                or any(q in t.lower() for t in c.get("tags", []))]
    df = pd.DataFrame([{
        "Customer": c.get("name", ""),
        "Orders": c.get("orders", 0),
        "Spent": cs_lib.money(c.get("spent", 0) or 0),
        "Last order": c.get("last_order", "") or "—",
        "Discipline": c.get("discipline", "") or "—",
        "Open follow-ups": sum(1 for f in c.get("followups", []) if f.get("status") != "Recovered"),
    } for c in rows])
    st.dataframe(df, hide_index=True, use_container_width=True, height=360)
    st.download_button("⬇  Export customers (CSV)", df.to_csv(index=False).encode(),
                       "equisphere_customers.csv", "text/csv")

    names = {c.get("name", "") + "  ·  " + (c.get("email", "") or "no email"): c["id"] for c in rows}
    pick = st.selectbox("Open a customer card", ["—"] + list(names.keys()))

with right:
    if pick and pick != "—":
        cid = names[pick]
        c = cs_lib.crm_get(cid)
        st.subheader(c.get("name", "Customer"))
        st.caption("{}  ·  {}{}".format(
            c.get("email", "") or "no email", c.get("phone", "") or "no phone",
            "  ·  📍 " + c["location"] if c.get("location") else ""))
        b = st.columns(3)
        b[0].metric("Orders", c.get("orders", 0))
        b[1].metric("Spent", cs_lib.money(c.get("spent", 0) or 0))
        b[2].metric("Last order", c.get("last_order", "") or "—")

        with st.form("edit_" + cid):
            disc = st.selectbox("Discipline", ["", "Dressage", "Show jumping", "Eventing", "Hacking", "Western"],
                                index=(["", "Dressage", "Show jumping", "Eventing", "Hacking", "Western"]
                                       .index(c.get("discipline", "")) if c.get("discipline", "")
                                       in ["", "Dressage", "Show jumping", "Eventing", "Hacking", "Western"] else 0))
            horse = st.text_input("Horse / size notes", value=c.get("horse", ""))
            tags = st.text_input("Tags (comma-separated)", value=", ".join(c.get("tags", [])))
            notes = st.text_area("Notes", value=c.get("notes", ""), height=100)
            if st.form_submit_button("💾  Save card", type="primary"):
                cs_lib.crm_upsert({"id": cid, "discipline": disc, "horse": horse, "notes": notes,
                                   "tags": [t.strip() for t in tags.split(",") if t.strip()]})
                st.success("Saved.")
                st.rerun()

        st.markdown("**Follow-ups**")
        for i, f in enumerate(c.get("followups", [])):
            fc = st.columns([3, 1])
            fc[0].write("• {} — _{}_ ({})".format(f.get("item", ""), f.get("status", ""), f.get("channel", "")))
            if f.get("status") != "Recovered":
                if fc[1].button("✅ Won", key="won_{}_{}".format(cid, i)):
                    cs_lib.crm_set_followup_status(cid, i, "Recovered")
                    st.rerun()
        with st.form("fu_" + cid, clear_on_submit=True):
            fi = st.text_input("New follow-up — item they're interested in")
            ch = st.selectbox("Channel", ["Email", "SMS", "Call"])
            if st.form_submit_button("➕  Schedule follow-up") and fi:
                cs_lib.crm_add_followup(cid, fi, ch)
                st.rerun()

        if orders is not None:
            hist = cs_lib.customer_purchases(c.get("email", ""), orders)
            st.markdown("**Recent purchases**")
            if hist:
                st.dataframe(pd.DataFrame([{"Date": h["date"], "Item": h["title"], "Qty": h["qty"]}
                                          for h in hist]), hide_index=True, use_container_width=True, height=160)
            else:
                st.caption("No orders on record in the last ~60 days.")

        if c.get("email"):
            with st.expander("✉️  Email this customer"):
                first = (c.get("name", "") or "there").split(" ")[0]
                subj = st.text_input("Subject",
                                     value="A note from {}".format(st.session_state.get("shop_name", "us")),
                                     key="subj_" + cid)
                body = st.text_area("Message", value="Hi {},\n\n".format(first), height=120, key="body_" + cid)
                if st.button("Send email", type="primary", key="send_" + cid):
                    if cs_lib.email_configured():
                        ok, msg = cs_lib.send_email(c["email"], subj, body)
                        (st.success if ok else st.error)(msg)
                    else:
                        st.warning("Email sending isn't set up yet — add SMTP settings in the app secrets "
                                   "and you'll be able to send follow-ups straight from here.")
    else:
        st.info("Pick a customer on the left to open their card — add their horse, discipline, sizes and "
                "schedule a follow-up.")

st.divider()
st.subheader("🎯  Clear-out targeting")
st.caption("Match your dead stock to the customers who already bought it — offer them a deal to clear it fast.")
if not cs_lib.has_data():
    st.info("Load your shop's stock data on the **Home** page first, so EquiSphere knows what's slow-moving.")
elif orders is None:
    st.info("Click **📦 Load purchase history** above to see who to target.")
else:
    r = cs_lib.get_r()
    targets = cs_lib.clearout_targets(r.get("at_risk", []), orders)
    if not targets:
        st.caption("No past buyers found for your current at-risk items (within the last ~60 days of orders).")
    else:
        for title, buyers in list(targets.items())[:20]:
            with st.expander("{}  —  {} past buyer(s)".format(title, len(buyers))):
                for nm, em in buyers:
                    st.write("• {} — {}".format(nm or "—", em or "no email"))

st.caption("Customers sync from Shopify; the horse/discipline/sizes and follow-ups you add are stored with "
           "EquiSphere. (For a large shop this moves to a hosted database — this version keeps it simple.)")
