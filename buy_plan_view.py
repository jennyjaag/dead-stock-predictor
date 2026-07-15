"""
buy_plan_view.py -- the AI Buy-Plan (Module 2) as a function the app can render.

Takes the app's already-scored item dicts (from shopify_join.compute or
master_load.load_master) and returns reorder / stop / seasonality structures.

Where the dead-stock report looks backward (what's ALREADY dead), the buy-plan
looks forward: what to REORDER (and how deep) and what to STOP buying, so dead
stock is prevented before a trade-show order goes in.

Richest with the master file (it carries 30/90-day + prior-year sales, so we get
real demand momentum). With the two-CSV / demo data only a 12-month rate exists,
so momentum & seasonality are skipped and the plan uses velocity + cover only.
"""

import math

import casa_report as C

TARGET_COVER_M = 4.0     # buy toward ~4 months of forward cover
MIN_ANNUAL_UNITS = 3     # only reorder items selling at least this many/year...
MIN_RECENT_90 = 2        # ...or with at least this many sold in the last 90 days
STOP_COVER_M = 24        # in stock, >24 months cover, and falling = stop buying
SEASON_HOT, SEASON_COLD = 1.20, 0.80


def _annualise(units, days):
    return units * (365.0 / days)


def compute_buyplan(items):
    reorder, stop = [], []
    any_windows = any(x.get("u90") is not None for x in items)

    for x in items:
        u12 = x["u12"]
        u30, u90, py12 = x.get("u30"), x.get("u90"), x.get("py12")
        stock, cost, price = x["stock"], x.get("cost"), x.get("price")
        cover = x["cover"]
        has_win = u90 is not None

        annual = u12
        if has_win:
            recent = 0.6 * _annualise(u90, 90) + 0.4 * _annualise(u30, 30)
            momentum = recent / annual if annual > 0 else (2.0 if recent > 0 else 0.0)
        else:
            recent = annual
            momentum = 1.0

        fwd_monthly = 0.5 * (annual / 12.0) + 0.5 * (recent / 12.0)
        target = fwd_monthly * TARGET_COVER_M
        qty = max(0, int(math.ceil(target - stock)))
        buy_cost = qty * cost if (cost and qty) else None
        rev = qty * price if (price and qty) else None
        selling = u12 >= MIN_ANNUAL_UNITS or (u90 or 0) >= MIN_RECENT_90

        row = {**x, "momentum": momentum, "reorder_qty": qty,
               "buy_cost": buy_cost, "rev_potential": rev}

        # STOP: in stock but not moving, or badly overstocked & fading
        falling = has_win and py12 is not None and py12 > u12
        if stock > 0 and (u12 == 0 or (cover != float("inf") and cover > STOP_COVER_M and (falling or not has_win))):
            reason = ("no sales in 12 months" if u12 == 0
                      else "{:.0f}mo cover".format(cover) + (" & sales falling" if falling else ""))
            stop.append({**row, "reason": reason})
        elif selling and qty >= 1 and x.get("status") != "archived" and not x.get("is_new"):
            reorder.append(row)

    reorder.sort(key=lambda r: (r["rev_potential"] or 0), reverse=True)
    stop.sort(key=lambda r: (r["cash"] or 0), reverse=True)

    # category momentum (only if we have the windows)
    seasons = []
    if any_windows:
        cats = {}
        for x in items:
            if x.get("u90") is None:
                continue
            c = cats.setdefault(x["type"], {"annual": 0.0, "recent": 0.0})
            c["annual"] += x["u12"]
            c["recent"] += 0.6 * _annualise(x["u90"], 90) + 0.4 * _annualise(x["u30"], 30)
        for name, c in cats.items():
            if c["annual"] < 4:
                continue
            m = c["recent"] / c["annual"] if c["annual"] > 0 else 1.0
            label = "Heating up" if m >= SEASON_HOT else "Cooling" if m <= SEASON_COLD else "Steady"
            seasons.append({"cat": name, "momentum": m, "label": label})
        seasons.sort(key=lambda s: s["momentum"], reverse=True)

    return {
        "reorder": reorder, "stop": stop, "seasons": seasons, "has_windows": any_windows,
        "total_buy": sum((r["buy_cost"] or 0) for r in reorder),
        "total_rev": sum((r["rev_potential"] or 0) for r in reorder),
        "stop_cash": sum((s["cash"] or 0) for s in stop),
    }
