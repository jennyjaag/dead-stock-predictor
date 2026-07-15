"""Home — landing page: first-run upload/demo prompt, or the dashboard + jump-back-in."""

import streamlit as st

import cs_lib

# ---------------------------------------------------------------------------
# First run — no data yet: show the upload area + demo button right here
# ---------------------------------------------------------------------------
if not cs_lib.has_data():
    cs_lib.page_title("Welcome to EquiSphere",
                      "Load your shop's data to see what's turning into dead stock — and what to buy instead.")
    tab_csv, tab_master = st.tabs(["📄  Two Shopify CSVs", "📊  One master file (xlsx)"])
    with tab_csv:
        c1, c2 = st.columns(2)
        sales_file = c1.file_uploader("Sales by product (CSV)", type="csv", key="home_sales",
                                      help="Shopify → Analytics → Reports → 'Sales by product' → Export.")
        prod_file = c2.file_uploader("Products export (CSV)", type="csv", key="home_prod",
                                     help="Shopify → Products → Export → CSV.")
        st.caption("Two-CSV mode also gives you the cash-at-risk **by brand** breakdown and per-variant view.")
    with tab_master:
        master_file = st.file_uploader("Master file (xlsx)", type=["xlsx"], key="home_master",
                                       help="One sheet with stock, cost, 30/90/12-month + prior-year sales, "
                                            "Date added, Vendor & Product type.")
    demo = st.button("✨  Try it with demo data")

    try:
        if master_file:
            cs_lib.set_data(cs_lib.compute_from("master", master_file, None), "master",
                            (master_file.name, "(single master file)"))
            st.rerun()
        elif sales_file and prod_file:
            cs_lib.set_data(cs_lib.compute_from("upload", sales_file, prod_file), "upload",
                            (sales_file.name, prod_file.name))
            st.rerun()
        elif demo:
            cs_lib.set_data(cs_lib.compute_from("demo", cs_lib.DEMO_SALES, cs_lib.DEMO_PRODS), "demo",
                            ("demo_sales.csv", "demo_products.csv"))
            st.rerun()
    except Exception as e:
        st.error("😕 Couldn't read that file. Please use the Shopify export(s) described above.")
        st.caption("Detail: {}".format(e))

    st.info("Everything runs on your computer — nothing is uploaded anywhere.")
    st.stop()

# ---------------------------------------------------------------------------
# Data loaded — dashboard
# ---------------------------------------------------------------------------
ss = st.session_state
r = cs_lib.get_r()

cs_lib.page_title("Welcome back",
                  "Here's where **{}** stands. Pick a tool on the left, or jump back in below.".format(ss["shop_name"]))

freed = cs_lib.freed_since_last_visit(ss["shop_name"], r["cash_at_risk"])
k = st.columns(3)
k[0].metric("Cash frozen in dead stock", cs_lib.money(r["cash_at_risk"]))
k[1].metric("At-risk items", r["at_risk_count"], "{} never sold".format(r["dead_count"]), delta_color="off")
if freed is not None and freed != 0:
    k[2].metric("Since your last visit", cs_lib.money(abs(freed)),
                "freed" if freed > 0 else "more frozen",
                delta_color="normal" if freed > 0 else "inverse")

st.subheader("Jump back in")
j = st.columns(3)
with j[0]:
    st.page_link("views/p_deadstock.py", label="📉  Dead-stock report", use_container_width=True)
    st.caption("What's stuck right now.")
with j[1]:
    st.page_link("views/p_buyai.py", label="🛒  Trade-show buy AI", use_container_width=True)
    st.caption("What to buy, in what depth.")
with j[2]:
    st.page_link("views/p_reorder.py", label="🔁  Reorder engine", use_container_width=True)
    st.caption("Right quantity + timing.")

st.divider()
if st.button("↻  Load different data"):
    for key in ["data", "kind", "names", "snapshotted", "freed_val",
                "home_sales", "home_prod", "home_master"]:
        st.session_state.pop(key, None)
    st.rerun()
