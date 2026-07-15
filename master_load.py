"""
master_load.py -- read the single-sheet Casa "dead-stock master" .xlsx and return
the SAME result structure as shopify_join.compute(), so the app and the HTML
report render it unchanged.

Why this file is better than the two-CSV path:
  * it already has stock value AT COST (no join, no per-variant cost averaging)
  * it has 30d / 90d / 12mo velocity AND prior-year (PY) windows -> real YoY trend
  * it has 'Date added' -> we can tell a NEW arrival apart from genuine dead stock
It is missing Vendor / Product Type, so the by-brand breakdown isn't available
from this file alone (the app simply hides that chart).

Public API:
  result = load_master(src)     # src = path OR uploaded file object
"""

from datetime import date, datetime

import openpyxl

import casa_report as C

NEW_DAYS = 90        # added within this many days + no sales = "new", not dead
# risk weights (adds a real trend term the two-CSV path couldn't)
W_COVER, W_RECENCY, W_CASH, W_TREND = 0.35, 0.30, 0.20, 0.15
ASOF = date(2026, 7, 15)


def _num(v):
    return v if isinstance(v, (int, float)) else 0.0


def _band(v, lo, hi):
    if v <= lo:
        return 0.0
    if v >= hi:
        return 100.0
    return (v - lo) / (hi - lo) * 100.0


def load_master(src):
    wb = openpyxl.load_workbook(src, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = {h: i for i, h in enumerate(rows[0])}

    def col(r, name):
        return r[hdr[name]] if name in hdr else None

    # gather in-stock, sellable (active/archived) products
    recs = []
    drafts_in_stock = archived_in_stock = 0
    missing_cost = 0
    missing_date = 0
    for r in rows[1:]:
        if not col(r, "Product title"):
            continue
        # 'Status' in the older file, 'Listing status' in the newer one
        status = (col(r, "Status") or col(r, "Listing status") or "").strip()
        stock = _num(col(r, "Inventory on hand"))
        if status == "draft":
            if stock > 0:
                drafts_in_stock += 1
            continue
        if stock <= 0:
            continue                       # dead-stock report is about stock on hand
        if status == "archived":
            archived_in_stock += 1
        cash = _num(col(r, "Stock value (at cost)")) or None
        if cash is None:
            missing_cost += 1
        added = col(r, "Date added")
        added = added if isinstance(added, datetime) else None
        if added is None:
            missing_date += 1
        # brand / type — present in the newer master export, absent in the older one
        vendor = (col(r, "Vendor") or "").strip()
        ptype = (col(r, "Product type") or col(r, "Shopify category") or "").strip() or "Uncategorised"
        recs.append({
            "title": col(r, "Product title"), "vendor": vendor, "ptype": ptype,
            "status": status, "stock": stock, "cash": cash,
            "u30": _num(col(r, "Items sold 30d")), "u90": _num(col(r, "Items sold 90d")),
            "u12": _num(col(r, "Items sold 12mo")), "py12": _num(col(r, "Items sold PY 12mo")),
            "added": added,
        })

    max_inv = max((x["cash"] for x in recs if x["cash"]), default=1.0)
    scored = [_score(x, max_inv) for x in recs]
    scored.sort(key=lambda x: x["risk"], reverse=True)

    in_stock = scored
    new_arrivals = [x for x in scored if x["is_new"]]
    at_risk = [x for x in in_stock if x["risk"] >= C.AT_RISK_SCORE and not x["is_new"]]
    dead = [x for x in in_stock if x["u12"] == 0 and not x["is_new"]]
    declining = [x for x in in_stock if x["u12"] > 0 and x["py12"] > x["u12"]]

    cash_at_risk = sum(x["cash"] for x in at_risk if x["cash"])
    dead_cash = sum(x["cash"] for x in dead if x["cash"])
    total_inv = sum(x["cash"] for x in in_stock if x["cash"])

    flags = [
        ("{} new arrivals kept OUT of dead stock".format(len(new_arrivals)), "info",
         "Added in the last {} days with no sales yet — flagged 'New, too early to tell' rather than "
         "'dead', so recent buys aren't wrongly written off.".format(NEW_DAYS)),
        ("{} genuinely dead products".format(len(dead)), "critical",
         "In stock, older than {} days, zero sales in 12 months — ${:,.0f} of cash frozen. Clear these first."
         .format(NEW_DAYS, dead_cash)),
        ("{} products declining vs last year".format(len(declining)), "warn",
         "Still selling but down year-on-year (from the prior-year columns) — watch before reordering."),
        ("{} in-stock products have no cost value".format(missing_cost), "warn",
         "Their cash-at-risk can't be valued; ranked on cover & sales only.") if missing_cost else None,
        ("{} products missing 'Date added'".format(missing_date), "info",
         "Older items that predate the field — treated as established (not new).") if missing_date else None,
        ("{} draft / {} archived products hold stock".format(drafts_in_stock, archived_in_stock), "info",
         "Drafts are excluded (not for sale); archived (discontinued) are kept — they're real dead stock."),
    ]
    has_vendor = any(x["vendor"] for x in recs)
    if not has_vendor:
        flags.append(("No Vendor / Category column in this file", "info",
                      "The master export doesn't carry brand or product type, so the 'cash at risk by brand' "
                      "breakdown isn't available. Use the two-CSV upload if you want brand-level rollups."))
    flags = [f for f in flags if f]

    # cash at risk by brand (case-insensitive merge, e.g. Animo/animo)
    vend = {}
    for x in at_risk:
        if x["cash"]:
            k = (x["vendor"] or "—").strip().title()
            vend[k] = vend.get(k, 0) + x["cash"]
    vend_sorted = sorted(vend.items(), key=lambda kv: kv[1], reverse=True)[:8]

    todo = [x for x in at_risk if x["action"] in ("Mark down / clear", "Watch")][:6]

    return {
        "scored": scored, "in_stock": in_stock, "at_risk": at_risk, "dead": dead,
        "cash_at_risk": cash_at_risk, "dead_cash": dead_cash, "total_inv": total_inv,
        "active_count": len(scored), "instock_count": len(in_stock),
        "at_risk_count": len(at_risk), "dead_count": len(dead),
        "flags": flags, "vend_sorted": vend_sorted, "todo": todo,
        "match_count": len(in_stock), "sales_count": len(in_stock),
        "new_arrivals": new_arrivals, "declining": declining,
    }


def _score(x, max_inv):
    stock, u12, u30, u90, py12 = x["stock"], x["u12"], x["u30"], x["u90"], x["py12"]
    cash = x["cash"]
    is_new = bool(x["added"]) and (ASOF - x["added"].date()).days <= NEW_DAYS and u12 == 0

    monthly = u12 / 12.0
    cover = float("inf") if (stock > 0 and monthly == 0) else (stock / monthly if monthly else 0.0)
    cost = (cash / stock) if (cash and stock > 0) else None

    # sub-scores
    cover_sub = 100.0 if cover == float("inf") else _band(cover, C.COVER_LOW_M, C.COVER_HIGH_M)
    if u12 == 0:
        recency_sub = 100.0
    elif u90 == 0:
        recency_sub = 70.0
    elif u30 == 0:
        recency_sub = 35.0
    else:
        recency_sub = 0.0
    cash_sub = min(100.0, 100.0 * cash / max_inv) if (cash and max_inv > 0) else 0.0
    # trend: only a decline vs prior year adds risk
    if py12 > 0 and u12 < py12:
        trend_sub = min(100.0, (py12 - u12) / py12 * 100.0)
    else:
        trend_sub = 0.0

    risk = round(W_COVER * cover_sub + W_RECENCY * recency_sub +
                 W_CASH * cash_sub + W_TREND * trend_sub)

    if is_new:
        action, risk = "New — too early to tell", min(risk, 18)
    elif u12 > 0 and 0 < cover <= C.REORDER_COVER_M:
        action = "Reorder"
    elif risk >= C.MARKDOWN_SCORE:
        action = "Mark down / clear"
    elif risk >= C.WATCH_SCORE:
        action = "Watch"
    else:
        action = "Healthy"

    return {"title": x["title"], "vendor": x.get("vendor", ""), "type": x.get("ptype", "Uncategorised"),
            "status": x["status"], "stock": stock, "u12": u12, "py12": py12, "cover": cover,
            "cost": cost, "price": None, "margin": None, "cash": cash,
            "risk": risk, "action": action, "is_new": is_new}


if __name__ == "__main__":
    import sys
    r = load_master(sys.argv[1] if len(sys.argv) > 1 else
                    "/Users/jennypersson/Downloads/casa_equestre_deadstock_master.xlsx")
    print("in-stock: {} | at-risk: {} (${:,.0f}) | genuinely dead: {} (${:,.0f}) | new kept out: {}".format(
        r["instock_count"], r["at_risk_count"], r["cash_at_risk"],
        r["dead_count"], r["dead_cash"], len(r["new_arrivals"])))
