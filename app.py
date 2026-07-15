"""
ClearShelf -- dead-stock intelligence for independent tack shops (web app).

A shop owner uploads their two Shopify CSV exports (or clicks "Try demo data")
and gets an action-first report on screen: the headline number, KPI cards, a
chart, and a ranked table of what to mark down / stop reordering.

ALL analysis is the same logic used by the command-line tools (shopify_join +
casa_report). This file is the product UI on top. Launch with:

    python3 -m streamlit run app.py

(First time only:  pip3 install -r requirements.txt )
"""

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import shopify_join as SJ
import master_load as ML
import buy_plan_view as BP
import casa_report as C

# ---------------------------------------------------------------------------
APP_NAME = "ClearShelf"
APP_TAGLINE = "Dead-stock intelligence for independent tack shops"
TODAY = date.today()

st.set_page_config(page_title=APP_NAME, page_icon="🐴", layout="wide")

# --- a little CSS so it doesn't look like default Streamlit -----------------
st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; max-width: 1200px;}
  #MainMenu, footer {visibility: hidden;}
  .cs-brand {font-size: 15px; font-weight: 700; color: #0f766e; letter-spacing:.02em;}
  .cs-tag {color:#667085; font-size:13px; margin-top:-4px;}
  .cs-hero {background: linear-gradient(100deg,#0f2b3d,#123a3a); color:#fff; border-radius:16px;
            padding: 26px 30px; margin: 6px 0 20px;}
  .cs-hero .num {font-size: 44px; font-weight: 800; line-height:1.05;}
  .cs-hero .sub {font-size: 14px; opacity:.85; margin-top:6px;}
  .cs-quickwin {background:#eef7f4; border:1px solid #cbe7df; border-radius:12px;
                padding:14px 18px; font-size:15px; color:#0c4a42; margin: 4px 0 18px;}
  .cs-quickwin b {color:#0f766e;}
  div[data-testid="stMetric"] {background:#f7f9fb; border:1px solid #e6eaef; border-radius:12px;
                padding:14px 16px;}
  .pill {display:inline-block; padding:3px 10px; border-radius:20px; font-weight:700; font-size:12px;}
  .pill.red{background:#fde2e1;color:#a11a12;} .pill.amber{background:#fdf3d8;color:#8a6100;}
  .pill.green{background:#e3f6e5;color:#1c6b28;}
  table.cs {width:100%; border-collapse:collapse; font-size:13px;}
  table.cs th{text-align:left; color:#667085; font-size:10.5px; text-transform:uppercase;
              letter-spacing:.04em; padding:8px 10px; border-bottom:1px solid #e6eaef;}
  table.cs td{padding:9px 10px; border-bottom:1px solid #eef1f4; vertical-align:top;}
  table.cs td.prod{font-weight:600; color:#182230;}
  table.cs .why{color:#667085; font-size:11.5px; display:block; margin-top:2px;}
  table.cs td.num{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap;}
  table.cs td.act{white-space:nowrap; font-weight:600;}
  table.cs td.act .date{display:block; color:#98a2b3; font-weight:400; font-size:11px;}
</style>
""", unsafe_allow_html=True)

# --- header -----------------------------------------------------------------
st.markdown(f"<div class='cs-brand'>🐴 {APP_NAME}</div>"
            f"<div class='cs-tag'>{APP_TAGLINE}</div>", unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------------------
# Sidebar: shop name + live filters
# ---------------------------------------------------------------------------
view = st.sidebar.radio("View", ["📉 Dead-stock report", "🛒 Buy-plan"], index=0)
st.sidebar.divider()
st.sidebar.header("Settings")
shop_name = st.sidebar.text_input("Shop name", value="Your shop")
st.sidebar.markdown("**Filters** (re-filter the tables & chart live)")
min_risk = st.sidebar.slider("Only show risk ≥", 0, 100, 0, 5)
min_cash = st.sidebar.number_input("Only show cash tied up ≥ ($)", min_value=0, value=0, step=50)
st.sidebar.caption("Raise these to shrink the list to just the items worth acting on today.")
variant_view = st.sidebar.checkbox("Break down by size / colour (per variant)", value=False,
    help="Show each size/colour as its own row with its own stock & cash. "
         "Needs the two-CSV upload (the master file is product-level).")


# ---------------------------------------------------------------------------
# Helpers: action, date, plain-English "why", badge
# ---------------------------------------------------------------------------
def cover_txt(c):
    return "∞" if c == float("inf") else "{:.0f} mo".format(c)


def badge_level(risk):
    if risk >= C.MARKDOWN_SCORE:
        return "red"
    if risk >= C.WATCH_SCORE:
        return "amber"
    return "green"


def recommend(x):
    """Return (action_text, when_text) — the action IS the product."""
    if x["action"] == "Reorder":
        return "Reorder — selling fast", "Now"
    if x["action"] == "Sold out":
        return "Sold out", "—"
    if x["risk"] >= C.MARKDOWN_SCORE:
        if x["u12"] == 0:
            act = "Stop reordering · mark down 30%"
        elif x["risk"] >= 85:
            act = "Mark down 40% now"
        else:
            act = "Mark down 25% now"
        return act, TODAY.strftime("%d %b %Y")
    if x["risk"] >= C.WATCH_SCORE:
        return "Watch — recheck in 3 weeks", (TODAY + timedelta(weeks=3)).strftime("%d %b %Y")
    return "Healthy — no action", "—"


def why(x):
    cash = SJ.money(x["cash"]) if x["cash"] is not None else "cost unknown"
    lead = "0 sales in 12 months" if x["u12"] == 0 else "{:.0f} sold last year".format(x["u12"])
    return "{} · {} of cover · {} tied up".format(lead, cover_txt(x["cover"]), cash)


def render_buyplan(r):
    """The Buy-Plan view: what to reorder (and how deep) and what to stop buying."""
    bp = BP.compute_buyplan(r["in_stock"])
    st.markdown("<div class='cs-hero'><div class='num'>Buy-Plan</div>"
                "<div class='sub'>What to reorder before your next show — and what to stop buying — "
                "so you prevent dead stock upstream instead of finding it later. Targets ~4 months of cover.</div></div>",
                unsafe_allow_html=True)
    if not bp["has_windows"]:
        st.info("ℹ️ This upload only carries a 12-month sales total, so the plan uses velocity + cover "
                "(no recent-momentum or seasonality). Upload the **master file** for demand momentum & trend.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("To reinvest", SJ.money(bp["total_buy"]), "{} products to reorder".format(len(bp["reorder"])), delta_color="off")
    k2.metric("Projected sell-through", SJ.money(bp["total_rev"]))
    k3.metric("Stop buying", len(bp["stop"]), "prevent future dead stock", delta_color="off")
    k4.metric("Cash already frozen there", SJ.money(bp["stop_cash"]))

    if bp["seasons"]:
        st.subheader("Demand momentum by category")
        st.caption("Recent run-rate vs the yearly average. Heating up → buy ahead; cooling → ease off.")
        sdf = pd.DataFrame([{"Category": s["cat"], "Trend": s["label"],
                             "vs year avg": "{:+.0f}%".format((s["momentum"] - 1) * 100)} for s in bp["seasons"]])
        st.dataframe(sdf, use_container_width=True, hide_index=True, height=min(320, 44 + 30 * len(sdf)))

    st.subheader("🟢 Reorder now — proven sellers running low")
    if bp["reorder"]:
        rdf = pd.DataFrame([{
            "Product": x["title"], "Brand": x["vendor"], "Sold/yr": int(x["u12"]),
            "In stock": int(x["stock"]), "Cover": cover_txt(x["cover"]), "Reorder qty": x["reorder_qty"],
            "Buy cost ($)": None if x["buy_cost"] is None else round(x["buy_cost"]),
            "Sell-thru value ($)": None if x["rev_potential"] is None else round(x["rev_potential"]),
        } for x in bp["reorder"]])
        st.dataframe(rdf, use_container_width=True, hide_index=True, height=430)
        st.caption("Quantity buys back to ~4 months of forward cover, nudged by recent momentum where available.")
    else:
        st.info("Nothing needs reordering right now.")

    st.subheader("🔴 Stop buying — don't feed the dead stock")
    if bp["stop"]:
        s2 = pd.DataFrame([{
            "Product": x["title"], "Brand": x["vendor"], "In stock": int(x["stock"]),
            "Cover": cover_txt(x["cover"]), "Sold/yr": int(x["u12"]),
            "Cash frozen ($)": None if x["cash"] is None else round(x["cash"]), "Why": x["reason"],
        } for x in bp["stop"]])
        st.dataframe(s2, use_container_width=True, hide_index=True, height=430)
    else:
        st.success("Nothing to stop — no dead stock building up. 🎉")

    st.caption("This plan is built from your store's own sell-through. Region-specific depth "
               "(buying for your local market rather than a rep's national pitch) comes once multiple "
               "stores feed the network — a later phase.")


# ---------------------------------------------------------------------------
# Input: upload two CSVs OR try demo data
# ---------------------------------------------------------------------------
if "use_demo" not in st.session_state:
    st.session_state.use_demo = False

tab_csv, tab_master = st.tabs(["📄  Two Shopify CSVs", "📊  One master file (xlsx)"])
with tab_csv:
    c1, c2 = st.columns(2)
    sales_file = c1.file_uploader("1 · Sales by product (CSV)", type="csv",
        help="Shopify → Analytics → Reports → 'Sales by product' → Export.")
    prod_file = c2.file_uploader("2 · Products export (CSV)", type="csv",
        help="Shopify → Products → Export → CSV (unzip first if it's a .zip).")
    st.caption("Two-CSV mode also gives you the cash-at-risk **by brand** breakdown.")
with tab_master:
    master_file = st.file_uploader("Master file (xlsx)", type=["xlsx"],
        help="One sheet with stock, cost, 30/90/12-month + prior-year sales, and 'Date added'. "
             "Adds new-arrival filtering and year-on-year trend (but no brand breakdown).")

if st.button("✨ Try it with demo data"):
    st.session_state.use_demo = True
if (sales_file and prod_file) or master_file:
    st.session_state.use_demo = False

# decide the data source (master file wins if provided)
source = None
if master_file:
    source = ("master", master_file, None, master_file.name, "(single master file)")
elif sales_file and prod_file:
    source = ("upload", sales_file, prod_file, sales_file.name, prod_file.name)
elif st.session_state.use_demo:
    source = ("demo", "demo_data/demo_sales.csv", "demo_data/demo_products.csv",
              "demo_sales.csv", "demo_products.csv")

if source is None:
    st.info("⬆️  Upload your files (two CSVs **or** one master xlsx), or click "
            "**Try it with demo data**. Everything runs on your computer — nothing is uploaded anywhere.")
    st.stop()

# ---------------------------------------------------------------------------
# Load + compute, with friendly errors (never a raw traceback)
# ---------------------------------------------------------------------------
kind, s_src, p_src, s_name, p_name = source
sales = prod = r = None
try:
    if kind == "master":
        r = ML.load_master(s_src)
    else:
        sales = SJ.load_sales(s_src)
        prod = SJ.load_products(p_src)
except Exception as e:
    st.error("😕 Couldn't read that file. Please upload the Shopify export(s) described above "
             "(two CSVs, or one master .xlsx).")
    st.caption("Technical detail: {}".format(e))
    st.stop()

# validation for the two-CSV path (outside the try, so st.stop isn't swallowed)
if kind != "master":
    if not sales:
        st.error("😕 The **sales file** doesn't look right — I couldn't find the "
                 "`Product title` and `Net items sold` columns. Is this the Shopify "
                 "'Sales by product' export?")
        st.stop()
    if not prod:
        st.error("😕 The **products file** doesn't look right — I couldn't find the expected "
                 "Shopify columns (`Handle`, `Title`, `Variant Inventory Qty`). Is this the "
                 "Shopify Products export?")
        st.stop()
    r = SJ.compute(prod, sales)

if r["match_count"] == 0:
    st.warning("⚠️ None of the products in your sales file matched the products export "
               "(the titles don't line up). Double-check both files are from the same store.")
if r["total_inv"] == 0:
    st.warning("⚠️ No cost data found, so I can't put a dollar figure on the frozen cash. "
               "Risk is still scored on sales & cover. Add **Cost per item** in Shopify to unlock the $ figures.")

if kind == "demo":
    st.caption("Showing **demo data** — a fictional tack shop. Upload your own files above to run it for real.")
elif kind == "master":
    st.caption("Loaded **master file** — {} in-stock products · **{} new arrivals** kept out of dead stock "
               "(added recently, no sales yet).".format(r["instock_count"], len(r.get("new_arrivals", []))))

# ---------------------------------------------------------------------------
# Buy-plan view (sidebar nav) — render it and stop before the dead-stock report
# ---------------------------------------------------------------------------
if "Buy-plan" in view:
    render_buyplan(r)
    st.stop()

# ---------------------------------------------------------------------------
# 1) HEADLINE
# ---------------------------------------------------------------------------
top_by_cash = sorted([x for x in r["at_risk"] if x["cash"]], key=lambda x: x["cash"], reverse=True)
free_top10 = sum(x["cash"] for x in top_by_cash[:10])

st.markdown(
    "<div class='cs-hero'><div class='num'>{} of your cash is frozen in dead stock.</div>"
    "<div class='sub'>{} · across {} at-risk products · as of {}</div></div>".format(
        SJ.money(r["cash_at_risk"]), shop_name, r["at_risk_count"], TODAY.strftime("%d %b %Y")),
    unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 2) KPI CARDS
# ---------------------------------------------------------------------------
finite_cov = [x["cover"] for x in r["at_risk"] if x["cover"] != float("inf")]
avg_cov = "{:.0f} mo".format(sum(finite_cov) / len(finite_cov)) if finite_cov else "∞"

k1, k2, k3, k4 = st.columns(4)
k1.metric("Cash at risk", SJ.money(r["cash_at_risk"]))
k2.metric("Dead / at-risk items", r["at_risk_count"], "{} never sold".format(r["dead_count"]), delta_color="off")
k3.metric("Avg. cover (at-risk)", avg_cov)
k4.metric("Free up (top 10 items)", SJ.money(free_top10))

# ---------------------------------------------------------------------------
# Apply live filters to the lists that follow
# ---------------------------------------------------------------------------
shown = [x for x in r["in_stock"] if x["risk"] >= min_risk and (x["cash"] or 0) >= min_cash]

# ---------------------------------------------------------------------------
# 3) CHART — dead stock clusters top-left (slow sellers, lots of cover)
# ---------------------------------------------------------------------------
st.subheader("The dead-stock map")
st.caption("Each dot is a product. Bottom-right = healthy (sells fast, little stock). "
           "Top-left = dead stock (barely sells, months of cover). Bigger dot = more cash tied up.")

cc1, cc2 = st.columns([3, 2])
with cc1:
    if shown:
        cdf = pd.DataFrame([{
            "Product": x["title"], "Sold/yr": x["u12"],
            "Cover (mo)": min(x["cover"], 60) if x["cover"] != float("inf") else 60,
            "Risk": ("Act now" if x["risk"] >= C.MARKDOWN_SCORE
                     else "Watch" if x["risk"] >= C.WATCH_SCORE else "Healthy"),
            "Cash": x["cash"] or 0,
        } for x in shown])
        chart = (alt.Chart(cdf).mark_circle(opacity=0.75).encode(
            x=alt.X("Sold/yr:Q", title="Units sold last year (velocity)"),
            y=alt.Y("Cover (mo):Q", title="Months of cover (capped at 60)"),
            size=alt.Size("Cash:Q", title="Cash tied up", scale=alt.Scale(range=[30, 900]), legend=None),
            color=alt.Color("Risk:N", scale=alt.Scale(
                domain=["Act now", "Watch", "Healthy"], range=["#d62d20", "#e0a825", "#1e8c3c"]),
                legend=alt.Legend(title="", orient="top")),
            tooltip=["Product", "Sold/yr", "Cover (mo)", alt.Tooltip("Cash:Q", format="$,.0f")],
        ).properties(height=340).configure_axis(grid=True, gridColor="#eef1f4"))
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No products match the current filters.")
with cc2:
    cat = {}
    for x in shown:
        if x["risk"] >= C.AT_RISK_SCORE and x["cash"]:
            cat[x["type"]] = cat.get(x["type"], 0) + x["cash"]
    if cat and len(cat) > 1:
        catdf = (pd.DataFrame(sorted(cat.items(), key=lambda kv: kv[1], reverse=True)[:8],
                              columns=["Category", "Cash at risk"]).set_index("Category"))
        st.caption("Cash at risk by category")
        st.bar_chart(catdf, horizontal=True, color="#d62d20", height=340)
    else:
        st.caption("Category breakdown not available for this file "
                   "(the master export has no product-type column).")

# ---------------------------------------------------------------------------
# 4) QUICK-WIN + ACTION TABLE
# ---------------------------------------------------------------------------
st.markdown(
    "<div class='cs-quickwin'>💡 If you act on the top 10 items, you free up "
    "<b>{}</b> in cash to reinvest in the stock that actually sells.</div>".format(SJ.money(free_top10)),
    unsafe_allow_html=True)

st.subheader("Do this first — your action list")
act_items = [x for x in shown if x["risk"] >= C.AT_RISK_SCORE][:25]
if act_items:
    rows = ""
    for x in act_items:
        lvl = badge_level(x["risk"])
        action, when = recommend(x)
        rows += ("<tr><td class='prod'>{n}<span class='why'>{v} · {t}<br>{w}</span></td>"
                 "<td><span class='pill {lvl}'>{r}</span></td>"
                 "<td class='num'>{cash}</td>"
                 "<td class='act'>{a}<span class='date'>{d}</span></td></tr>").format(
            n=C.esc(x["title"]), v=C.esc(x["vendor"]), t=C.esc(x["type"]), w=C.esc(why(x)),
            lvl=lvl, r=x["risk"], cash=SJ.money(x["cash"]) if x["cash"] is not None else "—",
            a=C.esc(action), d=when)
    st.markdown(
        "<div style='overflow-x:auto'><table class='cs'><thead><tr>"
        "<th>Product &amp; why</th><th>Risk</th><th class='num'>Cash tied up</th><th>Recommended action</th>"
        "</tr></thead><tbody>{}</tbody></table></div>".format(rows), unsafe_allow_html=True)
    st.caption("Showing the top {} at-risk items. Full ranked list below.".format(len(act_items)))
else:
    st.success("Nothing above the risk threshold — inventory looks healthy. 🎉")

# ---------------------------------------------------------------------------
# 5) FULL SORTABLE TABLE (product- or variant-level) + FLAGS + DOWNLOAD
# ---------------------------------------------------------------------------
def hl(v):
    if not isinstance(v, (int, float)):
        return ""
    if v >= C.MARKDOWN_SCORE:
        return "background-color:#fde2e1;color:#a11a12;font-weight:700"
    if v >= C.WATCH_SCORE:
        return "background-color:#fdf3d8;color:#8a6100;font-weight:700"
    return "background-color:#e3f6e5;color:#1c6b28;font-weight:700"

has_variants = any(len(x.get("variants") or []) for x in shown)

if variant_view and has_variants:
    # explode each product into its in-stock size/colour rows.
    # velocity/risk stay at the product level; stock & cash are per variant.
    vrows = []
    for x in shown:
        for v in (x.get("variants") or []):
            if v["stock"] <= 0:
                continue
            vcash = v["stock"] * v["cost"] if v["cost"] else None
            if (vcash or 0) < min_cash:
                continue
            vrows.append({
                "Product": x["title"], "Variant": v["label"], "Brand": x["vendor"],
                "Risk (product)": x["risk"], "Variant stock": int(v["stock"]),
                "Cover (product)": cover_txt(x["cover"]), "Sold/yr (product)": int(x["u12"]),
                "Variant cash ($)": None if vcash is None else round(vcash),
                "Action": recommend(x)[0],
            })
    with st.expander("📋 All in-stock **variants** (size/colour) — {} shown".format(len(vrows)), expanded=True):
        st.caption("Each row is one size/colour. Velocity, cover and risk are the product's overall figures "
                   "(sales aren't split per variant); **stock and cash are per variant** so you can see which "
                   "specific sizes hold the dead money.")
        vdf = pd.DataFrame(vrows)
        if len(vdf):
            st.dataframe(vdf.style.map(hl, subset=["Risk (product)"]), use_container_width=True,
                         hide_index=True, height=460)
        else:
            st.info("No variants match the current filters. Lower the thresholds in the sidebar.")
else:
    if variant_view and not has_variants:
        st.info("ℹ️ Variant breakdown needs the **two-CSV** upload (products export). "
                "The master file is product-level, so there are no size/colour rows to show.")
    with st.expander("📋 All in-stock products (sortable) — {} shown".format(len(shown))):
        df = pd.DataFrame([{
            "Product": x["title"], "Brand": x["vendor"], "Type": x["type"], "Risk": x["risk"],
            "Stock": int(x["stock"]), "Cover": cover_txt(x["cover"]), "Sold/yr": int(x["u12"]),
            "Cash @cost ($)": None if x["cash"] is None else round(x["cash"]),
            "Action": recommend(x)[0], "Status": x["status"],
        } for x in shown])
        if len(df):
            st.dataframe(df.style.map(hl, subset=["Risk"]), use_container_width=True,
                         hide_index=True, height=460)
        else:
            st.info("No products match the current filters. Lower the thresholds in the sidebar.")

with st.expander("⚠︎ Data-quality flags & how the columns were mapped"):
    st.markdown("**Mapping:** product = `Product title` ↔ `Title` · units = `Net items sold` · "
                "stock = Σ `Variant Inventory Qty` · cost = avg `Cost per item` · `Vendor`/`Type`/`Status` direct.")
    for title, level, body in r["flags"]:
        {"critical": st.error, "warn": st.warning, "info": st.info}[level]("**{}** — {}".format(title, body))

html = SJ.render_html(r, s_name, p_name).replace("Casa Equestre", shop_name)
st.download_button("⬇︎  Download the full report (HTML — open & print to PDF)", data=html,
                   file_name="{}_dead_stock_report.html".format(shop_name.replace(" ", "_")),
                   mime="text/html", type="primary")
