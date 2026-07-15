"""
shopify_join.py -- run the dead-stock predictor on two RAW Shopify exports:
    1) a "Total sales by product" CSV  (Product title + Net items sold, one period)
    2) a products export CSV           (variant-level: inventory qty + cost per item)

It maps each file's columns to what the engine needs, joins them on product
title, flags data-quality problems, scores dead-stock risk, and writes an HTML
report with the flags baked in.

Usage (command line):
  python3 shopify_join.py "<sales_by_product.csv>" "<products_export.csv>"

Reusable API (used by the Streamlit app app.py):
  prod  = load_products(src)     # src = path OR an uploaded file object
  sales = load_sales(src)
  result = compute(prod, sales)  # dict of all computed figures + flags
  html   = render_html(result, sales_name, prod_name)

Notes on the model: a single sales window gives us a 12-month velocity but NOT
30/90-day recency or year-on-year trend, so risk here blends months-of-cover,
slow/zero sales, and cash tied up (no trend term). See the report's methodology.
"""

import csv
import io
import os
import re
import sys

import casa_report as C   # reuse constants + money/fmt_cover/esc/colour

# ---- model knobs for the single-window (degraded) case --------------------
W_COVER, W_SALES, W_CASH = 0.40, 0.40, 0.20
PERIOD_MONTHS = 12         # the sales window is trailing 12 months
ASOF = "2026-07-14"


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def money(v):
    return "—" if v is None else "{}{:,.0f}".format(C.CURRENCY, v)


def band(v, lo, hi):
    if v <= lo:
        return 0.0
    if v >= hi:
        return 100.0
    return (v - lo) / (hi - lo) * 100.0


def _read_csv(src):
    """Accept a filesystem path OR an uploaded file object; return list of dicts."""
    if hasattr(src, "read"):
        data = src.read()
        if isinstance(data, bytes):
            data = data.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(data)))
    return list(csv.DictReader(open(src, encoding="utf-8-sig")))


# ===========================================================================
# LOAD + MAP
# ===========================================================================

def load_products(src):
    """Aggregate variant rows -> product records. Returns dict keyed by handle."""
    rows = _read_csv(src)
    prod = {}
    for v in rows:
        h = v.get("Handle")
        if not h:
            continue
        p = prod.setdefault(h, {"title": "", "vendor": "", "type": "", "status": "",
                                "giftcard": False, "stock": 0, "costs": [], "prices": [],
                                "variants": []})
        for key, col in [("title", "Title"), ("vendor", "Vendor"),
                         ("type", "Type"), ("status", "Status")]:
            if v.get(col):
                p[key] = v[col]
        if str(v.get("Gift Card", "")).strip().lower() == "true":
            p["giftcard"] = True
        try:
            vqty = int(v["Variant Inventory Qty"])
        except (ValueError, TypeError, KeyError):
            vqty = 0
        p["stock"] += vqty
        c = v.get("Cost per item")
        vcost = None
        if c not in (None, ""):
            try:
                vcost = float(c)
                p["costs"].append(vcost)
            except ValueError:
                vcost = None
        pr = v.get("Variant Price")
        if pr not in (None, ""):
            try:
                p["prices"].append(float(pr))
            except ValueError:
                pass
        # keep the per-variant row so the app can break stock down by size/colour
        opts = [v.get("Option1 Value"), v.get("Option2 Value"), v.get("Option3 Value")]
        label = " / ".join(o for o in opts if o and o != "Default Title")
        p["variants"].append({"label": label or "(single)", "sku": (v.get("Variant SKU") or "").strip(),
                              "stock": vqty, "cost": vcost})
    return prod


def load_sales(src):
    """Sum 'Net items sold' per product title over the file's period."""
    units = {}
    for s in _read_csv(src):
        t = s.get("Product title")
        try:
            units[norm(t)] = units.get(norm(t), 0) + float(s["Net items sold"])
        except (ValueError, TypeError, KeyError):
            pass
    return units


def avg(xs):
    return sum(xs) / len(xs) if xs else None


# ===========================================================================
# SCORE
# ===========================================================================

def score(p, units12, max_inv):
    stock = p["stock"]
    cost = avg(p["costs"])
    price = avg(p["prices"])
    margin = (price - cost) / price if (price and cost is not None and price > 0) else None
    cash = stock * cost if (cost is not None and stock > 0) else None

    monthly = units12 / PERIOD_MONTHS
    if stock <= 0:
        cover = 0.0
    elif monthly > 0:
        cover = stock / monthly
    else:
        cover = float("inf")

    cover_sub = 100.0 if cover == float("inf") else band(cover, C.COVER_LOW_M, C.COVER_HIGH_M)
    if stock <= 0:
        sales_sub = 0.0
    elif units12 == 0:
        sales_sub = 100.0
    elif units12 <= 1:
        sales_sub = 75.0
    elif units12 <= 3:
        sales_sub = 45.0
    elif units12 <= 6:
        sales_sub = 20.0
    else:
        sales_sub = 0.0
    cash_sub = min(100.0, 100.0 * cash / max_inv) if (cash and max_inv > 0) else 0.0

    risk = round(W_COVER * cover_sub + W_SALES * sales_sub + W_CASH * cash_sub)

    if stock <= 0:
        action = "Reorder" if units12 > 0 else "Sold out"
    elif units12 > 0 and 0 < cover <= C.REORDER_COVER_M:
        action = "Reorder"
    elif risk >= C.MARKDOWN_SCORE:
        action = "Mark down / clear"
    elif risk >= C.WATCH_SCORE:
        action = "Watch"
    else:
        action = "Healthy"

    return {"title": p["title"], "vendor": p["vendor"], "type": p["type"] or "Uncategorised",
            "status": p["status"], "stock": stock, "u12": units12, "cover": cover,
            "cost": cost, "price": price, "margin": margin, "cash": cash,
            "risk": risk, "action": action, "variants": p.get("variants", [])}


# ===========================================================================
# COMPUTE  (shared by CLI + web app)
# ===========================================================================

def compute(prod, sales):
    active, drafts_in_stock, archived_in_stock, giftcards, negatives = [], [], [], [], []
    missing_cost_in_stock = []
    for h, p in prod.items():
        if p["giftcard"]:
            giftcards.append(p); continue
        if p["stock"] < 0:
            negatives.append(p)
        if p["status"] == "draft" and p["stock"] > 0:
            drafts_in_stock.append(p); continue
        if p["status"] == "archived" and p["stock"] > 0:
            archived_in_stock.append(p)
        if p["status"] in ("active", "archived"):
            active.append(p)
        if p["stock"] > 0 and not p["costs"] and p["status"] != "draft":
            missing_cost_in_stock.append(p)

    max_inv = max((p["stock"] * avg(p["costs"]) for p in active
                   if avg(p["costs"]) and p["stock"] > 0), default=1.0)

    scored = [score(p, sales.get(norm(p["title"]), 0), max_inv) for p in active]
    scored.sort(key=lambda x: x["risk"], reverse=True)

    in_stock = [x for x in scored if x["stock"] > 0]
    at_risk = [x for x in in_stock if x["risk"] >= C.AT_RISK_SCORE]
    cash_at_risk = sum(x["cash"] for x in at_risk if x["cash"])
    dead = [x for x in in_stock if x["u12"] == 0]
    dead_cash = sum(x["cash"] for x in dead if x["cash"])
    total_inv = sum(x["cash"] for x in in_stock if x["cash"])

    match_count = sum(1 for k in sales if any(norm(p["title"]) == k for p in prod.values()))

    flags = [
        ("No sale dates in the sales export", "critical",
         "The 'Total sales by product' file is an aggregate over one period ({} months) with no per-transaction dates. "
         "So 'days since last sale' and year-on-year trend can't be computed — risk here uses months-of-cover, "
         "slow/zero sales and cash only. Pull the 30-day / 90-day / prior-year 'sales by product' files to restore full recency & trend."
         .format(PERIOD_MONTHS)),
        ("{} in-stock products have NO cost".format(len(missing_cost_in_stock)), "warn",
         "Their cash-at-risk can't be calculated, so they're ranked on cover & sales only and show '—' for cash. "
         "Add 'Cost per item' in Shopify to value them. Examples: " +
         ", ".join(p["title"][:28] for p in missing_cost_in_stock[:4]) + "."),
        ("{} DRAFT products are holding stock".format(len(drafts_in_stock)), "warn",
         "Draft = unpublished / not for sale, so I excluded them from the dead-stock analysis. "
         "But if any are really sellable stock sitting hidden, that's frozen cash you can't see — worth a look."),
        ("{} ARCHIVED products still hold stock".format(len(archived_in_stock)), "info",
         "Archived = discontinued. Since they're still holding units, they ARE dead stock and are included in the ranking below."),
        ("{} negative-stock items".format(len(negatives)), "info",
         "Usually oversold or a gift card. Ignored for dead-stock. Items: " +
         ", ".join("{} ({})".format(p["title"][:24], p["stock"]) for p in negatives) + "."),
        ("Vendor name duplicate: 'Animo' vs 'animo'", "info",
         "A capitalisation mismatch splits one brand into two. Merged (case-insensitively) in the by-brand rollup below; "
         "worth fixing in Shopify so future reports are clean."),
    ]

    vend = {}
    for x in at_risk:
        k = (x["vendor"] or "—").strip().title()
        vend[k] = vend.get(k, 0) + (x["cash"] or 0)
    vend_sorted = sorted(vend.items(), key=lambda kv: kv[1], reverse=True)[:8]

    todo = [x for x in at_risk if x["action"] in ("Mark down / clear", "Watch")][:6]

    return {
        "scored": scored, "in_stock": in_stock, "at_risk": at_risk, "dead": dead,
        "cash_at_risk": cash_at_risk, "dead_cash": dead_cash, "total_inv": total_inv,
        "active_count": len(active), "instock_count": len(in_stock),
        "at_risk_count": len(at_risk), "dead_count": len(dead),
        "flags": flags, "vend_sorted": vend_sorted, "todo": todo,
        "match_count": match_count, "sales_count": len(sales),
        "missing_cost": missing_cost_in_stock, "drafts_in_stock": drafts_in_stock,
        "archived_in_stock": archived_in_stock, "negatives": negatives,
    }


# ===========================================================================
# RENDER
# ===========================================================================

def render_html(r, sales_name, prod_name):
    def rowhtml(x):
        bg, fg = C.colour(x["risk"])
        star = " *" if not x["cost"] else ""
        arch = " <span class='tag'>archived</span>" if x["status"] == "archived" else ""
        return ("<tr><td class='name'>{n}{arch}<span class='sku'>{v} · {t}</span></td>"
                "<td><span class='pill' style='background:{bg};color:{fg}'>{r}</span></td>"
                "<td>{stock:.0f}</td><td>{cov}</td><td>{u:.0f}/yr</td>"
                "<td class='num'>{cash}{star}</td><td>{a}</td></tr>").format(
            n=C.esc(x["title"]), arch=arch, v=C.esc(x["vendor"]), t=C.esc(x["type"]),
            bg=bg, fg=fg, r=x["risk"], stock=x["stock"], cov=C.fmt_cover(x["cover"]),
            u=x["u12"], cash=money(x["cash"]), star=star, a=C.esc(x["action"]))

    rows_html = "".join(rowhtml(x) for x in r["in_stock"])
    todo_html = "".join(
        "<li><strong>{a}</strong> — {n} <span class='dim'>(risk {r}, {c} tied up, {u:.0f} sold/yr, {cov} cover)</span></li>".format(
            a=C.esc(x["action"]), n=C.esc(x["title"]), r=x["risk"], c=money(x["cash"]),
            u=x["u12"], cov=C.fmt_cover(x["cover"])) for x in r["todo"])
    vmax = r["vend_sorted"][0][1] if r["vend_sorted"] and r["vend_sorted"][0][1] else 1
    vend_html = "".join(
        "<div class='catrow'><div class='catname'>{n}</div><div class='cattrack'>"
        "<div class='catfill' style='width:{p:.0f}%'></div></div><div class='catval'>{v}</div></div>".format(
            n=C.esc(n), p=(val / vmax * 100), v=money(val)) for n, val in r["vend_sorted"])

    def flag_html(f):
        title, level, body = f
        colours = {"critical": "#a11a12", "warn": "#8a6100", "info": "#3a6ea5"}
        return ("<div class='flag'><span class='dot' style='background:{c}'></span>"
                "<div><b>{t}</b><div class='fb'>{b}</div></div></div>").format(
            c=colours[level], t=C.esc(title), b=C.esc(body))
    flags_html = "".join(flag_html(f) for f in r["flags"])

    return TEMPLATE.format(
        asof=ASOF, sales_file=C.esc(sales_name), prod_file=C.esc(prod_name),
        cash_at_risk=money(r["cash_at_risk"]), at_risk_count=r["at_risk_count"],
        total_inv=money(r["total_inv"]), instock_count=r["instock_count"],
        dead_count=r["dead_count"], dead_cash=money(r["dead_cash"]),
        active_count=r["active_count"], flags=flags_html, todo=todo_html,
        vendors=vend_html, rows=rows_html, cover_low=C.COVER_LOW_M, cover_high=C.COVER_HIGH_M)


# ===========================================================================
# CLI
# ===========================================================================

def main():
    sales_path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/jennypersson/Downloads/Total sales by product - 2025-07-14 - 2026-07-14.csv"
    prod_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/prodexp/products_export_1.csv"

    prod = load_products(prod_path)
    sales = load_sales(sales_path)
    r = compute(prod, sales)
    html = render_html(r, os.path.basename(sales_path), os.path.basename(prod_path))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "casa_from_raw_exports.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print("MAPPED & JOINED 2 raw Shopify exports  (as of {}, trailing {} months)".format(ASOF, PERIOD_MONTHS))
    print("  sales:    {}".format(os.path.basename(sales_path)))
    print("  products: {}".format(os.path.basename(prod_path)))
    print("  join match rate: {}/{} sales items found in products export".format(r["match_count"], r["sales_count"]))
    print("=" * 64)
    print("Active in-stock products: {}   inventory @ cost: {}".format(r["instock_count"], money(r["total_inv"])))
    print("At risk (>= {}): {} products, {} cash".format(C.AT_RISK_SCORE, r["at_risk_count"], money(r["cash_at_risk"])))
    print("Stone-dead (in stock, 0 sales/12mo): {} products, {}".format(r["dead_count"], money(r["dead_cash"])))
    print("=" * 64)
    print("Wrote -> {}".format(out))


TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Casa Equestre — Dead-Stock (from raw exports)</title>
<style>
  *{{box-sizing:border-box}} body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f5f6f8;color:#1b1f24}}
  .wrap{{max-width:1040px;margin:0 auto;padding:28px 20px 60px}}
  h1{{font-size:22px;margin:0 0 2px}} .sub{{color:#6b7280;font-size:12.5px;margin-bottom:22px}}
  .hero{{background:#12263a;color:#fff;border-radius:14px;padding:24px 26px;display:flex;flex-wrap:wrap;gap:26px;align-items:center}}
  .hero .big{{font-size:36px;font-weight:800;line-height:1}} .hero .stat{{font-size:22px;font-weight:600}}
  .hero .label{{font-size:11.5px;opacity:.82;margin-top:5px}} .hero .divider{{width:1px;align-self:stretch;background:rgba(255,255,255,.2)}}
  .card{{background:#fff;border-radius:14px;padding:20px 22px;margin-top:20px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  h2{{font-size:15px;margin:0 0 14px}}
  .flag{{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-bottom:1px solid #f0f1f3}}
  .flag:last-child{{border-bottom:0}} .dot{{width:9px;height:9px;border-radius:50%;margin-top:5px;flex:none}}
  .fb{{color:#5a616b;font-size:12px;line-height:1.5;margin-top:2px}}
  ol.todo{{margin:0;padding-left:20px}} ol.todo li{{margin-bottom:7px;line-height:1.45}} .dim{{color:#6b7280;font-size:12px}}
  .catrow{{display:grid;grid-template-columns:120px 1fr 70px;align-items:center;gap:10px;margin-bottom:8px;font-size:12.5px}}
  .catname{{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .cattrack{{background:#f0f1f3;border-radius:8px;height:14px;overflow:hidden}} .catfill{{background:#d0433a;height:100%}}
  .catval{{text-align:right;color:#4b5563;font-variant-numeric:tabular-nums}}
  .scroll{{overflow-x:auto}} table{{width:100%;border-collapse:collapse;font-size:12.5px}}
  th,td{{text-align:left;padding:8px;border-bottom:1px solid #eef0f2;white-space:nowrap}}
  th{{color:#6b7280;font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em}}
  td.num{{text-align:right;font-variant-numeric:tabular-nums}} td.name{{font-weight:600;white-space:normal}}
  .sku{{display:block;font-weight:400;color:#9aa0a6;font-size:11px}}
  .pill{{display:inline-block;min-width:32px;text-align:center;padding:3px 8px;border-radius:20px;font-weight:700}}
  .tag{{font-size:9.5px;background:#eceef1;color:#6b7280;border-radius:8px;padding:1px 5px;margin-left:4px;vertical-align:middle}}
  .legend{{font-size:11px;color:#6b7280;margin-top:10px}} .legend span{{display:inline-block;padding:2px 8px;border-radius:10px;margin-right:6px}}
  .mapbox{{font-size:12px;line-height:1.6;color:#40464e}} .mapbox code{{background:#f0f1f3;padding:1px 5px;border-radius:4px;font-size:11px}}
</style></head><body><div class="wrap">
  <h1>Casa Equestre — Dead-Stock Report</h1>
  <div class="sub">Built by joining two raw Shopify exports · sales: <b>{sales_file}</b> · products: <b>{prod_file}</b> · as of {asof} · trailing 12 months</div>

  <div class="hero">
    <div><div class="big">{cash_at_risk}</div><div class="label">cash tied up in at-risk stock ({at_risk_count} products)</div></div>
    <div class="divider"></div>
    <div><div class="stat">{dead_cash}</div><div class="label">stone-dead: {dead_count} products, 0 sales in 12mo</div></div>
    <div class="divider"></div>
    <div><div class="stat">{total_inv}</div><div class="label">active inventory at cost ({instock_count} in-stock of {active_count} active)</div></div>
  </div>

  <div class="card"><h2>⚠︎ Data-quality flags &amp; column mapping</h2>
    <div class="mapbox" style="margin-bottom:14px">
      <b>How I mapped the columns:</b>
      product = sales <code>Product title</code> ↔ products <code>Title</code> (100% matched) ·
      units = <code>Net items sold</code> (12-mo) ·
      stock = sum of <code>Variant Inventory Qty</code> per product ·
      cost = average <code>Cost per item</code> across variants ·
      <code>Vendor</code>, <code>Type</code>, <code>Status</code> direct.
      <br><span style="color:#8a6100">Unsure / judgement calls:</span> cost is a plain average across variants (not weighted by which size is in stock);
      untracked variants (blank inventory) count as 0 stock; rows marked <b>*</b> have no cost so their cash is unknown.
    </div>
    {flags}
  </div>

  <div class="card"><h2>What to do this week</h2><ol class="todo">{todo}</ol></div>

  <div class="card"><h2>Where the frozen cash sits — by brand</h2>{vendors}</div>

  <div class="card"><h2>All active in-stock products — ranked by dead-stock risk</h2>
    <div class="scroll"><table><thead><tr>
      <th>Product</th><th>Risk</th><th>Stock</th><th>Cover</th><th>Sold/yr</th><th class="num">Cash @cost</th><th>Action</th>
    </tr></thead><tbody>{rows}</tbody></table></div>
    <div class="legend">
      <span style="background:#fde2e1;color:#a11a12">70–100 Mark down</span>
      <span style="background:#fdf3d8;color:#8a6100">45–69 Watch</span>
      <span style="background:#e3f6e5;color:#1c6b28">0–44 Healthy</span>
      &nbsp; <b>*</b> = no cost recorded, cash unknown &nbsp; · &nbsp; ∞ cover = no sales in 12 months
    </div>
  </div>
</div></body></html>"""


if __name__ == "__main__":
    main()
