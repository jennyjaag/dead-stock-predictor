"""
cs_lib.py -- shared brain for the EquiSphere multi-page app.

Holds: theme CSS, the sidebar brand, session-state setup, data loading, the
"freed since last visit" snapshot, small formatting helpers, and the two big
renderers (dead-stock report + buy-plan) so every page stays thin. No analytics
live here that weren't already in shopify_join / master_load / buy_plan_view.
"""

import io
import json
import os
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import shopify_join as SJ
import master_load as ML
import buy_plan_view as BP
import casa_report as C

APP_NAME = "EquiSphere"
COMPANY = "Equine Edge"    # parent — shown as "EquiSphere by Equine Edge" (easy to change)
TAGLINE = "Dead-stock intelligence for independent tack shops"
TODAY = date.today()
SNAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cs_snapshots.json")
DEMO_SALES = "demo_data/demo_sales.csv"
DEMO_PRODS = "demo_data/demo_products.csv"


# ---------------------------------------------------------------------------
# state + theme
# ---------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    ss.setdefault("shop_name", "Your shop")
    ss.setdefault("currency", "$")
    ss.setdefault("min_risk", 0)
    ss.setdefault("min_cash", 0)
    ss.setdefault("variant_view", False)
    ss.setdefault("lead_time_weeks", 4)
    ss.setdefault("grace_weeks", 8)          # new stock younger than this isn't "dead"
    ss.setdefault("seasonal_types", [])      # product types held back from the red list
    ss.setdefault("data", None)
    ss.setdefault("kind", None)
    ss.setdefault("names", None)
    ss.setdefault("snapshotted", False)
    ss.setdefault("pro_plan", False)      # premium tier (gates the Trade-show buy AI)
    ss.setdefault("cat_filter", [])       # dead-stock filters
    ss.setdefault("brand_filter", [])
    ss.setdefault("action_filter", [])
    ss.setdefault("prod_search", "")
    ss.setdefault("threads", {})          # swap-network messages: {shop: [ {from, text} ]}
    if not ss.get("threads_seeded"):      # a couple of demo conversations to start with
        ss["threads"] = {
            "Willow Farm Tack": [{"from": "them",
                "text": "Hi! We keep selling out of Animo show coats — saw you've got some sitting. "
                        "Would you swap for fly rugs?"}],
            "Sunnyside Equestrian": [{"from": "them",
                "text": "Interested in your Horse Pilot AirVests. What would you want in return?"}],
        }
        ss["threads_seeded"] = True
    # push settings into the engine modules (used on the next data load)
    C.CURRENCY = ss["currency"]
    SJ.GRACE_WEEKS = int(ss["grace_weeks"])
    SJ.SEASONAL_TYPES = list(ss["seasonal_types"])
    ML.NEW_DAYS = int(ss["grace_weeks"]) * 7
    ML.SEASONAL_TYPES = list(ss["seasonal_types"])


def add_message(store, text, sender="you"):
    st.session_state.setdefault("threads", {}).setdefault(store, []).append(
        {"from": sender, "text": text})


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def _auth_users():
    """Logins live in secrets ([auth.users]); empty = no gate (local dev / pre-setup)."""
    try:
        return dict(st.secrets["auth"]["users"])
    except Exception:
        return {}


def require_login():
    """Gate the whole app behind a login when logins are configured in secrets."""
    users = _auth_users()
    if not users or st.session_state.get("authed_user"):
        return
    st.markdown("<div class='cs-brand' style='font-size:22px'>🐴 {} <span class='cs-by'>by {}</span></div>"
                .format(APP_NAME, COMPANY), unsafe_allow_html=True)
    st.markdown("<div class='cs-hero'><div class='num'>Log in</div>"
                "<div class='sub'>Access is for subscribed tack shops.</div></div>", unsafe_allow_html=True)
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Log in", type="primary"):
        if u in users and str(users[u]) == p:
            st.session_state["authed_user"] = u
            st.rerun()
        else:
            st.error("Incorrect username or password.")
    st.caption("Not a member yet? Subscribe on the Equine Edge site to get your login.")
    st.stop()


def sidebar_brand():
    st.sidebar.markdown(
        "<div class='cs-brand'>🐴 {}<span class='cs-by'>by {}</span></div>"
        "<div class='cs-tag'>{}</div>".format(APP_NAME, COMPANY, TAGLINE),
        unsafe_allow_html=True)
    user = st.session_state.get("authed_user")
    if user:
        lc1, lc2 = st.sidebar.columns([2, 1])
        lc1.caption("👤 {}".format(user))
        if lc2.button("Log out"):
            del st.session_state["authed_user"]
            st.rerun()
    if has_data():
        ss = st.session_state
        src = {"demo": "demo data", "master": "master file", "upload": "two CSVs",
               "shopify": "live Shopify"}.get(ss["kind"], "—")
        st.sidebar.caption("📂 Loaded: {} · {}".format(ss["shop_name"], src))
    st.sidebar.divider()


def page_title(title, subtitle, demo=False):
    badge = " <span class='demo-badge'>⚠️ DEMO DATA</span>" if demo else ""
    st.markdown("<div class='page-title'>{}{}</div><div class='page-sub'>{}</div>".format(
        title, badge, subtitle), unsafe_allow_html=True)


def problem_note(md):
    """The pain this module solves (with the poll % where relevant)."""
    st.markdown("<div class='cs-problem'>🎯 {}</div>".format(md), unsafe_allow_html=True)


def pricing_note(md):
    """Who pays / business model — shown at the foot of each module page."""
    st.markdown("<div class='cs-pricing'>💷 <b>Business model:</b> {}</div>".format(md), unsafe_allow_html=True)


def how_it_works(points):
    st.markdown("##### How it works")
    st.markdown("\n".join("- {}".format(p) for p in points))


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------
def money(v):
    return SJ.money(v)      # respects C.CURRENCY


def cover_txt(c):
    # never render a raw ∞ — zero-sales items would divide by zero
    if c is None or c == float("inf") or c > 600:
        return "no recent sales"
    return "{:.0f} mo".format(c)


def badge_level(risk):
    if risk >= C.MARKDOWN_SCORE:
        return "red"
    if risk >= C.WATCH_SCORE:
        return "amber"
    return "green"


def recommend(x):
    if x.get("action") == "New — too early to tell":
        return "New — too early to tell", "watch"
    if x.get("action") == "Seasonal — hold":
        return "Seasonal — hold (out of season)", "—"
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
    cash = money(x["cash"]) if x["cash"] is not None else "cost unknown"
    lead = "0 sales in 12 months" if x["u12"] == 0 else "{:.0f} sold last year".format(x["u12"])
    return "{} · {} of cover · {} tied up".format(lead, cover_txt(x["cover"]), cash)


# ---------------------------------------------------------------------------
# data loading + access
# ---------------------------------------------------------------------------
def has_data():
    return st.session_state.get("data") is not None


def get_r():
    return st.session_state.get("data")


def set_data(r, kind, names):
    ss = st.session_state
    ss["data"], ss["kind"], ss["names"] = r, kind, names


def compute_from(kind, s_src, p_src):
    """kind in {'master','upload','demo'}. Returns the result dict or raises."""
    if kind == "master":
        return ML.load_master(s_src)
    sales = SJ.load_sales(s_src)
    prod = SJ.load_products(p_src)
    if not sales:
        raise ValueError("The sales file is missing 'Product title' / 'Net items sold'.")
    if not prod:
        raise ValueError("The products file is missing 'Handle' / 'Title' / 'Variant Inventory Qty'.")
    return SJ.compute(prod, sales)


def require_data():
    """Guard for tool pages — if no data, point the user back to Home."""
    if not has_data():
        st.info("No data loaded yet. Head to **Home** to upload your files (or try the demo).")
        st.page_link("views/home.py", label="Go to Home", icon="🏠")
        st.stop()


def is_pro():
    return bool(st.session_state.get("pro_plan"))


def require_pro(feature, price, benefits):
    """Paywall for premium tools. Renders an upsell and stops unless Pro is on."""
    if is_pro():
        return
    st.markdown("<div class='cs-hero'><div class='num'>🔒 {} is a Pro feature</div>"
                "<div class='sub'>{}</div></div>".format(feature, price), unsafe_allow_html=True)
    st.markdown("##### What you get with Pro")
    st.markdown("\n".join("- {}".format(b) for b in benefits))
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🔓  Unlock (demo)", type="primary"):
            st.session_state["pro_plan"] = True
            st.rerun()
    with c2:
        st.caption("Demo only — 'Unlock' flips on the Pro plan for this session. Real billing comes later; "
                   "you can also toggle Pro in Settings.")
    st.stop()


# ---------------------------------------------------------------------------
# "freed since last visit" snapshot (small local JSON, keyed by shop name)
# ---------------------------------------------------------------------------
def _load_snaps():
    try:
        with open(SNAP_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_snaps(d):
    try:
        with open(SNAP_FILE, "w") as f:
            json.dump(d, f)
    except Exception:
        pass


def _email_cfg():
    """Read SMTP settings from Streamlit secrets (set in deployment). Never from chat."""
    try:
        return dict(st.secrets["email"])
    except Exception:
        return {}


def email_configured():
    c = _email_cfg()
    return bool(c.get("smtp_host") and c.get("smtp_user") and c.get("smtp_pass"))


def send_email(to, subject, body, attachment_bytes=None, filename="report.csv"):
    """Send via the SMTP account configured in secrets. Returns (ok, message)."""
    import smtplib
    import ssl
    from email.message import EmailMessage
    c = _email_cfg()
    if not email_configured():
        return False, "Email isn't set up yet (no SMTP configured)."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = c.get("from", c["smtp_user"])
    msg["To"] = to
    msg.set_content(body)
    if attachment_bytes is not None:
        msg.add_attachment(attachment_bytes, maintype="text", subtype="csv", filename=filename)
    try:
        with smtplib.SMTP(c["smtp_host"], int(c.get("smtp_port", 587))) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(c["smtp_user"], c["smtp_pass"])
            s.send_message(msg)
        return True, "Sent to {}.".format(to)
    except Exception as e:
        return False, "Send failed: {}".format(e)


def freed_since_last_visit(shop, current_cash):
    """Return $ freed vs the last saved snapshot (once per session), else None."""
    if st.session_state.get("snapshotted"):
        return st.session_state.get("freed_val")
    snaps = _load_snaps()
    prev = snaps.get(shop)
    freed = None
    if prev is not None and prev.get("cash_at_risk") is not None:
        freed = prev["cash_at_risk"] - current_cash
    snaps[shop] = {"cash_at_risk": current_cash, "ts": TODAY.isoformat()}
    _save_snaps(snaps)
    st.session_state["snapshotted"] = True
    st.session_state["freed_val"] = freed
    return freed


# ===========================================================================
# RENDERERS
# ===========================================================================
def _hl(v):
    if not isinstance(v, (int, float)):
        return ""
    if v >= C.MARKDOWN_SCORE:
        return "background-color:#f6e1dd;color:#b23a2e;font-weight:700"   # at risk (red)
    if v >= C.WATCH_SCORE:
        return "background-color:#fbf0d8;color:#94661a;font-weight:700"   # watch (amber)
    return "background-color:#e9e7df;color:#6b7268;font-weight:700"       # healthy (neutral grey)


_SHEET = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Dead-stock action sheet</title>
<style>
  @page {{ size:A4; margin:14mm; }}
  * {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }}
  body {{ font-family:-apple-system,Arial,sans-serif; color:#16241f; font-size:12px; margin:0; }}
  h1 {{ font-size:19px; margin:0 0 2px; }}
  .sub {{ color:#5a6b5e; font-size:11px; margin-bottom:12px; }}
  .tot {{ background:#1F5A43; color:#fff; padding:8px 12px; border-radius:8px; display:inline-block; font-weight:700; margin-bottom:14px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; font-size:9px; text-transform:uppercase; letter-spacing:.04em; color:#5a6b5e; border-bottom:1.5px solid #16241f; padding:5px; }}
  td {{ padding:8px 5px; border-bottom:0.5px solid #d9d5c8; vertical-align:top; }}
  tr {{ page-break-inside:avoid; }}
  td.p {{ font-weight:600; }} td.p .w {{ display:block; font-weight:400; color:#5a6b5e; font-size:10px; margin-top:2px; }}
  td.a {{ font-weight:600; white-space:nowrap; }} td.a .d {{ display:block; font-weight:400; color:#8a6100; font-size:10px; }}
  td.n {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .box {{ display:inline-block; width:15px; height:15px; border:1.5px solid #16241f; border-radius:3px; }}
  .foot {{ margin-top:12px; font-size:9px; color:#9a9686; }}
  @media print {{ .noprint {{ display:none; }} }}
</style></head><body>
  <button class="noprint" onclick="window.print()" style="float:right;padding:8px 16px;border-radius:8px;border:1px solid #1F5A43;background:#1F5A43;color:#fff;font-weight:700;cursor:pointer">🖨️ Print</button>
  <h1>Dead-stock action sheet</h1>
  <div class="sub">{shop} &middot; {date} &middot; {count} items to act on</div>
  <div class="tot">💰 {total} of cash frozen in these items</div>
  <table><thead><tr><th>Done</th><th>Product &amp; why</th><th>Action</th><th class="n">Cash</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="foot">EquiSphere by Equine Edge &middot; tick each item as you mark it down or clear it.</div>
</body></html>"""


def action_sheet_html(items, shop):
    rows = ""
    for x in items:
        act, when = recommend(x)
        rows += ("<tr><td><span class='box'></span></td>"
                 "<td class='p'>{p}<span class='w'>{w}</span></td>"
                 "<td class='a'>{a}{d}</td><td class='n'>{c}</td></tr>").format(
            p=C.esc(x["title"]), w=C.esc(why(x)), a=C.esc(act),
            d=("<span class='d'>by {}</span>".format(when) if when not in ("—", "watch", "Now") else ""),
            c=money(x["cash"]) if x["cash"] is not None else "—")
    return _SHEET.format(shop=C.esc(shop), date=TODAY.strftime("%d %b %Y"), count=len(items),
                         total=money(sum(x["cash"] for x in items if x["cash"])), rows=rows)


def _export_and_share(df, shop):
    """Download (CSV/Excel) and email the filtered product list."""
    if df is None or not len(df):
        return
    st.markdown("##### Export &amp; share this list")
    st.caption("Exports exactly what's filtered above ({} rows).".format(len(df)))
    fname = shop.replace(" ", "_") or "shop"
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    xbuf = io.BytesIO()
    df.to_excel(xbuf, index=False)
    e1, e2, e3 = st.columns([1, 1, 3])
    e1.download_button("⬇︎ CSV", csv_bytes, file_name=fname + "_products.csv", mime="text/csv",
                       use_container_width=True)
    e2.download_button("⬇︎ Excel", xbuf.getvalue(), file_name=fname + "_products.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    with e3:
        to = st.text_input("Email this list to", placeholder="name@shop.com",
                           key="email_to", label_visibility="collapsed")
        if st.button("✉️  Email the list", disabled=not to):
            ok, msg = send_email(
                to, "{} — dead-stock product list".format(shop),
                "Attached is your filtered dead-stock product list ({} rows) from EquiSphere.".format(len(df)),
                csv_bytes, fname + "_products.csv")
            (st.success if ok else st.warning)(msg)
            if not ok and not email_configured():
                st.caption("Email sending isn't switched on for this app yet. Download the CSV/Excel above and "
                           "attach it — or add SMTP details to the app's secrets to enable one-click send "
                           "(see DEPLOY.md).")


def render_deadstock(r):
    ss = st.session_state
    shop = ss["shop_name"]

    top_by_cash = sorted([x for x in r["at_risk"] if x["cash"]], key=lambda x: x["cash"], reverse=True)
    free_top10 = sum(x["cash"] for x in top_by_cash[:10])

    st.markdown(
        "<div class='cs-hero'><div class='num'>{} of your cash is frozen in dead stock.</div>"
        "<div class='sub'>{} · {} at-risk products · as of {}</div></div>".format(
            money(r["cash_at_risk"]), shop, r["at_risk_count"], TODAY.strftime("%d %b %Y")),
        unsafe_allow_html=True)

    finite = [x["cover"] for x in r["at_risk"] if x["cover"] != float("inf") and x["cover"] <= 600]
    avg_cov = "{:.0f} mo".format(sum(finite) / len(finite)) if finite else "no recent sales"
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cash at risk", money(r["cash_at_risk"]))
    k2.metric("Dead / at-risk items", r["at_risk_count"],
              "{} genuinely dead".format(r["dead_count"]), delta_color="off")
    k3.metric("Avg. cover (at-risk)", avg_cov)
    k4.metric("Free up (top 10)", money(free_top10))

    freed = freed_since_last_visit(shop, r["cash_at_risk"])
    if freed and abs(freed) >= 1:
        if freed > 0:
            st.caption("📉  **{}** of dead-stock cash freed since your last visit — nice work.".format(money(freed)))
        else:
            st.caption("📈  **{}** more cash frozen since your last visit.".format(money(abs(freed))))
    held = len(r.get("too_new", [])) + len(r.get("seasonal_held", []))
    if held:
        st.caption("🛡️  {} products held back (too new or seasonal) and **not** counted as dead — "
                   "tune the grace period in Settings.".format(held))

    # ---- Filter panel — everything to slice the report lives here ----
    cats = sorted({x["type"] for x in r["in_stock"] if x["type"] and x["type"] != "Uncategorised"})
    brands = sorted({x["vendor"] for x in r["in_stock"] if x["vendor"]})
    actions = sorted({x["action"] for x in r["in_stock"]})
    # drop any stale selections not in this dataset
    ss["cat_filter"] = [c for c in ss.get("cat_filter", []) if c in cats]
    ss["brand_filter"] = [b for b in ss.get("brand_filter", []) if b in brands]
    ss["action_filter"] = [a for a in ss.get("action_filter", []) if a in actions]

    with st.expander("🔎 Filter the report", expanded=True):
        a1, a2, a3 = st.columns(3)
        a1.slider("Risk score ≥", 0, 100, step=5, key="min_risk")
        a2.number_input("Cash tied up ≥ ({})".format(C.CURRENCY), min_value=0, step=50, key="min_cash")
        a3.text_input("Search product / brand", key="prod_search", placeholder="type to search…")
        b1, b2, b3 = st.columns(3)
        with b1:
            if cats:
                st.multiselect("Category", cats, key="cat_filter", placeholder="All categories")
        with b2:
            if brands:
                st.multiselect("Brand", brands, key="brand_filter", placeholder="All brands")
        with b3:
            st.multiselect("Action", actions, key="action_filter", placeholder="All actions")

    min_risk, min_cash, variant_view = ss["min_risk"], ss["min_cash"], ss["variant_view"]
    cat_sel, brand_sel, action_sel = ss["cat_filter"], ss["brand_filter"], ss["action_filter"]
    q = (ss.get("prod_search") or "").lower()

    shown = []
    for x in r["in_stock"]:
        if x["risk"] < min_risk or (x["cash"] or 0) < min_cash:
            continue
        if cat_sel and x["type"] not in cat_sel:
            continue
        if brand_sel and x["vendor"] not in brand_sel:
            continue
        if action_sel and x["action"] not in action_sel:
            continue
        if q and q not in x["title"].lower() and q not in (x["vendor"] or "").lower():
            continue
        shown.append(x)
    st.caption("**{} of {}** in-stock products match your filters.".format(len(shown), r["instock_count"]))

    st.subheader("The dead-stock map")
    st.caption("Bottom-right = healthy (sells fast). Top-left = dead stock (barely sells, months of cover). "
               "Bigger dot = more cash tied up.")
    cc1, cc2 = st.columns([3, 2])
    with cc1:
        if shown:
            cdf = pd.DataFrame([{
                "Product": x["title"], "Sold/yr": x["u12"],
                "Cover (mo)": min(x["cover"], 60) if x["cover"] != float("inf") else 60,
                "Risk": ("Act now" if x["risk"] >= C.MARKDOWN_SCORE else
                         "Watch" if x["risk"] >= C.WATCH_SCORE else "Healthy"),
                "Cash": x["cash"] or 0,
            } for x in shown])
            chart = (alt.Chart(cdf).mark_circle(opacity=0.75).encode(
                x=alt.X("Sold/yr:Q", title="Units sold last year (velocity)"),
                y=alt.Y("Cover (mo):Q", title="Months of cover (capped at 60)"),
                size=alt.Size("Cash:Q", scale=alt.Scale(range=[30, 900]), legend=None),
                color=alt.Color("Risk:N", scale=alt.Scale(
                    domain=["Act now", "Watch", "Healthy"], range=["#D1483B", "#E0A030", "#b8b3a4"]),
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
            catdf = pd.DataFrame(sorted(cat.items(), key=lambda kv: kv[1], reverse=True)[:8],
                                 columns=["Category", "Cash at risk"]).set_index("Category")
            st.caption("Cash at risk by category")
            st.bar_chart(catdf, horizontal=True, color="#D1483B", height=340)
        else:
            st.caption("Category breakdown not available for this file.")

    st.markdown("<div class='cs-quickwin'>💡 If you act on the top 10 items, you free up "
                "<b>{}</b> to reinvest in the stock that actually sells.</div>".format(money(free_top10)),
                unsafe_allow_html=True)

    st.subheader("Do this first — your action list")
    act_items = [x for x in shown if x["risk"] >= C.AT_RISK_SCORE][:25]
    if act_items:
        rows = ""
        for x in act_items:
            lvl = badge_level(x["risk"])
            action, when = recommend(x)
            rows += ("<tr><td class='prod'>{n}<span class='why'>{v} · {t}<br>{w}</span></td>"
                     "<td><span class='pill {lvl}'>{r}</span></td><td class='num'>{cash}</td>"
                     "<td class='act'>{a}<span class='date'>{d}</span></td></tr>").format(
                n=C.esc(x["title"]), v=C.esc(x["vendor"]), t=C.esc(x["type"]), w=C.esc(why(x)),
                lvl=lvl, r=x["risk"], cash=money(x["cash"]) if x["cash"] is not None else "—",
                a=C.esc(action), d=when)
        st.markdown("<div style='overflow-x:auto'><table class='cs'><thead><tr>"
                    "<th>Product &amp; why</th><th>Risk</th><th class='num'>Cash tied up</th>"
                    "<th>Recommended action</th></tr></thead><tbody>{}</tbody></table></div>".format(rows),
                    unsafe_allow_html=True)
        at_risk_shown = [x for x in shown if x["risk"] >= C.AT_RISK_SCORE]
        st.download_button(
            "🖨️  Printable action sheet (walk the floor)",
            data=action_sheet_html(at_risk_shown, shop),
            file_name="{}_action_sheet.html".format(shop.replace(" ", "_")),
            mime="text/html",
            help="A clean checklist with tick-boxes, action and date — open it and print (or save as PDF).")
    else:
        st.success("Nothing above the risk threshold — inventory looks healthy. 🎉")

    export_df = None
    has_variants = any(len(x.get("variants") or []) for x in shown)
    if variant_view and has_variants:
        # option dimensions present (Size, Colour, …) → a filter for each
        opt_values = {}
        for x in shown:
            for v in (x.get("variants") or []):
                for nm, val in (v.get("options") or {}).items():
                    opt_values.setdefault(nm, set()).add(val)
        selected_opts = {}
        if opt_values:
            fcols = st.columns(len(opt_values))
            for i, (nm, vals) in enumerate(sorted(opt_values.items())):
                with fcols[i]:
                    selected_opts[nm] = st.multiselect(nm, sorted(vals), key="vopt_" + nm,
                                                       placeholder="All " + nm)

        def variant_ok(v):
            if v["stock"] <= 0:
                return False
            for nm, chosen in selected_opts.items():
                if chosen and (v.get("options") or {}).get(nm) not in chosen:
                    return False
            return True

        vrows = []
        for x in shown:
            for v in (x.get("variants") or []):
                if not variant_ok(v):
                    continue
                vcash = v["stock"] * v["cost"] if v["cost"] else None
                if (vcash or 0) < min_cash:
                    continue
                vrows.append({"Product": x["title"], "Variant": v["label"], "Brand": x["vendor"],
                              "Risk (product)": x["risk"], "Variant stock": int(v["stock"]),
                              "Cover (product)": cover_txt(x["cover"]), "Sold/yr (product)": int(x["u12"]),
                              "Variant cash ($)": None if vcash is None else round(vcash),
                              "Action": recommend(x)[0]})
        with st.expander("📋 All in-stock **variants** (size/colour) — {} shown".format(len(vrows)), expanded=True):
            st.caption("Filter by size / colour above. Stock & cash are per variant; velocity/risk are the "
                       "product's overall figures.")
            vdf = pd.DataFrame(vrows)
            export_df = vdf
            if len(vdf):
                st.dataframe(vdf.style.map(_hl, subset=["Risk (product)"]), use_container_width=True,
                             hide_index=True, height=460)
            else:
                st.info("No variants match the current filters.")
    else:
        if variant_view and not has_variants:
            st.info("ℹ️ Variant breakdown needs the two-CSV upload (the master file is product-level).")
        with st.expander("📋 All in-stock products (sortable) — {} shown".format(len(shown))):
            df = pd.DataFrame([{
                "Product": x["title"], "Brand": x["vendor"], "Type": x["type"], "Risk": x["risk"],
                "Stock": int(x["stock"]), "Cover": cover_txt(x["cover"]), "Sold/yr": int(x["u12"]),
                "Cash @cost ($)": None if x["cash"] is None else round(x["cash"]),
                "Recommended action": recommend(x)[0], "By when": recommend(x)[1],
                "Why": why(x), "Status": x["status"]} for x in shown])
            export_df = df
            if len(df):
                st.dataframe(df.style.map(_hl, subset=["Risk"]), use_container_width=True,
                             hide_index=True, height=460)
            else:
                st.info("No products match the current filters. Lower the thresholds in Settings.")

    _export_and_share(export_df, shop)

    with st.expander("⚠︎ Data-quality flags & how the columns were mapped"):
        for title, level, body in r["flags"]:
            {"critical": st.error, "warn": st.warning, "info": st.info}[level]("**{}** — {}".format(title, body))

    names = st.session_state.get("names") or ("sales", "products")
    html = SJ.render_html(r, names[0], names[1]).replace("Casa Equestre", shop)
    st.download_button("⬇︎  Download the full report (HTML — open & print to PDF)", data=html,
                       file_name="{}_dead_stock_report.html".format(shop.replace(" ", "_")),
                       mime="text/html", type="primary")


def render_buyplan(r, reorder_only=False):
    ss = st.session_state
    bp = BP.compute_buyplan(r["in_stock"])
    lead = ss["lead_time_weeks"]

    if not bp["has_windows"]:
        st.info("ℹ️ This upload only carries a 12-month sales total, so the plan uses velocity + cover "
                "(no recent-momentum or seasonality). Upload the **master file** for demand momentum & trend.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("To reinvest", money(bp["total_buy"]), "{} to reorder".format(len(bp["reorder"])), delta_color="off")
    k2.metric("Projected sell-through", money(bp["total_rev"]))
    k3.metric("Stop buying", len(bp["stop"]), "prevent future dead stock", delta_color="off")
    k4.metric("Cash frozen there", money(bp["stop_cash"]))

    if bp["seasons"] and not reorder_only:
        st.subheader("Demand momentum by category")
        st.caption("Recent run-rate vs the yearly average. Heating up → buy ahead; cooling → ease off.")
        sdf = pd.DataFrame([{"Category": s["cat"], "Trend": s["label"],
                             "vs year avg": "{:+.0f}%".format((s["momentum"] - 1) * 100)} for s in bp["seasons"]])
        st.dataframe(sdf, use_container_width=True, hide_index=True, height=min(320, 44 + 30 * len(sdf)))

    st.subheader("🟢 Reorder now — proven sellers running low")
    st.caption("Quantity buys back to ~4 months of cover. Place orders ~{} weeks ahead of when you need them "
               "(your lead time — change it in Settings).".format(lead))
    if bp["reorder"]:
        rdf = pd.DataFrame([{
            "Product": x["title"], "Brand": x["vendor"], "Sold/yr": int(x["u12"]),
            "In stock": int(x["stock"]), "Cover": cover_txt(x["cover"]), "Reorder qty": x["reorder_qty"],
            "Buy cost ($)": None if x["buy_cost"] is None else round(x["buy_cost"]),
            "Sell-thru value ($)": None if x["rev_potential"] is None else round(x["rev_potential"]),
        } for x in bp["reorder"]])
        st.dataframe(rdf, use_container_width=True, hide_index=True, height=430)
    else:
        st.info("Nothing needs reordering right now.")

    if not reorder_only:
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


CSS = """
<style>
  .block-container {padding-top: 2rem; max-width: 1200px;}
  #MainMenu, footer {visibility: hidden;}
  /* Hard guarantee against headline clipping: the page never scrolls
     sideways, flex children may shrink (min-width:0) rather than expand to
     their content width, and all headings wrap. */
  html, body {overflow-x: hidden !important;}
  [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"],
  [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"], [data-testid="stColumn"],
  [data-testid="stElementContainer"], .block-container {min-width: 0 !important; max-width: 100% !important;}
  [data-testid="stMain"] {overflow-x: hidden;}
  .page-title, .page-sub, .cs-hero .num, .cs-hero .sub, h1, h2, h3, p {
    overflow-wrap: anywhere; word-break: break-word; white-space: normal;}
  .cs-brand {font-size: 16px; font-weight: 800; color: #1F5A43; letter-spacing:.02em;}
  .cs-by {font-size:11px; font-weight:600; color:#B07B4C; margin-left:6px;}
  .cs-tag {color:#5a6b5e; font-size:12px; margin-top:-3px;}
  .page-title {font-size: 24px; font-weight: 800; color:#16241F;}
  .page-sub {color:#5a6b5e; font-size:13.5px; margin: 2px 0 16px;}
  .demo-badge {font-size:11px; font-weight:700; color:#94661a; background:#fbf0d8;
               padding:2px 8px; border-radius:10px; vertical-align:middle; margin-left:8px;}
  .cs-problem {background:#f6efe1; border:1px solid #e6d8bd; border-radius:12px; padding:13px 16px;
               font-size:14px; color:#6a5733; margin: 2px 0 16px;}
  .cs-pricing {background:#eaf1ec; border:1px solid #cfe0d5; border-radius:12px; padding:12px 16px;
               font-size:13.5px; color:#1F5A43; margin: 18px 0 6px;}
  .cs-hero {background: linear-gradient(105deg,#16241F,#1F5A43); color:#fff; border-radius:16px;
            padding: 24px 28px; margin: 4px 0 18px; border-left:5px solid #B07B4C;}
  .cs-hero .num {font-size: 40px; font-weight: 800; line-height:1.05;}
  .cs-hero .sub {font-size: 14px; opacity:.88; margin-top:6px;}
  .cs-quickwin {background:#eaf1ec; border:1px solid #cfe0d5; border-radius:12px;
                padding:14px 18px; font-size:15px; color:#16241F; margin: 4px 0 18px;}
  .cs-quickwin b {color:#1F5A43;}
  div[data-testid="stMetric"] {background:#fbfaf5; border:1px solid #e7e1d3; border-radius:12px; padding:14px 16px;}
  .jump {display:block; background:#fbfaf5; border:1px solid #e7e1d3; border-radius:14px; padding:18px 20px;
         text-decoration:none; height:100%;}
  .jump h4 {margin:0 0 4px; color:#16241F; font-size:16px;}
  .jump p {margin:0; color:#5a6b5e; font-size:12.5px;}
  .pill {display:inline-block; padding:3px 10px; border-radius:20px; font-weight:700; font-size:12px;}
  .pill.red{background:#f6e1dd;color:#b23a2e;} .pill.amber{background:#fbf0d8;color:#94661a;} .pill.green{background:#e9e7df;color:#6b7268;}
  table.cs {width:100%; border-collapse:collapse; font-size:13px;}
  table.cs th{text-align:left; color:#5a6b5e; font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; padding:8px 10px; border-bottom:1px solid #e0dccf;}
  table.cs td{padding:9px 10px; border-bottom:1px solid #ece7db; vertical-align:top;}
  table.cs td.prod{font-weight:600; color:#16241F;}
  table.cs .why{color:#5a6b5e; font-size:11.5px; display:block; margin-top:2px;}
  table.cs td.num{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap;}
  table.cs td.act{white-space:nowrap; font-weight:600;}
  table.cs td.act .date{display:block; color:#9a9686; font-weight:400; font-size:11px;}
  .msg-row {display:flex; margin:6px 0;}
  .msg-them {background:#fff; border:1px solid #e0dccf; border-radius:14px 14px 14px 4px; padding:9px 13px; max-width:78%; font-size:13.5px; color:#16241F;}
  .msg-you {background:#1F5A43; color:#fff; border-radius:14px 14px 4px 14px; padding:9px 13px; max-width:78%; margin-left:auto; font-size:13.5px;}
</style>
"""
